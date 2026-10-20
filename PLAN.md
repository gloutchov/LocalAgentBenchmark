# Piano di sviluppo / Development Plan

Versione corrente / Current version: **0.13.1 (patch in corso)**

## Milestone 1 – Benchmark locale funzionale

- Obiettivo: confrontare modelli Ollama attraverso Pi con task derivati da `AGENTS.md`, grading automatico e report ispezionabile.
- Branch previsto: `milestone/1-local-benchmark`
- Incremento versione: `0.1.0`
- Attività: runner isolato, rilevamento modelli, quattro casi, grader, metriche, report, documentazione bilingue e CI.
- Criteri di accettazione: `doctor` rileva l'ambiente; un run smoke produce artefatti e report; i grader hanno massimo 100 e le fixture iniziali restano sotto 60; test unitari verdi.
- Test: compileall, unittest, doctor locale, smoke Pi/Ollama.
- Documentazione: README, manuali, security model, MAP, AGENTS e piano.
- Stato: **implementazione e verifica locale completate; il full diagnostico `20260829-120212` ha evidenziato confini incompleti e una fixture incoerente, corretti nella patch 0.1.2; la verifica reale mirata `20260829-164305` è valida; patch unita e pubblicata su `main`, CI verde su branch e `main`, tag `v0.1.2` pubblicato e branch patch rimosso; resta da eseguire il nuovo full conclusivo**.

### Checklist chiusura

- [x] Branch di lavoro creato (`patch/0.1.2-run-integrity`)
- [x] Implementazione completata
- [x] Test automatici aggiunti
- [x] Test automatici eseguiti su macOS, Windows e Ubuntu
- [x] Smoke test Pi/Ollama eseguito (timeout e grading post-mortem verificati)
- [x] Versione sincronizzata
- [x] README aggiornato
- [x] ISTRUZIONI.md aggiornato
- [x] INSTRUCTIONS.md aggiornato
- [x] SECURITY_MODEL.md aggiornato
- [x] MAP.md aggiornato
- [x] AGENTS.md aggiornato con note progetto
- [x] PLAN.md aggiornato
- [x] Approvazione esplicita del progettista per merge, tag, push e rimozione branch
- [x] Commit implementativi e documentali completati
- [x] Merge fast-forward verso `main` e push completati
- [x] CI verificata sul branch (`33260010840`) e su `main` (`33260064872`)
- [x] Tag `v0.1.2` pubblicato tramite patch di integrità
- [x] Nessuna GitHub release per la patch ordinaria; richiesti soltanto tag e push

## Patch prioritaria 0.1.1 – Ripristino CI e calibrazione `targeted_patch`

- Obiettivo: riportare la CI di `main` in stato verde correggendo la calibrazione iniziale del caso `targeted_patch`.
- Branch previsto: `patch/0.1.1-targeted-patch-calibration`
- Incremento versione: `+0.0.1`
- Attività: determinare se la fixture iniziale è stata completata o contaminata accidentalmente; ripristinare una baseline intenzionalmente incompleta e coerente con il prompt; verificare il grader senza ridurne copertura, punteggio massimo o soglia; mantenere fixture e grader immutati durante ogni benchmark attivo.
- Criteri di accettazione: il grader conserva un massimo di 100 punti; la fixture iniziale di `targeted_patch` ottiene meno di 60; gli altri casi mantengono la calibrazione prevista; tutti i test passano senza allentare asserzioni o soglie; la CI termina con successo su macOS, Windows e Linux.
- Test: `python3 -m compileall -q benchmark.py src cases tests`; `python3 -m unittest discover -s tests -v`; esecuzione diretta del grader sulla fixture iniziale; verifica GitHub Actions sui tre sistemi operativi.
- Documentazione: aggiornare `PLAN.md` con esito e checklist; aggiornare README, manuali, `SECURITY_MODEL.md`, `MAP.md` o `AGENTS.md` solo se il comportamento o la struttura cambiano.
- Release: nessuna GitHub release per questa patch, come approvato dal progettista; creare il tag `v0.1.1` dopo merge e CI verde su `main`.
- Stato: **correzione completata e approvata; baseline a 25/100 e CI branch/PR verde su macOS, Windows e Linux; merge e tag `v0.1.1` autorizzati**.

## Patch prioritaria 0.1.2 – Integrità dei run e baseline congelate

- Obiettivo: impedire che una task alteri gli input dei tentativi successivi e rendere automaticamente non classificabili modelli o risultati con violazioni di workspace, baseline o provenienza.
- Branch previsto: `patch/0.1.2-run-integrity`
- Incremento versione: `+0.0.1`
- Attività principali: ripristinare `targeted_patch` dopo la modifica esterna osservata nel run `20260828-204650`; bloccare input selezionati sporchi; creare prima della matrice un solo snapshot dei file tracciati e della policy di esecuzione; registrare SHA-256 effettivi, commit/stato Git, tree baseline, seed e ordine; randomizzare le task; effettuare unload/warmup a ogni cambio modello; preparare `.benchmark-scratch/` interna e assegnarla alle variabili temporanee; confrontare repository e snapshot prima/dopo le task; risolvere path shell rispetto ai cambi directory, proteggere l'intera root, auditare tentativi di rete e distinguere traversal confinati; non eseguire grader da snapshot alterati; escludere l'intero modello per violazioni o baseline divergenti; mostrare motivo/target/evidenza; riesaminare eventi legacy; includere nella fixture `milestone_closure` la `LICENSE` richiesta da `AGENTS.md`.
- Criteri di accettazione: la baseline `targeted_patch` resta sotto 60; tutte le workspace dello stesso caso ricevono hash input effettivo e tree baseline identici; path esterni, rete o mutazioni escludono l'intero modello; un traversal di prova risolto nello scratch interno non è una violazione; pattern shell non-path come programmi `awk` non producono falsi positivi; una mutazione dello snapshot interrompe la matrice prima del grader; il report mostra stato e dettagli prima della classifica; `doctor` segnala input sporchi; lo stesso seed produce lo stesso ordine; i run precedenti vengono riesaminati senza riscrivere i risultati originali.
- Test richiesti: compileall; unittest; calibrazione diretta di tutte le fixture; test mirati per snapshot/policy hash, scratch, seed, path strutturati e shell, rete, falsi positivi `awk`, riesame report, disqualifica modello, baseline di minoranza e flusso runner simulato; `doctor`; smoke Pi/Ollama con `qwen3.8:27b-q4_K_M` e `gpt-oss:20b`; verifica reale mirata di `milestone_closure` dopo il commit correttivo.
- Documentazione: README, manuali bilingui, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md` e `PLAN.md`.
- Release: nessuna GitHub release per questa patch ordinaria, come autorizzato dal progettista; tag `v0.1.2` pubblicato dopo merge e CI verde su `main`.
- Stato: **correzioni successive al full diagnostico implementate e committate; 24 test automatici locali e CI multipiattaforma verdi, inclusa la regressione per path assoluti di stile estraneo all'host aggiunta dopo il primo passaggio CI; il riesame in sola lettura di `20260829-120212` esclude soltanto Qwen per `/tmp`, repository reale e rete, senza falsi positivi sui pattern testuali di GPT-OSS; la verifica reale `20260829-164305` completa `milestone_closure` con Qwen a 100/100, integrità valida e scratch interno; merge e push su `main`, tag `v0.1.2` e rimozione del branch patch completati; resta da eseguire il nuovo confronto full**.

### Checklist patch 0.1.2

- [x] Branch patch creato
- [x] Fixture contaminata ripristinata e ricalibrata a 25/100
- [x] Implementazione completata
- [x] Test mirati aggiunti
- [x] Compileall e unittest locali eseguiti
- [x] Smoke reale Pi/Ollama eseguito
- [x] Full diagnostico `20260829-120212` analizzato senza modificare gli artefatti originali
- [x] `LICENSE` richiesta aggiunta alla fixture `milestone_closure`
- [x] Policy congelata e `.benchmark-scratch/` interna aggiunte
- [x] Audit path/rete versionato e report dettagliato calibrati sul full
- [x] Verifica reale `20260829-164305`: Qwen `milestone_closure` 100/100, integrità valida, 945,1 s
- [x] Versione sincronizzata
- [x] README aggiornato
- [x] ISTRUZIONI.md aggiornato
- [x] INSTRUCTIONS.md aggiornato
- [x] SECURITY_MODEL.md aggiornato
- [x] MAP.md aggiornato
- [x] AGENTS.md aggiornato
- [x] PLAN.md aggiornato
- [x] Approvazione esplicita del progettista per merge, tag, push e rimozione branch
- [x] Commit implementativi creati sul branch patch
- [x] Merge fast-forward verso `main` e push completati
- [x] CI verificata sul branch (`33260010840`) e su `main` (`33260064872`)
- [x] Tag `v0.1.2` pubblicato
- [x] Branch patch locale e remoto eliminato dopo le verifiche
- [x] Nessuna GitHub release: per questa patch ordinaria sono richiesti soltanto tag e push

## Milestone 2 – Sandbox e metriche di sistema

- Obiettivo: aggiungere un backend opzionale di isolamento OS e metriche hardware/energia dove disponibili, completando la prevenzione tecnica oltre ai controlli d'integrità introdotti nella 0.1.2.
- Branch previsto: `milestone/2-reproducibility-sandbox`
- Incremento versione: `+0.1.0`
- Attività: adapter sandbox multipiattaforma, test processi/rete e letture indirette, metriche hardware/energia, schema risultati compatibile e confronto statistico tra run. Ordine randomizzato, seed e provenienza restano la base già consegnata dalla patch 0.1.2.
- Criteri di accettazione: uscita dalla workspace bloccata tecnicamente nel backend sandbox; modalità corrente mantenuta e segnalata; report aggregato su più run.
- Test: unit, integrazione, sicurezza e smoke macOS/Windows/Linux.
- Documentazione: tutti i manuali, security model e MAP.
- Stato: **milestone integrata con fast-forward su `main` dopo l'approvazione esplicita del progettista. Il run standard `20260830-182507` ha individuato il diniego `realpath` degli antenati della workspace, poi corretto concedendo soltanto metadata letterali sui path autorizzati. Compileall e 40 test sono verdi; i probe macOS verificano `realpath`, sostituzione interna, lettura esterna negata e rete limitata. Dopo il diagnostico `20260830-201021`, lo smoke valido `20260830-202615` ha completato `targeted_patch` con Qwen 9B MLX a 100/100 in 151,9 s, integrità valida, Seatbelt enforced e tre tool `edit` riusciti. Le CI finali del branch (`33418463014`), della PR (`33418466714`) e di `main` (`33418580601`) sono verdi su macOS, Windows e Ubuntu. Tag `v0.2.0`, push e rimozione del branch sono autorizzati nel workflow corrente; la GitHub release non è inclusa nell'autorizzazione e resta pendente. Il confronto `comparison-m2-real-bounded`, il limite Windows audit-only accettato e il follow-up M3 restano invariati.**

### Checklist milestone 2

- [x] Branch milestone creato
- [x] Modalità audit mantenuta e dichiarata
- [x] Selezione `auto` con fallback esplicito e `required` fail-closed
- [x] Backend macOS Seatbelt con file utente e rete limitata a Ollama loopback
- [x] Backend Linux bubblewrap con filesystem e process tree isolati
- [x] Limite Windows audit-only accettato esplicitamente dal progettista per la 0.2.0
- [x] Follow-up per AppContainer Windows e isolamento rete Linux pianificato nella milestone 3
- [x] Metriche hardware, rusage e RAPL opzionale con provider/scope
- [x] Schema risultati/report 3 compatibile con lettura schema 2
- [x] Confronto statistico tra run compatibili con versione, parametri e digest verificati
- [x] Confronto reale di due run compatibili verificato (`comparison-m2-real-bounded`)
- [x] Test unitari e negativi aggiunti
- [x] Regressione Node/Pi per `realpath` e scrittura interna aggiunta; accesso esterno ancora negato
- [x] Test automatici locali completi e probe OS macOS rieseguiti dopo la correzione
- [x] Smoke diagnostico `config_i18n` (`20260830-201021`): 11 `write` riusciti senza `EPERM`; timeout e violazione modello separati dal fix
- [x] Smoke Pi/Ollama valido con sandbox reale rieseguito dopo la correzione (`20260830-202615`, 100/100, integrità valida)
- [x] CI finale macOS, Windows e Linux rieseguita dopo la correzione (push `33328347558`, PR `33328349531`)
- [x] Versione 0.2.0 sincronizzata
- [x] README e manuali aggiornati per il comportamento corrente
- [x] SECURITY_MODEL e MAP aggiornati
- [x] AGENTS e PLAN aggiornati
- [x] Approvazione esplicita del progettista prima del merge (2026-08-31)
- [x] Commit finale e merge fast-forward della PR #2 verso `main`
- [x] CI verificata sul branch (`33418463014`), sulla PR (`33418466714`) e su `main` (`33418580601`)
- [x] Tag `v0.2.0`, push e rimozione branch autorizzati dal progettista nel workflow di chiusura
- [ ] GitHub release `v0.2.0` da autorizzare, pubblicare e verificare separatamente

## Milestone 3 – Parità sandbox multipiattaforma

- Obiettivo: rendere `required` realmente enforced anche su Windows e chiudere il gap di rete del backend Linux, così che il benchmark possa essere eseguito e pubblicato con confini equivalenti e verificabili su macOS, Windows e Linux.
- Branch previsto: `milestone/3-cross-platform-sandbox`
- Incremento versione: `+0.1.0`
- Attività: prototipare e selezionare l'API Windows supportata più adatta tra AppContainer/LPAC e le API correnti di isolamento dei processi Win32; avviare Pi/Node e tutti i figli con identità e capacità minime; concedere accesso soltanto a workspace e configurazione Pi della task; negare directory utente, credenziali, registry non necessario e rete generica; progettare un trasporto locale ristretto verso Ollama senza aprire l'outbound; terminare in modo affidabile l'intero albero processi; mantenere probe, capability manifest, fallback `auto` esplicito e `required` fail-closed. Su Linux usare un network namespace bubblewrap e un proxy o trasporto locale minimo verso Ollama, eliminando la condivisione della rete host. Conservare Seatbelt macOS come regressione di riferimento e documentarne la deprecazione.
- Criteri di accettazione: `required` applica un backend OS su tutti e tre i sistemi supportati; Pi e i figli non possono leggere o scrivere fuori dalle directory concesse; la rete raggiunge soltanto il canale Ollama previsto e non Internet né altre porte locali; timeout e cancellazione terminano i discendenti; nessun backend richiede privilegi amministrativi impliciti; backend, capacità, limiti e fallback sono registrati senza sovrastimarli; un probe fallito interrompe `required` senza eseguire task.
- Test: unit e test negativi per selezione backend, ACL/capability, path assoluti, traversal, symlink/junction/reparse point, registry e rete; processi figli indiretti e sopravvissuti; porte loopback consentite e negate; probe reali Windows e Linux; smoke Pi/Ollama enforced su host Windows e Linux; regressione macOS; CI sui tre OS; verifica che gli stessi criteri di integrità e lo stesso schema report valgano per ogni backend.
- Documentazione: README e manuali bilingui, quick start dedicati Windows/Linux, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md` e piano; prerequisiti, limiti residui e troubleshooting per ogni backend.
- Release: milestone rilasciabile con GitHub release; artifact o pacchetto installabile e checksum SHA-256 se viene introdotta distribuzione fuori checkout.
- Stato: **milestone integrata con fast-forward su `main` dopo l'approvazione esplicita del progettista del 2026-08-31. Linux usa `unshare` per un network namespace vuoto, bubblewrap per filesystem/processi e un broker Unix a destinazione Ollama fissa. Windows usa AppContainer senza capability di rete, ACL/DACL sul SID esatto, named pipe nel namespace della sessione e Job Object kill-on-close. Lo smoke Windows reale in `required` è verde nel run `20260901-133810` dopo le correzioni emerse sul runtime Pi/Node/Python, sul broker e sul tool shell; compileall e 53 test locali sono verdi (5 probe non applicabili su Windows). Le CI del branch `33425751027` e `33430691610` e la CI post-merge su `main` `33430803855` restano verdi su macOS, Ubuntu e Windows. La CI di chiusura `33508052302` è verde sui tre sistemi e include la regressione Windows/Node 22 corretta dopo che il run precedente aveva rilevato `spawn EPERM`. I run benchmark Pi/Ollama reali sono stati verificati soltanto su macOS e Windows; lo smoke Linux reale non è stato eseguito, è documentato nel README ed è accettato come limite noto per il tag `v0.3.0`. Le correzioni Windows e commit, merge, tag e push sono stati approvati dal progettista il 2026-09-01; la GitHub release resta separata e non autorizzata.**

