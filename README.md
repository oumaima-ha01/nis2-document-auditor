# NIS2 Document Auditor

Un outil local pour rapprocher une documentation SI des exigences NIS2, retrouver les passages pertinents et préparer une revue humaine traçable. Il ne délivre pas de certification de conformité.

[Voir les tests et la construction Docker](https://github.com/oumaima-ha01/nis2-document-auditor/actions/workflows/ci.yml)

## Le projet

Un audit documentaire oblige à parcourir des politiques, procédures et registres de formats différents, puis à justifier chaque constat avec une source vérifiable. NIS2 Document Auditor rassemble ce travail dans une interface : on crée un dossier, on importe les documents, on lance l'analyse et on examine une matrice d'exigences avec ses passages candidats.

Le parti pris est de **ne jamais confondre un document qui décrit un contrôle avec la preuve que ce contrôle fonctionne**. Les résultats automatiques restent des propositions à revoir, et l'absence de passage retrouvé n'est pas présentée comme une preuve d'absence du contrôle.

Ce projet met en pratique une chaîne d'AI engineering complète : ingestion de fichiers hétérogènes, extraction avec provenance, lecture visuelle facultative, recherche de passages, évaluation par LLM facultative, validation des citations, revue humaine et export.

## Essayer l'application

Avec Docker Desktop ou Docker Engine et Compose :

```sh
git clone https://github.com/oumaima-ha01/nis2-document-auditor.git
cd nis2-document-auditor
docker compose up --build -d
```

Ouvrir [http://127.0.0.1:8000](http://127.0.0.1:8000). L'interface et l'API tournent dans le même conteneur ; un volume Docker conserve les dossiers et les documents entre deux démarrages. `docker compose down` arrête l'application sans supprimer ces données. Si le port 8000 est occupé, définir `NIS2_HOST_PORT=8080` dans un fichier `.env` à la racine du projet.

Pour faire un premier parcours, les trois fichiers de [`demo-documents/`](demo-documents/) sont fictifs :

1. Créer un dossier et choisir « Entité importante ».
2. Importer le PDF, le document Word et le classeur Excel.
3. Lancer l'analyse, ouvrir un constat et remonter à son passage source.
4. Enregistrer une revue humaine, puis exporter la matrice en CSV ou JSON.

Aucune clé d'API n'est nécessaire pour cette démonstration : sans IA configurée, l'application propose des passages candidats à vérifier.

## Comment fonctionne la chaîne

1. **Ingestion** — Contrôle du type et de la taille, puis stockage local des PDF, DOCX, XLSX, CSV et images.
2. **Lecture** — Extraction du texte avec sa provenance (page, paragraphe ou cellule). Les pages PDF peu lisibles et les images peuvent passer par un modèle de vision si celui-ci est configuré ; sinon, leur lecture est signalée comme incomplète.
3. **Rapprochement** — Sélection de passages candidats pour chaque exigence du catalogue. Un modèle texte facultatif propose un statut et une justification ; les citations qui ne correspondent pas au texte source sont rejetées.
4. **Décision** — L'utilisateur examine les éléments, consigne sa revue et exporte les résultats.

Le backend est en Python/FastAPI avec SQLite et des traitements en arrière-plan dans le processus. L'interface utilise JavaScript et CSS sans serveur frontend distinct. Le paquet Python est défini dans [`pyproject.toml`](pyproject.toml) ; [`Dockerfile`](Dockerfile) installe ce même paquet, et [`compose.yaml`](compose.yaml) expose uniquement l'adresse locale `127.0.0.1`.

## Référentiels et IA

Le catalogue par défaut résume, pour la démonstration, les dix familles de mesures de l'[article 21(2) de la directive NIS2](https://eur-lex.europa.eu/eli/dir/2022/2555/oj). `CATALOG_MODE=recyf` charge un catalogue de 152 mesures extraites du [document de travail ReCyF v2.5 de l'ANSSI](https://messervices.cyber.gouv.fr/documents-ressources/20260317_NIS_V2_ReCyF_v2.5.pdf). Cette extraction et les règles d'applicabilité simplifiées doivent être vérifiées avant tout usage réel.

Pour activer l'analyse IA, copier [`.env.example`](.env.example) vers `.env`, puis renseigner `AI_API_KEY`, `AI_TEXT_MODEL` et, pour les pages scannées, `AI_VISION_MODEL`. `AI_BASE_URL` permet d'utiliser une API compatible Chat Completions avec sortie JSON. **Avec l'IA activée, des extraits de documents ou des images de pages sont transmis au fournisseur configuré.** N'utiliser des documents sensibles qu'après avoir vérifié les conditions de ce fournisseur.

## Installation sans Docker

Le projet s'installe aussi comme paquet Python. Python 3.11 ou 3.12 est recommandé.

Sous Windows (PowerShell) :

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\nis2-auditor.exe serve
```

Sous Linux ou macOS :

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install .
./.venv/bin/nis2-auditor serve
```

Ouvrir ensuite [http://127.0.0.1:8000](http://127.0.0.1:8000). Par défaut, les données sont placées dans le répertoire utilisateur prévu par le système ; `NIS2_DATA_DIR` permet de choisir un autre emplacement.

## Tests et périmètre

```sh
python -m pip install '.[test]'
python -m pytest -q
```

La [CI](https://github.com/oumaima-ha01/nis2-document-auditor/actions/workflows/ci.yml) exécute les tests, construit l'image et vérifie que le conteneur sert l'API et l'interface. L'application reste un projet de démonstration local : pas d'authentification, pas d'isolation multi-client et pas de conclusion juridique automatique. **Ne pas l'exposer telle quelle sur Internet.**
