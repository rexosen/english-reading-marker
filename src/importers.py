"""Multi-format article importers (.txt, .md, .epub, .pdf) and pure-Python QR code generator."""
from __future__ import annotations

from html.parser import HTMLParser
import re
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap


SUPPORTED_EXTENSIONS = {".txt", ".md", ".markdown", ".epub", ".pdf"}


class _HTMLTextExtractor(HTMLParser):
    BLOCK_TAGS = {"p", "div", "br", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote", "tr"}

    def __init__(self) -> None:
        super().__init__()
        self._skip = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "head", "title"):
            self._skip += 1
        elif tag == "br":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in ("script", "style", "head", "title") and self._skip > 0:
            self._skip -= 1
        elif tag in self.BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip == 0:
            self.parts.append(data)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = re.sub(r"[ \t]+\n", "\n", raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def _decode_bytes(raw: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _clean_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`~]{1,3}([^*_`~]+)[*_`~]{1,3}", r"\1", text)
    return text.strip()


def _extract_epub(path: Path) -> str:
    chunks: list[str] = []
    with zipfile.ZipFile(path, "r") as zf:
        # Follow OPF spine order when available
        names: list[str] = []
        try:
            container = ET.fromstring(zf.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is not None and rootfile.attrib.get("full-path"):
                opf_path = rootfile.attrib["full-path"]
                opf_dir = str(Path(opf_path).parent).replace("\\", "/")
                if opf_dir == ".":
                    opf_dir = ""
                opf = ET.fromstring(zf.read(opf_path))
                manifest = {
                    item.attrib["id"]: item.attrib["href"]
                    for item in opf.findall(".//{*}manifest/{*}item")
                    if "id" in item.attrib and "href" in item.attrib
                }
                for itemref in opf.findall(".//{*}spine/{*}itemref"):
                    href = manifest.get(itemref.attrib.get("idref", ""))
                    if href:
                        full = f"{opf_dir}/{href}" if opf_dir else href
                        names.append(full)
        except Exception:
            names = []
        if not names:
            names = sorted(
                n for n in zf.namelist() if n.lower().endswith((".xhtml", ".html", ".htm"))
            )
        for name in names:
            if name not in zf.namelist():
                continue
            parser = _HTMLTextExtractor()
            parser.feed(_decode_bytes(zf.read(name)))
            content = parser.text()
            if content:
                chunks.append(content)
    return "\n\n".join(chunks).strip()


def _extract_pdf(path: Path) -> str:
    # Try optional pypdf / pymupdf if installed in the environment
    for module_name in ("pypdf", "PyPDF2"):
        try:
            mod = __import__(module_name)
            reader = mod.PdfReader(str(path))
            pages = [page.extract_text() or "" for page in reader.pages]
            text = "\n\n".join(p.strip() for p in pages if p.strip()).strip()
            if text:
                return text
        except Exception:
            pass
    # Lightweight pure-Python PDF text stream extractor for uncompressed / FlateDecode PDFs
    raw = path.read_bytes()
    streams = re.findall(rb"stream\r?\n(.*?)\r?\nendstream", raw, flags=re.DOTALL)
    extracted: list[str] = []
    for stream in streams:
        data = stream
        try:
            data = zlib.decompress(stream)
        except zlib.error:
            pass
        if b"BT" not in data or b"Tj" not in data and b"TJ" not in data:
            continue
        # Extract literal strings inside (...)
        tokens = re.findall(rb"\(([^()\\]*(?:\\.[^()\\]*)*)\)", data)
        if tokens:
            pieces = []
            for tok in tokens:
                tok = tok.replace(rb"\(", b"(").replace(rb"\)", b")").replace(rb"\n", b"\n").replace(rb"\\", b"\\")
                s = tok.decode("latin1", errors="ignore")
                if any(ch.isalpha() for ch in s):
                    pieces.append(s)
            if pieces:
                extracted.append(" ".join(pieces))
    result = "\n\n".join(extracted).strip()
    if not result:
        raise ValueError("未能从此 PDF 提取到纯文本（可能是扫描图片版或特殊编码字体），请先复制文字后粘贴导入。")
    return result


def import_article_file(path: Path) -> tuple[str, str]:
    """Import .txt, .md, .epub, or .pdf and return (title, normalized_text)."""
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".epub":
        text = _extract_epub(path)
    elif ext == ".pdf":
        text = _extract_pdf(path)
    elif ext in (".md", ".markdown"):
        text = _clean_markdown(_decode_bytes(path.read_bytes()))
    else:
        text = _decode_bytes(path.read_bytes())
    return path.stem, text


# ---- Pure-Python QR Code (Byte mode, ECC Level L, Versions 1..6) ------------
# Supports up to 134 UTF-8 bytes — plenty for "http://192.168.x.x:port|123456".

_QR_VERSIONS = [
    # (version, size, total_codewords, ec_per_block, blocks, align_centers)
    (1, 21, 26, 7, 1, []),
    (2, 25, 44, 10, 1, [6, 18]),
    (3, 29, 70, 15, 1, [6, 22]),
    (4, 33, 100, 20, 1, [6, 26]),
    (5, 37, 134, 26, 1, [6, 30]),
    (6, 41, 172, 18, 2, [6, 34]),
]

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256
_x = 1
for _i in range(255):
    _GF_EXP[_i] = _x
    _GF_LOG[_x] = _i
    _x <<= 1
    if _x & 0x100:
        _x ^= 0x11D
for _i in range(255, 512):
    _GF_EXP[_i] = _GF_EXP[_i - 255]


def _gf_mul(a: int, b: int) -> int:
    return 0 if a == 0 or b == 0 else _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_encode(data: list[int], ec_len: int) -> list[int]:
    gen = [1]
    for i in range(ec_len):
        nxt = [0] * (len(gen) + 1)
        factor = _GF_EXP[i]
        for j, coeff in enumerate(gen):
            nxt[j] ^= coeff
            nxt[j + 1] ^= _gf_mul(coeff, factor)
        gen = nxt
    rem = list(data) + [0] * ec_len
    for i in range(len(data)):
        coef = rem[i]
        if coef != 0:
            for j in range(1, len(gen)):
                rem[i + j] ^= _gf_mul(gen[j], coef)
    return rem[len(data):]


def _format_bits(mask: int) -> int:
    # Level L = 01
    data = (0b01 << 3) | mask
    rem = data << 10
    for i in range(4, -1, -1):
        if (rem >> (i + 10)) & 1:
            rem ^= 0x537 << i
    return ((data << 10) | rem) ^ 0x5412


def make_qr_matrix(text: str) -> list[list[bool]]:
    payload = text.encode("utf-8")
    chosen = None
    for spec in _QR_VERSIONS:
        ver, size, total_cw, ec_per_blk, blocks, aligns = spec
        data_cw = total_cw - ec_per_blk * blocks
        if len(payload) + 2 <= data_cw:
            chosen = spec
            break
    if chosen is None:
        raise ValueError("QR payload too long")
    ver, size, total_cw, ec_per_blk, blocks, aligns = chosen
    data_cw = total_cw - ec_per_blk * blocks

    bits: list[int] = []

    def push(val: int, length: int) -> None:
        for shift in range(length - 1, -1, -1):
            bits.append((val >> shift) & 1)

    push(0b0100, 4)  # Byte mode
    push(len(payload), 8)
    for b in payload:
        push(b, 8)
    push(0, min(4, data_cw * 8 - len(bits)))
    while len(bits) % 8:
        bits.append(0)
    codewords = [
        int("".join(str(b) for b in bits[i : i + 8]), 2) for i in range(0, len(bits), 8)
    ]
    pad_bytes = (0xEC, 0x11)
    idx = 0
    while len(codewords) < data_cw:
        codewords.append(pad_bytes[idx % 2])
        idx += 1

    # Split into blocks and interleave
    blk_len = data_cw // blocks
    data_blocks = [codewords[i * blk_len : (i + 1) * blk_len] for i in range(blocks)]
    ec_blocks = [_rs_encode(blk, ec_per_blk) for blk in data_blocks]
    final_cw: list[int] = []
    for i in range(blk_len):
        for blk in data_blocks:
            final_cw.append(blk[i])
    for i in range(ec_per_blk):
        for blk in ec_blocks:
            final_cw.append(blk[i])

    # Build matrix
    grid: list[list[bool | None]] = [[None] * size for _ in range(size)]
    func: list[list[bool]] = [[False] * size for _ in range(size)]

    def set_func(r: int, c: int, val: bool) -> None:
        if 0 <= r < size and 0 <= c < size:
            grid[r][c] = val
            func[r][c] = True

    def finder(r0: int, c0: int) -> None:
        for dr in range(-1, 8):
            for dc in range(-1, 8):
                r, c = r0 + dr, c0 + dc
                if 0 <= r < size and 0 <= c < size:
                    in_outer = 0 <= dr <= 6 and 0 <= dc <= 6
                    on_border = dr in (0, 6) or dc in (0, 6)
                    in_center = 2 <= dr <= 4 and 2 <= dc <= 4
                    set_func(r, c, in_outer and (on_border or in_center))

    finder(0, 0)
    finder(0, size - 7)
    finder(size - 7, 0)

    for i in range(8, size - 8):
        set_func(6, i, i % 2 == 0)
        set_func(i, 6, i % 2 == 0)

    for r0 in aligns:
        for c0 in aligns:
            if func[r0][c0]:
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    set_func(r0 + dr, c0 + dc, max(abs(dr), abs(dc)) != 1)

    # Reserve format info areas + dark module
    for i in range(9):
        if not func[8][i]:
            set_func(8, i, False)
        if not func[i][8]:
            set_func(i, 8, False)
    for i in range(8):
        set_func(8, size - 1 - i, False)
        set_func(size - 1 - i, 8, False)
    set_func(size - 8, 8, True)

    # Place data bits with mask 0: (r + c) % 2 == 0
    mask = 0
    stream_bits = [(cw >> s) & 1 for cw in final_cw for s in range(7, -1, -1)]
    bit_i = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        rows = range(size - 1, -1, -1) if upward else range(size)
        for row in rows:
            for dc in (0, -1):
                c = col + dc
                if not func[row][c]:
                    bit = stream_bits[bit_i] if bit_i < len(stream_bits) else 0
                    bit_i += 1
                    if (row + c) % 2 == 0:
                        bit ^= 1
                    grid[row][c] = bool(bit)
        upward = not upward
        col -= 2

    # Write format info
    fmt = _format_bits(mask)
    for i in range(6):
        set_func(8, i, bool((fmt >> (14 - i)) & 1))
    set_func(8, 7, bool((fmt >> 8) & 1))
    set_func(8, 8, bool((fmt >> 7) & 1))
    set_func(7, 8, bool((fmt >> 6) & 1))
    for i in range(6):
        set_func(5 - i, 8, bool((fmt >> (5 - i)) & 1))
    for i in range(7):
        set_func(size - 1 - i, 8, bool((fmt >> (14 - i)) & 1))
    for i in range(8):
        set_func(8, size - 8 + i, bool((fmt >> (7 - i)) & 1))

    return [[bool(cell) for cell in row] for row in grid]


def render_qr_pixmap(text: str, pixel_size: int = 180) -> QPixmap:
    matrix = make_qr_matrix(text)
    n = len(matrix)
    quiet = 3
    total = n + quiet * 2
    img = QImage(total, total, QImage.Format.Format_RGB32)
    img.fill(QColor("#ffffff"))
    black = QColor("#111827").rgb()
    for r, row in enumerate(matrix):
        for c, val in enumerate(row):
            if val:
                img.setPixel(c + quiet, r + quiet, black)
    return QPixmap.fromImage(
        img.scaled(pixel_size, pixel_size, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
    )
