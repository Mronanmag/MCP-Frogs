# Prompt de passation — MCP-Frogs

> Document destiné à une nouvelle équipe prenant en main le projet.
> Objectifs : comprendre rapidement le projet, identifier les problèmes, prioriser les correctifs.

---

## 1. Contexte et objectif du projet

**MCP-Frogs** est un serveur [MCP (Model Context Protocol)](https://modelcontextprotocol.io) qui permet à un LLM (Claude) d'orchestrer le pipeline bioinformatique **FROGS** de façon conversationnelle.

**FROGS** (Find Rapidly OTUs with Galaxy Solution) est un pipeline de métagénomique amplicon (16S / ITS / 18S) composé de **28 scripts Python séquentiels**, chacun pouvant durer de quelques minutes à plusieurs heures. Ces scripts sont des outils externes non modifiables.

**Ce que fait MCP-Frogs :**
- Expose 14 outils MCP à Claude (soumission de jobs, suivi, orchestration pipeline)
- Lance les scripts FROGS en arrière-plan via `subprocess.Popen` (non-bloquant)
- Suit l'état des jobs dans une base SQLite (thread daemon `JobPoller`)
- Résout automatiquement les fichiers d'entrée/sortie entre étapes via un graphe de flux (`FLOW_RULES` — 34 règles encodées dans `pipeline.py`)
- Persiste l'état de l'analyse entre sessions

**Cas d'usage concret :** L'équipe tente d'analyser un jeu de données réel (projet AQUALEHA, 83 paires de fichiers FASTQ Illumina pour surveillance qualité de l'eau) via conversation avec Claude.

---

## 2. Stack technique

| Composant | Technologie | Version |
|---|---|---|
| Serveur MCP | Python + FastMCP | 3.11 / mcp[cli] 1.9.4 |
| Scripts FROGS | Python | **3.7 strictement** (contrainte bioconda) |
| Persistance | SQLite (stdlib) | WAL mode |
| Transport HTTP | Starlette + uvicorn | — |
| Conteneurisation | Docker + Docker Compose | — |
| Environnements conda | micromamba 2.0.8 | — |
| Client LLM | Claude Code CLI | 2.1.63 |

**Deux environnements Python coexistent dans le même conteneur Docker :**
- `mcp_frogs` (Python 3.11) : fait tourner le serveur MCP
- `frogs` (Python 3.7) : fait tourner les scripts FROGS

---

## 3. Architecture des fichiers

```
MCP-Frogs/
├── .mcp.json                    # Config MCP — ATTENTION: pointe vers URL Docker interne
├── docker/
│   ├── Dockerfile.mcp           # Image MCP+FROGS (deux envs micromamba)
│   ├── Dockerfile.claude        # Image Claude Code CLI
│   ├── parse_frogs_reqs.py      # Helper: filtre les dépendances conda FROGS
│   └── claude/.mcp.json         # Config MCP côté conteneur Claude
├── docker-compose.yml           # Orchestration: mcp-server + claude-code
├── Makefile                     # Cibles pratiques: up/down/build/logs/health/clean
├── scripts/
│   └── run_mcp_server.sh        # Wrapper shell pour mode local (stdio)
├── mcp_server/
│   ├── server.py                # POINT D'ENTRÉE — 14 outils FastMCP
│   ├── http_entrypoint.py       # Entrée HTTP (Streamable HTTP + SSE legacy + /health)
│   ├── job_manager.py           # subprocess.Popen + thread daemon JobPoller
│   ├── pipeline.py              # FLOW_RULES + résolution automatique des inputs
│   ├── tools_registry.py        # Catalogue des 28 outils FROGS (dataclasses)
│   ├── database.py              # Toutes les opérations SQLite (3 tables)
│   ├── config.py                # Chemins et constantes (surchargeables via env vars)
│   └── requirements.txt         # mcp[cli]==1.9.4, pydantic==2.11.4
└── workspaces/                  # Sorties des jobs (auto-créé)
    └── <project_id>/<job_id>/   # stdout.txt, stderr.txt, log.txt + fichiers FROGS
```

