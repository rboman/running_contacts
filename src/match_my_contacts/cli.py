from pathlib import Path

import typer

from match_my_contacts.config import AppPaths, default_credentials_path, get_app_paths
from match_my_contacts.contacts.service import (
    empty_contacts_database,
    ensure_google_credentials_file,
    import_google_contacts_csv,
    resolve_google_sync_paths,
    sync_google_contacts,
    vacuum_contacts_database,
)
from match_my_contacts.contacts.storage import ContactsRepository
from match_my_contacts.matching.service import (
    export_selected_matches_csv,
    filter_and_sort_matches,
    match_dataset,
    select_matches,
)
from match_my_contacts.race_results.service import fetch_acn_results
from match_my_contacts.race_results.storage import RaceResultsRepository

app = typer.Typer()
contacts_app = typer.Typer(help="Synchroniser et interroger les contacts locaux.")
race_results_app = typer.Typer(help="Recuperer et interroger les resultats de course locaux.")
matching_app = typer.Typer(help="Croiser les contacts locaux avec des resultats de course locaux.")
config_app = typer.Typer(help="Inspecter la configuration locale et les chemins resolves.")

SORT_OPTIONS = ["position", "time", "athlete", "contact", "team", "score"]
STATUS_OPTIONS = ["accepted", "ambiguous", "all"]


@app.callback()
def main() -> None:
    """CLI principale de match_my_contacts."""
    return None

@app.command()
def hello() -> None:
    """Teste que la CLI fonctionne."""
    print("match-my-contacts OK")


@config_app.command("show")
def config_show() -> None:
    """Affiche la configuration locale et les chemins resolus."""
    app_paths = _app_paths()
    fallback_credentials_path = default_credentials_path()
    typer.echo(f"config_path: {app_paths.config_path}")
    typer.echo(f"data_dir: {app_paths.data_dir}")
    typer.echo(f"contacts_db: {app_paths.contacts_db}")
    typer.echo(f"race_results_db: {app_paths.race_results_db}")
    typer.echo(f"google_token: {app_paths.google_token}")
    typer.echo(f"raw_acn_dir: {app_paths.raw_acn_dir}")
    typer.echo(f"contacts_export_json: {app_paths.contacts_export_json}")
    typer.echo(f"race_results_export_json: {app_paths.race_results_export_json}")
    typer.echo(f"matches_export_csv: {app_paths.matches_export_csv}")
    if app_paths.credentials_path is not None:
        typer.echo(f"credentials_path: {app_paths.credentials_path}")
    else:
        typer.echo(f"credentials_path: {fallback_credentials_path} (fallback)")


def _resolve_dataset_id(
    *,
    repository: RaceResultsRepository,
    dataset: str | None,
    dataset_id: int | None,
) -> int:
    if dataset and dataset_id is not None:
        raise typer.BadParameter("Use either --dataset or --dataset-id, not both.")
    if dataset:
        try:
            return repository.resolve_dataset_selector(dataset)
        except KeyError as exc:
            raise typer.BadParameter(str(exc)) from exc
    if dataset_id is not None:
        return dataset_id
    raise typer.BadParameter("Missing dataset selector. Use --dataset or --dataset-id.")


def _validate_option(value: str, *, allowed: list[str], option_name: str) -> str:
    lowered = value.lower()
    if lowered not in allowed:
        raise typer.BadParameter(
            f"Invalid value for {option_name}: {value}. Allowed values: {', '.join(allowed)}."
        )
    return lowered


def _app_paths() -> AppPaths:
    return get_app_paths()


