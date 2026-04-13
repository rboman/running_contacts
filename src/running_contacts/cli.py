from pathlib import Path

import typer

from running_contacts.contacts.service import sync_google_contacts
from running_contacts.contacts.storage import ContactsRepository
from running_contacts.matching.service import export_matches_csv, match_dataset
from running_contacts.race_results.service import fetch_acn_results
from running_contacts.race_results.storage import RaceResultsRepository

app = typer.Typer()
contacts_app = typer.Typer(help="Synchroniser et interroger les contacts locaux.")
race_results_app = typer.Typer(help="Recuperer et interroger les resultats de course locaux.")
matching_app = typer.Typer(help="Croiser les contacts locaux avec des resultats de course locaux.")

DEFAULT_DB_PATH = Path("data/contacts.sqlite3")
DEFAULT_TOKEN_PATH = Path("data/google/token.json")
DEFAULT_EXPORT_PATH = Path("data/exports/contacts.json")
DEFAULT_CREDENTIALS_PATH = Path("credentials.json")
DEFAULT_RACE_DB_PATH = Path("data/race_results.sqlite3")
DEFAULT_RACE_RAW_DIR = Path("data/raw/acn_timing")
DEFAULT_MATCH_EXPORT_PATH = Path("data/exports/matches.csv")


@app.callback()
def main() -> None:
    """CLI principale de running_contacts."""
    pass

@app.command()
def hello() -> None:
    """Teste que la CLI fonctionne."""
    print("running_contacts OK")


@contacts_app.command("sync")
def contacts_sync(
    credentials_path: Path | None = typer.Option(
        None,
        "--credentials",
        file_okay=True,
        dir_okay=False,
        help="Chemin vers le fichier OAuth client secret Google. Par defaut, utilise ./credentials.json si present.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    token_path: Path = typer.Option(
        DEFAULT_TOKEN_PATH,
        "--token-path",
        help="Chemin local pour stocker le token OAuth.",
    ),
    account: str = typer.Option(
        "default",
        "--account",
        help="Nom logique du compte source dans la base locale.",
    ),
) -> None:
    """Synchronise Google Contacts vers SQLite."""
    resolved_credentials_path = credentials_path or DEFAULT_CREDENTIALS_PATH
    if not resolved_credentials_path.exists() or not resolved_credentials_path.is_file():
        raise typer.BadParameter(
            "Google OAuth credentials file not found. "
            "Pass --credentials /path/to/credentials.json or place credentials.json at the repository root."
        )

    stats = sync_google_contacts(
        credentials_path=resolved_credentials_path,
        token_path=token_path,
        db_path=db_path,
        source_account=account,
    )
    typer.echo(
        "Sync completed: "
        f"{stats.fetched_count} fetched, "
        f"{stats.written_count} written, "
        f"{stats.deactivated_count} deactivated."
    )


@contacts_app.command("list")
def contacts_list(
    query: str | None = typer.Option(
        None,
        "--query",
        "-q",
        help="Filtre texte sur le nom, l'email ou le téléphone.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    include_inactive: bool = typer.Option(
        False,
        "--include-inactive",
        help="Inclure les contacts absents de la dernière synchronisation.",
    ),
) -> None:
    """Liste les contacts locaux sans appeler Google."""
    repository = ContactsRepository(db_path)
    repository.initialize()
    contacts = repository.list_contacts(query=query, include_inactive=include_inactive)

    if not contacts:
        typer.echo("No contacts found.")
        raise typer.Exit(code=0)

    for contact in contacts:
        methods = ", ".join(method["value"] for method in contact["methods"])
        aliases = ", ".join(contact["aliases"])
        status = "" if contact["active"] else " [inactive]"
        line = f"{contact['id']}: {contact['display_name']}{status}"
        if methods:
            line = f"{line} - {methods}"
        if aliases:
            line = f"{line} - aliases: {aliases}"
        typer.echo(line)


