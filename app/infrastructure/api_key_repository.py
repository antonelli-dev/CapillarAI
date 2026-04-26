"""
API keys: optional SQLite store (SHA-256 hashes) plus legacy API_KEYS env (plain).

Use scripts/add_api_key.py to insert hashed keys without redeploying env.
"""

from __future__ import annotations

import hashlib
import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def hash_api_key(plain: str) -> str:
    return hashlib.sha256(plain.encode("utf-8")).hexdigest()


class ApiKeyRepository:
    """Validates keys against env list and/or sqlite table `api_keys`."""

    def __init__(self, db_path: str | None, env_plain_keys: frozenset[str]):
        self._env_plain = env_plain_keys
        self._db_path = db_path
        self._db_hashes: frozenset[str] = frozenset()
        if db_path:
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            self._init_db()
            self._db_hashes = self._load_active_hashes()

    def _init_db(self) -> None:
        assert self._db_path
        with sqlite3.connect(self._db_path) as cx:
            cx.execute(
                """
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    label TEXT,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
                """
            )

    def _load_active_hashes(self) -> frozenset[str]:
        assert self._db_path
        with sqlite3.connect(self._db_path) as cx:
            rows = cx.execute(
                "SELECT key_hash FROM api_keys WHERE active = 1"
            ).fetchall()
        return frozenset(r[0] for r in rows)

    def reload_db_hashes(self) -> None:
        """Call after add_key in another process (optional)."""
        if self._db_path:
            self._db_hashes = self._load_active_hashes()

    def is_valid(self, plain: str | None) -> bool:
        if not plain:
            return False
        if plain in self._env_plain:
            return True
        h = hash_api_key(plain)
        return h in self._db_hashes

    def add_key(self, plain: str, label: str = "") -> str:
        """Insert or replace active key; returns key_hash."""
        if not self._db_path:
            raise RuntimeError("API_KEYS_DB is not configured")
        h = hash_api_key(plain)
        with sqlite3.connect(self._db_path) as cx:
            cx.execute(
                """
                INSERT INTO api_keys (key_hash, label, active)
                VALUES (?, ?, 1)
                ON CONFLICT(key_hash) DO UPDATE SET
                    label = excluded.label,
                    active = 1
                """,
                (h, label or ""),
            )
        self._db_hashes = frozenset(self._db_hashes | {h})
        logger.info("API key registrada (hash prefix=%s…)", h[:12])
        return h

    def list_db_keys(self, active_only: bool = True) -> list[dict]:
        """Lista claves en SQLite (usa rowid). key_hash acortado para pantalla."""
        if not self._db_path:
            return []
        where = "WHERE active = 1" if active_only else ""
        with sqlite3.connect(self._db_path) as cx:
            cx.row_factory = sqlite3.Row
            rows = cx.execute(
                f"""
                SELECT rowid AS id, key_hash, label, active, created_at
                FROM api_keys
                {where}
                ORDER BY rowid DESC
                """
            ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            kh = d.get("key_hash", "")
            d["key_hash_preview"] = f"{kh[:12]}…" if len(kh) > 12 else kh
            del d["key_hash"]
            out.append(d)
        return out

    def revoke_by_id(self, key_id: int) -> bool:
        """Desactiva por SQLite rowid; devuelve False si no existe."""
        if not self._db_path:
            return False
        with sqlite3.connect(self._db_path) as cx:
            cur = cx.execute(
                "UPDATE api_keys SET active = 0 WHERE rowid = ?", (key_id,)
            )
            if cur.rowcount == 0:
                return False
        self._db_hashes = self._load_active_hashes()
        logger.info("API key revocada rowid=%s", key_id)
        return True

    def has_auth_configured(self) -> bool:
        return bool(self._env_plain) or bool(self._db_hashes)


_repo: ApiKeyRepository | None = None


def get_api_key_repository() -> ApiKeyRepository:
    global _repo
    if _repo is None:
        from app.config import get_settings

        s = get_settings()
        env_keys = frozenset(
            k.strip() for k in s.api_keys.split(",") if k.strip()
        )
        _repo = ApiKeyRepository(s.api_keys_db or None, env_keys)
    return _repo


def reset_api_key_repository_for_tests() -> None:
    global _repo
    _repo = None