def _run_contacts_sync_google(
    *,
    credentials_path: Path | None = typer.Option(
        None,
        "--credentials",
        file_okay=True,
        dir_okay=False,
        help="Chemin vers le fichier OAuth client secret Google. Par defaut, utilise credentials.json a la racine du projet si present.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    token_path: Path | None = typer.Option(
        None,
        "--token-path",
        help="Chemin local pour stocker le token OAuth.",
    ),
    account: str = typer.Option(
        "default",
        "--account",
        help="Nom logique du compte source dans la base locale.",
    ),
) -> None:
    app_paths = _app_paths()
    resolved_paths = resolve_google_sync_paths(
        app_paths=app_paths,
        db_path=db_path,
        token_path=token_path,
        credentials_path=credentials_path,
    )
    try:
        ensure_google_credentials_file(resolved_paths.credentials_path)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc

    stats = sync_google_contacts(
        credentials_path=resolved_paths.credentials_path,
        token_path=resolved_paths.token_path,
        db_path=resolved_paths.db_path,
        source_account=account,
    )
    typer.echo(
        "Sync completed: "
        f"{stats.fetched_count} fetched, "
        f"{stats.written_count} written, "
        f"{stats.deactivated_count} deactivated."
    )


@contacts_app.command("sync")
def contacts_sync(
    credentials_path: Path | None = typer.Option(
        None,
        "--credentials",
        file_okay=True,
        dir_okay=False,
        help="Chemin vers le fichier OAuth client secret Google. Par defaut, utilise credentials.json a la racine du projet si present.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    token_path: Path | None = typer.Option(
        None,
        "--token-path",
        help="Chemin local pour stocker le token OAuth.",
    ),
    account: str = typer.Option(
        "default",
        "--account",
        help="Nom logique du compte source dans la base locale.",
    ),
) -> None:
    """Alias retrocompatible pour la synchronisation Google Contacts."""
    _run_contacts_sync_google(
        credentials_path=credentials_path,
        db_path=db_path,
        token_path=token_path,
        account=account,
    )


@contacts_app.command("sync-google")
def contacts_sync_google(
    credentials_path: Path | None = typer.Option(
        None,
        "--credentials",
        file_okay=True,
        dir_okay=False,
        help="Chemin vers le fichier OAuth client secret Google. Par defaut, utilise credentials.json a la racine du projet si present.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    token_path: Path | None = typer.Option(
        None,
        "--token-path",
        help="Chemin local pour stocker le token OAuth.",
    ),
    account: str = typer.Option(
        "default",
        "--account",
        help="Nom logique du compte source dans la base locale.",
    ),
) -> None:
    """Synchronise explicitement Google Contacts vers SQLite."""
    _run_contacts_sync_google(
        credentials_path=credentials_path,
        db_path=db_path,
        token_path=token_path,
        account=account,
    )


@contacts_app.command("import-google-csv")
def contacts_import_google_csv(
    csv_path: Path = typer.Option(
        ...,
        "--csv-path",
        file_okay=True,
        dir_okay=False,
        exists=True,
        help="Chemin vers un export CSV Google Contacts.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    account: str = typer.Option(
        "default",
        "--account",
        help="Nom logique du slot d'import pour cette source.",
    ),
) -> None:
    """Importe un export CSV Google Contacts dans SQLite."""
    try:
        stats = import_google_contacts_csv(
            csv_path=csv_path,
            db_path=db_path or _app_paths().contacts_db,
            source_account=account,
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=2)
    typer.echo(
        "Import completed: "
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
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
    include_inactive: bool = typer.Option(
        False,
        "--include-inactive",
        help="Inclure les contacts absents de la dernière synchronisation.",
    ),
    source: str | None = typer.Option(
        None,
        "--source",
        help="Filtrer sur une source precise, par exemple google_people ou google_contacts_csv.",
    ),
) -> None:
    """Liste les contacts locaux sans appeler Google."""
    repository = ContactsRepository(db_path or _app_paths().contacts_db)
    repository.initialize()
    contacts = repository.list_contacts(query=query, include_inactive=include_inactive, source=source)

    if not contacts:
        typer.echo("No contacts found.")
        raise typer.Exit(code=0)

    for contact in contacts:
        methods = ", ".join(method["value"] for method in contact["methods"])
        aliases = ", ".join(contact["aliases"])
        status = "" if contact["active"] else " [inactive]"
        line = f"{contact['id']}: {contact['display_name']}{status} [{contact['source_display']}]"
        if methods:
            line = f"{line} - {methods}"
        if aliases:
            line = f"{line} - aliases: {aliases}"
        typer.echo(line)