### Checklist milestone 3

- [x] Branch milestone creato (`milestone/3-cross-platform-sandbox`)
- [x] Architettura broker Ollama a destinazione fissa definita senza aprire Internet
- [x] Linux bubblewrap aggiornato con network namespace e socket Unix interno alla workspace
- [x] Windows AppContainer implementato senza capability di rete e con named pipe dedicato
- [x] Job Object Windows kill-on-close applicato prima di avviare il processo
- [x] ACL Windows temporanee limitate a workspace, configurazione Pi e runtime Pi
- [x] Probe fail-closed e fallback `auto` esplicito mantenuti
- [x] Test strutturali e negativi iniziali aggiunti
- [x] Probe reali Linux e Windows verificati in CI (`33424327842`)
- [x] Correzioni emerse dai probe multipiattaforma completate
- [x] Smoke Pi/Ollama enforced su Windows eseguito (`20260901-133810`: stato e integrità `ok`)
- [ ] Smoke Pi/Ollama enforced su Linux eseguito (non disponibile; limite noto accettato e documentato nel README)
- [x] Versione 0.3.0 sincronizzata
- [x] README, quick start, manuali, SECURITY_MODEL, MAP e AGENTS aggiornati
- [x] Compileall e 53 test rieseguiti dopo le correzioni Windows (verdi; 5 probe OS non applicabili su Windows)
- [x] CI finale del branch verificata dopo la documentazione (`33425552438`)
- [x] CI di chiusura delle correzioni Windows verde su macOS, Ubuntu e Windows/Node 22 (`33508052302`)
- [x] Approvazione esplicita del progettista prima del merge originario (2026-08-31)
- [x] Correzioni emerse dallo smoke Windows revisionate e approvate (2026-09-01)
- [x] Commit finale, merge fast-forward verso `main` e CI su `main` (`33430803855`)
- [x] Commit, merge, tag `v0.3.0` e push della chiusura Windows autorizzati (2026-09-01)
- [x] Vecchio branch `milestone/3-cross-platform-sandbox` eliminato localmente e dal remoto su richiesta esplicita del progettista (2026-09-03)
- [ ] GitHub release `v0.3.0` da autorizzare, pubblicare e verificare separatamente

## Milestone 4 – Casi personali estensibili

- Obiettivo: rendere semplice importare nuovi casi e pesi senza modificare il core.
- Branch previsto: `milestone/4-case-sdk`
- Incremento versione: `+0.1.0`
- Attività: schema JSON manifesto per caso; discovery confinata sotto `cases/`; titoli bilingui, categoria, peso e path dichiarati dal caso; validatore strutturale e di calibrazione; template atomico; guida autore; rubriche manuali opzionali conservate separatamente; compatibilità di lettura per configurazioni inline e result schema 3 precedenti.
- Criteri di accettazione: `case create` genera senza overwrite un caso autocontenuto e subito selezionabile con `--cases`; `case validate` controlla tutti i manifesti o una selezione, esegue i grader revisionati, impone massimo/somma di 100 punti e baseline sotto 60; path assoluti, traversal, symlink sui path dichiarati, fixture con symlink esterni, pesi invalidi, campi sconosciuti e directory incomplete vengono rifiutati; manifesto e rubrica entrano nello snapshot/hash; lo score manuale non altera la classifica automatica.
- Test: schema e discovery; manifesti oltre 64 KiB o corrotti; ID discordanti; path POSIX/Windows non sicuri; pesi e contratti grader invalidi; baseline già completate; creazione atomica e rifiuto overwrite; CLI create/validate; configurazione legacy; snapshot manifesti/rubriche; compatibilità report schema 3; suite completa multipiattaforma.
- Documentazione: README e manuali bilingui, `QUICK-START_Case-Author.md`, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md` e piano.
- Release: milestone rilasciabile `v0.4.0`; nessun artifact binario nuovo, perché l'esecuzione resta dal checkout. Tag e GitHub release soltanto dopo merge e autorizzazione esplicita.
- Stato: **milestone completata e pubblicata. I quattro casi esistenti sono migrati a manifesti scoperti automaticamente. Compileall, 63 test locali e `case validate` sui quattro casi sono verdi; 8 probe OS risultano non applicabili nel sandbox locale. Il run Pi/Ollama reale `20260901-193330` ha eseguito tramite manifesti `targeted_patch` e `secure_workspace` con `qwen3.5:9b-mlx` e Seatbelt in modalità `required`: le task sono terminate con score grezzi 100/100 e 90/100; il tentativo del modello di usare `/tmp/update_agents.py` è stato bloccato dalla sandbox e ha correttamente escluso il modello dalla classifica. Il progettista ha accettato il run come verifica funzionale di M4 e ha autorizzato l'intera chiusura il 2026-09-01. Il branch è stato integrato con fast-forward su `main`; le CI `33542311823`, `33542444039` e `33542606245` sono verdi su macOS, Windows e Ubuntu. Il tag annotato `v0.4.0` e la GitHub release stabile sono pubblicati e verificati senza artifact binari, come previsto; il branch milestone locale e remoto è stato eliminato dopo le verifiche.**

### Checklist milestone 4

- [x] Branch milestone creato (`milestone/4-case-sdk`)
- [x] Schema pubblico `schemas/case.schema.json` e manifesti dei quattro casi aggiunti
- [x] Discovery confinata e compatibilità configurazione inline pre-0.4 implementate
- [x] Comando `case create` atomico e senza overwrite implementato
- [x] Comando `case validate` con protocollo grader e calibrazione baseline implementato
- [x] Rubrica manuale opzionale mantenuta separata dallo score automatico
- [x] Manifesti e rubriche inclusi in preflight, snapshot, hash e artefatti del run
- [x] Test negativi, template, CLI, snapshot e compatibilità report aggiunti
- [x] Compileall e 63 test locali verdi (8 probe OS non applicabili)
- [x] Validazione esplicita dei quattro casi verde
- [x] Run Pi/Ollama reale `20260901-193330` completato con discovery da manifesti e sandbox `required` applicata; la violazione del modello è stata bloccata e registrata correttamente
- [x] Versione 0.4.0 sincronizzata in `VERSION`, package, README e piano
- [x] README, manuali, quick start autore, SECURITY_MODEL, MAP e AGENTS aggiornati
- [x] CI aggiornata per validare documenti, schema e calibrazione casi
- [x] Commit finale creato sul branch milestone
- [x] Branch pubblicato e CI macOS/Windows/Linux verificata (`33535189256`, `33535352417`, `33542311823`)
- [x] Approvazione esplicita del progettista per commit, merge, tag, GitHub release, push e successiva rimozione branch (2026-09-01)
- [x] Merge fast-forward verso `main`, push e CI post-merge verificata (`33542444039`)
- [x] Tag annotato `v0.4.0` pubblicato e verificato sul commit `a255341`
- [x] GitHub release stabile `v0.4.0` pubblicata e verificata senza artifact binari
- [x] Branch milestone locale e remoto eliminato dopo le verifiche di chiusura

## Milestone 5 – Finalissima dashboard interattiva

- Obiettivo: aggiungere una prova pratica finale in cui i modelli migliori trasformano gli stessi risultati reali dei profili `smoke`, `standard` e `full` in una dashboard interattiva, offline, accessibile e verificabile, riutilizzabile in seguito come lettore dei nuovi report del benchmark.
- Branch previsto: `milestone/5-results-dashboard-showcase`
- Incremento versione: `+0.1.0`
- Attività: nuovo caso `results_dashboard` e profilo separato `showcase`; comando `dashboard-data` che riceve una o più directory di run, combina `run.json` e `report.json`, conserva profilo e provenienza e genera un unico `dashboard-data.json` tramite whitelist dei soli campi necessari; fotografia immutabile dello stesso dataset reale per tutti i finalisti; visualizzazione del funnel `smoke` → `standard` → `full`, con partecipanti e passaggi tra le fasi senza classificare automaticamente come falliti i modelli non eseguiti nelle fasi successive; classifiche per profilo, andamento dei modelli, confronto metriche, filtri, ordinamento e dettaglio task; importazione successiva di uno o più report compatibili senza ricostruire l'app; applicazione statica HTML/CSS/JavaScript senza dipendenze runtime esterne; gestione di errori, timeout, dati mancanti e stati vuoti; tema chiaro/scuro e lingua italiano/inglese con preferenze persistenti; layout responsive e accessibilità da tastiera; rubrica visuale manuale e artefatti ispezionabili.
- Criteri di accettazione: tutti i finalisti ricevono la stessa copia immutabile dei report reali selezionati e gli stessi limiti; il dataset aggregato distingue run e profili e non contiene percorsi assoluti, comandi, prompt, risposte integrali, log o altri dati non necessari; una dashboard candidata completata funziona completamente offline, non modifica i dati sorgente e non contiene valori o nomi di modelli hardcoded; i dati visualizzati corrispondono ai report e nuovi report compatibili possono essere importati localmente; funnel, classifiche separate, filtri, ordinamento, dettagli, lingua e tema sono operativi; gli stati anomali sono leggibili; il grader automatico ha massimo 100 punti, mantiene la fixture iniziale sotto la soglia di completamento e verifica la generalità con un secondo dataset non fornito nel prompt; il punteggio tecnico resta distinto dalla valutazione visuale umana; workspace, patch e istruzioni di avvio restano disponibili per la revisione finale. Il superamento della soglia da parte di almeno un modello non è un requisito del sistema: timeout, errori e baseline non modificate sono esiti negativi validi se snapshot e integrità restano verificabili.
- Test: calibrazione del grader; unit test per aggregazione, whitelist, provenienza e compatibilità schema; verifica che l'export non includa percorsi, prompt, comandi o log; test delle trasformazioni con un dataset alternativo per rilevare valori hardcoded; test di integrazione dell'app; test browser per importazione locale, funnel, filtri, ordinamento, responsive, accessibilità di base, persistenza e assenza di richieste remote; test negativi con JSON invalido, campi mancanti, timeout e token non disponibili; smoke multipiattaforma con un modello compatibile.
- Documentazione: README, manuali bilingui, quick start della finalissima e del comando `dashboard-data`, schema del dataset aggregato, SECURITY_MODEL, MAP, AGENTS e piano; rubrica manuale documentata con criteri ripetibili.
- Stato: **milestone chiusa e integrata con fast-forward su `main` dopo l'approvazione esplicita del progettista del 2026-09-05. Il comando `dashboard-data` applica una whitelist privacy-bounded a run/report schema 2–3, conserva provenienza hashata, costruisce il funnel senza interpretare `not_run_in_next` come fallimento e scrive atomicamente entro la root. Il dataset reale dei run `m5-smoke-20260904`, `m5-standard-20260904` e `m5-full-20260904` è stato revisionato, congelato e committato in `e55bf57`; il commit documentale `2e8718b` aggiunge la procedura di congelamento. I run reali `m5-showcase-20260904` e `m5-showcase-rerun-20260905` hanno consegnato a entrambi i finalisti lo stesso dataset; il secondo ha integrità valida ma nessun candidato supera la baseline calibrata a 20/100: Muse termina senza modifiche dopo errori terminali dello stream provider, mentre Qwen termina in timeout senza modifiche. Il progettista ha accettato questi risultati come esiti negativi validi della prova. La revisione browser ha confermato la baseline non operativa e il file chooser privo di effetto; le verifiche visuali funzionali non sono applicabili e non viene attribuito un punteggio manuale positivo. Il commit `2ee76c1` converte in `pi_error` gli errori terminali agente/provider anche con exit code Pi zero, senza copiare il testo libero nei metadata o nell'export dashboard. Compileall, 72 test locali e la validazione dei cinque casi sono verdi; 8 probe OS sono non applicabili nell'ambiente corrente. Le CI sulla testa approvata sono verdi per push (`33974672909`) e PR (`33974674799`) su macOS, Ubuntu e Windows; le CI su `main` dopo il merge (`33974749960`) e dopo il verbale di merge (`33974826778`) sono verdi sui tre sistemi. Il tag annotato `v0.5.0` punta al commit verificato `462c235`; la GitHub release stabile è pubblicata senza artifact binari e il branch milestone locale e remoto è stato eliminato dopo le verifiche.**

### Checklist milestone 5

- [x] Branch milestone creato (`milestone/5-results-dashboard-showcase`)
- [x] Comando `dashboard-data` e modulo dedicato implementati senza dipendenze runtime
- [x] Lettura limitata a `run.json`/`report.json` schema 2–3 e a 32 MiB per sorgente
- [x] Whitelist verificata: nessun path assoluto, prompt, risposta, comando, log, evidenza di violazione o errore libero esportato
- [x] Provenienza tramite schema sorgente, SHA-256 e commit conservata senza modificare i run
- [x] Scrittura atomica confinata alla root, fuori dalle sorgenti e senza overwrite implicito
- [x] Funnel `smoke` → `standard` → `full` con `continued_to_next`, `not_run_in_next` e nuovi partecipanti
- [x] Schema pubblico `schemas/dashboard-data.schema.json` aggiunto
- [x] Caso `results_dashboard` e profilo separato `showcase` aggiunti
- [x] Fixture sintetica con profili, errori, metriche mancanti ed esclusione d'integrità aggiunta
- [x] Grader automatico da 100 punti con API JS verificabile e secondo dataset non fornito nel prompt
- [x] Rubrica visuale manuale da 20 punti mantenuta separata dallo score automatico
- [x] Baseline iniziale calibrata a 20/100
- [x] Test unitari per aggregazione, whitelist, provenienza, funnel, path, atomicità, CLI e schema aggiunti
- [x] Compileall e 72 test locali verdi; 8 probe OS non applicabili nell'ambiente corrente
- [x] Validazione esplicita dei cinque casi verde
- [x] Versione 0.5.0 sincronizzata in `VERSION`, package, README e piano
- [x] README, manuali, quick start finalissima, SECURITY_MODEL, MAP e AGENTS aggiornati
- [x] Dataset reale `smoke`/`standard`/`full` revisionato, congelato e committato (`e55bf57`)
- [x] Due run Pi/Ollama reali del profilo `showcase` eseguiti sui finalisti; rerun integro accettato come esito negativo valido (entrambi 20/100)
- [x] Revisione browser eseguita: entrambe le workspace conservano la baseline non operativa; checklist funzionale non applicabile e nessun punteggio manuale positivo attribuito
- [x] Errori terminali agente/provider classificati `pi_error` anche con exit code Pi zero, con test di regressione e senza esportare testo libero
- [x] Commit implementativo `929b39a` e push del branch completati
- [x] CI iniziali del branch `33790271591` e della PR `33790584645`, più CI del dataset reale su push `33962699324` e PR `33962702247`, verdi su macOS, Windows e Ubuntu
- [x] PR #3 aperta e merge state pulito prima delle correzioni finali
- [x] Correzioni finali pubblicate (`2ee76c1`) e CI multipiattaforma verdi su push `33974265316` e PR `33974267305`
- [x] Approvazione esplicita del progettista per merge, tag `v0.5.0`, GitHub release e successiva rimozione branch (2026-09-05)
- [x] Merge fast-forward verso `main`, push e CI post-merge verificata (`33974749960`)
- [x] Tag annotato `v0.5.0` pubblicato e verificato sul commit `462c235`
- [x] GitHub release stabile `v0.5.0` pubblicata e verificata senza artifact binari
- [x] Branch milestone locale e remoto eliminato dopo le verifiche di chiusura

## Milestone 6 – Dashboard ufficiale dei risultati

- Obiettivo: fornire nel repository una dashboard ufficiale, mantenuta dal progetto e distinta dalle dashboard candidate della finalissima, che renda i risultati del benchmark comprensibili anche a chi non vuole leggere direttamente i file JSON o usare comandi di analisi.
- Branch previsto: `milestone/6-official-results-dashboard`
- Incremento versione: `+0.1.0` (`v0.6.0`)
- Attività: creare un'applicazione statica ufficiale sotto `dashboard/`, composta da HTML, CSS e JavaScript modulari e priva di dipendenze runtime, CDN, telemetria e asset remoti; aggiungere `dashboard.py`, basato soltanto sulla libreria standard, che individua o riceve directory di run compatibili, riusa l'aggregatore `dashboard-data`, espone esclusivamente il dataset consentito tramite un server temporaneo su loopback e apre la dashboard nel browser; consentire la generazione esplicita di uno snapshot locale privacy-bounded per l'uso opzionale tramite `file://`, mantenendolo escluso da Git; supportare opzioni documentate per indicare run espliciti, non aprire automaticamente il browser e selezionare la porta senza sovrascrivere file sorgente; mantenere l'importazione manuale di `dashboard-data.json` tramite file chooser. La UI deve offrire una sintesi immediata, classifiche per profilo, funnel `smoke` → `standard` → `full`, confronto tra modelli, dettaglio task, score, tempi, token, stato, integrità ed eventuali metriche disponibili; deve distinguere chiaramente dato mancante, modello non eseguito, timeout, errore ed esclusione per integrità. Prevedere filtri e ordinamento, terminologia comprensibile, lingua italiana/inglese, tema chiaro/scuro, preferenze persistenti, layout responsive, navigazione da tastiera, stati di caricamento/vuoto/errore e indicazione visibile della provenienza e dell'aggiornamento del dataset.
- Criteri di accettazione: con un checkout pulito, `python3 dashboard.py` avvia su `127.0.0.1` la dashboard con i risultati locali compatibili, apre il browser e termina in modo pulito con `Ctrl+C`; se non esistono run compatibili usa in memoria la fixture revisionata; lo snapshot opzionale per `file://` viene generato soltanto su richiesta e resta ignorato da Git; i path espliciti sono risolti entro la root del progetto e gli input incompatibili o corrotti producono messaggi chiari senza esporre contenuti sensibili; browser e file statici ricevono soltanto i campi ammessi da `dashboard-data`, mai prompt, risposte integrali, comandi, log, errori liberi, evidenze di violazione o path assoluti; nessun dato sorgente viene modificato e nessun export locale viene committato implicitamente; i valori mostrati corrispondono al dataset, `not_run_in_next` non viene trasformato in fallimento e i modelli esclusi dall'integrità non rientrano nelle classifiche; la dashboard funziona offline sulle versioni supportate di macOS, Windows e Linux e resta leggibile su desktop e mobile; il codice ufficiale non dipende dalla fixture incompleta o dagli artefatti generati dai finalisti, salvo il dataset revisionato usato come fallback locale.
- Test: unit test Python per selezione run, validazione path, aggregazione, modalità senza apertura browser, binding loopback, arresto e assenza di scritture nelle sorgenti; test JavaScript delle trasformazioni, classifiche, funnel, filtri, ordinamento, formattazione dei dati mancanti e gestione di dataset schema 2–3; verifica che lo snapshot locale generato sia riproducibile dal dataset congelato, contenga soltanto la whitelist pubblica e sia ignorato da Git; test negativi con JSON invalido, schema non supportato, directory fuori root, porte occupate e dataset vuoti; test browser tramite server Python e, quando lo snapshot viene generato localmente, anche da `file://`, per caricamento iniziale, importazione file, cambio lingua/tema, persistenza, tastiera, responsive e assenza di richieste remote; compileall, suite unittest, validazione casi e CI su macOS, Ubuntu e Windows.
- Documentazione: aggiornare README, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, aggiungere un quick start bilingue o due quick start coordinati per dashboard e launcher, aggiornare `SECURITY_MODEL.md` per server loopback, lettura dei risultati e dati esposti al browser, aggiornare `MAP.md`, `AGENTS.md` e questo piano; documentare esattamente la differenza fra snapshot locale ignorato, risultati locali e importazione manuale, oltre a troubleshooting per browser che limitano `file://`, porta occupata e assenza di run compatibili.
- Release: milestone pubblicata come `v0.6.0`; tag e GitHub Release stabile sono stati autorizzati esplicitamente il 2026-09-05 dopo verifica manuale e CI verde. La release distribuisce il repository sorgente senza artifact binari di progetto, quindi non si applicano checksum di artifact; GitHub genera automaticamente gli archivi sorgente.
- Stato: **milestone chiusa, integrata con fast-forward su `main` e pubblicata dopo le approvazioni esplicite del progettista del 2026-09-05. La dashboard ufficiale statica usa il launcher standard-library per aggregare in memoria i run compatibili, serve soltanto asset autorizzati su `127.0.0.1` e non modifica le sorgenti. Lo snapshot opzionale per `file://` è generato localmente e ignorato da Git. I validatori Python e JavaScript applicano anche ai campi annidati la whitelist del dataset pubblico. Il flusso loopback è stato provato con cinque run reali: caricamento, filtri, dettaglio task, import valido e invalido, lingua/tema persistenti, tastiera, layout mobile senza overflow e sole richieste agli asset locali; nessun errore o warning console. Compileall, 83 test unittest e 7 test Node sono verdi; i probe OS/loopback non applicabili nel sandbox della suite restano espliciti. I cinque casi sono validi. Le CI finali sul branch approvato `2f72a5a` sono verdi per push (`33983519086`) e PR #4 (`33983522094`) su macOS, Ubuntu e Windows; le CI post-merge su `main` (`33983607418`, `33983699641`, `33983866513`) sono verdi sugli stessi sistemi. Il tag annotato `v0.6.0` e la GitHub Release stabile bilingue sono pubblicati senza artifact binari di progetto. Prima della pubblicazione del repository, la cronologia è stata sanificata e lo snapshot generato è stato rimosso da tutti i commit.**

