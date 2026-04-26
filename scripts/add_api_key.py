#!/usr/bin/env python3
"""
Insert an API key into API_KEYS_DB (SHA-256 stored). Example:

  set API_KEYS_DB=data/keys.db
  python scripts/add_api_key.py --label "Clínica demo"

Reads the plaintext key from stdin (one line).
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

# Proyecto raíz en PYTHONPATH
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> None:
    parser = argparse.ArgumentParser(description="Registrar API key (hash en SQLite)")
    parser.add_argument(
        "--db",
        default=os.environ.get("API_KEYS_DB", ""),
        help="Ruta SQLite (o env API_KEYS_DB)",
    )
    parser.add_argument("--label", default="", help="Etiqueta opcional")
    args = parser.parse_args()
    if not args.db:
        print("Indica --db o variable API_KEYS_DB", file=sys.stderr)
        sys.exit(1)

    plain = getpass.getpass("Nueva API key (no se muestra): ").strip()
    if not plain:
        print("Clave vacía", file=sys.stderr)
        sys.exit(1)

    from app.infrastructure.api_key_repository import ApiKeyRepository

    repo = ApiKeyRepository(args.db, frozenset())
    h = repo.add_key(plain, label=args.label)
    print(f"Registrada (hash SHA-256): {h[:16]}…")


if __name__ == "__main__":
    main()
