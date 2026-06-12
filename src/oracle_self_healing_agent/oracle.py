from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Protocol

from .config import DatabaseConfig


class DatabaseClient(Protocol):
    def query(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        ...

    def execute(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> int:
        ...


class OracleClient:
    def __init__(self, config: DatabaseConfig):
        self.config = config
        self._connection = None

    def __enter__(self) -> "OracleClient":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def connect(self) -> None:
        try:
            import oracledb  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "Live Oracle mode requires the optional 'oracledb' package. "
                "Install it with: python3 -m pip install 'oracledb>=2.0'"
            ) from exc

        if not self.config.user or not self.config.password or not self.config.dsn:
            raise RuntimeError("Oracle credentials are incomplete. Set ORACLE_USER, ORACLE_PASSWORD, and ORACLE_DSN.")

        self._connection = oracledb.connect(
            user=self.config.user,
            password=self.config.password,
            dsn=self.config.dsn,
        )

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def query(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        if self._connection is None:
            self.connect()

        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, binds or {})
            columns = [description[0].lower() for description in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            cursor.close()

    def execute(self, sql: str, binds: Optional[Dict[str, Any]] = None) -> int:
        if self._connection is None:
            self.connect()

        cursor = self._connection.cursor()
        try:
            cursor.execute(sql, binds or {})
            rowcount = cursor.rowcount
            self._connection.commit()
            return rowcount
        finally:
            cursor.close()


def sql_literal(value: Any) -> str:
    text = str(value)
    return "'" + text.replace("'", "''") + "'"


def first_present(row: Dict[str, Any], names: Iterable[str], default: Any = None) -> Any:
    for name in names:
        if name in row and row[name] is not None:
            return row[name]
    return default
