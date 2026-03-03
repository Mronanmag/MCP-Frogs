# MCP-Frogs 🐸

Un **serveur MCP** (Model Context Protocol) qui permet à un LLM (Claude) d'orchestrer le pipeline d'analyse métagénomique amplicon **FROGS** de façon conversationnelle et asynchrone.

---

## Table des matières

- [Qu'est-ce que FROGS ?](#qu-est-ce-que-frogs-)
- [Comment fonctionne le serveur MCP ?](#comment-fonctionne-le-serveur-mcp)
- [Architecture](#architecture)
- [Prérequis](#prérequis)
- [Installation](#installation)
- [Configuration](#configuration)
- [Lancement du serveur](#lancement-du-serveur)
- [Déploiement Docker (rapide)](#déploiement-docker-rapide)
- [Outils MCP disponibles](#outils-mcp-disponibles)
- [Utilisation type](#utilisation-type)
- [Points techniques](#points-techniques)

---

## Qu'est-ce que FROGS ?

**FROGS** (Find Rapidly OTUs with Galaxy Solution) est un pipeline d'analyse amplicon (métagénomique 16S / ITS / 18S) composé de **28 scripts Python** qui s'exécutent séquentiellement. Chaque script peut durer de quelques minutes à plusieurs heures.

---

## Comment fonctionne le serveur MCP ?

Le serveur MCP agit comme une **couche d'orchestration** entre Claude et les outils FROGS :

1. Claude appelle un **outil MCP** (ex. `submit_pipeline_step`).
2. Le serveur lance le script FROGS correspondant via **`subprocess.Popen`** (non-bloquant) et retourne un `job_id` immédiatement.
3. Un **thread daemon** (`JobPoller`) surveille les processus en arrière-plan toutes les 10 secondes et met à jour leur statut dans une base **SQLite**.
4. Claude peut interroger le statut avec `get_job_status(job_id)` à tout moment.
5. Une fois une étape terminée, `get_pipeline_recommendations` calcule automatiquement les fichiers d'entrée de l'étape suivante en utilisant les **règles de flux** (`FLOW_RULES`), et fournit une commande `submit_pipeline_step` prête à l'emploi.

```
Claude  ──tool call──►  MCP Server  ──Popen──►  FROGS script (env frogs)
                             │
                        JobPoller (thread)
                             │
                          SQLite DB  ◄──── get_job_status / get_pipeline_recommendations
```

---

## Architecture

```
MCP-Frogs/
├── .mcp.json                     # Configuration MCP pour Claude Code
├── FROGS/                        # Pipeline FROGS existant (non modifié)
│   ├── tools/                    # 28 scripts Python (un par outil)
│   ├── lib/                      # Bibliothèques partagées (frogsUtils.py, ...)
│   └── libexec/                  # Binaires externes (swarm, vsearch, ...)
├── workspaces/                   # Créé automatiquement — sorties des jobs
│   └── <project_id>/<job_id>/    # Répertoire isolé par job
└── mcp_server/
    ├── server.py                 # Point d'entrée FastMCP — 14 outils MCP
    ├── job_manager.py            # Soumission subprocess + thread poller
    ├── pipeline.py               # Résolution automatique des inputs/outputs
    ├── tools_registry.py         # Catalogue des 28 outils FROGS
    ├── database.py               # Toutes les opérations SQLite
    ├── config.py                 # Chemins et constantes
    ├── requirements.txt          # mcp[cli], pydantic
    └── frogs_jobs.db             # Créé automatiquement au premier démarrage
```

### Deux environnements Python séparés

| Environnement | Rôle | Exemple de chemin |
|---|---|---|
| `mcp_frogs` (micromamba) | Fait tourner le serveur MCP | `/home/ronan/micromamba/envs/mcp_frogs/` |
| `frogs` (conda/micromamba) | Fait tourner les scripts FROGS | `/home/ronan/miniconda3/envs/frogs/` |

Cette séparation permet d'isoler les dépendances du serveur MCP (`mcp[cli]`, `pydantic`) de celles de FROGS (numpy, biopython, etc.).

---

## Prérequis

- **Python ≥ 3.10** dans l'environnement MCP
- **conda** ou **micromamba** pour gérer les environnements
- **FROGS** installé et fonctionnel (avec son propre environnement conda)
- **Claude Code** (CLI) pour utiliser le serveur via `.mcp.json`

---

## Installation

### 1. Cloner le dépôt

```bash
git clone https://github.com/Mronanmag/MCP-Frogs.git
cd MCP-Frogs
```

### 2. Créer l'environnement MCP

```bash
micromamba create -n mcp_frogs python=3.11
micromamba activate mcp_frogs
```

### 3. Installer les dépendances du serveur MCP

```bash
pip install -r mcp_server/requirements.txt
```

> Les dépendances sont minimales : `mcp[cli]>=1.0.0` et `pydantic>=2.0.0`.

### 4. Vérifier le chemin Python de l'environnement FROGS

```bash
micromamba activate frogs   # ou conda activate frogs
which python3               # noter ce chemin pour la configuration
micromamba deactivate
```

---

## Configuration

### `.mcp.json` (à la racine du projet)

Le dépôt fournit maintenant une configuration **portable** qui évite les chemins absolus (`/home/...`) et lance un wrapper shell (`scripts/run_mcp_server.sh`).

```json
{
  "mcpServers": {
    "frogs": {
      "command": "bash",
      "args": ["-lc", "./scripts/run_mcp_server.sh"],
      "env": {
        "MCP_FROGS_PYTHON": "python3",
        "FROGS_PYTHON": "python3"
      }
    }
  }
}
```

Vous pouvez surcharger les binaires Python sans modifier le JSON :

```bash
export MCP_FROGS_PYTHON=/chemin/vers/python_mcp
export FROGS_PYTHON=/chemin/vers/python_frogs
claude
```

### `mcp_server/config.py`

Les chemins FROGS sont déduits automatiquement à partir de l'emplacement du dépôt. Si votre installation FROGS est dans un dossier différent, modifiez `config.py` :

```python
FROGS_TOOLS_DIR  = "/chemin/vers/FROGS/tools"
FROGS_LIB_DIR    = "/chemin/vers/FROGS/lib"
FROGS_BIN_DIR    = "/chemin/vers/FROGS/libexec"
```

---

### Résoudre `Failed to reconnect to frogs`

Si Claude affiche `frogs: ✗ failed`, lancez :

```bash
claude --debug
```

Puis vérifiez, dans les logs debug :

1. **Commande exécutée** (doit être `./scripts/run_mcp_server.sh` en mode local, ou `http://mcp-server:8000/sse` en mode Docker 2 conteneurs).
2. **Erreur Python import** (`ModuleNotFoundError`) → vérifier `PYTHONPATH`.
3. **Erreur binaire Python introuvable** (`No such file or directory` ou `exec: python3: not found`) → exporter `MCP_FROGS_PYTHON`/`FROGS_PYTHON` vers les bons chemins.
4. **Crash serveur au démarrage** → tester manuellement :

```bash
./scripts/run_mcp_server.sh
```

Si ce test échoue, le message terminal est la cause racine à corriger.

5. **Erreur `TypeError: FastMCP.run() got an unexpected keyword argument "host"`**
   - Cause : incompatibilité de version `mcp` (la méthode `run()` n'accepte pas `host/port` en argument).
   - Correctif appliqué : `mcp_server/http_entrypoint.py` configure `mcp.settings.host` / `mcp.settings.port` puis appelle `mcp.run(transport="sse")`.

---

## Lancement du serveur

### Via Claude Code (recommandé)

Claude Code détecte automatiquement `.mcp.json` et démarre le serveur :

```bash
cd ~/Projet/MCP_FROGS
claude
```

### Via l'inspecteur MCP (debug dans le navigateur)

```bash
cd ~/Projet/MCP_FROGS/mcp_server
mcp dev server.py
```

Puis dans l'interface web, changer la commande de `uv` vers le Python de l'environnement `mcp_frogs`.

### Test direct en ligne de commande

```bash
cd ~/Projet/MCP_FROGS/mcp_server
PYTHONPATH=. python server.py
```

---

## Déploiement Docker (rapide)

Le dépôt inclut une structure Docker prête à l'emploi avec deux options :

1. **Mode recommandé (2 conteneurs)** :
   - `mcp-server` : héberge MCP + env `frogs=5.1.0` via **micromamba** (avec contrainte Python 3.7 imposée par FROGS 5.1.0).
   - `claude-code` : CLI Claude isolée, connectée au MCP via transport HTTP.
2. **Mode fallback (1 conteneur)** : profil `fallback`, utile si votre version de Claude Code n'accepte pas le transport MCP distant.

### Fichiers ajoutés

- `docker/Dockerfile.mcp` : construit deux environnements micromamba (`frogs` et `mcp_frogs`).
  - `frogs` est créé avec `python=3.7` (compatibilité stricte de `frogs=5.1.0`).
- `docker/Dockerfile.claude` : conteneur isolé pour Claude Code.
- `docker-compose.yml` : orchestration complète.
- `docker/claude/.mcp.json` : config MCP côté Claude (URL interne compose).
- `mcp_server/http_entrypoint.py` : expose le serveur en `sse` sur le port `8000`.

### Lancer le setup 2 conteneurs

```bash
docker compose build
docker compose up -d mcp-server
docker compose run --rm claude-code claude
```

> Pensez à définir `ANTHROPIC_API_KEY` dans votre shell avant de lancer `claude-code`.
>
> Le service `claude-code` monte `docker/claude/.mcp.json` **sur le `.mcp.json` du projet** dans le conteneur, pour forcer la connexion HTTP vers `mcp-server` (et éviter le mode stdio local).

### Lancer le mode fallback (tout dans un seul conteneur)

```bash
docker compose --profile fallback run --rm all-in-one
```

Dans ce shell, vous pouvez démarrer MCP et Claude localement dans le même conteneur.

### Notes pratiques

- Le volume `./workspaces` est monté pour conserver les sorties des jobs.
- La base SQLite `mcp_server/frogs_jobs.db` est persistée via volume.
- Le serveur MCP est exposé sur `http://localhost:8000` (endpoint MCP: `/sse`).
- Variables de contrôle HTTP: `MCP_HOST`, `MCP_PORT`, `MCP_DISABLE_DNS_REBINDING_PROTECTION`.

---

## Outils MCP disponibles

Le serveur expose **14 outils** utilisables par Claude.

### Gestion des jobs

| Outil | Description |
|---|---|
| `submit_job(tool_name, params, project_id?)` | Soumet n'importe quel outil FROGS en arrière-plan |
| `get_job_status(job_id)` | Statut, durée écoulée, code de sortie |
| `get_job_results(job_id)` | Fichiers de sortie + 50 dernières lignes de log |
| `list_jobs(project_id?)` | Liste tous les jobs (filtrables par projet) |
| `cancel_job(job_id)` | Annule un job en cours (SIGTERM) |

### Orchestration pipeline

| Outil | Description |
|---|---|
| `create_project(name, description?)` | Crée un projet et initialise le suivi des 28 étapes |
| `submit_pipeline_step(project_id, step_name, params, auto_resolve_inputs=True)` | Soumet une étape avec résolution automatique des inputs |
| `get_pipeline_status(project_id)` | Vue complète de toutes les étapes du projet |
| `get_pipeline_recommendations(project_id)` | ⭐ **Outil principal** — rapport Markdown guidant l'étape suivante |

### Utilitaires

| Outil | Description |
|---|---|
| `list_tools(category?)` | Liste les 28 outils FROGS avec descriptions |
| `get_tool_help(tool_name)` | Paramètres détaillés d'un outil |
| `list_projects()` | Liste tous les projets existants |
| `read_log(job_id, tail_lines=100)` | Lit le log FROGS ou stderr |
| `read_report(job_id)` | Lit un rapport HTML (strippé) ou TSV |

---

## Utilisation type

Voici la séquence d'une analyse 16S complète :

```
1. list_tools()
   → Liste les 28 outils disponibles

2. create_project("Etude_16S_Sol_2024")
   → project_id: "a1b2c3d4"

3. get_pipeline_recommendations("a1b2c3d4")
   → Affiche : prochaine étape = reads_processing
     Paramètres requis : sequencer, min_amplicon_size, max_amplicon_size,
                         five_prim_primer, three_prim_primer, input_archive

4. submit_pipeline_step("a1b2c3d4", "reads_processing", {
     "sequencer": "illumina",
     "process": "swarm",
     "min_amplicon_size": 44,
     "max_amplicon_size": 490,
     "five_prim_primer": "GGCGVACGGGTGAGTAA",
     "three_prim_primer": "GTGCCAGCNGCNGCGG",
     "R1_size": 267,
     "R2_size": 266,
     "input_archive": "/data/reads.tar.gz"
   })
   → job_id: "uuid-xxx" (retourné immédiatement)

5. get_job_status("uuid-xxx")
   → status: "running", elapsed_seconds: 142

6. [... attente ...]
   get_job_status("uuid-xxx")
   → status: "completed"

7. get_pipeline_recommendations("a1b2c3d4")
   → Prochaine étape : remove_chimera
     Inputs auto-résolus :
       input_fasta = /workspaces/a1b2c3d4/uuid-xxx/reads_processing.fasta
       input_biom  = /workspaces/a1b2c3d4/uuid-xxx/reads_processing_abundance.biom
     Aucun paramètre supplémentaire requis.

8. submit_pipeline_step("a1b2c3d4", "remove_chimera", {})
   → Les inputs sont résolus automatiquement depuis l'étape précédente
   → Continuer ainsi jusqu'à phyloseq_alpha_diversity
```

---

## Points techniques

### Non-bloquant
`submit_job()` retourne un `job_id` en quelques millisecondes. Le script FROGS tourne en arrière-plan via `subprocess.Popen`.

### Persistance
SQLite en mode WAL (`PRAGMA journal_mode=WAL`) permet aux accès concurrents (thread poller + appels MCP) de coexister, et préserve l'état de tous les jobs entre redémarrages du serveur.

### Isolation des jobs
Chaque job dispose d'un répertoire dédié `workspaces/<project_id>/<job_id>/` pour ses fichiers de sortie, logs, et stderr.

### Résolution automatique des fichiers
Les 34 règles `FLOW_RULES` dans `pipeline.py` encodent le flux de données entre étapes. Elles sont stockées sous forme de liste de tuples (et non un dict) pour supporter les relations many-to-many — par exemple, la sortie `.rdata` de `phyloseq_import` alimente 6 étapes différentes.

### Annulation propre
`cancel_job()` envoie `SIGTERM`. Les scripts FROGS interceptent ce signal et nettoient leurs fichiers temporaires avant de se terminer.

### Étapes du pipeline

**12 étapes principales (obligatoires) :**
`reads_processing` → `remove_chimera` → `cluster_filters` → `taxonomic_affiliation` → `affiliation_postprocess` → `affiliation_filters` → `affiliation_report` → `tree` → `normalisation` → `phyloseq_import` → `phyloseq_composition` → `phyloseq_alpha_diversity`

**16 étapes optionnelles :**
`demultiplex`, `clustering`, `itsx`, `biom_to_tsv`, `tsv_to_biom`, `biom_to_stdBiom`, `cluster_asv_report`, `phyloseq_beta_diversity`, `phyloseq_clustering`, `phyloseq_structure`, `phyloseq_manova`, `deseq2_preprocess`, `deseq2_visualisation`, `frogsfunc_placeseqs`, `frogsfunc_functions`, `frogsfunc_pathways`