### Checklist milestone 6

- [x] Branch milestone creato (`milestone/6-official-results-dashboard`)
- [x] Obiettivo, flussi di apertura e confini rispetto alla finalissima definiti nel piano
- [x] Architettura di `dashboard/` e contratto dati ufficiale definiti senza duplicare la logica del core
- [x] Snapshot locale opzionale, riproducibile e privacy-bounded, generabile ma escluso da Git
- [x] Flusso principale tramite launcher loopback verificato; `file://` disponibile dopo generazione locale esplicita
- [x] Launcher `dashboard.py` implementato con sola libreria standard, binding `127.0.0.1` e arresto pulito
- [x] Selezione automatica ed esplicita dei run compatibili implementata con path confinati alla root
- [x] Panoramica, classifiche, funnel, confronti, dettaglio task, filtri e ordinamento implementati
- [x] Stati `not_run_in_next`, timeout, errore, dati mancanti ed esclusione d'integrità rappresentati correttamente
- [x] Lingua italiana/inglese, tema chiaro/scuro, persistenza, responsive e accessibilità da tastiera verificati
- [x] Importazione manuale di `dashboard-data.json` mantenuta e documentata
- [x] Test Python, JavaScript, negativi e browser aggiunti e verdi
- [x] Smoke manuale con `python3 dashboard.py` eseguito su piattaforme applicabili
- [x] Assenza di rete remota, telemetria, dati sensibili e modifiche ai risultati sorgente verificata
- [x] Versione `0.6.0` sincronizzata nei punti canonici
- [x] README, manuali, quick start, SECURITY_MODEL, MAP, AGENTS e PLAN aggiornati
- [x] CI macOS, Ubuntu e Windows verde sul branch e sulla PR (`33983519086`, `33983522094`)
- [x] Approvazione esplicita del progettista per commit, merge, tag, push e rimozione branch (2026-09-05)
- [x] Merge fast-forward verso `main`, PR #4 chiusa e CI post-merge verificata (`33983607418`)
- [x] Tag annotato `v0.6.0` pubblicato e verificato sul commit `86f53a7`
- [x] GitHub Release stabile `v0.6.0` autorizzata, pubblicata e verificata senza artifact binari di progetto
- [x] Branch milestone locale e remoto eliminato dopo merge, CI e verifica del tag

## Milestone 7 – Controllo verificabile della modalità thinking

