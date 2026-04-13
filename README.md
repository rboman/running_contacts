# running_contacts

## Vision

Ce projet fait partie d’un ensemble d’outils personnels en Python visant à exploiter et croiser différentes sources de données autour de mes contacts.

Objectif global à long terme :
- centraliser mes contacts dans une base locale réutilisable,
- enrichir ces données à partir de différentes sources externes,
- identifier automatiquement des correspondances entre mes contacts et d'autres jeux de données (courses, documents, etc.),
- construire des outils simples pour explorer ces correspondances.

Ce projet est volontairement local, modulaire et orienté réutilisation.

---

## Cas d’usage initial

Identifier quels contacts ont participé à une course à pied (ex: 15 km de Liège Métropole), et obtenir leurs résultats.

Cela implique :
1. récupérer mes contacts (Google Contacts),
2. récupérer les résultats d’une course (scraping ou API),
3. faire correspondre les noms,
4. afficher un résumé exploitable.

---

## Extensions prévues

Le projet est conçu pour être étendu à d’autres cas d’usage similaires :

- analyser des documents (PDF, PV de réunion) pour détecter les mentions de contacts,
- enrichir les contacts avec des informations externes,
- agréger plusieurs sources de résultats sportifs,
- construire des outils d’exploration (CLI, export CSV, etc.).

---

## Philosophie du projet

- Projet **local-first** (pas de backend distant)
- Code **simple, lisible, modulaire**
- Développement **incrémental**
- Réutilisation maximale des modules
- Pas d’overengineering
- Préférence pour la **standard library Python** quand possible

---

## Architecture cible (évolutive)

Le projet est structuré en modules indépendants :

- `contacts/`
  - synchronisation et stockage des contacts (Google, local, etc.)
- `race_results/`
  - récupération et parsing des résultats de course (par provider)
- `matching/`
  - logique de correspondance entre contacts et données externes
- `cli.py`
  - point d’entrée CLI (Typer)

Chaque module doit pouvoir être utilisé indépendamment.

---

## Stockage des données

- Base principale : **SQLite (local)**
- Données brutes : `data/raw/`
- Exports éventuels : JSON / CSV

SQLite est utilisé comme source de vérité locale.

---

## Contraintes techniques

- Python 3.12+
- CLI avec Typer
- Tests avec pytest
- Pas d’ORM au départ (utilisation de `sqlite3`)
- Typage Python encouragé

---

## État actuel

Projet en phase initiale :
- mise en place de la structure
- future implémentation de la base SQLite
- futures commandes CLI de base

---

## Développement avec Codex CLI

Ce projet est développé avec assistance IA (Codex CLI).

Principes importants :
- travailler par petites étapes,
- demander des plans avant les modifications complexes,
- éviter les changements larges ou non demandés,
- privilégier la simplicité.

Les instructions détaillées pour l’agent sont définies dans `AGENTS.md`.

---

## Roadmap (indicative)

1. Initialisation du projet et CLI
2. Ajout SQLite + commandes de base
3. Gestion locale des contacts
4. Intégration Google Contacts
5. Import des résultats de course
6. Matching des noms
7. Export des résultats
8. Extensions (PDF, autres sources)

---

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Usage (temporaire)

```bash
running-contacts hello
```