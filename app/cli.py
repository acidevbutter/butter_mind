import typer
from alembic import command as alembic_command
from alembic.config import Config
from alembic.script import ScriptDirectory

app = typer.Typer()
db_app = typer.Typer()
app.add_typer(db_app, name="db")


def _alembic_config() -> Config:
    return Config("alembic.ini")


def _get_heads(cfg: Config) -> list[str]:
    script = ScriptDirectory.from_config(cfg)
    return list(script.get_heads())


@db_app.command("heads")
def db_heads() -> None:
    """Show current Alembic heads."""
    heads = _get_heads(_alembic_config())
    for h in heads:
        typer.echo(h)


@db_app.command("history")
def db_history() -> None:
    """Show Alembic revision history."""
    alembic_command.history(_alembic_config())


@db_app.command("migrate")
def db_migrate() -> None:
    """Upgrade the database to head."""
    alembic_command.upgrade(_alembic_config(), "head")


@db_app.command("rollback")
def db_rollback() -> None:
    """Downgrade one revision, following Alembic's native chain."""
    alembic_command.downgrade(_alembic_config(), "-1")


@db_app.command("make")
def db_make(description: str) -> None:
    """Autogenerate a migration from the current head, with single-head checks."""
    cfg = _alembic_config()

    heads_before = _get_heads(cfg)
    if len(heads_before) > 1:
        typer.echo(
            f"ERROR: expected at most one Alembic head, found {len(heads_before)}: {heads_before}. "
            "Resolve the branch (e.g. `alembic merge heads`) before generating a new migration.",
            err=True,
        )
        raise typer.Exit(code=1)

    alembic_command.revision(cfg, message=description, autogenerate=True)

    heads_after = _get_heads(cfg)
    if len(heads_after) != 1:
        typer.echo(
            f"ERROR: migration generation resulted in {len(heads_after)} heads: {heads_after}. "
            "This should not happen from a single-head autogenerate -- investigate before "
            "proceeding.",
            err=True,
        )
        raise typer.Exit(code=1)

    typer.echo(f"Created migration at new head: {heads_after[0]}")


if __name__ == "__main__":
    app()