- Obiettivo: garantire che la modalità thinking dichiarata dal benchmark sia trasformata in un controllo Ollama esplicito, osservabile e riproducibile per ogni percorso di esecuzione, inclusi i profili `smoke`, `standard`, `full`, `showcase` e le selezioni esplicite con `--cases`; mantenere `off` come default ufficiale e impedire che risultati con controllo assente, incompatibile o inatteso entrino in classifica.
- Branch previsto: `milestone/7-verifiable-thinking-control`
- Incremento versione: `+0.1.0` (`v0.7.0`)
- Attività principali: introdurre un modulo dedicato alla policy thinking e una canonicalizzazione pura dei livelli Pi verso Ollama (`off` → `none`, alias documentati e nessun downgrade silenzioso); interrogare `POST /api/show` per ogni modello selezionato e conservare soltanto capability e metadati in whitelist; eseguire prima delle task un preflight reale sullo stesso endpoint OpenAI-compatible usato da Pi e con lo stesso `reasoning_effort`; generare `models.json` per modello con `samplingParams.reasoning_effort` come controllo autorevole, `supportsReasoningEffort: true`, `maxTokensField: "max_tokens"`, `reasoning` e `thinkingLevelMap` coerenti con le capability osservate; aggiungere `--thinking` alla CLI e propagare il valore richiesto ed effettivo senza fallback; configurare esplicitamente in `settings.json` timeout HTTP idle e retry dell'agente/provider; rendere unload, preflight e warmup coerenti con la stessa modalità; contare reasoning osservabile, retry ed errori senza copiarne il testo libero nei metadata pubblici; escludere l'intero modello quando il controllo non è verificabile o una task `off` emette thinking; aggiornare report, confronto multi-run, export dashboard e dashboard ufficiale; introdurre schema run/report 4 mantenendo la lettura degli schemi 2–3 come legacy non verificati.
- Regole del preflight: `/api/show` è una fonte di capability, non una prova sufficiente dei livelli supportati; il preflight deve verificare l'accettazione del valore effettivo e l'assenza/presenza osservabile di reasoning senza salvare la traccia; `off` fallisce chiuso se `none` viene rifiutato o compare reasoning; una modalità attiva richiede capability thinking e un segnale osservabile, altrimenti il modello viene marcato `thinking_control_unverified`; modelli che non consentono lo spegnimento completo non vengono riconosciuti tramite euristiche sul nome e non vengono degradati automaticamente a un livello minimo.
- Semantica warmup: il preflight è obbligatorio e può caricare il modello; `--no-warmup` disabilita soltanto l'eventuale warmup aggiuntivo, mai la verifica del controllo. Preflight e warmup devono essere registrati separatamente e non contribuire a tempi, token o punteggi delle task.
- Provenienza e privacy: `run.json` deve registrare versione del controllo, livello richiesto, valore canonicalizzato inviato, sorgente del controllo, capability, esito preflight, policy retry, timeout idle, versioni Pi/Ollama e digest modello; ogni risultato deve registrare soltanto conteggi di thinking/reasoning e retry. Nessuna catena di pensiero del preflight deve essere persistita; report e dataset dashboard non devono includere contenuti di reasoning. Gli eventi raw di Pi restano artefatti locali potenzialmente sensibili secondo `SECURITY_MODEL.md`.
- Compatibilità: `compare` deve rifiutare run con versione del controllo, modalità richiesta o effettiva, policy retry, timeout idle, versione Pi/Ollama, digest o capability incompatibili. I run precedenti alla 0.7.0 restano consultabili come evidenza storica con `thinking_control: unverified`, non sono confrontabili statisticamente con run verificati e non devono essere presentati come baseline prestazionali ufficiali.
- Test richiesti: unit test per mapping, capability e combinazioni incompatibili; test di `models.json` e `settings.json`; test CLI e configurazione; test del warmup nativo con `think: false` e livelli attivi; test runner per preflight, skip/esclusione modello, reasoning inatteso, retry e manifesto; test comparison e compatibilità legacy; test report/dashboard e whitelist privacy; server OpenAI-compatible locale fittizio che avvia realmente una versione Pi supportata e cattura il payload verificando `reasoning_effort`, `max_tokens` e assenza di retry; compileall, unittest, test Node della dashboard, validazione di tutti i casi e CI macOS/Ubuntu/Windows; smoke reale `off` e `medium` con un modello thinking-capable disponibile.
- Criteri di accettazione: ogni richiesta task della coorte `off` contiene `reasoning_effort: "none"`; il payload effettivo è verificato con Pi reale, non soltanto dedotto dalla configurazione; nessuna task `off` classificabile contiene thinking osservabile; una combinazione incompatibile viene esclusa prima delle task senza impedire la verifica degli altri modelli; nessun fallback cambia il livello richiesto; Pi non applica retry automatici o il timeout idle predefinito e il timeout del runner resta autorevole; il warmup usa la stessa modalità; manifesti e risultati permettono di ricostruire la policy senza esporre reasoning; `smoke`, `standard`, `full`, `showcase` e `--cases` attraversano lo stesso controllo; run legacy e run con modalità diverse non vengono aggregati; documentazione e dashboard descrivono chiaramente stato verificato, non verificato e incompatibile; suite e CI sono verdi e gli smoke reali dimostrano `off` e `medium` come coorti distinte.
- Documentazione: aggiornare README, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, quick start CLI/dashboard/showcase, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md` e questo piano; documentare versioni Pi supportate, significato limitato del preflight, riscaldamento implicito, dati conservati, gestione legacy e impossibilità di provare processi interni non esposti dal provider.
- Release: milestone integrata e taggata come `v0.7.0`; la GitHub Release non è stata pubblicata perché non inclusa nell'autorizzazione del progettista del 2026-09-19. Il repository resta distribuito come sorgente salvo decisione separata sugli artifact.
- Stato: **completata e integrata in `main` il 2026-09-19 tramite PR #1 e merge commit `8807d97`. Policy, capability discovery, preflight, configurazione Pi, schema 4, esclusione, confronto, dashboard e documentazione sono implementati; compileall, 104 test Python, 7 test Node e la validazione dei 5 casi sono verdi. I test loopback mirati sono verdi fuori dal sandbox ristretto: 2 contratti Pi 0.85.1 (`off`, `medium`, `max_tokens`, zero retry) e 8 test del launcher dashboard. Due smoke reali su Pi 0.85.1, Ollama 0.34.2 e `qwen3.5:9b-mlx`, stesso seed `20260919`, hanno verificato coorti distinte: `off` 83/100 in 238,0 s, nessun thinking osservato e zero retry; `medium` 100/100 in 310,8 s, 5.468 caratteri thinking osservati e zero retry. `compare` ha rifiutato correttamente l'aggregazione per `thinking`/`reasoning_effort`; l'export dashboard schema 2 non contiene reasoning o preflight dettagliati. La CI è verde su macOS, Ubuntu e Windows sia sulla PR sia su `main` (run `35451967605`); il tag annotato `v0.7.0` è pubblicato e il branch milestone è stato eliminato in locale e sul remoto. La verifica visuale browser non è stata eseguita perché in questa sessione non era disponibile alcun browser controllabile. Il file locale di appoggio `THINKING_MODE_CORRECTIONS.md` è stato eliminato senza essere mai tracciato.**

### Ordine di implementazione milestone 7

1. Aggiungere test inizialmente rossi per payload Pi reale, mapping, configurazione isolata, timeout, retry, warmup e compatibilità.
2. Implementare il modello di dominio della policy thinking e il parsing in whitelist di `/api/show`.
3. Implementare preflight fail-closed e integrazione con unload/warmup senza contaminare le metriche task.
4. Correggere `models.json` e `settings.json` isolati e verificare il payload con il server fittizio.
5. Aggiungere `--thinking` e propagare livello richiesto ed effettivo a runner, manifesti e risultati.
6. Applicare esclusione, reportistica, schema 4 e regole di compatibilità multi-run.
7. Aggiornare export/dashboard, avvisi legacy e documentazione di sicurezza/privacy.
8. Eseguire suite completa, validazione casi e CI multipiattaforma.
9. Eseguire smoke reali separati `off` e `medium`, revisionare artefatti e assenza di fallback.
10. Aggiornare documentazione e checklist finale, quindi richiedere avallo prima di merge, tag, release e rimozione branch.

### Checklist milestone 7

- [x] Branch milestone creato (`milestone/7-verifiable-thinking-control`)
- [x] Piano iniziale M7 e follow-up M8 definiti
- [x] Test di regressione per mapping, payload, runner, confronto e dashboard aggiunti
- [x] Policy thinking e discovery capability implementate in moduli dedicati
- [x] Preflight fail-closed implementato senza euristiche sul nome modello
- [x] Payload Pi reale verificato tramite server OpenAI-compatible fittizio (Pi 0.85.1)
- [x] Configurazione timeout, retry, token e warmup resa esplicita
- [x] Override CLI e provenienza completa implementati
- [x] Schema run/report 4 e compatibilità legacy implementati
- [x] Esclusione per controllo non verificato, thinking o retry inatteso implementata
- [x] Confronto multi-run aggiornato con chiave di compatibilità thinking
- [x] Export dashboard e dashboard ufficiale aggiornati senza contenuto di reasoning
- [x] Compileall, 104 test unittest, 7 test Node e validazione dei 5 casi eseguiti; test loopback mirati eseguiti senza skip
- [x] Smoke reale `off` eseguito e revisionato (`results/m7-smoke-off-qwen35`, 83/100, thinking assente, retry 0)
- [x] Smoke reale `medium` eseguito e revisionato come coorte separata (`results/m7-smoke-medium-qwen35`, 100/100, thinking osservato, retry 0)
- [x] CI macOS, Ubuntu e Windows verde sul branch/PR (PR #1)
- [x] Versione `0.7.0` sincronizzata nei punti canonici
- [x] README, ISTRUZIONI, INSTRUCTIONS, quick start, SECURITY_MODEL, MAP e AGENTS aggiornati
- [x] PLAN aggiornato con implementazione, verifiche e chiusura
- [x] Approvazione esplicita del progettista ottenuta prima del merge (2026-09-19)
- [x] Commit finale e PR/merge verso `main` completati (PR #1, merge `8807d97`)
- [x] CI verificata su `main` (run `35451967605`)
- [x] Tag `v0.7.0` creato e pubblicato
- [x] GitHub Release non pubblicata perché non inclusa nell'autorizzazione ricevuta
- [x] Branch obsoleto eliminato in locale e sul remoto dopo merge, CI e tag

## Milestone 8 – Caso di benchmark e coorti thinking

- Obiettivo: aggiungere un caso sintetico, riproducibile e calibrato che misuri il valore pratico del thinking sul risultato osservabile, integrarlo nella progressione del benchmark e fornire confronti `off`/`medium` equi e separati anche per la finalissima `showcase`, senza chiedere o premiare l'esposizione della catena di pensiero.
- Branch previsto: `milestone/8-thinking-benchmark-case`
- Incremento versione: `+0.1.0` (`v0.8.0`)
- Dipendenza: Milestone 7 completata, integrata e verificata con almeno una coorte reale `off` e una `medium`.
- Attività principali: progettare il caso `thinking_challenge` come task multi-vincolo con fixture sintetica, soluzione verificabile e grader deterministico da 100 punti; crearlo tramite `python3 benchmark.py case create ...`, revisionare integralmente il grader prima della validazione e calibrare la baseline sotto 60; aggiungere un profilo indipendente `thinking` per gli esperimenti rapidi; includere il caso in `standard` e quindi in `full` dopo la calibrazione; lasciare il contenuto di `smoke` invariato per preservarne rapidità e significato, affidando al preflight M7 la verifica del controllo; mantenere `showcase` come caso specialistico distinto ma permettere una finalissima sperimentale a coorti accoppiate; aggiornare report/dashboard affinché la modalità thinking sia una dimensione/coorte e il profilo `thinking` non venga interpretato come fase successiva del funnel `smoke` → `standard` → `full`.
- Integrazione profili: `smoke` continua a verificare Pi/Ollama, tool calling e controllo thinking tramite preflight; `standard` aggiunge `thinking_challenge`; `full` include lo stesso caso oltre a `milestone_closure`; `thinking` esegue soltanto il nuovo caso per confronti A/B; `showcase` conserva `results_dashboard` e riceve sempre il controllo M7, senza essere mescolato automaticamente con la leaderboard principale.
- Protocollo `off`/`medium`: ogni confronto usa directory diverse, stesso digest modello, fixture, seed, temperatura, context window, token massimi, timeout, sandbox, policy retry, versione Pi/Ollama e ambiente; almeno tre ripetizioni per cella quando il risultato deve sostenere una decisione. Le modalità restano leaderboard separate e il comando normale `compare` continua a rifiutarne l'aggregazione; un riepilogo dedicato può affiancare qualità, completion rate, durata, token totali e reasoning token disponibili.
- Finalissima `showcase`: il percorso ufficiale resta una coorte `off` verificata per coerenza con il benchmark principale. Quando si vuole misurare il beneficio del thinking, tutti i finalisti devono ricevere anche la stessa coorte `medium`, indipendentemente dall'esito `off`, con lo stesso dataset congelato e lo stesso numero di tentativi. L'ordine delle coorti deve essere alternato o controbilanciato tra ripetizioni per ridurre effetti termici e d'ordine. Non è ammesso il fallback condizionale “prima thinking, poi off soltanto se fallisce” o l'inverso: timeout ed errori restano risultati della relativa coorte e non concedono tentativi aggiuntivi selettivi. La dashboard deve mostrare le due coorti affiancate e non fondere punteggi o classifiche salvo una futura metrica combinata definita prima dei run.
- Criteri di accettazione: manifesto conforme a `schemas/case.schema.json`; titoli italiano/inglese, prompt, fixture e grader autocontenuti; massimo e somma grader pari a 100; baseline iniziale sotto 60; nessuna credenziale, rete o path esterno; soluzione non dipendente da stringhe hardcoded o dall'esposizione del reasoning; profilo `thinking` selezionabile; `standard` e `full` includono il caso senza rompere la progressione; `smoke` e `showcase` mantengono il loro scopo; export e dashboard distinguono profilo, modalità e coorte senza alterare il funnel; esperimento reale `off`/`medium` completato su almeno un modello compatibile; se viene eseguita la finalissima doppia, tutti i finalisti ricevono entrambe le modalità con condizioni simmetriche e risultati separati.
- Test richiesti: calibrazione diretta della fixture; unit e test negativi del grader; fixture alternativa nascosta se necessaria per impedire hardcoding; `case validate thinking_challenge` e validazione completa; test config/profili; test runner e manifesti per coorti; test comparison per separazione delle modalità; test dashboard/export per modalità, profilo indipendente e funnel invariato; compileall, unittest, test Node, CI multipiattaforma; smoke reale del nuovo profilo e confronto con almeno tre ripetizioni per cella; verifica manuale degli artefatti migliori e dei fallimenti.
- Documentazione: README, manuali bilingui, quick start autore e showcase/dashboard, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md` e questo piano; documentare obiettivo del caso, protocollo A/B, limiti statistici, costo aggiuntivo, interpretazione dei reasoning token e divieto di fallback condizionali.
- Release: milestone rilasciabile come `v0.8.0`; tag, GitHub Release, push, merge e rimozione branch richiedono approvazione esplicita del progettista.
- Stato: **milestone chiusa, integrata e pubblicata il 2026-09-19. Il caso `thinking_challenge` è stato creato tramite Case SDK come pianificatore esatto multi-vincolo, con baseline 5/100, scenari alternativi nel grader, regressione anti-hardcoding sotto 60 e soluzione generica temporanea calibrata a 100/100. Il profilo indipendente `thinking` è configurato; `standard` e `full` includono il caso, mentre `smoke` e `showcase` restano invariati. Export e dashboard mantengono `thinking`/`showcase` fuori dal funnel principale e separano classifiche e fattori per run/modalità. Compileall, 106 test Python, 8 test Node e la validazione dei sei casi sono verdi; 12 probe dipendenti da loopback o sistemi operativi diversi non sono applicabili nel sandbox corrente. La verifica Playwright via server locale è verde a 1440×900 e 390×844 in tema chiaro/scuro, senza overflow orizzontale, errori console o richieste remote e con dialogo accessibile da tastiera. L'esperimento reale su Pi 0.85.1, Ollama 0.34.2 e `qwen3.5:9b-mlx`, seed `20260919`, sandbox Seatbelt `required`, timeout 1.200 s e tre ripetizioni per cella ha mantenuto condizioni e retry simmetrici: `medium` ha ottenuto 60/0/0, qualità media 20,0, completion 33%, mediana 532,2 s e 14.589 token output; `off` ha ottenuto 22/0/10, qualità media 10,7, completion 0%, mediana 486,8 s e 13.874 token output. Il preflight e ogni task confermano reasoning `medium` osservato (1.548–1.895 caratteri thinking) e nessun thinking in `off`, sempre con zero retry e integrità valida. Tutte le task terminano per limite `length`: con soli tre campioni il risultato segnala un vantaggio descrittivo di qualità per `medium`, a costo di circa 45,5 s e 715 token mediani, ma non sostiene inferenza statistica. `compare` rifiuta correttamente l'aggregazione incrociata; l'export dashboard schema 2 mostra le due coorti separate e un funnel vuoto, senza contenuto reasoning. La revisione manuale conferma che il 60/100 supera scenari nascosti, tie-break e infeasibilità, mentre gli 0/100 derivano da implementazioni troncate/non importabili, non da errori del grader. Dopo l'approvazione esplicita del progettista, la PR #2 è stata integrata con merge commit `1861253`; la CI è verde su macOS, Ubuntu e Windows sia sulla PR (`35457236695`) sia su `main` (`35457439164`). Il tag annotato `v0.8.0` punta al merge verificato e la GitHub Release stabile è pubblicata senza artifact binari di progetto; il branch milestone è stato eliminato dal remoto e in locale.**

### Checklist milestone 8