@contacts_app.command("list-sources")
def contacts_list_sources(
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Liste les sources contacts connues, leurs volumes et leur dernier run."""
    repository = ContactsRepository(db_path or _app_paths().contacts_db)
    repository.initialize()
    sources = repository.list_source_summaries()

    if not sources:
        typer.echo("No contact sources found.")
        raise typer.Exit(code=0)

    for source_summary in sources:
        line = (
            f"{source_summary['source']}/{source_summary['source_account']}: "
            f"{source_summary['source_label']} "
            f"[{source_summary['source_behavior']}] - "
            f"{source_summary['active_contacts']} active, "
            f"{source_summary['inactive_contacts']} inactive"
        )
        if source_summary["last_run_id"] is not None:
            line = (
                f"{line} - last run #{source_summary['last_run_id']} "
                f"{source_summary['last_run_status']}"
            )
            if source_summary["last_run_completed_at"]:
                line = f"{line} at {source_summary['last_run_completed_at']}"
        typer.echo(line)


@contacts_app.command("empty-db")
def contacts_empty_db(
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des contacts.",
    ),
    results_db_path: Path | None = typer.Option(
        None,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats, pour purger aussi les reviews de matching.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Confirmer sans prompt interactif.",
    ),
) -> None:
    """Vide la base contacts locale et purge les reviews de matching associees."""
    app_paths = _app_paths()
    resolved_contacts_db = db_path or app_paths.contacts_db
    resolved_results_db = results_db_path or app_paths.race_results_db

    warning_message = (
        f"This will permanently empty {resolved_contacts_db}, delete contacts, methods, aliases, "
        "and sync history, reset local contact IDs, and delete matching reviews from "
        f"{resolved_results_db}. Race datasets and race results will be kept. Continue?"
    )
    if not yes and not typer.confirm(warning_message):
        typer.echo("Empty DB cancelled.")
        raise typer.Exit(code=0)

    stats = empty_contacts_database(
        db_path=resolved_contacts_db,
        results_db_path=resolved_results_db,
    )
    typer.echo(
        "Empty DB completed: "
        f"{stats.contacts_deleted} contacts, "
        f"{stats.methods_deleted} methods, "
        f"{stats.aliases_deleted} aliases, "
        f"{stats.sync_runs_deleted} sync runs, "
        f"{stats.match_reviews_deleted} matching reviews deleted. "
        f"IDs reset: {'yes' if stats.ids_reset else 'no'}."
    )


@contacts_app.command("vacuum-db")
def contacts_vacuum_db(
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des contacts.",
    ),
) -> None:
    """Compacte la base contacts locale avec SQLite VACUUM."""
    resolved_db_path = db_path or _app_paths().contacts_db
    stats = vacuum_contacts_database(db_path=resolved_db_path)
    typer.echo(
        "VACUUM completed: "
        f"{stats.before_size_bytes} bytes before, "
        f"{stats.after_size_bytes} bytes after, "
        f"{stats.reclaimed_bytes} bytes reclaimed."
    )


@contacts_app.command("export-json")
def contacts_export_json(
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help="Chemin du fichier JSON d'export.",
    ),
    db_path: Path | None = typer.Option(
        None,
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
    app_paths = _app_paths()
    repository = ContactsRepository(db_path or app_paths.contacts_db)
    repository.initialize()
    export_path = repository.write_export_json(
        output_path=output_path or app_paths.contacts_export_json,
        include_inactive=include_inactive,
    )
    typer.echo(f"Exported contacts to {export_path}")


@contacts_app.command("add-alias")
def contacts_add_alias(
    contact_id: int = typer.Option(..., "--contact-id", help="Identifiant local du contact."),
    alias_text: str = typer.Option(..., "--alias", help="Alias a ajouter pour ce contact."),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Ajoute un alias manuel a un contact local."""
    repository = ContactsRepository(db_path or _app_paths().contacts_db)
    repository.initialize()
    repository.add_alias(contact_id=contact_id, alias_text=alias_text)
    typer.echo(f"Added alias to contact {contact_id}: {alias_text}")


@contacts_app.command("remove-alias")
def contacts_remove_alias(
    contact_id: int = typer.Option(..., "--contact-id", help="Identifiant local du contact."),
    alias_text: str = typer.Option(..., "--alias", help="Alias a supprimer."),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Supprime un alias manuel d'un contact local."""
    repository = ContactsRepository(db_path or _app_paths().contacts_db)
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
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale.",
    ),
) -> None:
    """Liste les alias manuels enregistres."""
    repository = ContactsRepository(db_path or _app_paths().contacts_db)
    repository.initialize()
    aliases = repository.list_aliases(contact_id=contact_id)
    if not aliases:
        typer.echo("No aliases found.")
        raise typer.Exit(code=0)
    for alias in aliases:
        typer.echo(f"{alias['contact_id']}: {alias['contact_name']} -> {alias['alias_text']}")


