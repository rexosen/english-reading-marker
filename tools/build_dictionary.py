"""Build assets/dictionary.sqlite3 from an ECDICT CSV export.

ECDICT (https://github.com/skywind3000/ECDICT, MIT license) ships word lists as
CSV. This tool keeps every entry that has a Chinese translation and writes the
two-column table the app queries at runtime. Without the result file the app
still works, falling back to online translation.

Usage:
    python tools/build_dictionary.py <path-to-stardict.csv> [output.sqlite3]
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT = PROJECT_ROOT / "assets" / "dictionary.sqlite3"


def build(csv_path: Path, output_path: Path) -> int:
    csv.field_size_limit(10_000_000)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    rows = []
    with csv_path.open(newline="", encoding="utf-8", errors="replace") as handle:
        for record in csv.DictReader(handle):
            word = (record.get("word") or "").strip().casefold()
            meaning = (record.get("translation") or "").replace("\\n", "\n").strip()
            if word and meaning:
                rows.append((word, meaning))
    with sqlite3.connect(output_path) as db:
        db.execute("CREATE TABLE words(word TEXT PRIMARY KEY, meaning TEXT NOT NULL)")
        db.executemany("INSERT OR REPLACE INTO words VALUES(?,?)", rows)
        db.commit()
        return db.execute("SELECT COUNT(*) FROM words").fetchone()[0]


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    csv_path = Path(sys.argv[1])
    if not csv_path.is_file():
        raise SystemExit(f"找不到 CSV 文件: {csv_path}")
    output_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    count = build(csv_path, output_path)
    print(f"{count} 条词条 -> {output_path}")


if __name__ == "__main__":
    main()
