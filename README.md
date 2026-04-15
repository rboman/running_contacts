# match-my-contacts

Outil local-first pour centraliser des contacts, importer des résultats de course, puis croiser les deux sans dépendre à chaque fois des sources externes.

## Problème visé

Après une course avec plusieurs milliers de participants, l’objectif est de répondre rapidement à la question: quels contacts ont participé, et quel est leur résultat ? Le projet est pensé dès le départ comme trois briques indépendantes et réutilisables:

1. `contacts`: importer et stocker les contacts localement.
2. `race_results`: récupérer et normaliser les résultats d’une course.
3. `matching`: croiser les données déjà stockées et produire un tableau exploitable.

Une extension envisagée ensuite est l’analyse de documents longs, par exemple des PDF de réunions, pour retrouver les passages qui mentionnent certains contacts.

## Choix d’architecture

- Source de vérité locale: SQLite.
- Exports secondaires: JSON/CSV selon les besoins.
- Code organisé par domaines réutilisables, pas comme un seul script.
- Projet local, sans backend distant.
- Pas d’ORM en première intention: `sqlite3` suffit.

## État actuel

La première brique `contacts` gère maintenant plusieurs sources locales de contacts:

- OAuth Desktop via Google People API (`google_people`).
- Import snapshot d'exports Google Contacts CSV (`google_contacts_csv`).
- Coexistence de plusieurs sources dans la même base SQLite sans fusion automatique.
- Resync et réimport isolés par `source` et `source_account`.
- Consultation locale sans appel réseau.
- Export JSON de l’état local.

Le stockage local repose sur trois tables:

- `contacts`
- `contact_methods`
- `sync_runs`

La deuxième brique `race_results` est maintenant en place pour ACN Timing:

- parsing d’URL publique ACN Timing,
- récupération des métadonnées d’événement via Chronorace,
- récupération du tableau de résultats via l’API Chronorace utilisée par ACN,
- snapshot JSON brut sous `raw/acn_timing/` dans le `data_dir` configuré,
- stockage SQLite local dans `race_results.sqlite3` dans le `data_dir` configuré,
- alias manuels de datasets pour éviter d’utiliser seulement `dataset_id`.

La troisième brique `matching` est maintenant disponible:

- matching 100% local entre `contacts` et `race_results`,
- normalisation des noms (accents, casse, ponctuation),
- match exact puis fuzzy avec `rapidfuzz`,
- garde-fou d’ambiguïté via un score minimal et un écart minimal entre candidats,
- affichage terminal et export CSV,
- tri et filtrage sur les matches (`time`, `team`, `athlete`, etc.),
- alias manuels réutilisables sur les contacts,
- reviews manuelles pour accepter ou rejeter un match résultat par résultat.