- [x] Branch milestone creato (`milestone/8-thinking-benchmark-case`)
- [x] Brief funzionale e minacce alla validità del caso revisionati
- [x] Caso creato tramite Case SDK e manifesto validato
- [x] Fixture sintetica e grader deterministico completati
- [x] Baseline calibrata a 5/100 con massimo/somma pari a 100; soluzione generica di controllo a 100/100
- [x] Test negativi e anti-hardcoding aggiunti
- [x] Profilo indipendente `thinking` aggiunto
- [x] Caso integrato in `standard` e `full`; `smoke` mantenuto rapido
- [x] Controllo thinking verificato anche per `showcase`
- [x] Dashboard/export aggiornati per coorti indipendenti e funnel invariato
- [x] Protocollo simmetrico `off`/`medium` documentato senza fallback condizionale
- [x] Compileall, 106 test Python, 8 test Node e validazione completa dei 6 casi eseguiti; 12 skip ambientali motivati
- [x] Verifica browser/server Playwright completata su desktop/mobile, temi chiaro/scuro, tastiera e rete solo locale
- [x] Smoke reale del profilo `thinking` eseguito su `qwen3.5:9b-mlx` con sandbox `required`
- [x] Esperimento reale con tre ripetizioni per cella `medium`/`off` eseguito e revisionato
- [x] Miglior artefatto e fallimenti revisionati; limite `length`, punteggi parziali e assenza di errori grader documentati
- [x] `compare` incrociato rifiutato ed export/dashboard reali verificati con coorti separate e funnel vuoto
- [x] Finalissima doppia non eseguita: verifica opzionale non necessaria per l'accettazione M8; il protocollo controbilanciato resta documentato per i futuri finalisti
- [x] CI macOS, Ubuntu e Windows verde sulla PR #2 (run `35457236695`)
- [x] Versione `0.8.0` sincronizzata nei punti canonici
- [x] README, ISTRUZIONI, INSTRUCTIONS, quick start, SECURITY_MODEL, MAP e AGENTS aggiornati
- [x] PLAN aggiornato con stato, calibrazione e verifiche pendenti
- [x] Approvazione esplicita del progettista ottenuta il 2026-09-19 prima del merge
- [x] Commit finali e PR #2 integrati in `main` con merge commit `1861253`
- [x] CI verificata su `main` (run `35457439164`)
- [x] Tag annotato `v0.8.0` e GitHub Release stabile pubblicati senza artifact binari di progetto
- [x] Branch obsoleto eliminato dal remoto e in locale dopo merge, CI, tag e release

## Milestone 9 – Mappa visiva di efficienza

- Obiettivo: aggiungere alla dashboard ufficiale una lettura cartesiana e accessibile del rapporto tra qualità, durata e token, così da rendere immediatamente visibili i modelli efficienti senza alterare la formula di scoring o mescolare coorti incompatibili.
- Branch previsto: `milestone/9-dashboard-efficiency-map`
- Incremento versione: `+0.1.0` (`v0.9.0`)
- Attività principali: introdurre una sezione full-width “Mappa efficienza / Efficiency map” con due scatter plot per qualità/tempo e qualità/token; derivare i punti esclusivamente dai campi pubblici già presenti nella leaderboard; usare `quality_score` come risultato indipendente per evitare il doppio conteggio di velocità ed efficienza già incluso in `overall_score`; separare ogni run e modalità thinking in una coorte distinta; usare una scala logaritmica dichiarata per gli assi orizzontali; distinguere completamenti pieni e risultati sotto soglia; aggiungere dettaglio hover/focus, riepilogo testuale e navigazione da tastiera; mantenere filtri, tema, lingua, CSP, importazione e funzionamento `file://` esistenti; non introdurre dipendenze, CDN, telemetria o richieste remote.
- Criteri di accettazione: ogni punto appartiene a un solo run/coorte e non produce classifiche combinate implicite; i modelli esclusi per integrità restano assenti; gli assi gestiscono valori mancanti, identici, nulli e range molto diversi senza overflow; la zona desiderabile è spiegata come alta qualità con minore durata/token senza introdurre una curva di tendenza; tooltip/focus espongono modello, qualità, metrica X, completamento, profilo e thinking; il contenuto resta leggibile in italiano e inglese, tema chiaro/scuro, desktop e mobile; la dashboard continua a funzionare offline sia tramite server loopback sia, quando viene generato lo snapshot locale, da `file://`.
- Test richiesti: unit test JavaScript per derivazione dei punti, separazione delle coorti, ordinamento, domini logaritmici, valori degeneri e filtri; test Python invariati per whitelist/export/server; suite Node e unittest complete; compileall; verifica browser tramite server locale su desktop e mobile, temi chiaro/scuro, tastiera e focus dei punti; controllo console, overflow e assenza di richieste remote; verifica opzionale `file://` soltanto se viene rigenerato uno snapshot locale.
- Documentazione: aggiornare README, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md`, quick start dashboard e questo piano; documentare significato degli assi, scala logaritmica, separazione delle coorti e limiti interpretativi.
- Release: milestone funzionale rilasciabile come `v0.9.0`; commit, push, PR, merge, tag, GitHub Release e rimozione branch richiedono approvazione esplicita del progettista dopo test e revisione visuale.
- Stato: **milestone chiusa, integrata e pubblicata il 2026-09-20. I due scatter plot nativi e offline separano le coorti per run/modalità, usano `quality_score` con assi orizzontali logaritmici e mantengono filtri, i18n, tema e accessibilità da tastiera. Compileall, 106 test Python, 10 test Node e la validazione dei sei casi sono verdi; 12 probe dipendenti da loopback o sistemi operativi diversi risultano non applicabili nel sandbox corrente. La verifica HTTP manuale conferma asset autorizzati e dataset ridotto con header di sicurezza, oltre al rifiuto 404 di file non autorizzati. La revisione Playwright via server locale è verde a 1440×900 e 390×844 in tema chiaro/scuro e italiano/inglese: nessun overflow orizzontale, zero errori o warning console, focus dei punti raggiungibile con `Tab`, riepilogo testuale aggiornato e sole otto richieste statiche a `127.0.0.1`. Dopo l'approvazione esplicita del progettista, la PR #3 è stata integrata con merge commit `8bb68e0`; la CI è verde su macOS, Ubuntu e Windows sia sulla PR (`35501206550`) sia su `main` (`35501371878`). Il tag annotato `v0.9.0` punta al merge verificato e la GitHub Release stabile è pubblicata senza artifact binari di progetto; il branch milestone è stato eliminato dal remoto e in locale.**

### Checklist milestone 9

- [x] Branch milestone creato (`milestone/9-dashboard-efficiency-map`)
- [x] Brief funzionale, incremento `0.9.0` e criteri di accettazione definiti
- [x] Implementazione dei due scatter plot completata
- [x] Coorti, soglie, valori mancanti e scala logaritmica coperti da test JavaScript
- [x] Test Python, JavaScript e compileall eseguiti (106 Python superati, 12 skip attesi; 10 Node superati)
- [x] Verifica browser desktop/mobile, temi, lingue, tastiera, overflow, console e rete completata
- [x] Verifica server loopback, header di sicurezza, asset autorizzati e route negate completata
- [x] Validazione dei sei casi benchmark completata
- [x] Versione `0.9.0` sincronizzata nei punti canonici
- [x] README, manuali, quick start, security model, MAP e AGENTS aggiornati
- [x] PLAN aggiornato con verifiche browser, CI, merge, tag, release e chiusura della milestone
- [x] Approvazione esplicita del progettista ottenuta il 2026-09-20 prima del merge
- [x] Commit finale e PR #3 integrati in `main` con merge commit `8bb68e0`
- [x] CI macOS, Ubuntu e Windows verificata sulla PR (`35501206550`) e su `main` (`35501371878`)
- [x] Tag annotato `v0.9.0` e GitHub Release stabile pubblicati senza artifact binari di progetto
- [x] Branch obsoleto eliminato dal remoto e in locale dopo merge, CI, tag e release

## Milestone 10 – Landing page bilingue su GitHub Pages

- Obiettivo: creare una landing page pubblica, moderna e sobria che presenti LocalAgent Benchmark, spieghi cosa misura e come funziona il percorso `smoke` → `standard` → `full`, illustri dashboard e risultati senza sovraccaricare la pagina di testo e offra accessi chiari al repository, alla release più recente e al sito personale del progettista.
- Branch previsto: `milestone/10-github-pages-landing`
- Incremento versione: `+0.1.0`, da `0.9.0` a `0.10.0`, con tag previsto `v0.10.0`.
- Architettura e pubblicazione: realizzare un sito statico dedicato sotto `site/`, con HTML, CSS e JavaScript modulari, asset locali e nessuna dipendenza runtime, CDN, font remoto, telemetria o analytics; aggiungere un workflow GitHub Pages dedicato che pubblichi esclusivamente il contenuto revisionato di `site/` all'indirizzo `https://gloutchov.github.io/LocalAgentBenchmark/`. Il workflow e la configurazione Pages possono essere attivati soltanto dopo l'approvazione esplicita del progettista.
- Struttura dei contenuti: prevedere almeno hero e sintesi del progetto; panoramica delle capacità valutate; spiegazione dei profili e dei casi; metodologia, riproducibilità, sandbox, controllo thinking e limiti interpretativi; presentazione visuale della dashboard ufficiale; istruzioni rapide per eseguire o consultare il benchmark; collegamenti alla documentazione; call to action verso il repository `https://github.com/gloutchov/LocalAgentBenchmark` e verso `https://github.com/gloutchov/LocalAgentBenchmark/releases/latest`, chiarendo che il download disponibile è quello distribuito dalla release e senza promettere artifact non presenti; footer con indicazione e link alla Apache License 2.0.
- Navigazione: inserire nell'header un menu che raggiunga tramite anchor le sezioni principali della landing page; immediatamente dopo il menu aggiungere un'icona a forma di casa, accessibile da tastiera e dotata di etichetta comprensibile, che apra `https://glaucosilvestri.it`. Rendere visibili focus, stato attivo e comportamento del menu su schermi stretti senza introdurre navigazioni inattese.
- Lingua: rilevare `navigator.language` e usare italiano soltanto quando la lingua di sistema è italiana, inglese in tutti gli altri casi; offrire un controllo manuale `Italiano`/`English`, aggiornare correttamente l'attributo `lang` del documento e persistere la preferenza in `localStorage`; mantenere sincronizzati i dizionari e non lasciare stringhe user-facing hardcoded fuori dal sistema i18n.
- Tema: usare `prefers-color-scheme` per il comportamento automatico e offrire un controllo manuale `Auto`/`Chiaro`/`Scuro` (`Auto`/`Light`/`Dark` in inglese), persistendo la preferenza in `localStorage`; evitare flash cromatici evidenti al caricamento e verificare contrasto, immagini, header, link, pulsanti, focus e stati hover/disabled in entrambi i temi.
- Direzione visuale: adottare un linguaggio grafico contemporaneo ma misurato, coerente con un progetto tecnico e con la dashboard esistente; privilegiare gerarchia tipografica, griglia, spaziatura e contenuti reali rispetto a decorazioni, card annidate o animazioni gratuite; supportare `prefers-reduced-motion`; mantenere il percorso principale leggibile su desktop e mobile.
- Materiale visuale: revisionare il file locale non tracciato `assets/Dashboard.mov` prima di utilizzarlo, verificando che non mostri path, dati sensibili o elementi non destinati alla pubblicazione; trattarlo come sorgente locale immutabile e non committarlo automaticamente. Estrarre fotogrammi rappresentativi della dashboard, ritagliarli e ottimizzarli in formati web moderni con fallback quando necessario; versionare sotto `site/assets/` soltanto immagini derivate, leggere, prive di metadati non necessari e approvate dal progettista, con dimensioni dichiarate, caricamento responsivo/lazy e testi alternativi bilingui. Un breve video ottimizzato potrà essere valutato solo se migliora davvero la comprensione senza penalizzare peso, accessibilità o prestazioni.
- Sicurezza e privacy: pubblicare esclusivamente testo, link e asset revisionati; non incorporare risultati raw, path locali, prompt, risposte, reasoning, log o identificatori sensibili; non usare form, cookie, tracker o richieste remote; limitare `localStorage` a lingua e tema; definire una Content Security Policy compatibile con GitHub Pages e documentare in `SECURITY_MODEL.md` la superficie pubblica, i link esterni, lo storage locale e i limiti residui dell'hosting Pages.
- Criteri di accettazione: apertura diretta sull'esperienza utile; contenuti completi e coerenti in italiano e inglese; selezione automatica e override persistente di lingua e tema; menu e icona casa corretti e accessibili; link a repository, release più recente, licenza e sito personale validi; immagini della dashboard nitide, responsive, non sensibili e non meramente decorative; assenza di overflow orizzontale e layout leggibile almeno a 390 px e 1440 px; navigazione completa da tastiera, focus visibile, contrasto adeguato, landmark semantici, skip link e rispetto di `prefers-reduced-motion`; nessuna richiesta verso CDN, font, analytics o altri asset remoti; percorsi relativi funzionanti sotto il prefisso Pages `/LocalAgentBenchmark/`; metadata essenziali per titolo, descrizione, social preview e URL canonico coerenti; pagina 404 o fallback di navigazione appropriato alla natura statica del sito; licenza Apache 2.0 indicata chiaramente.
- Test richiesti: test unitari JavaScript senza dipendenze runtime per selezione/persistenza di lingua e tema e sincronizzazione dei dizionari; controllo statico di link, anchor, asset, `lang`, testi alternativi, metadata e assenza di URL remoti non autorizzati; verifica locale tramite server statico; test browser su desktop e mobile in italiano/inglese e tema auto/chiaro/scuro; prova tastiera, focus, menu responsive, preferenze persistenti, `prefers-reduced-motion`, console, overflow e richieste di rete; controllo dei link esterni senza dipendere dalla rete nella suite ordinaria; esecuzione di compileall, unittest, test Node esistenti, validazione dei casi e CI multipiattaforma per assicurare che la landing page non introduca regressioni nel benchmark.
- Documentazione: aggiornare `README.md`, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md` e questo piano; aggiungere istruzioni per anteprima locale, manutenzione dei contenuti/asset, aggiornamento dei link e funzionamento del deploy Pages; sincronizzare la versione `0.10.0` in tutti i punti canonici soltanto durante l'implementazione della milestone. Tutti gli aggiornamenti documentali devono essere completati e revisionati sul branch della milestone prima dell'approvazione al merge, così che `main` riceva insieme funzionalità, documentazione e modello di sicurezza coerenti.
- Release: creare il tag sorgente `v0.10.0`; per decisione esplicita del progettista non creare una GitHub Release, perché la milestone aggiunge presentazione e pubblicazione web senza modificare il comportamento funzionale del benchmark. Il link “ultima release” della landing page resta stabile tramite `/releases/latest` e continua a puntare all'ultima GitHub Release effettivamente pubblicata.
- Gate di approvazione: all'avvio dei lavori creare il branch dedicato, ma mantenere tutte le modifiche non committate per consentire la verifica personale locale del progettista. Prima dell'avallo esplicito sono vietati commit, push, apertura PR, merge, tag, GitHub Release, attivazione/deploy Pages e rimozione del branch. Dopo test automatici e verifica browser, presentare diff, anteprima locale, elenco degli asset derivati, risultati dei test e limiti residui; procedere con ciascuna operazione Git e di pubblicazione soltanto nell'ambito autorizzato dal progettista.
- Stato: **milestone chiusa, integrata e pubblicata il 2026-09-26. Implementazione e documentazione sono state approvate dal progettista prima del primo commit, inclusi i fotogrammi derivati, la rinomina del repository in `LocalAgentBenchmark` e il deploy Pages. La PR #4 è stata integrata in `main` con merge commit `673bd85`; la CI è verde su macOS, Ubuntu e Windows sia sulla PR (`36234009259`) sia su `main` (`36234153770` e `36234380839`). Il workflow Pages `36234153769` ha pubblicato `https://gloutchov.github.io/LocalAgentBenchmark/`; landing e asset rispondono `200`, la route inesistente usa il fallback personalizzato con stato `404` e i link pubblici a repository, release effettiva più recente, documentazione, licenza e sito personale sono raggiungibili. I test locali sono verdi (compileall, 113 test Python con 12 skip ambientali, 15 test Node e validazione dei sei casi); la verifica browser locale copre desktop/mobile, lingua, temi, persistenza, tastiera, overflow, console, asset lazy e sole richieste same-origin. Durante la CI è stato inoltre corretto il percorso del socket Linux per restare entro il limite `AF_UNIX` anche dopo la rinomina più lunga. `assets/Dashboard.mov` è rimasto immutato e ignorato. Il tag annotato `v0.10.0` punta al commit verificato `2f1984e`; il branch milestone è stato eliminato dal remoto e in locale. Per decisione esplicita non è stata creata una GitHub Release.**

