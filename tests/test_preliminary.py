from __future__ import annotations

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from localagent_bench.config import ConfigError, load_config
from localagent_bench.dashboard_data import build_dashboard_data, validate_dashboard_data, DashboardDataError
from localagent_bench.guided import evaluate_preliminary, GuidedError
from localagent_bench.integrity import InputIntegrityError, require_clean_inputs
from localagent_bench.ollama import OllamaModel, ThinkingPreflight
from localagent_bench.pi_compatibility import PiCompatibility, CONTRACT_VERSION
from localagent_bench.preliminary_report import summarize
from localagent_bench.preliminary_stream import measure
from localagent_bench.preliminary_suite import grade_answer, load_suite, settings
from localagent_bench.providers import ProviderError
from localagent_bench.runner import run_benchmark, BenchmarkError
from localagent_bench.thinking import resolve_thinking_policy


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.payloads.append(body)
        mode = self.server.mode
        if mode == 'redirect':
            self.send_response(302)
            self.send_header('Location','http://example.invalid/private-secret')
            self.end_headers()
            return
        if mode == 'http_error':
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b'private-secret')
            return
        prompt = body['messages'][0]['content']
        question = next((q for q in self.server.suite['questions'] if q['prompt'] in prompt), None)
        answer = json.dumps({'status':question['category'],'value':question['expected']}) if question else 'A synthetic response with two chunks.'
        if mode == 'wrong':
            answer = '{"status":"answer","value":"invented"}'
        if mode == 'inline':
            answer = '<think>private-secret</think>' + answer
        chunks = []
        if mode == 'reasoning':
            chunks.append({'choices':[{'delta':{'reasoning_content':'private-secret'}}]})
        for text in (answer[:9], answer[9:]):
            chunks.append({'choices':[{'delta':{'content':text}}]})
        chunks.append({'choices':[{'delta':{},'finish_reason':'length' if mode == 'length' else 'stop'}],
                       'usage':{'completion_tokens':12,'completion_tokens_details':{'reasoning_tokens':1 if mode == 'reasoning_tokens' else 0}}})
        if mode == 'no_usage':
            chunks[-1].pop('usage')
        data = b''.join(('data: '+json.dumps(c)+'\r\n\r\n').encode() for c in chunks)
        if mode == 'malformed': data = b'data: {bad json}\n\n'
        if mode == 'large': data = b'data: '+b'x'*70000+b'\n\n'
        if mode != 'incomplete': data += b'data: [DONE]\n\n'
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        try:
            if mode == 'slow': time.sleep(.2)
            # Split protocol frames as well as content across network reads.
            for start in range(0,len(data),7): self.wfile.write(data[start:start+7])
        except (BrokenPipeError,ConnectionResetError):
            pass


class PreliminaryUnitTests(unittest.TestCase):
    def test_suite_has_balanced_controls_and_exact_ground_truth(self):
        suite=load_suite(ROOT/'preliminary/suite.json')
        self.assertEqual({'short','long'},{p['id'] for p in suite['performance']})
        self.assertGreater(len(suite['performance'][1]['prompt']),len(suite['performance'][0]['prompt']))
        for q in suite['questions']:
            self.assertEqual('correct',grade_answer(json.dumps({'status':q['category'],'value':q['expected']}),q))
        q=next(q for q in suite['questions'] if q['category']=='unknown')
        self.assertEqual('unsupported_answer',grade_answer('{"status":"answer","value":"2000"}',q))
        for text in ('garbage','{}','{"status":[],"value":""}','[]'):
            self.assertEqual('invalid',grade_answer(text,q))
        known=next(q for q in suite['questions'] if q['category']=='answer')
        self.assertEqual('unnecessary_abstention',grade_answer('{"status":"unknown","value":""}',known))

    def test_options_reject_unbounded_values_and_unsafe_paths(self):
        for raw in ({'repetitions':True},{'max_tokens':-1},{'timeout_seconds':0},{'suite':'../secret'},{'suite':'/tmp/secret'},{'extra':1},{'max_response_bytes':1024,'max_event_bytes':2048}):
            with self.subTest(raw=raw), self.assertRaises(ValueError): settings(ROOT,raw)

    def test_descriptive_summary_has_no_rank_or_score_and_keeps_unavailable_values(self):
        manifest={'models':['a'],'preliminary':{'observations':[{'model':'a','context':'short','status':'error'}]},'integrity':{}}
        rows=summarize(manifest,set())
        self.assertIsNone(rows[0]['output_tokens_per_second'])
        self.assertEqual(1,rows[0]['failed'])
        self.assertFalse(any('score' in k or 'rank' in k for row in rows for k in row))
        manifest['integrity']['aborted']=True
        self.assertTrue(all(r['status']=='excluded' for r in summarize(manifest,set())))