@contacts_app.command("export-json")
def contacts_export_json(
    output_path: Path = typer.Option(
        DEFAULT_EXPORT_PATH,
        "--output",
        help="Chemin du fichier JSON d'export.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    include_inactive: bool = typer.Option(
        False,
        "--include-inactive",
        help="Inclure les contacts absents de la dernière synchronisation.",
    ),
) -> None:
    """Exporte l'état local des contacts au format JSON."""
    repository = ContactsRepository(db_path)
    repository.initialize()
    export_path = repository.write_export_json(
        output_path=output_path,
        include_inactive=include_inactive,
    )
    typer.echo(f"Exported contacts to {export_path}")


@contacts_app.command("add-alias")
def contacts_add_alias(
    contact_id: int = typer.Option(..., "--contact-id", help="Identifiant local du contact."),
    alias_text: str = typer.Option(..., "--alias", help="Alias a ajouter pour ce contact."),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Ajoute un alias manuel a un contact local."""
    repository = ContactsRepository(db_path)
    repository.initialize()
    repository.add_alias(contact_id=contact_id, alias_text=alias_text)
    typer.echo(f"Added alias to contact {contact_id}: {alias_text}")


@contacts_app.command("remove-alias")
def contacts_remove_alias(
    contact_id: int = typer.Option(..., "--contact-id", help="Identifiant local du contact."),
    alias_text: str = typer.Option(..., "--alias", help="Alias a supprimer."),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Supprime un alias manuel d'un contact local."""
    repository = ContactsRepository(db_path)
    repository.initialize()
    removed = repository.remove_alias(contact_id=contact_id, alias_text=alias_text)
    if not removed:
        typer.echo("Alias not found.")
        raise typer.Exit(code=1)
    typer.echo(f"Removed alias from contact {contact_id}: {alias_text}")


@contacts_app.command("list-aliases")
def contacts_list_aliases(
    contact_id: int | None = typer.Option(
        None,
        "--contact-id",
        help="Limiter l'affichage a un contact.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Liste les alias manuels enregistres."""
    repository = ContactsRepository(db_path)
    repository.initialize()
    aliases = repository.list_aliases(contact_id=contact_id)
    if not aliases:
        typer.echo("No aliases found.")
        raise typer.Exit(code=0)
    for alias in aliases:
        typer.echo(f"{alias['contact_id']}: {alias['contact_name']} -> {alias['alias_text']}")


app.add_typer(contacts_app, name="contacts")


@race_results_app.command("fetch-acn")
def race_results_fetch_acn(
    url: str = typer.Option(
        ...,
        "--url",
        help="URL publique ACN Timing de la course ou du tableau de resultats.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
    raw_dir: Path = typer.Option(
        DEFAULT_RACE_RAW_DIR,
        "--raw-dir",
        help="Dossier de snapshots JSON bruts.",
    ),
) -> None:
    """Recupere une course ACN Timing et la stocke localement."""
    stats = fetch_acn_results(url=url, db_path=db_path, raw_dir=raw_dir)
    typer.echo(
        f"Fetched ACN dataset {stats.dataset_id} with {stats.results_count} result rows."
    )


@race_results_app.command("list-datasets")
def race_results_list_datasets(
    db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Liste les jeux de resultats disponibles localement."""
    repository = RaceResultsRepository(db_path)
    repository.initialize()
    datasets = repository.list_datasets()

    if not datasets:
        typer.echo("No race datasets found.")
        raise typer.Exit(code=0)

    for dataset in datasets:
        typer.echo(
            f"{dataset['id']}: {dataset['event_title']} "
            f"({dataset['event_date']}, {dataset['event_location']}) "
            f"[{dataset['context_db']}/{dataset['report_key']}] "
            f"- {dataset['total_results']} rows"
        )


@race_results_app.command("list-results")
def race_results_list_results(
    dataset_id: int = typer.Option(
        ...,
        "--dataset-id",
        help="Identifiant local du dataset a afficher.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
    query: str | None = typer.Option(
        None,
        "--query",
        "-q",
        help="Filtre texte sur le nom, l'equipe ou le dossard.",
    ),
    limit: int = typer.Option(
        20,
        "--limit",
        min=1,
        help="Nombre maximal de lignes a afficher.",
    ),
) -> None:
    """Liste des resultats deja stockes localement."""
    repository = RaceResultsRepository(db_path)
    repository.initialize()
    results = repository.list_results(dataset_id=dataset_id, query=query, limit=limit)

    if not results:
        typer.echo("No race results found.")
        raise typer.Exit(code=0)

    for result in results:
        parts = [
            f"#{result['id']}",
            result["position_text"] or "-",
            result["athlete_name"],
        ]
        if result["finish_time"]:
            parts.append(result["finish_time"])
        if result["team"]:
            parts.append(result["team"])
        if result["bib"]:
            parts.append(f"bib {result['bib']}")
        typer.echo(" | ".join(parts))


@race_results_app.command("export-json")
def race_results_export_json(
    dataset_id: int = typer.Option(
        ...,
        "--dataset-id",
        help="Identifiant local du dataset a exporter.",
    ),
    output_path: Path = typer.Option(
        Path("data/exports/race_results.json"),
        "--output",
        help="Chemin du fichier JSON d'export.",
    ),
    db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Exporte un dataset de resultats au format JSON."""
    repository = RaceResultsRepository(db_path)
    repository.initialize()
    export_path = repository.write_export_json(dataset_id=dataset_id, output_path=output_path)
    typer.echo(f"Exported race dataset to {export_path}")


app.add_typer(race_results_app, name="race-results")


@matching_app.command("run")
def matching_run(
    dataset_id: int = typer.Option(
        ...,
        "--dataset-id",
        help="Identifiant local du dataset de resultats a comparer.",
    ),
    contacts_db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
    min_score: float = typer.Option(
        95.0,
        "--min-score",
        min=0.0,
        max=100.0,
        help="Score fuzzy minimal pour accepter un match.",
    ),
    min_gap: float = typer.Option(
        3.0,
        "--min-gap",
        min=0.0,
        max=100.0,
        help="Ecart minimal entre le meilleur et le deuxieme candidat.",
    ),
    include_ambiguous: bool = typer.Option(
        False,
        "--include-ambiguous",
        help="Afficher aussi les candidats ambigus non acceptes automatiquement.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        min=1,
        help="Limiter le nombre de lignes affichees.",
    ),
) -> None:
    """Croise un dataset de course avec les contacts locaux."""
    report = match_dataset(
        contacts_db_path=contacts_db_path,
        results_db_path=results_db_path,
        dataset_id=dataset_id,
        min_score=min_score,
        min_gap=min_gap,
    )

    typer.echo(
        f"Dataset {dataset_id}: {report.dataset['event_title']} "
        f"({report.dataset['event_date']}, {report.dataset['event_location']})"
    )
    typer.echo(
        f"{len(report.accepted_matches)} accepted matches, "
        f"{len(report.ambiguous_matches)} ambiguous, "
        f"{report.unmatched_count} unmatched "
        f"across {report.results_count} results and {report.contacts_count} contacts."
    )
    if report.reviewed_rejections_count:
        typer.echo(f"{report.reviewed_rejections_count} results were explicitly rejected by review.")

    displayed = report.accepted_matches[:limit] if limit else report.accepted_matches
    if not displayed:
        typer.echo("No accepted matches found.")
    else:
        for match in displayed:
            parts = [
                f"#{match.result_id}",
                match.position_text or "-",
                match.athlete_name,
                "->",
                f"{match.contact_name or '?'} (contact {match.contact_id})" if match.contact_id else (match.contact_name or "?"),
                f"{match.match_method}:{match.score:.1f}",
            ]
            if match.finish_time:
                parts.append(match.finish_time)
            if match.team:
                parts.append(match.team)
            typer.echo(" | ".join(parts))

    if include_ambiguous and report.ambiguous_matches:
        typer.echo("Ambiguous candidates:")
        ambiguous_displayed = report.ambiguous_matches[:limit] if limit else report.ambiguous_matches
        for match in ambiguous_displayed:
            typer.echo(
                f"result {match.result_id}: {match.athlete_name} -> "
                f"{match.contact_name or '?'}"
                f"{f' (contact {match.contact_id})' if match.contact_id else ''} "
                f"(score {match.score:.1f}, gap {match.confidence_gap:.1f})"
            )


@matching_app.command("export-csv")
def matching_export_csv(
    dataset_id: int = typer.Option(
        ...,
        "--dataset-id",
        help="Identifiant local du dataset de resultats a comparer.",
    ),
    output_path: Path = typer.Option(
        DEFAULT_MATCH_EXPORT_PATH,
        "--output",
        help="Chemin du fichier CSV a produire.",
    ),
    contacts_db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
    min_score: float = typer.Option(
        95.0,
        "--min-score",
        min=0.0,
        max=100.0,
        help="Score fuzzy minimal pour accepter un match.",
    ),
    min_gap: float = typer.Option(
        3.0,
        "--min-gap",
        min=0.0,
        max=100.0,
        help="Ecart minimal entre le meilleur et le deuxieme candidat.",
    ),
) -> None:
    """Exporte les matches acceptes au format CSV."""
    report = match_dataset(
        contacts_db_path=contacts_db_path,
        results_db_path=results_db_path,
        dataset_id=dataset_id,
        min_score=min_score,
        min_gap=min_gap,
    )
    export_path = export_matches_csv(report=report, output_path=output_path)
    typer.echo(
        f"Exported {len(report.accepted_matches)} matches to {export_path}"
    )


@matching_app.command("accept")
def matching_accept(
    dataset_id: int = typer.Option(..., "--dataset-id", help="Identifiant local du dataset."),
    result_id: int = typer.Option(..., "--result-id", help="Identifiant local du resultat."),
    contact_id: int = typer.Option(..., "--contact-id", help="Identifiant local du contact."),
    note: str | None = typer.Option(None, "--note", help="Note libre de revue."),
    contacts_db_path: Path = typer.Option(
        DEFAULT_DB_PATH,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Force un match manuel entre un resultat et un contact."""
    contacts_repository = ContactsRepository(contacts_db_path)
    contacts_repository.initialize()
    contact = contacts_repository.get_contact(contact_id=contact_id)

    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    results_repository.set_match_review(
        dataset_id=dataset_id,
        result_id=result_id,
        status="accepted",
        contact_id=contact_id,
        note=note,
    )
    typer.echo(
        f"Accepted review for result {result_id}: contact {contact['id']} ({contact['display_name']})"
    )


@matching_app.command("reject")
def matching_reject(
    dataset_id: int = typer.Option(..., "--dataset-id", help="Identifiant local du dataset."),
    result_id: int = typer.Option(..., "--result-id", help="Identifiant local du resultat."),
    note: str | None = typer.Option(None, "--note", help="Note libre de revue."),
    results_db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Marque un resultat comme non-match manuel."""
    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    results_repository.set_match_review(
        dataset_id=dataset_id,
        result_id=result_id,
        status="rejected",
        contact_id=None,
        note=note,
    )
    typer.echo(f"Rejected review for result {result_id}")


@matching_app.command("clear-review")
def matching_clear_review(
    dataset_id: int = typer.Option(..., "--dataset-id", help="Identifiant local du dataset."),
    result_id: int = typer.Option(..., "--result-id", help="Identifiant local du resultat."),
    results_db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Supprime une revue manuelle sur un resultat."""
    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    cleared = results_repository.clear_match_review(dataset_id=dataset_id, result_id=result_id)
    if not cleared:
        typer.echo("Review not found.")
        raise typer.Exit(code=1)
    typer.echo(f"Cleared review for result {result_id}")


@matching_app.command("list-reviews")
def matching_list_reviews(
    dataset_id: int = typer.Option(..., "--dataset-id", help="Identifiant local du dataset."),
    results_db_path: Path = typer.Option(
        DEFAULT_RACE_DB_PATH,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Liste les revues manuelles enregistrees."""
    results_repository = RaceResultsRepository(results_db_path)
    results_repository.initialize()
    reviews = results_repository.list_match_reviews(dataset_id=dataset_id)
    if not reviews:
        typer.echo("No reviews found.")
        raise typer.Exit(code=0)
    for review in reviews:
        suffix = f" -> contact {review['contact_id']}" if review["contact_id"] else ""
        note = f" [{review['note']}]" if review["note"] else ""
        typer.echo(
            f"result {review['result_id']}: {review['athlete_name']} - {review['status']}{suffix}{note}"
        )


app.add_typer(matching_app, name="matching")


if __name__ == "__main__":
    app()