**Graphe de dépendances des modules :**
```
server.py
  ├── config.py
  ├── database.py
  ├── job_manager.py  ──► config.py, database.py, tools_registry.py
  ├── pipeline.py     ──► database.py, tools_registry.py
  └── tools_registry.py

http_entrypoint.py
  └── server.py (importe l'instance FastMCP `mcp`)
```

**Schéma base de données (3 tables SQLite) :**
- `projects` — métadonnées projet (id, nom, description, working_dir)
- `jobs` — état de chaque job (tool, step, params JSON, pid, status, stdout/stderr paths, output_files JSON)
- `pipeline_steps` — statut de chaque étape du pipeline par projet

---

## 4. Comment lancer le projet

### Mode Docker (recommandé)

```bash
# Prérequis: ANTHROPIC_API_KEY dans l'environnement shell
export ANTHROPIC_API_KEY=sk-ant-...

make build        # Construit les deux images Docker
make up           # Lance mcp-server en arrière-plan
make health       # Vérifie que le serveur répond sur /health
docker compose run --rm claude-code claude  # Lance Claude connecté au MCP
```

### Mode local (développement)

```bash
# 1. Créer les environnements conda
micromamba create -n mcp_frogs python=3.11
micromamba activate mcp_frogs
pip install -r mcp_server/requirements.txt

# 2. Configurer les variables d'environnement (voir config.py)
export FROGS_PYTHON=/path/to/frogs/env/bin/python3
export FROGS_DIR=/path/to/FROGS

# 3. IMPORTANT: adapter .mcp.json pour le mode stdio (pas HTTP)
# Le fichier actuel pointe vers http://mcp-server:8000/mcp (URL Docker interne!)
# Pour le mode local, utiliser la config stdio du README

# 4. Lancer Claude
claude
```

### Debug rapide du serveur

```bash
# Tester le serveur directement (sans Claude)
cd mcp_server && PYTHONPATH=. python server.py

# Inspecter via l'interface web MCP
mcp dev mcp_server/server.py

# Voir les logs en temps réel (Docker)
make logs-mcp
```

---

## 5. Bugs confirmés et problèmes critiques

### CRITIQUE — Échec d'exécution des jobs FROGS (exit code 127)

**Symptôme :** Les jobs soumis échouent avec `vsearch: command not found` (exit 127).

**Cause :** FROGS lance ses propres workers multiprocessing qui héritent de l'environnement différemment. Le `PATH` configuré dans `job_manager.py` (ajout de `FROGS_BIN_DIR`) n'est pas propagé aux sous-processus fils de FROGS.

**Fichier de preuve :** `workspaces/838f85d6/40722b91-fcee-40a0-b701-a1771cad22b0/stderr.txt`

**Piste de correction :** Vérifier que le `PATH` est aussi injecté dans l'environnement `os.environ` global avant le `Popen`, ou passer explicitement `env=` à chaque `Popen` avec le PATH complet incluant tous les binaires FROGS.

**Fichier concerné :** `mcp_server/job_manager.py`

---

### CRITIQUE — `FROGS_PYTHON` par défaut pointe vers le mauvais Python

**Symptôme :** Les scripts FROGS s'exécutent avec le Python système (`/usr/bin/python3`) qui n'a pas les dépendances FROGS. Les jobs échouent silencieusement.

**Cause :** Dans `mcp_server/config.py` :
```python
FROGS_PYTHON = os.environ.get("FROGS_PYTHON", "/usr/bin/python3")
```
Si `FROGS_PYTHON` n'est pas défini, le Python système est utilisé.

**Correction :** Ajouter une vérification au démarrage du serveur qui valide que `FROGS_PYTHON` pointe vers un interpréteur capable d'importer les modules FROGS, et lever une erreur explicite sinon.

---

### MAJEUR — Race condition dans `cancel_job()`

**Symptôme :** Un job annulé peut repasser en statut `failed` peu après.

