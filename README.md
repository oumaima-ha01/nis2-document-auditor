# NIS2 Auditor — audit documentaire local

Audit documentaire assisté : import PDF, DOCX, XLSX, CSV et images ; passages avec page, paragraphe ou cellule ; matrice NIS2/ReCyF ; analyse IA facultative ; revue humaine ; exports CSV et JSON. Ce prototype ne remplace pas un auditeur ni une analyse juridique.

## Installation rapide, sans Docker

Python 3.11 ou 3.12 est requis. Depuis le dossier du projet :

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

Ouvrir <http://127.0.0.1:8000>. L'application, l'interface et les catalogues sont installés dans le paquet Python ; elle fonctionne depuis n'importe quel répertoire de travail. Pour distribuer un seul fichier de paquet, construire une roue avec `python -m pip wheel . --no-deps -w dist`, copier le `.whl` sur l'autre machine puis l'installer avec `python -m pip install chemin/vers/nis2_document_auditor-0.2.0-py3-none-any.whl`. L'installation récupère les dépendances depuis PyPI ; elle nécessite donc Internet ou un cache de paquets.

La commande `nis2-auditor serve --port 8080` permet de choisir le port. Le serveur écoute uniquement sur `127.0.0.1` par défaut. `python -m nis2_auditor serve` fonctionne également si le lanceur n'est pas dans le `PATH`.

Les données (base SQLite, documents, pages rendues) sont conservées dans le répertoire de données de l'utilisateur, défini par le système d'exploitation. Définir `NIS2_DATA_DIR` pour choisir un dossier explicite. Un `.env` dans le répertoire courant est lu au démarrage ; voir `.env.example`.

Sur cette machine de développement, `run-local.ps1` garde les dossiers d'audit existants dans `data/` et démarre la version installée dans `.venv`.

## Docker — interface et API dans une seule image

L'image installe le paquet Python, l'API FastAPI, l'interface statique et les deux catalogues. Aucun serveur frontend ni Python hôte supplémentaire n'est nécessaire. Avec Docker Desktop ou Docker Engine et Compose :

```sh
docker compose up --build -d
docker compose ps
docker compose logs -f auditor
```

Ouvrir <http://127.0.0.1:8000>. `docker compose down` arrête le service sans supprimer le volume `auditor_data`. La configuration IA peut être placée dans `.env` avant le démarrage ; Compose transmet ces valeurs au conteneur. Le port est lié à `127.0.0.1` sur l'hôte, car cette version n'a pas d'authentification.

Si le port 8000 est déjà occupé, définir `NIS2_HOST_PORT=8080` dans `.env`, puis ouvrir <http://127.0.0.1:8080>. Vérifier l'API avec `docker compose exec auditor python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/health').read().decode())"`. Les documents et la base restent dans le volume nommé après recréation du conteneur. `docker compose down -v` supprimerait ce volume et toutes les données d'audit ; ne l'utiliser que si c'est volontaire.

Le paquet Python est la voie d'installation prioritaire. L'image Docker utilise ce même paquet ; aucun Python du poste hôte n'est utilisé par le conteneur. Le conteneur tourne avec un utilisateur non privilégié et stocke ses données dans un volume nommé.

Sous Windows, Docker Desktop nécessite un moteur Linux fonctionnel. Si WSL 2 n'est pas encore activé, lancer `wsl --install --no-distribution` dans un PowerShell **administrateur**, redémarrer, puis démarrer Docker Desktop avec le backend WSL 2. Une distribution Ubuntu n'est pas nécessaire pour lancer les conteneurs depuis PowerShell.

## Catalogues et IA

Le catalogue de démonstration reprend les dix familles de mesures de l'article 21(2) de NIS2. Le paquet contient également 152 mesures extraites du document de travail ReCyF v2.5. Pour utiliser celles-ci, définir `CATALOG_MODE=recyf` dans `.env` puis redémarrer. `nis2-auditor build-catalog` télécharge à nouveau le PDF officiel et génère une copie du catalogue dans le dossier de données ; cette copie prend alors priorité sur celle fournie dans le paquet. L'extraction automatique et l'applicabilité doivent être relues avant tout audit réel.

Pour activer l'IA, renseigner `AI_API_KEY`, `AI_BASE_URL`, `AI_TEXT_MODEL` et `AI_VISION_MODEL` dans `.env` pour une API compatible Chat Completions avec sortie JSON. Le modèle texte évalue les passages trouvés ; les citations inventées sont rejetées. Le modèle vision transcrit les pages PDF sans texte exploitable et les images. Sans API, la recherche locale signale des passages candidats « À vérifier » ; une image ou page scannée non lue reste en lecture partielle. **Ne pas exposer cette version sur Internet ni importer des documents confidentiels dans une démonstration publique.**

## Démonstration et tests

Depuis le dépôt source, `python scripts/make_demo.py` crée trois documents fictifs dans `demo-documents/`. Créer un dossier dans l'interface, choisir « Entité importante », déposer ces fichiers, lancer l'analyse, examiner les preuves et enregistrer une revue.

Pour installer et exécuter les tests de développement :

```powershell
.\.venv\Scripts\python.exe -m pip install '.[test]'
.\.venv\Scripts\python.exe -m pytest -q
```

L'application actuelle est volontairement locale, sans authentification, stockage objet ni workers persistants. Ne pas la publier telle quelle comme service accessible sur Internet.
