"""Create a consistent SQLite snapshot, including committed WAL data."""
import argparse
import sqlite3
from pathlib import Path
from .db import default_db


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", help="New snapshot filename (must not exist)")
    args = parser.parse_args()
    destination = Path(args.destination).resolve()
    source = Path(default_db()).resolve()
    if not source.is_file():
        parser.error("Database does not exist")
    if destination == source or destination.exists():
        parser.error("Choose a new destination; existing files are never overwritten")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(source) as live, sqlite3.connect(destination) as snapshot:
        live.backup(snapshot)
        if snapshot.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise RuntimeError("Backup integrity check failed")
    print(destination)


if __name__ == "__main__":
    main()