**Cause :** `cancel_job()` envoie SIGTERM et met le statut à `cancelled` dans la DB, mais ne retire pas le job de `JobPoller._active`. Au prochain cycle de poll (10 secondes), le poller détecte que le processus est terminé (exit -15) et écrase le statut `cancelled` par `failed`.

**Fichiers concernés :** `mcp_server/job_manager.py` (méthodes `cancel_job` et `_poll_loop`)

**Correction :** Retirer le job de `_active` dans `cancel_job()`, avec un verrou thread-safe.

---

### MAJEUR — Statut `pipeline_steps` désynchronisé des statuts `jobs`

**Symptôme :** `get_pipeline_status()` affiche des étapes comme `pending` alors qu'elles sont `completed`.

**Cause :** `update_pipeline_step()` n'est appelée que si `step_name` est défini. Les jobs soumis via `submit_job()` (sans step) ne mettent jamais à jour `pipeline_steps`. Les deux tables divergent.

**Fichiers concernés :** `mcp_server/database.py`, `mcp_server/server.py`

---

### MAJEUR — Fichiers de sortie qui sont des dossiers supprimés silencieusement

**Symptôme :** Certaines étapes en aval ne trouvent pas leurs inputs auto-résolus.

**Cause :** Dans `JobPoller`, après completion d'un job, les `output_files` sont filtrés avec `os.path.isfile(v)`. Les sorties qui sont des **répertoires** (ex: `matrix_outdir` pour `phyloseq_beta_diversity`) sont rejetées silencieusement, cassant la résolution automatique.

**Fichier concerné :** `mcp_server/job_manager.py` — remplacer `os.path.isfile` par `os.path.exists`.

---

### MINEUR — `_elapsed()` peut retourner `None` pour tous les jobs

**Cause :** La fonction mixe des datetimes naïfs et avec timezone. Les timestamps stockés en DB sont au format ISO avec `+00:00`, mais le parsing utilise `%Y-%m-%dT%H:%M:%S.%f` qui ne gère pas le suffixe de timezone.

**Fichier concerné :** `mcp_server/server.py` — fonction `_elapsed()`

---

### MINEUR — Erreurs de typage statique dans `server.py`

L'analyseur de types (Pylance/pyright) signale plusieurs erreurs dans `server.py` :
- Ligne 74 : opérateur `-` appliqué sur une valeur potentiellement `None` (calcul `_elapsed()`)
- Lignes 119, 120, 277, 340 : `.get()` appelé sur `None` (accès à des dicts potentiellement absents)
- Ligne 169 : `None` passé là où `str` est attendu (`_read_tail`)

Ces erreurs indiquent des chemins de code où des `None` non gardés peuvent provoquer des `AttributeError` à l'exécution.

**Fichier concerné :** `mcp_server/server.py`

---

### MINEUR — Erreurs de typage statique dans `http_entrypoint.py`

- Ligne 81 : accès à `mcp.settings.transport_security` — attribut non documenté du SDK MCP
- Ligne 102 : accès à `.app` sur un `BaseRoute` — attribut absent du type public

Ces accès à des attributs privés/internes du SDK risquent de casser à chaque mise à jour de `mcp[cli]`.

**Fichier concerné :** `mcp_server/http_entrypoint.py`

---

### MINEUR — Dead code dans `tools_registry.py`

```python
# Cette condition est une tautologie (toujours True)
tool_dir = self.name if self.name != "phyloseq_import" else "phyloseq_import"
```

**Fichier concerné :** `mcp_server/tools_registry.py` — propriété `script_path`

---

## 6. Problèmes d'hygiène du dépôt

| Problème | Impact | Correction |
|---|---|---|
| `mcp_server/frogs_jobs.db` committé | Conflits de merge, fuite de données | Ajouter `.gitignore`, supprimer du dépôt |
| Pas de `.gitignore` | `__pycache__/`, `*.pyc`, `workspaces/`, `*.db` trackés | Créer `.gitignore` |
| `.mcp.json` racine pointe vers URL Docker interne | Mode local inopérant sans modification manuelle | Documenter clairement ou fournir deux configs |
| `RECAP_MCP_FROGS.Rmd` contient une commande de session debug ligne 375 | Pollution du doc de design | Supprimer la ligne |
| Commentaire "13 outils" dans `server.py` alors qu'il y en a 14 | Documentation incorrecte | Corriger le docstring |