class PreliminaryHTTPTests(unittest.TestCase):
    def setUp(self):
        try: self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        except OSError as exc: self.skipTest(f'loopback unavailable: {type(exc).__name__}')
        self.server.mode='ok';self.server.payloads=[]
        self.server.suite=load_suite(ROOT/'preliminary/suite.json')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.options=settings(ROOT,{})

    def tearDown(self):
        if hasattr(self,'server'):
            self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def probe(self):
        return measure(self.url,'synthetic','test',resolve_thinking_policy('off'),self.options,temperature=0,seed=3)

    def test_stream_framing_metrics_and_no_tool_or_history_payload(self):
        result=self.probe()
        self.assertEqual('A synthetic response with two chunks.',result['answer'])
        self.assertGreater(result['output_tokens_per_second'],0)
        self.assertIsNone(result['decode_tokens_per_second'])
        payload=self.server.payloads[0]
        self.assertEqual('none',payload['reasoning_effort'])
        self.assertNotIn('tools',payload)
        self.assertEqual(1,len(payload['messages']))
        self.assertEqual(1,len(self.server.payloads))

    def test_missing_usage_is_not_zero_and_truncation_is_explicit(self):
        self.server.mode='no_usage';self.assertIsNone(self.probe()['output_tokens_per_second'])
        self.server.mode='length';self.assertTrue(self.probe()['truncated'])

    def test_reasoning_is_detected_and_never_returned_as_answer(self):
        for mode in ('reasoning','reasoning_tokens','inline'):
            with self.subTest(mode=mode):
                self.server.mode=mode;result=self.probe()
                self.assertTrue(result['thinking_observed'])
                self.assertNotIn('private-secret',result['answer'])

    def test_bad_streams_bounds_redirect_and_total_timeout_fail_without_retry(self):
        for mode in ('malformed','large','redirect','incomplete','http_error','slow'):
            with self.subTest(mode=mode):
                self.server.mode=mode;self.server.payloads=[]
                options=replace(self.options,timeout_seconds=.05) if mode=='slow' else self.options
                with self.assertRaises(Exception):
                    measure(self.url,'model','test',resolve_thinking_policy('off'),options,temperature=0,seed=1)
                self.assertEqual(1,len(self.server.payloads))
        with self.assertRaises(ProviderError):
            measure('http://example.invalid','m','test',resolve_thinking_policy('off'),self.options,temperature=0,seed=1)

    def _run(self, root, *, kind='ollama', failed_preflight=False, mutate=None):
        suite=root/'preliminary/suite.json';suite.parent.mkdir();shutil.copy2(ROOT/'preliminary/suite.json',suite)
        (root/'AGENTS.md').write_text('Synthetic test policy\n')
        (root/'.gitignore').write_text('results/\n')
        subprocess.run(['git','init','-q',str(root)],check=True)
        for key,val in [('user.name','Synthetic Test'),('user.email','test@example.invalid')]:
            subprocess.run(['git','-C',str(root),'config',key,val],check=True)
        subprocess.run(['git','-C',str(root),'add','.'],check=True)
        subprocess.run(['git','-C',str(root),'commit','-qm','synthetic baseline'],check=True)
        config=replace(load_config(ROOT/'benchmark.json'),root=root,profiles={'preliminary':()},cases={},
                       preliminary=replace(self.options,suite=suite,repetitions=2),provider_kind=kind,ollama_url=self.url)
        model=OllamaModel('synthetic',1,'digest','now',{})
        provider=Mock(kind=kind,explicit_load=kind!='ollama',infer_capability_from_preflight=False,version_source='test')
        provider.list_models.return_value=[model];provider.inspect_model.return_value=model
        provider.fingerprint_model.return_value=model;provider.version.return_value='synthetic'
        provider.preflight_thinking.return_value=ThinkingPreflight('provider_error' if failed_preflight else 'passed','off','none',False,False,0,0,1)
        original=measure
        def controlled(*args,**kwargs):
            result=original(*args,**kwargs)
            if mutate: mutate(root)
            return result
        with patch('localagent_bench.runner.create_provider',return_value=provider), patch('localagent_bench.runner._command_version',return_value='synthetic'),patch('localagent_bench.runner.check_pi_compatibility',return_value=PiCompatibility('passed',CONTRACT_VERSION,())),patch('localagent_bench.preliminary.measure',side_effect=controlled):
            run=run_benchmark(config,profile='preliminary',requested_models=['synthetic'],requested_cases=None,repetitions=None,timeout_seconds=10,thinking_level='off',use_warmup=True,output_dir=root/'results/run',order_seed=7,sandbox_mode='audit')
        return run,provider

    def test_end_to_end_all_provider_ids_keep_gates_scores_and_public_whitelist(self):
        for kind in ('ollama','lmstudio','llama_cpp'):
            with self.subTest(kind=kind),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);run,provider=self._run(root,kind=kind)
                manifest=json.loads((run/'run.json').read_text());report=json.loads((run/'report.json').read_text())
                self.assertEqual([],report['leaderboard']);self.assertEqual([],report['results'])
                grounding=next(r for r in report['preliminary'] if r['context']=='grounding')
                self.assertEqual(8,grounding['known_correct']);self.assertEqual(4,grounding['missing_correct']);self.assertEqual(4,grounding['premise_correct'])
                self.assertEqual(20,len(manifest['preliminary']['observations']))
                self.assertTrue(manifest['inputs']['extra_inputs'])
                provider.preflight_thinking.assert_called_once();provider.warmup.assert_called_once()
                report['preliminary'][0]['answer']='private-secret'
                (run/'report.json').write_text(json.dumps(report))
                public=build_dashboard_data([run]);validate_dashboard_data(public)
                self.assertEqual([],public['funnel']);self.assertNotIn('private-secret',json.dumps(public))
                self.assertNotIn('prompt',json.dumps(public));self.assertNotIn(str(root),json.dumps(public))
                outcome=evaluate_preliminary(run,root=root,expected_models=['synthetic'],process_returncode=0)
                self.assertEqual(('synthetic',),outcome.promoted)
                # Dirty probes cannot be run a second time.
                (root/'preliminary/suite.json').write_text('{}')
                with self.assertRaises(InputIntegrityError):require_clean_inputs(root,[],[root/'preliminary/suite.json'])

    def test_descriptive_answer_failures_do_not_prevent_smoke(self):
        self.server.mode='wrong'
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);run,_=self._run(root)
            report=json.loads((run/'report.json').read_text())
            grounding=next(r for r in report['preliminary'] if r['context']=='grounding')
            self.assertEqual(8,grounding['unsupported_answers'])
            self.assertEqual(('synthetic',),evaluate_preliminary(run,root=root,expected_models=['synthetic'],process_returncode=0).promoted)
            manifest=json.loads((run/'run.json').read_text());manifest['preliminary']['observations'].pop()
            (run/'run.json').write_text(json.dumps(manifest))
            with self.assertRaises(GuidedError):evaluate_preliminary(run,root=root,expected_models=['synthetic'],process_returncode=0)

    def test_preflight_failure_never_calls_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            run,_=self._run(Path(directory),failed_preflight=True)
            self.assertEqual([],self.server.payloads)
            report=json.loads((run/'report.json').read_text())
            self.assertTrue(all(r['status']=='excluded' for r in report['preliminary']))

    def test_unexpected_reasoning_excludes_entire_model_without_persisting_trace(self):
        self.server.mode='reasoning'
        with tempfile.TemporaryDirectory() as directory:
            run,_=self._run(Path(directory))
            report=json.loads((run/'report.json').read_text())
            self.assertEqual(['synthetic'],report['integrity']['disqualified_models'])
            self.assertTrue(all(r['first_answer_seconds'] is None for r in report['preliminary']))
            self.assertNotIn('private-secret',(run/'run.json').read_text())

    def test_cancellation_unwinds_lifecycle_and_keeps_diagnostic_artifacts(self):
        def cancel(_root): raise KeyboardInterrupt()
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            with self.assertRaises(KeyboardInterrupt):self._run(root,mutate=cancel)
            run=root/'results/run';manifest=json.loads((run/'run.json').read_text())
            self.assertTrue(manifest['cancelled']);self.assertTrue(manifest['integrity']['aborted'])
            self.assertEqual('unload_after',manifest['preliminary']['lifecycle'][-1]['event'])
            self.assertTrue((run/'REPORT.md').is_file())

    def test_snapshot_mutation_aborts_matrix(self):
        def mutate(root):
            (root/'results/run/benchmark-context/extra-0.json').write_text('{}')
        with tempfile.TemporaryDirectory() as directory:
            run,_=self._run(Path(directory),mutate=mutate)
            manifest=json.loads((run/'run.json').read_text())
            self.assertTrue(manifest['integrity']['aborted'])
            self.assertEqual(1,len(self.server.payloads))
            with self.assertRaises(GuidedError): evaluate_preliminary(run,root=Path(directory),expected_models=['synthetic'],process_returncode=1)