### Checklist milestone 10

- [x] Branch `milestone/10-github-pages-landing` creato senza commit iniziali non autorizzati
- [x] Brief dei contenuti, architettura informativa e direzione visuale revisionati
- [x] `assets/Dashboard.mov` ispezionato per privacy e contenuti pubblicabili senza modificarne l'originale
- [x] Fotogrammi derivati selezionati, ottimizzati, privati dei metadati superflui e approvati
- [x] Struttura statica modulare sotto `site/` implementata senza dipendenze runtime o asset remoti
- [x] Header, menu per sezioni e icona casa verso `https://glaucosilvestri.it` implementati e accessibili
- [x] Contenuti completi e sincronizzati in italiano e inglese
- [x] Rilevamento automatico e override persistente della lingua verificati
- [x] Tema automatico, chiaro e scuro con override persistente verificati
- [x] Sezioni descrittive, metodologia, sicurezza, dashboard, quick start e call to action completate
- [x] Link a repository, `/releases/latest`, documentazione e Apache License 2.0 verificati
- [x] Responsive, accessibilità, tastiera, contrasto, focus e `prefers-reduced-motion` verificati
- [x] Metadata, social preview, URL canonico, percorsi `/LocalAgentBenchmark/` e fallback 404 verificati
- [x] Assenza di CDN, font remoti, telemetria, tracker, richieste inattese e dati sensibili verificata
- [x] Test JavaScript, controlli statici, compileall, unittest, validazione casi e suite esistenti verdi
- [x] Verifica browser locale completata a 1440×900 e 390×844 in entrambe le lingue e in tutti i temi
- [x] Workflow GitHub Pages preparato ma non attivato né pubblicato prima dell'avallo
- [x] Versione `0.10.0` predisposta e sincronizzata nei punti canonici
- [x] README, manuali, SECURITY_MODEL, MAP, AGENTS e PLAN aggiornati e revisionati sul branch prima del merge
- [x] Diff completo, anteprima locale, asset derivati, test e limiti residui presentati al progettista
- [x] Approvazione esplicita del progettista ottenuta prima del primo commit
- [x] Commit autorizzati creati sul branch dedicato
- [x] Push e PR eseguiti soltanto dopo autorizzazione esplicita
- [x] CI verificata sul branch/PR (`36234009259`) e, dopo merge autorizzato, su `main` (`36234153770`)
- [x] Merge verso `main` eseguito soltanto dopo autorizzazione esplicita (`673bd85`)
- [x] Tag annotato `v0.10.0` creato dopo autorizzazione; GitHub Release intenzionalmente non prevista
- [x] Deploy GitHub Pages verificato all'URL pubblico dopo autorizzazione esplicita (`36234153769`)
- [x] Link della landing page, repository, release più recente, licenza e sito personale verificati sul sito pubblicato
- [x] Branch obsoleto eliminato soltanto dopo merge, CI, tag e deploy verificati

## Milestone 11 – Percorso rapido guidato del benchmark