---

## 7. Absence complète de tests

Il n'existe **aucun test** dans le projet (pas de `tests/`, pas de `pytest.ini`, pas de CI/CD).

Les modules les plus critiques à tester en priorité :

1. **`pipeline.py`** — logique de résolution automatique des inputs (`_resolve_inputs`) : c'est le coeur de la valeur ajoutée du projet et le code le plus complexe
2. **`job_manager.py`** — construction des commandes CLI (`build_command`), gestion du cycle de vie des jobs
3. **`database.py`** — opérations CRUD, cohérence entre les 3 tables
4. **Transport HTTP** — `http_entrypoint.py` accède à un attribut interne non documenté du SDK MCP (`mcp.session_manager`)

**Recommandation :** Mettre en place `pytest` avec des mocks pour `subprocess.Popen` et SQLite en mémoire (`:memory:`).

---

## 8. Priorités suggérées pour la reprise

### Semaine 1 — Faire fonctionner le pipeline de bout en bout

1. Reproduire l'échec (exit 127) sur un job `reads_processing` avec les données AQUALEHA
2. Corriger la propagation du `PATH`/`env` dans `job_manager.py`
3. Corriger le filtre `os.path.isfile` → `os.path.exists` pour les sorties dossiers
4. Corriger la race condition `cancel_job()` / `JobPoller`
5. Valider manuellement un pipeline complet (au moins les 4 premières étapes)

### Semaine 2 — Hygiène et observabilité

6. Créer `.gitignore`, supprimer `frogs_jobs.db` du dépôt
7. Remplacer les `print()` par `logging` avec niveaux configurables
8. Corriger `_elapsed()` pour gérer les timezones correctement
9. Ajouter une validation au démarrage : vérifier que `FROGS_PYTHON` est valide
10. Corriger la synchronisation `pipeline_steps` ↔ `jobs`

### Semaine 3 — Tests et CI

11. Mettre en place `pytest` + tests unitaires pour `pipeline.py` et `job_manager.py`
12. Configurer un workflow GitHub Actions minimal (lint + tests)
13. Ajouter des tests d'intégration Docker (healthcheck + un job factice)

---

## 9. Variables d'environnement importantes

| Variable | Défaut | Description |
|---|---|---|
| `FROGS_PYTHON` | `/usr/bin/python3` | **CRITIQUE** — Python de l'env FROGS |
| `MCP_FROGS_PYTHON` | détection auto | Python de l'env MCP |
| `FROGS_DIR` | déduit du repo | Racine de l'installation FROGS |
| `FROGS_TOOLS_DIR` | `$FROGS_DIR/tools` | Dossier des 28 scripts |
| `FROGS_BIN_DIR` | `$FROGS_DIR/libexec` | Binaires externes (vsearch, swarm...) |
| `WORKSPACE_ROOT` | `./workspaces` | Dossier des sorties de jobs |
| `DB_PATH` | `./mcp_server/frogs_jobs.db` | Chemin de la base SQLite |
| `DEFAULT_NB_CPUS` | `4` | CPUs alloués par défaut aux jobs FROGS |
| `POLL_INTERVAL_SEC` | `10` | Fréquence de poll du JobPoller |
| `MCP_HOST` / `MCP_PORT` | `0.0.0.0` / `8000` | Binding du serveur HTTP |
| `ANTHROPIC_API_KEY` | — | **Requis** pour le conteneur claude-code |

---

## 10. Liens et références

- Dépôt GitHub : `https://github.com/Mronanmag/MCP-Frogs`
- Documentation FROGS : `https://frogs.readthedocs.io`
- Spec MCP : `https://modelcontextprotocol.io`
- SDK Python MCP : `https://github.com/modelcontextprotocol/python-sdk`
- Document de design interne : `RECAP_MCP_FROGS.Rmd` (en français)
- README principal : `README.md` (en français, très complet)
