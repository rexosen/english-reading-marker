from __future__ import annotations
import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
from src.domain import WORD_PATTERN

class PronunciationError(RuntimeError):
    pass

def audio_word(text):
    text=text.strip().replace("’", "'")
    if len(text)>80 or not WORD_PATTERN.fullmatch(text):
        raise PronunciationError("词典发音只支持单个英文单词。")
    return text if text.isupper() and len(text)>1 else text.lower()

def valid_mp3(data):
    return len(data)>=128 and (data.startswith(b'ID3') or data[0]==255 and data[1]&224==224)

def pronunciation_file(word,accent='us',cache_dir=None,timeout=4):
    word=audio_word(word)
    if accent not in ('us','uk'):raise PronunciationError('不支持的口音')
    from src.storage import data_directory
    root=Path(cache_dir) if cache_dir else data_directory()/'pronunciation'
    root.mkdir(parents=True,exist_ok=True)
    path=root/(hashlib.sha256((accent+':'+word).encode()).hexdigest()+'.mp3')
    if path.exists() and valid_mp3(path.read_bytes()):return path
    query=urlencode({'audio':word,'type':2 if accent=='us' else 1})
    try:
        with urlopen(Request('https://dict.youdao.com/dictvoice?'+query,headers={'User-Agent':'Mozilla/5.0 ReadingDesk/1.1'}),timeout=timeout) as response:
            data=response.read(512001)
        if len(data)>512000 or not valid_mp3(data):raise ValueError('无效的音频')
        with tempfile.NamedTemporaryFile(dir=root,suffix='.tmp',delete=False) as temp:
            temp.write(data);temporary=Path(temp.name)
        try:os.replace(temporary,path)
        finally:temporary.unlink(missing_ok=True)
        return path
    except (OSError,ValueError) as error:
        raise PronunciationError('词典音频暂不可用，改用较慢的系统英文语音。') from error