Le matching actuel est jugé suffisamment satisfaisant pour l'usage courant. La priorité produit suivante n'est donc plus l'amélioration du moteur, mais l'ajout d'une petite interface graphique locale simple.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[gui]
```

## Répertoire de données configurable

Le projet utilise maintenant un fichier de config local par machine pour choisir où stocker l'état local.

Fichier de config:

```bash
~/.config/match_my_contacts/config.toml
```

Sous Windows, l'emplacement équivalent est:

```powershell
$env:APPDATA\match_my_contacts\config.toml
```

La première exécution de la CLI ou de la GUI crée automatiquement ce fichier s'il n'existe pas encore, en pointant vers `data/` à la racine du projet.

Format:

```toml
data_dir = "/chemin/absolu/vers/match_my_contacts_data"
credentials_path = "/chemin/absolu/vers/credentials.json"
```

Tout l'état local dérive ensuite de ce répertoire:

- `contacts.sqlite3`
- `race_results.sqlite3`
- `google/token.json`
- `raw/acn_timing/`
- `exports/`

Cela permet de pointer vers un dossier Dropbox partagé entre machines, à condition de n'utiliser qu'une seule machine à la fois sur ces bases SQLite.

Pour inspecter la config et les chemins résolus:

```bash
match-my-contacts config show
```

Pour installer aussi la GUI desktop PySide6:

```bash
pip install -e .[gui]
```

Sous Linux avec une session X11, Qt peut aussi nécessiter la librairie système `libxcb-cursor0`:

```bash
sudo apt install libxcb-cursor0
```

## Préparer l’accès Google Contacts

1. Créer un projet Google Cloud.
2. Activer Google People API.
3. Créer des identifiants OAuth pour une application Desktop.
4. Télécharger le fichier `credentials.json`.

Le fichier d’identifiants peut rester hors du dépôt. Le token OAuth généré par la CLI est stocké localement sous `google/token.json` dans le `data_dir` configuré.
Si `credentials.json` est présent à la racine du projet, la commande de sync l’utilise automatiquement, même si la CLI est lancée depuis un autre répertoire.

## Commandes utiles

Tester la CLI:

```bash
match-my-contacts hello
```

Synchroniser les contacts Google vers SQLite:

```bash
match-my-contacts contacts sync
match-my-contacts contacts sync-google
match-my-contacts contacts sync --credentials /chemin/vers/credentials.json
```

Importer un export Google Contacts CSV dans la base locale:

```bash
match-my-contacts contacts import-google-csv --csv-path /chemin/vers/google-contacts.csv
match-my-contacts contacts empty-db
match-my-contacts contacts vacuum-db
```

Récupérer un tableau de résultats ACN Timing:

```bash
match-my-contacts race-results fetch-acn --url 'https://www.acn-timing.com/?lng=FR#/events/2157220339092161/ctx/20260412_liege/generic/197994_1/home/LIVE1'
```

Lister les datasets de résultats locaux:

```bash
match-my-contacts race-results list-datasets
match-my-contacts race-results add-alias --dataset-id 1 --alias liege-15k-2026
match-my-contacts race-results list-results --dataset liege-15k-2026 --query dupont
```

Lancer le matching local:

```bash
match-my-contacts matching run --dataset liege-15k-2026
match-my-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE --sort time
match-my-contacts matching export-csv --dataset liege-15k-2026 --output data/exports/matches.csv
```

Corriger les cas limites:

```bash
match-my-contacts contacts list --query noel
match-my-contacts contacts add-alias --contact-id 42 --alias "Jean Noel"
match-my-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 20
match-my-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 42
match-my-contacts matching reject --dataset liege-15k-2026 --result-id 5678 --note "homonyme"
match-my-contacts matching list-reviews --dataset liege-15k-2026
```

Lister les contacts locaux:

```bash
match-my-contacts contacts list
match-my-contacts contacts list --query dupont
match-my-contacts contacts list --source google_people
match-my-contacts contacts list-sources
```

Exporter l’état local en JSON:

```bash
match-my-contacts contacts export-json --output data/exports/contacts.json
```

Lancer les tests:

```bash
pytest -q
```

Lancer la GUI locale:

```bash
match-my-contacts-gui
```

La GUI actuelle reste volontairement simple, mais elle est déjà utile au quotidien:

- interface desktop locale en PySide6,
- sections `Contacts`, `Race Results` et `Matching`,
- menu `Help` avec `About` et `Credits`,
- table centrale unique,
- sync Google depuis l'onglet `Contacts`,
- dialog de résumé après `Sync Google`,
- auto-load local des contacts au dÃ©marrage quand la base existe dÃ©jÃ ,
- import CSV ciblÃ© pour le vrai format exporté par Google Contacts,
- bouton `Empty DB...` avec confirmation explicite,
- bouton `VACUUM DB` pour compacter `contacts.sqlite3` si besoin,
- choix des colonnes visibles dans la table contacts,
- visibilité optionnelle de l'origine des contacts dans la table,
- fiche contact dÃ©taillÃ©e au double-clic avec les mÃ©tadonnÃ©es de source,
- import ACN depuis l'interface,
- ajout d'alias de dataset,
- export JSON des contacts,
- filtrage local du matching et export CSV,
- visualisation et édition de la configuration locale,
- aucun auto-sync réseau au démarrage,
- reviews manuelles encore laissées à la CLI.

## Migration vers Dropbox

1. lancer une fois la CLI ou la GUI pour créer le fichier de config local
2. éditer `config.toml` pour pointer `data_dir` vers un dossier Dropbox partagé
3. copier le contenu actuel de `data/` vers ce dossier partagé
4. relancer `match-my-contacts` ou `match-my-contacts-gui`
5. vérifier que contacts, datasets, alias et exports sont bien retrouvés

Précautions:

- ne pas ouvrir la même base SQLite en même temps sur deux machines
- laisser Dropbox finir la synchronisation avant de changer de machine
- en cas de conflit Dropbox, inspecter d'abord les fichiers `.sqlite3` et les copies conflictuelles avant de continuer

Guide pratique d'utilisation:

```bash
sed -n '1,220p' USAGE.md
```

Fichier de reprise pour une future session Codex:

```bash
sed -n '1,220p' HANDOFF.md
```

Mise Ã  jour GUI rÃ©cente:

- auto-load local des contacts au dÃ©marrage si la base existe dÃ©jÃ 
- bouton `Sync Google` dans l'onglet `Contacts`
- dialog de résumé après `Sync Google`
- bouton `Empty DB...` avec confirmation et purge des reviews de matching
- bouton `VACUUM DB` pour compacter la base locale
- import CSV ciblÃ© pour le vrai format exporté par Google Contacts
- choix persistant des colonnes visibles dans la table contacts
- colonne optionnelle pour afficher l'origine du contact
- fiche contact dÃ©taillÃ©e au double-clic avec les mÃ©tadonnÃ©es de source
- menu `Help` avec `About` et `Credits`

## Roadmap courte

1. Consolider la GUI comme interface locale de pilotage quotidien.
2. Ajouter ensuite la revue manuelle des matches dans la GUI.
3. Garder le moteur métier et la CLI stables pendant cette montée en capacité.
4. Étendre `race_results` à d’autres providers si nécessaire.
