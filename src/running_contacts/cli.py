import typer

app = typer.Typer()

@app.callback()
def main() -> None:
    """CLI principale de running_contacts."""
    pass

@app.command()
def hello() -> None:
    """Teste que la CLI fonctionne."""
    print("running_contacts OK")

if __name__ == "__main__":
    app()
