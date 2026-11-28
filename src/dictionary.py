from __future__ import annotations

from contextlib import closing
import html
import json
import re
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

API_ENDPOINT = "https://api.mymemory.translated.net/get"
_google_blocked_until = 0.0
_dict_columns_cache: dict[str, set[str]] = {}

TAG_LABELS = {
    "zk": "中考",
    "gk": "高考",
    "cet4": "四级",
    "cet6": "六级",
    "ky": "考研",
    "toefl": "托福",
    "ielts": "雅思",
    "gre": "GRE",
}

IRREGULAR_LEMMAS = {
    "was": "be", "were": "be", "been": "be", "am": "be", "is": "be", "are": "be",
    "had": "have", "has": "have", "did": "do", "done": "do", "does": "do",
    "went": "go", "gone": "go", "saw": "see", "seen": "see", "came": "come",
    "took": "take", "taken": "take", "made": "make", "got": "get", "gotten": "get",
    "gave": "give", "given": "give", "found": "find", "thought": "think",
    "told": "tell", "became": "become", "left": "leave", "felt": "feel",
    "brought": "bring", "began": "begin", "begun": "begin", "kept": "keep",
    "held": "hold", "wrote": "write", "written": "write", "stood": "stand",
    "heard": "hear", "meant": "mean", "met": "meet", "ran": "run", "paid": "pay",
    "sat": "sit", "spoke": "speak", "spoken": "speak", "lay": "lie", "lain": "lie",
    "led": "lead", "grew": "grow", "grown": "grow", "lost": "lose", "fell": "fall",
    "fallen": "fall", "sent": "send", "built": "build", "understood": "understand",
    "drew": "draw", "drawn": "draw", "broke": "break", "broken": "break",
    "spent": "spend", "rose": "rise", "risen": "rise", "drove": "drive",
    "driven": "drive", "bought": "buy", "wore": "wear", "worn": "wear",
    "chose": "choose", "chosen": "choose", "ate": "eat", "eaten": "eat",
    "drank": "drink", "drunk": "drink", "knew": "know", "known": "know",
    "flew": "fly", "flown": "fly", "forgot": "forget", "forgotten": "forget",
    "caught": "catch", "taught": "teach", "fought": "fight", "sought": "seek",
    "sold": "sell", "sung": "sing", "sang": "sing", "swam": "swim", "swum": "swim",
    "threw": "throw", "thrown": "throw", "woke": "wake", "woken": "wake",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "farther": "far", "farthest": "far", "further": "far", "furthest": "far",
    "children": "child", "men": "man", "women": "woman", "feet": "foot",
    "teeth": "tooth", "geese": "goose", "mice": "mouse", "people": "person",
    "leaves": "leaf", "lives": "life", "knives": "knife", "wives": "wife",
    "wolves": "wolf", "shelves": "shelf", "halves": "half", "thieves": "thief",
    "analyses": "analysis", "crises": "crisis", "theses": "thesis",
    "phenomena": "phenomenon", "criteria": "criterion", "indices": "index",
    "data": "datum", "media": "medium",
}

_INFLECTION_ONLY_RE = re.compile(
    r"^\s*(?:[a-z]+\.\s*)?[\w'-]+\s*的(?:过去式|过去分词|现在分词|复数|第三人称单数|比较级|最高级)",
    re.IGNORECASE,
)


class DictionaryError(RuntimeError):
    pass


def _cache_path() -> Path:
    from src.storage import data_directory
    root = data_directory()
    root.mkdir(parents=True, exist_ok=True)
    return root / "translations.sqlite3"


def _dictionary_path() -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return root / "assets/dictionary.sqlite3"


def _dictionary_columns(db: sqlite3.Connection, path: Path) -> set[str]:
    key = str(path)
    cols = _dict_columns_cache.get(key)
    if cols is None:
        cols = {row[1] for row in db.execute("PRAGMA table_info(words)")}
        _dict_columns_cache[key] = cols
    return cols


def lemmatize_candidates(word: str) -> list[str]:
    """Generate likely base forms for an inflected English word."""
    w = word.strip().casefold()
    if not w or not re.fullmatch(r"[a-z]+", w) or len(w) <= 2:
        return []
    candidates: list[str] = []

    def add(item: str) -> None:
        if item and item != w and len(item) >= 2 and item not in candidates:
            candidates.append(item)

    if w in IRREGULAR_LEMMAS:
        add(IRREGULAR_LEMMAS[w])
    if w.endswith("ies") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("ied") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("ier") and len(w) > 4:
        add(w[:-3] + "y")
    if w.endswith("iest") and len(w) > 5:
        add(w[:-4] + "y")
    if w.endswith("ves") and len(w) > 4:
        add(w[:-3] + "f")
        add(w[:-3] + "fe")
    if w.endswith("es") and len(w) > 3:
        add(w[:-2])
        add(w[:-1])
    if w.endswith("s") and not w.endswith("ss") and len(w) > 3:
        add(w[:-1])
    if w.endswith("ing") and len(w) > 5:
        stem = w[:-3]
        add(stem)
        add(stem + "e")
        if len(stem) >= 3 and stem[-1] == stem[-2]:
            add(stem[:-1])
        if stem.endswith("y"):
            add(stem[:-1] + "ie")
    if w.endswith("ed") and len(w) > 4:
        stem = w[:-2]
        add(stem)
        add(stem + "e")
        if len(stem) >= 3 and stem[-1] == stem[-2]:
            add(stem[:-1])
    if w.endswith("er") and len(w) > 4:
        stem = w[:-2]
        add(stem)
        add(stem + "e")
        if len(stem) >= 3 and stem[-1] == stem[-2]:
            add(stem[:-1])
    if w.endswith("est") and len(w) > 5:
        stem = w[:-3]
        add(stem)
        add(stem + "e")
        if len(stem) >= 3 and stem[-1] == stem[-2]:
            add(stem[:-1])
    return candidates


