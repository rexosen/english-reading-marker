from __future__ import annotations

from contextlib import closing
import html
import json
import os
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ENDPOINT = "https://api.mymemory.translated.net/get"
_google_blocked_until = 0.0

class DictionaryError(RuntimeError):
    pass

def _cache_path():
    from src.storage import data_directory
    root = data_directory()
    root.mkdir(parents=True, exist_ok=True)
    return root / "translations.sqlite3"

def cached_translation(text: str) -> str | None:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    dictionary = root / "assets/dictionary.sqlite3"
    if dictionary.exists() and re.fullmatch(r"[A-Za-z’' -]+", text) and len(text) < 90:
        with closing(sqlite3.connect(f"{dictionary.as_uri()}?mode=ro", uri=True)) as db:
            row = db.execute("SELECT meaning FROM words WHERE word=?", (text.casefold(),)).fetchone()
            if row:
                return row[0]
    with closing(sqlite3.connect(_cache_path())) as db:
        db.execute("CREATE TABLE IF NOT EXISTS cache(text TEXT PRIMARY KEY, meaning TEXT NOT NULL)")
        row = db.execute("SELECT meaning FROM cache WHERE text=?", (text,)).fetchone()
        db.commit()
        return row[0] if row else None

def _chunks(text: str, limit: int = 450) -> list[str]:
    # Keep requests under the fallback provider's 500 UTF-8 byte limit.
    chunks, current = [], ""
    for token in re.findall(r"\S+\s*", text):
        if len((current + token).encode("utf-8")) > limit and current:
            chunks.append(current.strip()); current = ""
        while len(token.encode("utf-8")) > limit:
            part = token[:100]
            chunks.append(part); token = token[100:]
        current += token
    if current.strip(): chunks.append(current.strip())
    return chunks

def _translate_chunk(text: str, timeout: float) -> str:
    global _google_blocked_until
    # Google is unreachable on mainland networks; remember failures for 10 minutes
    # so subsequent translations skip straight to MyMemory instead of waiting 1.5s each time.
    now = time.monotonic()
    google_url = "https://translate.googleapis.com/translate_a/single?" + urlencode({"client":"gtx", "sl":"en", "tl":"zh-CN", "dt":"t", "q":text})
    mymemory_url = API_ENDPOINT + "?" + urlencode({"q":text, "langpair":"en|zh-CN"})
    providers = []
    if now >= _google_blocked_until:
        providers.append(("google", google_url, min(timeout, 1.5)))
    providers.append(("mymemory", mymemory_url, timeout))
    for name, url, provider_timeout in providers:
        try:
            request = Request(url, headers={"User-Agent":"EnglishReaderMarker/2.0"})
            with urlopen(request, timeout=provider_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                translated = "".join(item[0] or "" for item in payload[0])
            else:
                if payload.get("responseStatus") != 200: continue
                translated = payload.get("responseData", {}).get("translatedText", "")
            translated = html.unescape(translated).strip()
            if translated and translated.casefold() != text.casefold():
                if name == "google":
                    _google_blocked_until = 0.0
                return translated
        except (OSError, ValueError, TypeError, IndexError, KeyError):
            if name == "google":
                _google_blocked_until = time.monotonic() + 600.0
            continue
    raise DictionaryError("翻译服务未返回可用结果，请检查网络后右键重试。")

def lookup_chinese(text: str, timeout: float = 4.0) -> str:
    text = text.strip()
    if not text: raise DictionaryError("请先选择英文内容。")
    cached = cached_translation(text)
    if cached: return cached
    parts = _chunks(text)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda part: _translate_chunk(part, timeout), parts))
    result = "\n".join(results)
    with closing(sqlite3.connect(_cache_path())) as db:
        db.execute("CREATE TABLE IF NOT EXISTS cache(text TEXT PRIMARY KEY, meaning TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (text, result))
        db.commit()
    return result
