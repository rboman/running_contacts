# running_contacts

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

La première brique `contacts` est en place pour un compte Google:

- OAuth Desktop via Google People API.
- Synchronisation complète réexécutable vers `data/contacts.sqlite3`.
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
- snapshot JSON brut sous `data/raw/acn_timing/`,
- stockage SQLite local dans `data/race_results.sqlite3`,
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
pip install -e .
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

Le fichier d’identifiants peut rester hors du dépôt. Le token OAuth généré par la CLI est stocké localement sous `data/google/token.json` par défaut.
Si `credentials.json` est présent à la racine du dépôt, la commande de sync l’utilise automatiquement.

## Commandes utiles

Tester la CLI:

```bash
running-contacts hello
```

Synchroniser les contacts Google vers SQLite:

```bash
running-contacts contacts sync
running-contacts contacts sync --credentials /chemin/vers/credentials.json
```

Récupérer un tableau de résultats ACN Timing:

```bash
running-contacts race-results fetch-acn --url 'https://www.acn-timing.com/?lng=FR#/events/2157220339092161/ctx/20260412_liege/generic/197994_1/home/LIVE1'
```

Lister les datasets de résultats locaux:

```bash
running-contacts race-results list-datasets
running-contacts race-results add-alias --dataset-id 1 --alias liege-15k-2026
running-contacts race-results list-results --dataset liege-15k-2026 --query dupont
```

Lancer le matching local:

```bash
running-contacts matching run --dataset liege-15k-2026
running-contacts matching list --dataset liege-15k-2026 --team TEAMULIEGE --sort time
running-contacts matching export-csv --dataset liege-15k-2026 --output data/exports/matches.csv
```

Corriger les cas limites:

```bash
running-contacts contacts list --query noel
running-contacts contacts add-alias --contact-id 42 --alias "Jean Noel"
running-contacts matching run --dataset liege-15k-2026 --include-ambiguous --limit 20
running-contacts matching accept --dataset liege-15k-2026 --result-id 1234 --contact-id 42
running-contacts matching reject --dataset liege-15k-2026 --result-id 5678 --note "homonyme"
running-contacts matching list-reviews --dataset liege-15k-2026
```

Lister les contacts locaux:

```bash
running-contacts contacts list
running-contacts contacts list --query dupont
```

Exporter l’état local en JSON:

```bash
running-contacts contacts export-json --output data/exports/contacts.json
```

Lancer les tests:

```bash
pytest -q
```

Lancer la GUI locale:

```bash
running-contacts-gui
```

La GUI actuelle reste volontairement simple, mais elle est déjà utile au quotidien:

- interface desktop locale en PySide6,
- sections `Contacts`, `Race Results` et `Matching`,
- table centrale unique,
- import ACN depuis l'interface,
- ajout d'alias de dataset,
- export JSON des contacts,
- filtrage local du matching et export CSV,
- sync Google et reviews manuelles encore laissées à la CLI.

Guide pratique d'utilisation:

```bash
sed -n '1,220p' USAGE.md
```

Fichier de reprise pour une future session Codex:

```bash
sed -n '1,220p' HANDOFF.md
```

## Roadmap courte

1. Consolider la GUI comme interface locale de pilotage quotidien.
2. Ajouter ensuite la revue manuelle des matches dans la GUI.
3. Garder le moteur métier et la CLI stables pendant cette montée en capacité.
4. Étendre `race_results` à d’autres providers si nécessaire.