app.add_typer(contacts_app, name="contacts")
app.add_typer(config_app, name="config")


@race_results_app.command("fetch-acn")
def race_results_fetch_acn(
    url: str = typer.Option(
        ...,
        "--url",
        help="URL publique ACN Timing de la course ou du tableau de resultats.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
    raw_dir: Path | None = typer.Option(
        None,
        "--raw-dir",
        help="Dossier de snapshots JSON bruts.",
    ),
) -> None:
    """Recupere une course ACN Timing et la stocke localement."""
    app_paths = _app_paths()
    stats = fetch_acn_results(
        url=url,
        db_path=db_path or app_paths.race_results_db,
        raw_dir=raw_dir or app_paths.raw_acn_dir,
    )
    typer.echo(
        f"Fetched ACN dataset {stats.dataset_id} with {stats.results_count} result rows."
    )


@race_results_app.command("list-datasets")
def race_results_list_datasets(
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Liste les jeux de resultats disponibles localement."""
    repository = RaceResultsRepository(db_path or _app_paths().race_results_db)
    repository.initialize()
    datasets = repository.list_datasets()

    if not datasets:
        typer.echo("No race datasets found.")
        raise typer.Exit(code=0)

    for dataset in datasets:
        aliases = ", ".join(dataset["aliases"])
        typer.echo(
            f"{dataset['id']}: {dataset['event_title']} "
            f"({dataset['event_date']}, {dataset['event_location']}) "
            f"[{dataset['context_db']}/{dataset['report_key']}] "
            f"- {dataset['total_results']} rows"
            f"{f' - aliases: {aliases}' if aliases else ''}"
        )


@race_results_app.command("add-alias")
def race_results_add_alias(
    dataset_id: int = typer.Option(..., "--dataset-id", help="Identifiant local du dataset."),
    alias_text: str = typer.Option(..., "--alias", help="Alias a associer a cette course."),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Ajoute un alias manuel a une course locale."""
    repository = RaceResultsRepository(db_path or _app_paths().race_results_db)
    repository.initialize()
    repository.add_dataset_alias(dataset_id=dataset_id, alias_text=alias_text)
    typer.echo(f"Added alias to dataset {dataset_id}: {alias_text}")


@race_results_app.command("remove-alias")
def race_results_remove_alias(
    alias_text: str = typer.Option(..., "--alias", help="Alias a supprimer."),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Supprime un alias manuel de course."""
    repository = RaceResultsRepository(db_path or _app_paths().race_results_db)
    repository.initialize()
    removed = repository.remove_dataset_alias(alias_text=alias_text)
    if not removed:
        typer.echo("Alias not found.")
        raise typer.Exit(code=1)
    typer.echo(f"Removed dataset alias: {alias_text}")


@race_results_app.command("list-aliases")
def race_results_list_aliases(
    dataset_id: int | None = typer.Option(
        None,
        "--dataset-id",
        help="Limiter l'affichage a une course.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Liste les alias de courses enregistres."""
    repository = RaceResultsRepository(db_path or _app_paths().race_results_db)
    repository.initialize()
    aliases = repository.list_dataset_aliases(dataset_id=dataset_id)
    if not aliases:
        typer.echo("No dataset aliases found.")
        raise typer.Exit(code=0)
    for alias in aliases:
        typer.echo(
            f"{alias['dataset_id']}: {alias['event_title']} ({alias['event_date']}) -> {alias['alias_text']}"
        )


@race_results_app.command("list-results")
def race_results_list_results(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Identifiant ou alias local du dataset a afficher.",
    ),
    dataset_id: int | None = typer.Option(
        None,
        "--dataset-id",
        help="Compat: identifiant local du dataset a afficher.",
    ),
    db_path: Path | None = typer.Option(
        None,
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
    repository = RaceResultsRepository(db_path or _app_paths().race_results_db)
    repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=repository, dataset=dataset, dataset_id=dataset_id)
    results = repository.list_results(dataset_id=resolved_dataset_id, query=query, limit=limit)

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
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Identifiant ou alias local du dataset a exporter.",
    ),
    dataset_id: int | None = typer.Option(
        None,
        "--dataset-id",
        help="Compat: identifiant local du dataset a exporter.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help="Chemin du fichier JSON d'export.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db-path",
        help="Chemin vers la base SQLite locale des resultats.",
    ),
) -> None:
    """Exporte un dataset de resultats au format JSON."""
    app_paths = _app_paths()
    repository = RaceResultsRepository(db_path or app_paths.race_results_db)
    repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=repository, dataset=dataset, dataset_id=dataset_id)
    export_path = repository.write_export_json(
        dataset_id=resolved_dataset_id,
        output_path=output_path or app_paths.race_results_export_json,
    )
    typer.echo(f"Exported race dataset to {export_path}")


