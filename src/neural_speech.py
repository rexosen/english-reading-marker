"""Neural (edge-tts) sentence/article reading for the desktop reader.

Keeps the same state contract as QTextToSpeech so the sentence-by-sentence
loop, pause/resume and dictation all keep working; on any failure (for
example no network) the main window falls back to the system voice.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtTextToSpeech import QTextToSpeech

VOICES = {'us': 'en-US-AriaNeural', 'uk': 'en-GB-SoniaNeural'}


class NeuralSpeechError(RuntimeError):
    pass


def neural_rate(speed):
    """Map a playback multiple like 0.75 to an edge-tts rate string like '-25%'."""
    percent = int(round((float(speed) - 1.0) * 100.0))
    return f"{percent:+d}%"


def neural_cache_key(text, accent, speed):
    voice = VOICES.get(accent, VOICES['us'])
    raw = f"{voice}|{neural_rate(speed)}|{' '.join(text.split())}"
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def neural_cache_file(text, accent, speed, cache_dir):
    return Path(cache_dir) / 'neural' / f"{neural_cache_key(text, accent, speed)}.mp3"


def synthesize(text, accent='us', speed=1.0, cache_dir=None):
    """Render text to an mp3 (cached). Returns the file path."""
    text = ' '.join(str(text).split())
    if not text:
        raise NeuralSpeechError('没有可朗读的内容。')
    if cache_dir is None:
        from src.storage import data_directory
        cache_dir = data_directory()
    path = neural_cache_file(text, accent, speed, cache_dir)
    if path.exists() and path.stat().st_size >= 128:
        return path
    voice = VOICES.get(accent, VOICES['us'])
    try:
        import edge_tts
    except ImportError as error:
        raise NeuralSpeechError('神经网络语音组件未安装。') from error
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.part')

    async def run():
        await edge_tts.Communicate(text, voice, rate=neural_rate(speed)).save(str(temporary))

    try:
        asyncio.run(asyncio.wait_for(run(), timeout=15))
        if not temporary.exists() or temporary.stat().st_size < 128:
            raise NeuralSpeechError('神经网络语音返回了空音频。')
        os.replace(temporary, path)
        return path
    except NeuralSpeechError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as error:
        temporary.unlink(missing_ok=True)
        raise NeuralSpeechError('神经网络语音暂不可用（请检查网络）。') from error


def split_chunks(text: str, limit: int = 260) -> list[str]:
    """Split long passages into manageable chunks so neural TTS starts quickly and won't time out."""
    text = ' '.join(str(text).split())
    if not text:
        return []
    if len(text) <= limit:
        return [text]
    from src.study import sentence_ranges
    chunks: list[str] = []
    for _, _, sentence in sentence_ranges(text):
        remaining = sentence.strip()
        while len(remaining) > limit:
            cut = remaining.rfind(' ', 0, limit)
            if cut <= 0:
                cut = limit
            chunks.append(remaining[:cut].strip())
            remaining = remaining[cut:].strip()
        if remaining:
            if chunks and len(chunks[-1]) + 1 + len(remaining) <= limit:
                chunks[-1] = chunks[-1] + ' ' + remaining
            else:
                chunks.append(remaining)
    return chunks or [text]


class _WorkerSignals(QObject):
    finished = Signal(int, str, object)


class _SynthesizeWorker(QRunnable):
    def __init__(self, text, accent, speed, request_id):
        super().__init__()
        self.text, self.accent, self.speed, self.request_id = text, accent, float(speed), request_id
        self.signals = _WorkerSignals()

    @Slot()
    def run(self):
        try:
            result = synthesize(self.text, self.accent, self.speed)
        except Exception as error:
            result = error
        self.signals.finished.emit(self.request_id, self.text, result)


class NeuralSpeech(QObject):
    """Plays edge-tts audio with a QTextToSpeech-like state machine."""

    stateChanged = Signal(object)
    errorOccurred = Signal(str, str)  # text, reason

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_pool = QThreadPool.globalInstance()
        self.player = QMediaPlayer(self)
        self.output = QAudioOutput(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(0.9)
        self._state = QTextToSpeech.State.Ready
        self._request_id = 0
        self._spoken = False
        self._pending_text = ''
        self._queue: list[str] = []
        self._accent = 'us'
        self._speed = 1.0
        self.player.playbackStateChanged.connect(self._on_playback_state)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.player.errorOccurred.connect(self._on_player_error)

    def state(self):
        return self._state

    def _set_state(self, state):
        if state != self._state:
            self._state = state
            self.stateChanged.emit(state)

    def say(self, text, accent='us', speed=1.0):
        chunks = split_chunks(text)
        if not chunks:
            return
        self._request_id += 1
        self._accent = accent
        self._speed = float(speed)
        self._queue = chunks[1:]
        self._spoken = False
        self.player.stop()
        self._start_chunk(chunks[0])

    def _start_chunk(self, text):
        request_id = self._request_id
        self._pending_text = text
        self._spoken = False
        if self._state != QTextToSpeech.State.Speaking:
            self._set_state(QTextToSpeech.State.Synthesizing)
        worker = _SynthesizeWorker(text, self._accent, self._speed, request_id)
        worker.signals.finished.connect(self._on_synthesized)
        self.thread_pool.start(worker)

    def _on_synthesized(self, request_id, text, result):
        if request_id != self._request_id:
            return
        if isinstance(result, Exception):
            remaining = ' '.join([text, *self._queue])
            self._queue = []
            self._pending_text = ''
            self._set_state(QTextToSpeech.State.Ready)
            self.errorOccurred.emit(remaining, str(result))
            return
        self.player.setSource(QUrl.fromLocalFile(str(result)))
        self.player.play()

    def _finish(self):
        self._pending_text = ''
        if self._queue:
            next_chunk = self._queue.pop(0)
            self._start_chunk(next_chunk)
            return
        if self._spoken:
            self._spoken = False
            self._set_state(QTextToSpeech.State.Ready)
        elif self._state != QTextToSpeech.State.NotReady:
            self._set_state(QTextToSpeech.State.Ready)

    def _on_playback_state(self, state):
        if state == QMediaPlayer.PlaybackState.PlayingState:
            self._spoken = True
            self._set_state(QTextToSpeech.State.Speaking)
        elif state == QMediaPlayer.PlaybackState.PausedState:
            self._set_state(QTextToSpeech.State.Paused)
        elif state == QMediaPlayer.PlaybackState.StoppedState:
            if self._spoken and not self._queue:
                self._finish()

    def _on_media_status(self, status):
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self._finish()

    def _on_player_error(self, error):
        if error == QMediaPlayer.Error.NoError:
            return
        remaining = ' '.join([p for p in [self._pending_text, *self._queue] if p])
        self._pending_text = ''
        self._queue = []
        self._spoken = False
        self._set_state(QTextToSpeech.State.Ready)
        if remaining:
            self.errorOccurred.emit(remaining, '音频播放失败，')

    def pause(self):
        if self._state == QTextToSpeech.State.Speaking:
            self.player.pause()

    def resume(self):
        if self._state == QTextToSpeech.State.Paused:
            self.player.play()

    def stop(self):
        self._request_id += 1
        self._pending_text = ''
        self._queue = []
        self._spoken = False
        self.player.stop()
        self._set_state(QTextToSpeech.State.Ready)
