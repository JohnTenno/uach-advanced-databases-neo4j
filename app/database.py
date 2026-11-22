"""Neo4j connection. Every service runs its Cypher through read() / write().

The driver is thread safe and keeps its own pool, so one instance serves the
whole app. Each call runs in a managed transaction: the driver retries
transient errors and a failed write leaves nothing behind.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TypeVar

from neo4j import GraphDatabase, ManagedTransaction
from neo4j.exceptions import ConstraintError, Neo4jError
from neo4j.time import Date, DateTime

from app.common.errors import AppError, NotFoundError
from app.config import Config

Row = Dict[str, Any]
T = TypeVar("T")

config = Config.from_env()
driver = GraphDatabase.driver(config.neo4j_uri, auth=(config.neo4j_user, config.neo4j_password))

UNIQUE_MESSAGES = {
    ("User", "email"): "Ya existe un usuario con ese correo.",
    ("Tag", "name"): "Ya existe una etiqueta con ese nombre.",
    ("Tag", "url"): "Ya existe una etiqueta con esa URL.",
    ("Category", "name"): "Ya existe una categoría con ese nombre.",
    ("Category", "url"): "Ya existe una categoría con esa URL.",
}


def read(query: str, **params: Any) -> List[Row]:
    return _run("execute_read", query, params)


def read_one(query: str, **params: Any) -> Optional[Row]:
    rows = read(query, **params)
    return rows[0] if rows else None


def write(query: str, not_found: Optional[str] = None, **params: Any) -> List[Row]:
    """Run a write. With ``not_found`` the query must RETURN a row; none means
    its MATCH found nothing, which is reported with that message."""
    rows = _run("execute_write", query, params)
    if not_found and not rows:
        raise NotFoundError(not_found)
    return rows


class Transaction:
    """One step runner handed to the work function of transaction()."""

    def __init__(self, tx):
        self._tx = tx

    def run(self, query: str, not_found: Optional[str] = None, **params: Any) -> List[Row]:
        rows = _collect(self._tx, query, params)
        if not_found and not rows:
            raise NotFoundError(not_found)
        return rows


def transaction(work: Callable[[Transaction], T]) -> T:
    """Run several Cypher steps as one unit: commit only if every step succeeds.

    Any error (a business AppError or a Neo4j failure) rolls everything back,
    so the graph never keeps half of an operation.
    """
    with driver.session(database=config.neo4j_database) as session:
        tx = session.begin_transaction()
        try:
            result = work(Transaction(tx))
            tx.commit()
            return result
        except ConstraintError as error:
            raise AppError(_unique_message(error.message or "")) from error
        except Neo4jError as error:
            raise AppError(f"Error de Neo4j: {error.message}") from error
        finally:
            if not tx.closed():
                tx.rollback()


def _run(mode: str, query: str, params: dict) -> List[Row]:
    try:
        with driver.session(database=config.neo4j_database) as session:
            return getattr(session, mode)(_collect, query, params)
    except ConstraintError as error:
        raise AppError(_unique_message(error.message or "")) from error
    except Neo4jError as error:
        raise AppError(f"Error de Neo4j: {error.message}") from error


def _collect(tx: ManagedTransaction, query: str, params: dict) -> List[Row]:
    # Neo4j's clock is UTC; every query gets $tz so localdatetime({timezone: $tz}) is local time.
    params = {"tz": config.timezone, **params}
    return [{key: _native(value) for key, value in record.items()} for record in tx.run(query, params)]


def _native(value: Any) -> Any:
    # Neo4j temporal values become datetime/date so Jinja can format them.
    return value.to_native() if isinstance(value, (DateTime, Date)) else value


def _unique_message(message: str) -> str:
    for (label, prop), text in UNIQUE_MESSAGES.items():
        if f"`{label}`" in message and f"`{prop}`" in message:
            return text
    return "El registro ya existe."