- Obiettivo: offrire a chi non è a proprio agio con il terminale una procedura guidata, avviabile senza comporre comandi, che rilevi i modelli Ollama installati, esegua in sequenza il funnel `smoke` → `standard` → `full`, promuova automaticamente i modelli meglio classificati e apra infine la dashboard ufficiale sui tre run prodotti.
- Dipendenza: iniziare questa milestone soltanto dopo la chiusura e l'integrazione della milestone 10, perché la landing page realizzata in quella milestone dovrà essere aggiornata nello stesso branch per presentare il nuovo percorso rapido.
- Branch previsto: `milestone/11-guided-benchmark-funnel`
- Incremento versione: `+0.1.0`, da `0.10.0` a `0.11.0`, con tag previsto `v0.11.0`.
- Flusso funzionale: eseguire prima i controlli equivalenti a `doctor` e rilevare i modelli tramite l'adapter Ollama esistente; mostrare l'elenco rilevato e le impostazioni effettive prima della conferma di avvio; eseguire `smoke` su tutti i modelli locali selezionati, leggere la leaderboard ufficiale del relativo `report.json` e promuovere al massimo i primi quattro modelli classificabili; eseguire `standard` su questi candidati, quindi promuovere al massimo i primi due classificabili; eseguire `full` sui finalisti; costruire il dataset ridotto in memoria attraverso i componenti esistenti e aprire automaticamente la dashboard ufficiale con i run `smoke`, `standard` e `full`. Se una task fallisce ma il report della fase è completo e compatibile, escludere soltanto il modello interessato e proseguire con gli altri; se nessun modello è classificabile, interrompere il funnel con un messaggio chiaro e conservare gli artefatti già prodotti.
- Selezione e riproducibilità: riusare senza duplicarla la logica di ordinamento della leaderboard ufficiale, inclusi punteggio composito e tie-break esistenti; non promuovere modelli esclusi per integrità, controllo thinking non verificato, run incompleto o task fallita; registrare in un manifesto del percorso modelli scoperti e selezionati, directory dei run disponibili, seed, impostazioni effettive, graduatorie, motivi di esclusione e passaggi di selezione. I limiti predefiniti `4` e `2`, i profili e le altre opzioni modificabili devono stare nella configurazione centrale, essere validati all'avvio e non introdurre fallback silenziosi.
- Interfaccia e piattaforme: mantenere il core in moduli Python testabili e senza nuove dipendenze runtime; fornire un launcher sottile e documentato per l'avvio con doppio clic almeno su macOS e Windows, con il miglior equivalente ragionevole su Linux, senza richiedere all'utente di scrivere comandi. L'interfaccia deve mostrare stato corrente, modello/caso in esecuzione, avanzamento fra le tre fasi, directory dei risultati, tempi potenzialmente lunghi, errori e azione di annullamento; la tabella modelli deve essere ordinabile per nome, dimensione e thinking con direzione visibile e selezione preservata. Un'interruzione deve terminare in modo controllato i processi avviati e preservare i run completati o diagnosticabili, senza promuovere risultati parziali.
- Configurazione operativa: usare `benchmark.json` come fonte unica per endpoint Ollama, Pi, timeout, warmup, thinking, retry, sandbox e directory dei risultati; il percorso guidato deve mostrare almeno thinking e sandbox effettivi prima dell'avvio, mantenere il default ufficiale `thinking: off`, non degradare silenziosamente il sandbox e non aggirare preflight, snapshot, input puliti, hash, audit, unload/warmup o altri controlli già applicati dal runner.
- Esclusione della finalissima: il percorso rapido non deve eseguire il profilo `showcase`, non deve lanciare il caso `results_dashboard`, non deve chiedere ai modelli di creare una dashboard e non deve modificare o congelare `cases/results_dashboard/fixture/dashboard-data.json`; apre soltanto la dashboard ufficiale mantenuta dal progetto per analizzare i risultati del funnel.
- Sicurezza e privacy: invocare i processi con argomenti strutturati, senza interpolare nomi modello in comandi shell; restare su Ollama locale e sul server dashboard `127.0.0.1`; non introdurre rete Internet, telemetria o scritture fuori dalla root; applicare gli stessi controlli di path, input, sandbox, thinking e integrità della CLI; trattare `results/` e il manifesto del percorso come dati locali potenzialmente sensibili; richiedere conferma esplicita prima dell'avvio e prima di eventuali operazioni distruttive, senza cancellazioni automatiche dei run precedenti.
- Stati ed errori: distinguere prerequisiti mancanti, Ollama non raggiungibile, nessun modello rilevato, input Git sporchi, modello escluso, task fallita, fase senza candidati, annullamento utente e dashboard non avviabile; una task fallita esclude il modello interessato, mentre dati globalmente incompleti o incompatibili fermano il funnel. Al termine mostrare un riepilogo bilingue con promossi/esclusi, punteggi, percorsi relativi dei run e possibilità di aprire senza rerun da uno a tre run disponibili, senza presentare un funnel parziale come completato.
- Criteri di accettazione: da un checkout valido l'utente avvia il percorso senza digitare comandi; vede, ordina e conferma i modelli Ollama locali e le impostazioni; lo `smoke` usa il set selezionato, lo `standard` riceve esattamente i primi quattro classificabili o meno se non disponibili e il `full` riceve esattamente i primi due classificabili o meno se non disponibili; ogni fase usa una directory distinta e verificabile; modelli con task fallite vengono esclusi senza bloccare i modelli validi; esclusioni e interruzioni non vengono reinterpretate come successi; la dashboard ufficiale si apre con i tre run prodotti e, dopo un arresto, può mostrare i soli run disponibili; nessuna task `results_dashboard` e nessun run `showcase` vengono creati; il flusso funziona almeno su macOS e Windows e degrada con un messaggio documentato quando un prerequisito di piattaforma manca.
- Test richiesti: unit test per discovery, configurazione, macchina a stati, ordinamento tabella, selezione top 4/top 2, tie-break, meno candidati del limite, leaderboard vuota, esclusioni d'integrità/thinking/task fallita, run parziale, annullamento e costruzione sicura degli argomenti; integration test con adapter e runner simulati per verificare ordine delle fasi, directory distinte, provenienza e apertura dashboard completa o parziale; test negativi per nomi modello ostili, path non confinati, output esistente, Ollama/Pi indisponibili e input protetti sporchi; smoke manuale del launcher su macOS e Windows, e su Linux quando disponibile; verifica browser della dashboard finale, funnel e assenza di richieste remote; esecuzione di `python3 -m compileall -q benchmark.py dashboard.py guided_benchmark.py src cases tests`, `python3 -m unittest discover -s tests -v`, suite JavaScript, validazione di tutti i casi e CI multipiattaforma.
- Landing page: aggiungere una sezione bilingue “Percorso rapido / Quick path” che descriva rilevamento automatico, selezione progressiva `tutti` → `4` → `2`, durata indicativa non garantita, risultati locali e apertura della dashboard; chiarire che il metodo riduce il lavoro sui modelli meno promettenti ma non altera punteggi o controlli e non include la finalissima in cui i modelli costruiscono una dashboard. Aggiornare call to action, quick start e link senza introdurre download o capacità non realmente distribuiti.
- Documentazione: creare un quick start bilingue dedicato al percorso guidato e aggiornare `README.md`, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md`, la documentazione della dashboard, la landing page e questo piano; documentare installazione/prerequisiti, avvio per piattaforma, selezione automatica, configurazione, tempi attesi, arresto, ripresa o riapertura dei risultati, troubleshooting, privacy e limiti. Tutti gli aggiornamenti documentali devono essere completati e revisionati sul branch prima dell'approvazione al merge.
- Release: milestone funzionale rilasciabile come `v0.11.0`, con GitHub Release prevista; verificare il tipo di distribuzione effettivamente disponibile e non promettere launcher o artifact binari non prodotti. Se vengono distribuiti nuovi artifact, generarli per le piattaforme supportate, verificarli fuori dal checkout e pubblicare checksum SHA-256, documentando chiaramente l'assenza di firma quando applicabile.
- Gate di approvazione: all'avvio dell'implementazione creare il branch dedicato e mantenere le modifiche non committate per la verifica del progettista. Prima dell'avallo esplicito sono vietati il primo commit e ogni commit successivo, push, apertura PR, merge, tag, GitHub Release, pubblicazione di artifact, deploy della landing aggiornata e rimozione del branch. Dopo implementazione, test, smoke multipiattaforma e aggiornamento completo della documentazione, presentare diff, procedura locale, risultati, artefatti e limiti residui; procedere con ciascuna operazione soltanto nell'ambito autorizzato dal progettista.
- Stato: **milestone chiusa, integrata e pubblicata il 2026-09-26. Il percorso reale `results/guided-20260926-135428-71b453` è terminato con stato `completed`: sei modelli nello `smoke`, due candidati validi promossi a `standard`, gli stessi due promossi a `full` e dashboard ufficiale aperta sui tre run distinti. La landing presenta il percorso guidato con un fotogramma revisionato e ottimizzato derivato da `assets/Guided.mov`; i video sorgente restano locali e ignorati. Compileall, 136 test Python con 12 skip ambientali attesi, 15 test Node e i 6 casi sono verdi. Landing e dashboard reale sono state verificate in browser a 1440×900 e 390×844, in italiano/inglese e nei temi automatico/chiaro/scuro, con tastiera, focus, assenza di overflow, console pulita e sole richieste locali. Il launcher e il funnel reali sono verificati su macOS; i launcher Windows/Linux restano coperti da test automatici e documentazione, senza smoke GUI reale in questa sessione. La PR #5 è stata integrata con merge commit `51dbbac`; la CI è verde su macOS, Ubuntu e Windows sia sulla testa finale della PR (`36245709518`) sia su `main` (`36245909299`). Il workflow Pages `36245909341` ha pubblicato la landing aggiornata: il percorso rapido e l'asset WebP rispondono correttamente sul dominio pubblico. Il tag annotato `v0.11.0` e la GitHub Release stabile sorgente sono pubblicati senza artifact binari di progetto, quindi non si applicano checksum di artifact; il branch milestone è stato eliminato dal remoto e in locale dopo le verifiche.**

### Checklist milestone 11

- [x] Milestone 10 chiusa e integrata prima dell'avvio
- [x] Branch `milestone/11-guided-benchmark-funnel` creato senza commit iniziali non autorizzati
- [x] Flusso UX, configurazione e criteri di promozione revisionati
- [x] Core di orchestrazione modulare implementato senza nuove dipendenze runtime
- [x] Launcher senza composizione manuale di comandi disponibile per macOS e Windows; comportamento Linux documentato
- [x] Discovery dei modelli Ollama e riepilogo delle impostazioni effettive verificati
- [x] Preflight e controlli esistenti riusati senza bypass o fallback silenziosi
- [x] Run `smoke` reale eseguito su sei modelli selezionati nel funnel completo `guided-20260926-135428-71b453`
- [x] Fino a 4 classificabili promossi automaticamente allo `standard`, verificato nell'integrazione simulata e con 2 candidati nel run reale
- [x] Fino a 2 classificabili promossi automaticamente al `full`, verificato nell'integrazione simulata e con 2 candidati nel run reale
- [x] Limiti inferiori, nessun candidato, errori, esclusioni e annullamento gestiti senza falsi successi
- [x] Manifesto del percorso con provenienza, seed, graduatorie e selezioni prodotto e validato nei test di integrazione
- [x] Profili `showcase` e caso `results_dashboard` esclusi dal percorso e fixture della finalissima non modificata
- [x] Dashboard ufficiale aperta sui tre run distinti con funnel coerente e confermata dal progettista
- [x] Dashboard diagnostica parziale verificata sul run `smoke` reale (`run_count=1`, profilo `smoke`)
- [x] Riepilogo bilingue finale e riapertura della dashboard senza rerun verificati automaticamente
- [x] Test unitari e di integrazione del percorso guidato verdi
- [x] Compileall, unittest, test JavaScript e validazione completa dei casi verdi
- [x] Smoke manuale del launcher e funnel reale completati su macOS; Windows/Linux coperti da test automatici e documentati come limite della verifica manuale corrente
- [x] Dashboard finale verificata in browser per funnel, accessibilità di base, console, overflow e assenza di richieste remote
- [x] Landing page aggiornata con la sezione bilingue “Percorso rapido / Quick path” e call to action coerenti
- [x] Quick start dedicato, README, manuali, SECURITY_MODEL, MAP, AGENTS, documentazione dashboard e PLAN aggiornati sul branch prima del merge
- [x] Versione `0.11.0` predisposta e sincronizzata in tutti i punti canonici
- [x] Diff completo, procedura locale, risultati dei test, artifact e limiti residui presentati al progettista
- [x] Approvazione esplicita del progettista ottenuta prima del primo commit locale (2026-09-26)
- [x] Commit locali `6ea9f3d`, `59a8309`, `da7d9c4` e `0bd9351`, insieme alle operazioni remote finali, autorizzati esplicitamente dal progettista il 2026-09-26
- [x] Push e PR #5 eseguiti soltanto dopo autorizzazione esplicita
- [x] CI verificata sul branch/PR su macOS, Ubuntu e Windows (`36245709518`)
- [x] CI verificata su `main` dopo il merge autorizzato (`36245909299`)
- [x] Merge verso `main` eseguito soltanto dopo autorizzazione esplicita (`51dbbac`)
- [x] Tag annotato `v0.11.0` e GitHub Release creati soltanto dopo autorizzazione esplicita
- [x] Release sorgente senza artifact binari di progetto; checksum di artifact non applicabili
- [x] Landing aggiornata pubblicata e verificata soltanto dopo autorizzazione esplicita (`36245909341`)
- [x] Branch obsoleto eliminato soltanto dopo merge, CI, tag, release e deploy verificati

## Patch 0.11.1 – Gerarchia dei percorsi nella landing

- Obiettivo: distinguere chiaramente il percorso rapido guidato dal flusso avanzato a terminale e rendere immediatamente riconoscibili prerequisiti e documentazione utente.
- Branch: `patch/0.11.1-landing-content`.
- Incremento versione: `+0.0.1`, da `0.11.0` a `0.11.1`, con tag previsto `v0.11.1` soltanto dopo verifica locale e nuova approvazione del progettista.
- Attività: rinominare la sezione 06 in “Full immersion”; descrivere l'esecuzione separata di `smoke`, `standard` e `full`, le opzioni e i casi personalizzati e la finalissima `showcase`; aggiungere prima della documentazione una sezione “Inizia” con requisiti e accessi; limitare la sezione documentale ai manuali e ai quick start, mostrando il solo manuale coerente con la lingua attiva; allineare la tipografia delle etichette di sezione; rendere il menu coerente con tutte le otto sezioni e compattare lingua e tema in controlli grafici; aggiornare test, mappa, versione e questo piano.
- Criteri di accettazione: “Percorso rapido” e “Full immersion” non sono presentati come sinonimi; i comandi mostrano profili, opzioni, casi personalizzati e `showcase` senza omettere il requisito del dataset congelato; “Inizia” contiene Python, Ollama, Pi e checkout Git pulito; in italiano è visibile soltanto `ISTRUZIONI.md`, in inglese soltanto `INSTRUCTIONS.md`; README, `SECURITY_MODEL.md`, `MAP.md` e `PLAN.md` non compaiono nella griglia pubblica della documentazione; le etichette 06 e 07 conservano dimensione e colore comuni alle altre sezioni; il menu riprende nell'ordine le otto voci della landing senza andare a capo sui desktop ampi; lingua `ITA/ENG` e tema automatico/sole/luna restano accessibili da tastiera e persistenti.
- Test: test statici Python e Node della landing, suite Python completa, compileall, validazione dei casi e verifica browser locale desktop/mobile in entrambe le lingue e nei temi chiaro/scuro; CI multipiattaforma soltanto dopo il push autorizzato.
- Documentazione: aggiornare README per versione e asset della landing, MAP per la nuova gerarchia e PLAN per il workflow della patch; `SECURITY_MODEL.md` resta invariato perché non cambiano rete, dati, storage, CSP o superfici operative.
- Release: patch sorgente `v0.11.1`; GitHub Release esplicitamente autorizzata dal progettista il 2026-09-26.
- Stato: **patch chiusa, integrata e pubblicata il 2026-09-26. La PR #6 è stata integrata con merge commit `a277f63`; la CI è verde su macOS, Ubuntu e Windows sia sulla testa finale della PR (`36251652936`) sia su `main` dopo il merge (`36251839491`). Il workflow Pages `36251839489` ha pubblicato la landing aggiornata. Il tag annotato `v0.11.1` e la GitHub Release sorgente sono stati autorizzati esplicitamente dal progettista e pubblicati nel workflow di chiusura; non essendoci artifact binari di progetto, i checksum di artifact non sono applicabili. Il branch remoto è stato eliminato automaticamente dopo il merge e quello locale è stato rimosso dopo le verifiche.**

### Checklist patch 0.11.1

- [x] Branch dedicato creato da `main` pulito
- [x] Sezione 06 trasformata in “Full immersion” con profili, opzioni, casi personalizzati e finalissima
- [x] Nuova sezione “Inizia” aggiunta prima della documentazione
- [x] Griglia documentale limitata a istruzioni e quick start, con manuale filtrato per lingua
- [x] Versione `0.11.1`, README, MAP, test e PLAN aggiornati
- [x] Test automatici e verifica browser locale completati
- [x] Commit locale creato per la verifica del progettista
- [x] Correzione tipografica 06/07, menu completo e controlli compatti lingua/tema verificati
- [x] Commit di revisione creato dopo il feedback del progettista
- [x] Verifica locale e approvazione esplicita del progettista ottenute (2026-09-26)
- [x] Push e PR #6 eseguiti soltanto dopo approvazione
- [x] CI verificata sulla testa finale della PR (`36251652936`) e su `main` dopo il merge (`36251839491`)
- [x] Merge PR #6 (`a277f63`) e deploy Pages (`36251839489`) completati e verificati
- [x] Tag annotato `v0.11.1` creato e pubblicato nel workflow di chiusura autorizzato
- [x] GitHub Release sorgente autorizzata e pubblicata; nessun artifact binario, checksum non applicabili
- [x] Branch remoto eliminato automaticamente dopo il merge e branch locale eliminato dopo tutte le verifiche previste

## C12 – Compatibilità Pi verificata all'avvio

- Obiettivo: consentire l'uso di versioni Pi diverse dalla `0.85.1` quando soddisfano il contratto operativo del benchmark, sostituendo il vincolo sulla versione con un test locale obbligatorio prima di ogni benchmark, sia da riga di comando sia dal percorso semplice con UI avviata tramite script.
- Dipendenza: `main` e il checkpoint remoto precedente verificati al commit `174d7e7` prima di creare il branch dedicato.
- Branch previsto: `milestone/12-pi-runtime-compatibility`.
- Tag di checkpoint previsto: `milestone/C12`, sul commit finale di `main` dopo approvazione e merge.
- Incremento versione: `+0.1.0`, dalla versione corrente `0.11.1` a `0.12.0`, con tag versione previsto `v0.12.0`.
- Attività principali:
  - Estrarre dal test contrattuale esistente un servizio modulare, senza nuove dipendenze runtime, che avvii il comando Pi effettivamente configurato contro un server OpenAI-compatible fittizio su `127.0.0.1`, con dati sintetici, directory isolata, timeout espliciti, cancellazione e cleanup. Il probe non deve contattare Internet o modelli reali, leggere contenuti utente o usare la configurazione personale di Pi.
  - Verificare sul payload reale i livelli thinking richiesti, inclusi `off` canonicalizzato in `reasoning_effort: "none"` e una modalità attiva, il limite token, il formato degli eventi necessario al runner, il riconoscimento degli errori terminali e l'assenza di retry automatici. Non limitarsi a leggere `pi --version` e non saltare il test perché la versione installata è diversa dalla `0.85.1`.
  - Riutilizzare lo stesso servizio in `doctor` e nel gate del runner prima di warmup e task, per tutti i profili e per `--cases`; eliminare i blocchi basati esclusivamente sull'elenco di versioni ammesse. Il percorso guidato deve mostrare il controllo nella UI e mantenere il gate anche nei processi CLI delle fasi `smoke`, `standard` e `full`, senza introdurre percorsi alternativi che lo aggirino.
  - Verificare separatamente i requisiti del backend sandbox selezionato, in particolare marker, staging e adattamento del bundle Pi su Windows: un payload compatibile non certifica da solo la compatibilità AppContainer. Conservare i probe del backend, il fallimento di `required` e la segnalazione esplicita del fallback di `auto`.
  - In caso di incompatibilità o verifica non conclusiva, fermare il benchmark prima delle task e mostrare in italiano/inglese requisito fallito, versione rilevata e indicazioni utili. Consigliare Pi `0.85.1` come versione di riferimento già verificata, senza installarla automaticamente, senza bypass e senza presentarla come rimedio garantito per problemi estranei a Pi.
  - Registrare versione effettiva Pi, versione del contratto, esito e metadata diagnostici sanitizzati del probe; escludere probe da tempi, token e punteggi delle task. Conservare la distinzione dal preflight thinking per-modello su Ollama, che resta obbligatorio. Mantenere il rifiuto di aggregazioni statistiche tra versioni Pi o contratti incompatibili e la lettura degli artefatti legacy; non esportare diagnostica libera o payload tramite `dashboard-data`.
- Estensione richiesta durante la prova M12: aggiungere al percorso rapido toggle per thinking `off`/`medium` e sandbox `audit`/`required`, applicati a tutte le fasi senza fallback; mostrare nel Dettaglio task della dashboard le esclusioni per thinking osservato con `off` e per violazioni dei confini workspace/rete, separate dalle task realmente eseguite e senza esportare evidenze raw.
- Criteri di accettazione: una versione diversa dalla `0.85.1` che supera il contratto e i controlli applicabili può eseguire il benchmark; anche la `0.85.1` deve superare il test; CLI, selezioni personalizzate e UI avviata dai launcher applicano lo stesso gate prima delle task; errori, timeout, eventi incompatibili, retry inattesi e controllo non verificabile impediscono l'avvio con diagnostica comprensibile; la UI resta reattiva e consente l'annullamento; nessuna metrica task include il probe; nessuna garanzia thinking, sandbox, integrità o riproducibilità viene ridotta.
- Test richiesti: unit test e integrazione con Pi simulato per versioni differenti compatibili/incompatibili, payload errati, eventi corrotti, errori terminali, retry, timeout, cancellazione e cleanup; regressione sul comando Pi configurato; test reali con server fittizio su Pi `0.85.1` e sulla versione aggiornata disponibile, registrando versioni ed eventuali limiti ambientali; test del gate su CLI, tutti i profili e `--cases`, orchestrazione guidata e launcher; regressioni sandbox multipiattaforma, inclusa la compatibilità del bundle Windows; smoke Pi/Ollama da CLI e UI sulle piattaforme disponibili. Eseguire `python3 -m unittest discover -s tests -v` e `python3 -m compileall -q benchmark.py dashboard.py guided_benchmark.py src cases tests`; riportare test non eseguiti e motivi. Usare GitHub Actions soltanto per verifiche necessarie non sostituibili adeguatamente in locale.
- Documentazione da aggiornare: `README.md`, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, quick start CLI/percorso guidato e piattaforme interessate, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md`, istruzioni pubbliche sotto `site/` e `PLAN.md`. Sostituire nella stessa milestone la regola che impone Pi `0.85.1`, documentando contratto, probe, dati trattati, costi di avvio, troubleshooting e limiti per piattaforma; sincronizzare la versione nei punti canonici.
- Release: funzionalità rilasciabile come `v0.12.0`; GitHub Release prevista dopo approvazione esplicita. Artifact e checksum SHA-256 soltanto se vengono effettivamente distribuiti pacchetti; nessuna installazione o modifica automatica di Pi.
- Stato: **milestone 0.12.0 integrata e pubblicata dopo autorizzazione esplicita del progettista il 2026-10-17. La PR #8 è stata integrata su `main` con merge commit `7da765e`; CI della PR `39063684815` e CI post-merge `39063915231` verdi su macOS, Ubuntu e Windows. Il controllo contrattuale locale accetta Pi 1.0.4 in `audit` e Seatbelt `required`; lo smoke CLI e i batch guidati dell’utente hanno verificato il percorso reale. I toggle thinking/sandbox e il Dettaglio task della dashboard mostrano le esclusioni senza esportare eventi sensibili. L’audit v4 corregge il falso positivo di traversal nello scratch: la rilettura dei vecchi eventi elimina i 2 rilievi di Julioa/qwen3.8 e conserva i 4 tentativi esterni di qwen3.5. La suite locale ha eseguito 147 test Python (18 skip ambientali), 17 test JavaScript, `compileall` e la validazione dei 6 casi; Pages `39063914901` è verde e l’asset pubblico coincide con quello locale. Tag annotati `milestone/C12` e `v0.12.0` pubblicati sul commit documentale finale di `main`; GitHub Release sorgente pubblicata senza binari né checksum di artifact applicabili, e branch milestone rimosso. Limiti residui: Pi 0.85.1 e smoke reali Windows/Linux con Pi aggiornato non disponibili su questo host; gli errori di stream di gpt-oss e il timeout di Julioa/qwen3.8 restano esiti del run, non corretti dalla milestone.**

### Checklist chiusura M12

