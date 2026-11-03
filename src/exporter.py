from __future__ import annotations

import csv
from pathlib import Path


CSV_COLUMNS = [
    ("单词", "word"),
    ("中文释义", "definition"),
    ("原句", "context"),
    ("文章", "article_title"),
    ("标记日期", "created_at"),
]


def export_vocabulary_csv(records: list[dict], destination: Path | str) -> Path:
    output_path = Path(destination)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=[label for label, _ in CSV_COLUMNS])
        writer.writeheader()
        for record in records:
            writer.writerow({label: record.get(key, "") for label, key in CSV_COLUMNS})
    return output_path