def _query_word_row(db: sqlite3.Connection, cols: set[str], word: str) -> dict | None:
    if {"phonetic", "tag", "collins", "exchange"}.issubset(cols):
        row = db.execute(
            "SELECT meaning, phonetic, tag, collins, exchange FROM words WHERE word=?",
            (word,),
        ).fetchone()
        if not row:
            return None
        return {
            "word": word,
            "meaning": row[0],
            "phonetic": row[1] or "",
            "tag": row[2] or "",
            "collins": row[3] or "",
            "exchange": row[4] or "",
        }
    row = db.execute("SELECT meaning FROM words WHERE word=?", (word,)).fetchone()
    if not row:
        return None
    return {
        "word": word,
        "meaning": row[0],
        "phonetic": "",
        "tag": "",
        "collins": "",
        "exchange": "",
    }


def _lemma_from_exchange(exchange: str) -> str:
    # ECDICT exchange field uses e.g. "0:study/1:d" where 0:<lemma> is base form.
    for part in (exchange or "").split("/"):
        if part.startswith("0:"):
            return part[2:].strip().casefold()
    return ""


def lookup_local_entry(text: str) -> dict | None:
    """Look up a word or short phrase in local ECDICT with automatic lemmatization."""
    cleaned = text.strip()
    dictionary = _dictionary_path()
    if not (dictionary.exists() and re.fullmatch(r"[A-Za-z’' -]+", cleaned) and len(cleaned) < 90):
        return None
    key = cleaned.casefold()
    with closing(sqlite3.connect(f"{dictionary.as_uri()}?mode=ro", uri=True)) as db:
        cols = _dictionary_columns(db, dictionary)
        exact = _query_word_row(db, cols, key)
        if exact:
            # If the exact entry is only a pointer to an inflection (e.g. "study的过去式"),
            # attach the base form's definition so the reader doesn't need a second lookup.
            lemma = _lemma_from_exchange(exact["exchange"])
            if not lemma and _INFLECTION_ONLY_RE.match(exact["meaning"]):
                for cand in lemmatize_candidates(key):
                    if _query_word_row(db, cols, cand):
                        lemma = cand
                        break
            if lemma and lemma != key:
                base = _query_word_row(db, cols, lemma)
                if base and base["meaning"] not in exact["meaning"]:
                    exact["lemma"] = lemma
                    exact["lemma_meaning"] = base["meaning"]
                    if not exact["phonetic"] and base["phonetic"]:
                        exact["phonetic"] = base["phonetic"]
                    if not exact["tag"] and base["tag"]:
                        exact["tag"] = base["tag"]
            return exact
        # Exact word not found: try lemmatized candidates for single words
        for cand in lemmatize_candidates(key):
            base = _query_word_row(db, cols, cand)
            if base:
                return {
                    "word": key,
                    "meaning": base["meaning"],
                    "phonetic": base["phonetic"],
                    "tag": base["tag"],
                    "collins": base["collins"],
                    "exchange": base["exchange"],
                    "lemma": cand,
                    "lemma_meaning": "",
                }
    return None


def cached_translation(text: str) -> str | None:
    entry = lookup_local_entry(text)
    if entry:
        meaning = entry["meaning"]
        if entry.get("lemma") and entry.get("lemma_meaning"):
            return f"{meaning}\n\n原形 {entry['lemma']}：\n{entry['lemma_meaning']}"
        return meaning
    with closing(sqlite3.connect(_cache_path())) as db:
        db.execute("CREATE TABLE IF NOT EXISTS cache(text TEXT PRIMARY KEY, meaning TEXT NOT NULL)")
        row = db.execute("SELECT meaning FROM cache WHERE text=?", (text,)).fetchone()
        db.commit()
        return row[0] if row else None


