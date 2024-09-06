import typer
from typing import Optional

from dat1 import __app_name__, __version__


app = typer.Typer()


@app.command()
def init() -> None:
    """Initialize the project"""
    print("""Initialize the project""")


@app.command()
def deploy() -> None:
    """Deploy the project"""
    print("""Deploy the project""")

@app.command()
def serve() -> None:
    """Serve the project locally"""
    print("""Serve the project locally""")


@app.command()
def destroy() -> None:
    """Destroy the project"""
    print("""Destroy the project""")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"{__app_name__} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        help="Show CLI version and exit.",
        callback=_version_callback,
        is_eager=True,
    )
) -> None:
    return
