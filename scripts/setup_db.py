"""Load cypher/01_schema.cypher and cypher/02_datos.cypher into Neo4j.

Usage:
    .venv/bin/python -m scripts.setup_db                both files (wipes the data first)
    .venv/bin/python -m scripts.setup_db --schema-only  only constraints and index
"""
import sys
from pathlib import Path

from neo4j.exceptions import AuthError, Neo4jError, ServiceUnavailable

from app.database import config, driver

CYPHER_DIR = Path(__file__).resolve().parent.parent / "cypher"


def statements(path: Path) -> list:
    """Split on ';' at the end of a line and drop // comment lines."""
    lines = [line for line in path.read_text(encoding="utf-8").splitlines()
             if not line.strip().startswith("//")]
    # shortcut: assumes no string literal ends a line with ';'; true for our files.
    return [s.strip().rstrip(";") for s in "\n".join(lines).split(";\n") if s.strip().rstrip(";")]


def main() -> None:
    files = ["01_schema.cypher"] + ([] if "--schema-only" in sys.argv else ["02_datos.cypher"])
    print(f"Connecting to {config.db_target} ...")
    try:
        driver.verify_connectivity()
    except (ServiceUnavailable, AuthError) as error:
        print(f"Could not connect: {error}")
        sys.exit(1)

    with driver.session(database=config.neo4j_database) as session:
        for name in files:
            parts = statements(CYPHER_DIR / name)
            for statement in parts:
                try:
                    session.run(statement).consume()
                except Neo4jError as error:
                    print(f"{name} failed on:\n{statement}\n{error.message}")
                    sys.exit(1)
            print(f"  {name}: {len(parts)} statements")
    print("Done. Run: .venv/bin/python main.py")


if __name__ == "__main__":
    main()