app.add_typer(race_results_app, name="race-results")


@matching_app.command("run")
def matching_run(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Identifiant ou alias local du dataset de resultats.",
    ),
    dataset_id: int | None = typer.Option(
        None,
        "--dataset-id",
        help="Compat: identifiant local du dataset de resultats a comparer.",
    ),
    contacts_db_path: Path | None = typer.Option(
        None,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path | None = typer.Option(
        None,
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
    app_paths = _app_paths()
    resolved_contacts_db_path = contacts_db_path or app_paths.contacts_db
    resolved_results_db_path = results_db_path or app_paths.race_results_db
    results_repository = RaceResultsRepository(resolved_results_db_path)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    report = match_dataset(
        contacts_db_path=resolved_contacts_db_path,
        results_db_path=resolved_results_db_path,
        dataset_id=resolved_dataset_id,
        min_score=min_score,
        min_gap=min_gap,
    )

    typer.echo(
        f"Dataset {resolved_dataset_id}: {report.dataset['event_title']} "
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


@matching_app.command("list")
def matching_list(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Identifiant ou alias local du dataset de resultats.",
    ),
    dataset_id: int | None = typer.Option(
        None,
        "--dataset-id",
        help="Compat: identifiant local du dataset de resultats.",
    ),
    contacts_db_path: Path | None = typer.Option(
        None,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path | None = typer.Option(
        None,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
    status: str = typer.Option(
        "accepted",
        "--status",
        help="accepted, ambiguous, all",
    ),
    sort_by: str = typer.Option(
        "position",
        "--sort",
        help="position, time, athlete, contact, team, score",
    ),
    desc: bool = typer.Option(False, "--desc", help="Tri descendant."),
    team: str | None = typer.Option(None, "--team", help="Filtre sur l'equipe."),
    name_query: str | None = typer.Option(None, "--name-query", help="Filtre sur nom resultat/contact."),
    category: str | None = typer.Option(None, "--category", help="Filtre sur la categorie."),
    reviewed_only: bool = typer.Option(False, "--reviewed-only", help="Limiter aux matches revus manuellement."),
    limit: int | None = typer.Option(None, "--limit", min=1, help="Limiter le nombre de lignes affichees."),
    min_score: float = typer.Option(95.0, "--min-score", min=0.0, max=100.0, help="Score fuzzy minimal."),
    min_gap: float = typer.Option(3.0, "--min-gap", min=0.0, max=100.0, help="Ecart minimal entre candidats."),
) -> None:
    """Liste les matches avec tri et filtres."""
    app_paths = _app_paths()
    resolved_contacts_db_path = contacts_db_path or app_paths.contacts_db
    resolved_results_db_path = results_db_path or app_paths.race_results_db
    status = _validate_option(status, allowed=STATUS_OPTIONS, option_name="--status")
    sort_by = _validate_option(sort_by, allowed=SORT_OPTIONS, option_name="--sort")
    results_repository = RaceResultsRepository(resolved_results_db_path)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    report = match_dataset(
        contacts_db_path=resolved_contacts_db_path,
        results_db_path=resolved_results_db_path,
        dataset_id=resolved_dataset_id,
        min_score=min_score,
        min_gap=min_gap,
    )
    matches = filter_and_sort_matches(
        select_matches(report, status=status),
        name_query=name_query,
        team=team,
        category=category,
        reviewed_only=reviewed_only,
        sort_by=sort_by,
        descending=desc,
    )
    if limit:
        matches = matches[:limit]

    if not matches:
        typer.echo("No matches found.")
        raise typer.Exit(code=0)

    for match in matches:
        parts = [
            f"#{match.result_id}",
            match.position_text or "-",
            match.athlete_name,
            "->",
            f"{match.contact_name or '?'}{f' (contact {match.contact_id})' if match.contact_id else ''}",
            f"{match.match_method}:{match.score:.1f}",
        ]
        if match.finish_time:
            parts.append(match.finish_time)
        if match.team:
            parts.append(match.team)
        if match.category:
            parts.append(match.category)
        typer.echo(" | ".join(parts))


@matching_app.command("export-csv")
def matching_export_csv(
    dataset: str | None = typer.Option(
        None,
        "--dataset",
        help="Identifiant ou alias local du dataset de resultats.",
    ),
    dataset_id: int | None = typer.Option(
        None,
        "--dataset-id",
        help="Compat: identifiant local du dataset de resultats a comparer.",
    ),
    output_path: Path | None = typer.Option(
        None,
        "--output",
        help="Chemin du fichier CSV a produire.",
    ),
    contacts_db_path: Path | None = typer.Option(
        None,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path | None = typer.Option(
        None,
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
    status: str = typer.Option(
        "accepted",
        "--status",
        help="accepted, ambiguous, all",
    ),
    sort_by: str = typer.Option(
        "position",
        "--sort",
        help="position, time, athlete, contact, team, score",
    ),
    desc: bool = typer.Option(False, "--desc", help="Tri descendant."),
    team: str | None = typer.Option(None, "--team", help="Filtre sur l'equipe."),
    name_query: str | None = typer.Option(None, "--name-query", help="Filtre sur nom resultat/contact."),
    category: str | None = typer.Option(None, "--category", help="Filtre sur la categorie."),
    reviewed_only: bool = typer.Option(False, "--reviewed-only", help="Limiter aux matches revus manuellement."),
) -> None:
    """Exporte les matches acceptes au format CSV."""
    app_paths = _app_paths()
    resolved_contacts_db_path = contacts_db_path or app_paths.contacts_db
    resolved_results_db_path = results_db_path or app_paths.race_results_db
    status = _validate_option(status, allowed=STATUS_OPTIONS, option_name="--status")
    sort_by = _validate_option(sort_by, allowed=SORT_OPTIONS, option_name="--sort")
    results_repository = RaceResultsRepository(resolved_results_db_path)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    report = match_dataset(
        contacts_db_path=resolved_contacts_db_path,
        results_db_path=resolved_results_db_path,
        dataset_id=resolved_dataset_id,
        min_score=min_score,
        min_gap=min_gap,
    )
    matches = filter_and_sort_matches(
        select_matches(report, status=status),
        name_query=name_query,
        team=team,
        category=category,
        reviewed_only=reviewed_only,
        sort_by=sort_by,
        descending=desc,
    )
    export_path = export_selected_matches_csv(
        matches=matches,
        output_path=output_path or app_paths.matches_export_csv,
    )
    typer.echo(
        f"Exported {len(matches)} matches to {export_path}"
    )


@matching_app.command("accept")
def matching_accept(
    dataset: str | None = typer.Option(None, "--dataset", help="Identifiant ou alias local du dataset."),
    dataset_id: int | None = typer.Option(None, "--dataset-id", help="Compat: identifiant local du dataset."),
    result_id: int = typer.Option(..., "--result-id", help="Identifiant local du resultat."),
    contact_id: int = typer.Option(..., "--contact-id", help="Identifiant local du contact."),
    note: str | None = typer.Option(None, "--note", help="Note libre de revue."),
    contacts_db_path: Path | None = typer.Option(
        None,
        "--contacts-db-path",
        help="Chemin vers la base SQLite des contacts.",
    ),
    results_db_path: Path | None = typer.Option(
        None,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Force un match manuel entre un resultat et un contact."""
    app_paths = _app_paths()
    resolved_contacts_db_path = contacts_db_path or app_paths.contacts_db
    resolved_results_db_path = results_db_path or app_paths.race_results_db
    contacts_repository = ContactsRepository(resolved_contacts_db_path)
    contacts_repository.initialize()
    contact = contacts_repository.get_contact(contact_id=contact_id)

    results_repository = RaceResultsRepository(resolved_results_db_path)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    results_repository.set_match_review(
        dataset_id=resolved_dataset_id,
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
    dataset: str | None = typer.Option(None, "--dataset", help="Identifiant ou alias local du dataset."),
    dataset_id: int | None = typer.Option(None, "--dataset-id", help="Compat: identifiant local du dataset."),
    result_id: int = typer.Option(..., "--result-id", help="Identifiant local du resultat."),
    note: str | None = typer.Option(None, "--note", help="Note libre de revue."),
    results_db_path: Path | None = typer.Option(
        None,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Marque un resultat comme non-match manuel."""
    results_repository = RaceResultsRepository(results_db_path or _app_paths().race_results_db)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    results_repository.set_match_review(
        dataset_id=resolved_dataset_id,
        result_id=result_id,
        status="rejected",
        contact_id=None,
        note=note,
    )
    typer.echo(f"Rejected review for result {result_id}")


@matching_app.command("clear-review")
def matching_clear_review(
    dataset: str | None = typer.Option(None, "--dataset", help="Identifiant ou alias local du dataset."),
    dataset_id: int | None = typer.Option(None, "--dataset-id", help="Compat: identifiant local du dataset."),
    result_id: int = typer.Option(..., "--result-id", help="Identifiant local du resultat."),
    results_db_path: Path | None = typer.Option(
        None,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Supprime une revue manuelle sur un resultat."""
    results_repository = RaceResultsRepository(results_db_path or _app_paths().race_results_db)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    cleared = results_repository.clear_match_review(dataset_id=resolved_dataset_id, result_id=result_id)
    if not cleared:
        typer.echo("Review not found.")
        raise typer.Exit(code=1)
    typer.echo(f"Cleared review for result {result_id}")


@matching_app.command("list-reviews")
def matching_list_reviews(
    dataset: str | None = typer.Option(None, "--dataset", help="Identifiant ou alias local du dataset."),
    dataset_id: int | None = typer.Option(None, "--dataset-id", help="Compat: identifiant local du dataset."),
    results_db_path: Path | None = typer.Option(
        None,
        "--results-db-path",
        help="Chemin vers la base SQLite des resultats.",
    ),
) -> None:
    """Liste les revues manuelles enregistrees."""
    results_repository = RaceResultsRepository(results_db_path or _app_paths().race_results_db)
    results_repository.initialize()
    resolved_dataset_id = _resolve_dataset_id(repository=results_repository, dataset=dataset, dataset_id=dataset_id)
    reviews = results_repository.list_match_reviews(dataset_id=resolved_dataset_id)
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