- [x] `main` remoto verificato al commit `174d7e7`; branch dedicato creato da quel commit
- [x] Servizio contrattuale condiviso implementato e vincolo sulla versione rimosso
- [x] Gate obbligatorio verificato su CLI e orchestrazione UI tramite test e rilevamento reale; launcher GUI avviato, verifica visiva non conclusa per timeout dello strumento UI
- [x] Diagnostica bilingue e suggerimento Pi `0.85.1` verificati
- [x] Thinking, retry, eventi e sandbox macOS verificati; staging Windows coperto da test strutturali, smoke reale Windows pendente
- [x] Test automatici e validazione dei casi eseguiti; smoke Pi 1.0.4/Seatbelt e `doctor` riusciti; limiti ambientali registrati nello stato
- [x] Versione, README, manuali, quick start, SECURITY_MODEL, MAP, AGENTS e istruzioni pubbliche aggiornati
- [x] Commit locali creati soltanto sul branch dedicato e non pubblicati prima del controllo
- [x] Branch congelato al commit `c5d1f7e`, con hash, diff, test, esiti e limiti presentati al progettista; il successivo fix portabile `0269e12` è stato verificato dalla CI della PR
- [x] Approvazione esplicita del progettista per commit, merge, tag, push, release e rimozione branch ricevuta il 2026-10-17; fix CI successivo documentato e verificato
- [x] PR #8, merge commit `7da765e`, CI multipiattaforma sulla PR e su `main` e deploy Pages verificati
- [x] Voce rinominata `C12` con riepilogo, verifiche, limiti residui, versione `0.12.0` e checkpoint `milestone/C12`
- [x] Tag annotati `milestone/C12` e `v0.12.0` creati sul commit finale di `main`; push di `main` e tag verificati sul remoto
- [x] GitHub Release `v0.12.0` sorgente pubblicata e verificata; nessun artifact binario di progetto o checksum applicabile
- [x] Branch milestone locale eliminato dopo release e verifiche; branch remoto rimosso automaticamente da GitHub dopo il merge

## Patch 0.12.1 – Aggiornamento dell'azione setup-node

- Obiettivo: mantenere i workflow CI e Pages sulla versione revisionata di `actions/setup-node`, conservando il pin a commit e il supporto a Node 24.
- Branch di release: `patch/0.12.1-setup-node`, creato dal merge della PR Dependabot #7 su `main`.
- Incremento versione: `+0.0.1`, da `0.12.0` a `0.12.1`; tag previsto `v0.12.1`.
- Attività: integrare la PR Dependabot #7 (`actions/setup-node` 7.0.0 → 7.1.0) dopo verifica del tag upstream e della CI; sincronizzare versione, README, guida rapida e test; pubblicare una release sorgente come richiesto dal progettista.
- Criteri di accettazione: entrambi i workflow usano lo SHA ufficiale `949feb2413d6458794dcd2491c4babbbce0c15c1`; CI su macOS, Windows e Ubuntu e deploy Pages riescono dopo il merge; versione e tag coincidono; nessuna dipendenza runtime o comportamento del benchmark cambia.
- Test: CI della PR aggiornata, CI e Pages su `main`, suite locale Python, compilazione e validazione dei casi; verificare la release e l'archivio sorgente.
- Documentazione: `README.md`, `QUICK-START_Guided.md` e `PLAN.md`. Nessuna modifica a sicurezza, struttura, comandi o regole operative.
- Release: `v0.12.1` sorgente, autorizzata esplicitamente dal progettista; nessun binario di progetto o relativo checksum.
- Stato: **PR #7 integrata al commit `fd05d63`; SHA upstream verificato. CI sulla PR aggiornata (`39066068492`) e su `main` (`39066608772`) verde su macOS, Windows e Ubuntu; Pages post-merge (`39066608797`) verde. La patch `0.12.1` ha superato 147 test Python (18 skip ambientali), `compileall` e la validazione dei 6 casi; è pronta per il controllo del progettista sul commit locale. Tag e release non sono ancora stati creati.**

## C13 – Provider locali alternativi

- Obiettivo: eseguire lo stesso benchmark Pi su Ollama, LM Studio e router `llama-server` con GGUF locali, conservando controlli, isolamento e provenienza. `node-llama-cpp` resta una libreria utilizzabile tramite un futuro bridge HTTP dedicato, senza introdurre una dipendenza runtime oggi.
- Branch: `milestone/13-local-providers`.
- Incremento versione: `+0.1.0`, da `0.12.1` a `0.13.0`; tag `v0.13.0` e release sorgente soltanto dopo approvazione, CI e smoke reali.
- Attività: configurazione `provider` retrocompatibile con `ollama`; adapter LM Studio v1 e llama.cpp router; discovery, capability, caricamento, preflight thinking e warmup; provider Pi isolato per task e nel probe contrattuale sintetico; trasporto loopback unico nei backend sandbox; versione runtime dichiarata e hash SHA-256 dei GGUF opzionali per singolo run e obbligatori per l'aggregazione; confronto separato per provider/endpoint/versione/hash; percorso guidato e testi bilingui aggiornati; manuali, quick start, sicurezza, mappa, landing e test.
- Criteri di accettazione: `doctor`, `list` e `run` selezionano un solo provider senza rete esterna; Pi supera il contratto con l'ID selezionato; `off` rifiuta reasoning osservabile e le modalità attive senza segnale non entrano in classifica; `required` inoltra soltanto alla porta configurata; LM Studio e router caricano/scaricano il modello selezionato; Pi riceve sempre una directory isolata; `compare` rifiuta coorti diverse o run alternativi privi di provenienza; la GUI applica lo stesso percorso; i vecchi run Ollama restano leggibili.
- Test richiesti: unit e integrazione HTTP fittizia per discovery, load/unload, preflight, payload e risposte ostili; test config/CLI/GUI/comparison e Pi reale contro server sintetico sui tre ID provider; suite Python, `compileall`, validazione dei casi, suite Node e verifica browser della landing; smoke con LM Studio e llama.cpp reali su host disponibili e CI multipiattaforma prima del merge.
- Documentazione: `README.md`, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, `QUICK-START_Guided.md`, `QUICK-START_LocalProviders.md`, `SECURITY_MODEL.md`, `MAP.md`, `AGENTS.md`, landing bilingue e questo piano.
- Stato: **funzionalità integrata in `main` tramite PR #10, merge commit `5de1d1a`. L'approvazione del commit `1439540` ha preceduto push e merge. La CI della PR (`39321099461`) e quella su `main` (`39321684758`) sono verdi su macOS, Windows e Ubuntu; Pages (`39321684586`) ha pubblicato la landing bilingue e la pagina pubblica mostra Ollama, LM Studio, llama.cpp e la guida dedicata. Su macOS sono passati 167 test Python con 5 skip ambientali, 17 test Node, `compileall`, validazione dei sei casi e `git diff --check`. Il probe Pi sintetico è riuscito per tutti e tre gli ID provider; lo smoke LM Studio ha prodotto due modelli classificabili e un percorso guidato llama.cpp ha completato smoke, standard e full con integrità e thinking verificati. La qualità dei GGUF provati resta un limite: Mistral 7B non ha superato 60/100 in alcuna delle cinque task full e Gemma 4 è andato in timeout nello smoke. Mancano un funnel LM Studio completo e smoke reali dei nuovi provider su Windows/Linux; su Windows manca anche uno smoke reale dopo la correzione del timeout Pi. Versione `0.13.0`; checkpoint previsto `milestone/C13` e tag di release `v0.13.0` sul commit finale di `main`, con GitHub Release sorgente senza artifact binari né checksum di artifact applicabili.**
- Verifica Windows 2026-10-19: il run guidato Pi/Ollama `guided-20261019-141243-725fbd` è stato annullato dopo che `qwen3:4b` ha superato il limite di 1.200 s in `targeted_patch`; il launcher Pi terminato lasciava il processo Node e la pipe aperti. Il runner ora assegna il processo Pi a un Job Object Windows kill-on-close quando disponibile, termina l'albero in fallback e limita la raccolta finale dell'output. Due regressioni con processi figli e un test del drain passano; passano anche 55 test mirati di adapter, compatibilità, runner e percorso guidato e `compileall`. La suite completa locale ha eseguito 162 test: 4 failure e 3 error restano legati a `spawn EPERM` di Node, AppContainer negato dal sandbox e contratto del Pi 0.84.3 installato; 7 test sono skip ambientali. Serve ancora uno smoke reale dopo la correzione e la CI multipiattaforma.
- Verifica macOS 2026-10-19: lo smoke guidato LM Studio `guided-20261019-194500-c4d58d` ha prodotto due modelli classificabili, senza completare l'intero funnel. I run llama.cpp `guided-20261019-203147-313097` e `guided-20261019-203204-2c59f7` hanno escluso entrambi i modelli nel preflight: `/models/load` rispondeva prima che i processi figli fossero pronti. Il router 0.5.0 ha impiegato circa 17 s per portare Mistral a `loaded`. L'adapter attende ora tale stato entro il timeout e fallisce chiuso su errore o scadenza; i preflight reali `off` di Mistral 7B e Gemma 4 passano. La suite completa macOS passava con 164 test e 5 skip ambientali; lo smoke guidato llama.cpp restava da eseguire.
- Verifica macOS 2026-10-19, secondo smoke llama.cpp: il run guidato `guided-20261019-204556-792411` ha superato il preflight per entrambi i modelli, ma si è concluso con `no_candidates`. Mistral 7B è stato escluso per errore di caricamento prima della task: il router conferma `/models/unload` quando il modello è ancora `loaded`, poi rifiuta il nuovo `/models/load` con HTTP 400. Gemma 4 ha eseguito 11 chiamate agli strumenti, di cui 5 fallite (quattro `edit` senza il parametro obbligatorio `path`), senza modificare la fixture; la task è terminata per timeout a 300 s e il suo punteggio tecnico è 25/100, non classificabile. L'adapter ora attende anche `unloaded` con timeout esplicito: una prova reale di due cicli consecutivi di load/unload di Mistral è riuscita. Restano da ripetere lo smoke completo con la correzione e la verifica della capacità dei modelli di completare la task.
- Verifica macOS 2026-10-19, dopo la correzione: lo smoke mirato `20261019-214652` ha caricato Mistral e completato `targeted_patch` in 138,5 s senza violazioni d'integrità, ma con 25/100 e nessuna chiamata agli strumenti, sotto la soglia di completamento di 60/100. Sono passati 166 test Python con 5 skip ambientali, `compileall` e `git diff --check`. La correzione del router è verificata; uno smoke guidato completo con entrambi i modelli resta da ripetere. Nessuno dei due GGUF usati ha finora dimostrato di completare la task smoke sopra soglia.
- Verifica macOS 2026-10-19, percorso guidato dopo la correzione: `guided-20261019-215751-4e0bd7` è `completed` dopo smoke, standard e full. Tutte le fasi riportano integrità e controllo thinking `passed`, senza violazioni; Mistral 7B è stato promosso da smoke e standard perché le sue task hanno stato `ok`, mentre Gemma 4 è stata esclusa dallo smoke per timeout. Mistral non ha usato strumenti né modificato le fixture: in full le cinque task hanno ottenuto 20, 15, 22, 25 e 5 punti su 100; la qualità media è 17,14/100 e la completion rate sopra soglia è 0/5. Il percorso tecnico funziona, ma questo GGUF non ha dimostrato capacità utile sulle task. Al momento del run restavano da verificare le piattaforme/CI previste per M13.
- Verifica landing macOS 2026-10-19: l'hero presenta i tre provider e la guida dedicata, sincronizzati in italiano e inglese. Test Python e Node della landing verdi; anteprima browser verificata a 1440×900 e 390×844 in italiano/inglese, temi automatico, chiaro e scuro, menu mobile e ritorno del focus con Escape. Nessun overflow orizzontale, errore console o richiesta runtime fuori da `127.0.0.1`. Suite completa: 167 test Python, 5 skip ambientali; 17 test Node; `compileall`, 6 casi validi e `git diff --check` verdi.

### Checklist chiusura C13

- [x] Branch dedicato creato da `main` pulito
- [x] Adapter, configurazione, percorso guidato e confronto implementati
- [x] Test unitari e probe Pi sintetico aggiunti
- [x] Test mirati, suite JavaScript, compilazione e validazione dei casi eseguiti
- [x] Versione e documentazione predisposte sul branch
- [x] Installazione e verifica Windows di Pi, Ollama, LM Studio e llama.cpp documentate in italiano e inglese
- [x] Suite locale completa e validazione dei casi verdi su macOS; CI su macOS, Windows e Ubuntu dopo il push autorizzato
- [x] Smoke reali LM Studio e llama.cpp sui sistemi disponibili (esiti e limiti registrati sopra)
- [x] Verifica browser landing desktop/mobile, lingue, temi e richieste di rete
- [x] Revisione del diff e avallo esplicito del progettista sul commit `1439540`
- [x] Commit finale locale creato sul branch dedicato e congelato per la revisione
- [x] PR #10, CI multipiattaforma e merge autorizzato verificati
- [x] CI su `main` e deploy Pages verificati
- [ ] Revisione e avallo esplicito del commit finale del verbale C13 prima di pubblicarlo
- [ ] Tag `milestone/C13` e `v0.13.0`, release sorgente e branch cleanup verificati

## Patch 0.13.1 – Gerarchia della landing per i provider locali

- Obiettivo: riportare l'introduzione del benchmark e i tre accessi principali in apertura, spostando la novità di Ollama, LM Studio e llama.cpp in una sezione autonoma prima del punto 01.
- Branch: `patch/0.13.1-landing-provider-news`.
- Incremento versione: `+0.0.1`, da `0.13.0` a `0.13.1`; tag previsto `v0.13.1` dopo merge e CI su `main`.
- Attività: rimuovere richiamo e riquadro provider dall'hero, aggiungere voce di navigazione e sezione «Novità», mantenere i dizionari italiano/inglese sincronizzati, aggiornare documentazione e test statici.
- Criteri di accettazione: titolo, descrizione e pulsanti repository/release/percorso rapido precedono la sezione «Novità»; i tre provider e la guida sono leggibili nella nuova sezione; il punto 01 segue la novità; desktop e mobile restano accessibili, senza overflow o richieste runtime remote.
- Test: test Python e JavaScript della landing, verifica browser a 1440×900 e 390×844 in entrambe le lingue e nei temi automatico/chiaro/scuro, tastiera/focus, console e rete; compilazione Python e `git diff --check`.
- Documentazione: `README.md`, `ISTRUZIONI.md`, `INSTRUCTIONS.md`, `QUICK-START_Guided.md`, `MAP.md` e questo piano. `SECURITY_MODEL.md` resta invariato perché non cambiano CSP, rete, storage o superfici operative.
- Release: tag sorgente `v0.13.1`; nessuna GitHub Release richiesta per questa patch ordinaria.
- Stato: **layout e documentazione approvati dal progettista il 2026-10-20, con autorizzazione esplicita a commit, merge, tag, push e rimozione del branch. Sono riusciti 167 test Python (7 skip ambientali), inclusi i 9 test statici della landing e i test JavaScript, `compileall`, la validazione dei 6 casi e `git diff --check`; lo smoke HTTP degli asset principali ha restituito 200. La verifica visiva a 1440×900 e 390×844 nelle due lingue e nei tre temi non è stata possibile: il browser integrato non è disponibile. Chiusura remota in corso.**
