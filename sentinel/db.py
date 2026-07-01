"""DuckDB access layer (local stand-in for BigQuery).

A single connection guarded by a lock — simple and correct for a single-process
local demo. The same SQL maps to BigQuery for the cloud phase.
"""
from __future__ import annotations

import os
import threading

import duckdb

DEFAULT_DB = os.environ.get("SENTINEL_DUCKDB", "data/sentinel.duckdb")


class Database:
    def __init__(self, path: str | None = None, read_only: bool = False):
        self.path = path or DEFAULT_DB
        self.con = duckdb.connect(self.path, read_only=read_only)
        self._lock = threading.Lock()

    def df(self, sql: str, params: list | None = None):
        with self._lock:
            return self.con.execute(sql, params or []).df()

    def execute(self, sql: str, params: list | None = None):
        with self._lock:
            self.con.execute(sql, params or [])

    def scalar(self, sql: str, params: list | None = None):
        with self._lock:
            row = self.con.execute(sql, params or []).fetchone()
            return row[0] if row else None

    def close(self):
        self.con.close()