def format_translation_html(word: str, meaning: str, *, entry: dict | None = None, dark: bool = False) -> str:
    """Format a dictionary entry or sentence translation as clean rich HTML."""
    text_color = "#e6edf3" if dark else "#203044"
    muted = "#94a3b8" if dark else "#64748b"
    pos_bg = "#253449" if dark else "#eaf1ff"
    pos_fg = "#7cc0ff" if dark else "#2558b8"
    tag_bg = "#2a2f3a" if dark else "#f1f5f9"
    tag_fg = "#cbd5e1" if dark else "#475569"
    lemma_bg = "#1e293b" if dark else "#f8fafc"
    lemma_border = "#334155" if dark else "#e2e8f0"

    parts: list[str] = []
    if entry:
        meta_bits: list[str] = []
        if entry.get("phonetic"):
            meta_bits.append(
                f'<span style="color:{muted};font-family:Consolas,monospace;font-size:10.5pt;">'
                f'/{html.escape(entry["phonetic"])}/</span>'
            )
        if entry.get("tag"):
            for raw_tag in entry["tag"].split():
                label = TAG_LABELS.get(raw_tag.lower())
                if label:
                    meta_bits.append(
                        f'<span style="background:{tag_bg};color:{tag_fg};padding:1px 6px;'
                        f'border-radius:4px;font-size:8.5pt;margin-left:4px;">{html.escape(label)}</span>'
                    )
        if entry.get("collins") and str(entry["collins"]).isdigit() and int(entry["collins"]) > 0:
            stars = "★" * int(entry["collins"])
            meta_bits.append(f'<span style="color:#d97706;font-size:9pt;margin-left:4px;">{stars}</span>')
        if entry.get("lemma") and not entry.get("lemma_meaning"):
            meta_bits.append(
                f'<span style="color:{muted};font-size:9pt;margin-left:6px;">原形：{html.escape(entry["lemma"])}</span>'
            )
        if meta_bits:
            parts.append(f'<div style="margin-bottom:8px;">{" ".join(meta_bits)}</div>')

    pos_re = re.compile(r"^([a-z]{1,6}\.|\[网络\])\s*(.+)$", re.IGNORECASE)
    for raw_line in meaning.splitlines():
        line = raw_line.strip()
        if not line:
            parts.append('<div style="height:6px;"></div>')
            continue
        if line.startswith("原形 ") and line.endswith("："):
            parts.append(
                f'<div style="margin-top:8px;padding:4px 8px;background:{lemma_bg};'
                f'border-left:3px solid {pos_fg};border-radius:4px;color:{muted};font-weight:700;">'
                f'{html.escape(line)}</div>'
            )
            continue
        m = pos_re.match(line)
        if m:
            pos, rest = m.group(1), m.group(2)
            parts.append(
                f'<div style="margin:4px 0;line-height:1.55;">'
                f'<span style="background:{pos_bg};color:{pos_fg};font-weight:700;'
                f'padding:1px 6px;border-radius:4px;font-size:9.5pt;margin-right:6px;">'
                f'{html.escape(pos)}</span>'
                f'<span style="color:{text_color};">{html.escape(rest)}</span></div>'
            )
        else:
            parts.append(
                f'<div style="margin:4px 0;line-height:1.6;color:{text_color};">{html.escape(line)}</div>'
            )
    return f'<div style="font-family:\'Microsoft YaHei UI\';font-size:10.5pt;color:{text_color};">{"".join(parts)}</div>'


def _chunks(text: str, limit: int = 450) -> list[str]:
    # Keep requests under the fallback provider's 500 UTF-8 byte limit.
    chunks, current = [], ""
    for token in re.findall(r"\S+\s*", text):
        if len((current + token).encode("utf-8")) > limit and current:
            chunks.append(current.strip())
            current = ""
        while len(token.encode("utf-8")) > limit:
            part = token[:100]
            chunks.append(part)
            token = token[100:]
        current += token
    if current.strip():
        chunks.append(current.strip())
    return chunks


def _translate_chunk(text: str, timeout: float) -> str:
    global _google_blocked_until
    # Google is unreachable on mainland networks; remember failures for 10 minutes
    # so subsequent translations skip straight to MyMemory instead of waiting 1.5s each time.
    now = time.monotonic()
    google_url = "https://translate.googleapis.com/translate_a/single?" + urlencode(
        {"client": "gtx", "sl": "en", "tl": "zh-CN", "dt": "t", "q": text}
    )
    mymemory_url = API_ENDPOINT + "?" + urlencode({"q": text, "langpair": "en|zh-CN"})
    providers = []
    if now >= _google_blocked_until:
        providers.append(("google", google_url, min(timeout, 1.5)))
    providers.append(("mymemory", mymemory_url, timeout))
    for name, url, provider_timeout in providers:
        try:
            request = Request(url, headers={"User-Agent": "EnglishReaderMarker/2.0"})
            with urlopen(request, timeout=provider_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if isinstance(payload, list):
                translated = "".join(item[0] or "" for item in payload[0])
            else:
                if payload.get("responseStatus") != 200:
                    continue
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
    if not text:
        raise DictionaryError("请先选择英文内容。")
    cached = cached_translation(text)
    if cached:
        return cached
    parts = _chunks(text)
    with ThreadPoolExecutor(max_workers=3) as executor:
        results = list(executor.map(lambda part: _translate_chunk(part, timeout), parts))
    result = "\n".join(results)
    with closing(sqlite3.connect(_cache_path())) as db:
        db.execute("CREATE TABLE IF NOT EXISTS cache(text TEXT PRIMARY KEY, meaning TEXT NOT NULL)")
        db.execute("INSERT OR REPLACE INTO cache VALUES (?,?)", (text, result))
        db.commit()
    return result
