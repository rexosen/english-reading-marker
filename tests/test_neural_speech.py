import asyncio
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from src.neural_speech import (
    NeuralSpeechError,
    neural_cache_file,
    neural_cache_key,
    neural_rate,
    synthesize,
)


class FakeCommunicate:
    calls = []

    def __init__(self, text, voice, rate="+0%"):
        FakeCommunicate.calls.append((text, voice, rate))

    async def save(self, path):
        Path(path).write_bytes(b"ID3" + b"\x00" * 200)


class RateTests(unittest.TestCase):
    def test_common_speeds_map_to_edge_rate_strings(self):
        self.assertEqual(neural_rate(1.0), "+0%")
        self.assertEqual(neural_rate(0.75), "-25%")
        self.assertEqual(neural_rate(0.6), "-40%")
        self.assertEqual(neural_rate(1.25), "+25%")


class CacheKeyTests(unittest.TestCase):
    def test_key_changes_with_accent_speed_and_text(self):
        base = neural_cache_key("Hello world.", "us", 1.0)
        self.assertEqual(base, neural_cache_key("Hello   world.", "us", 1.0))
        self.assertNotEqual(base, neural_cache_key("Hello world.", "uk", 1.0))
        self.assertNotEqual(base, neural_cache_key("Hello world.", "us", 0.75))
        self.assertNotEqual(base, neural_cache_key("Hello there.", "us", 1.0))

    def test_uk_uses_sonia_like_the_phone_client(self):
        from src.neural_speech import VOICES
        self.assertEqual(VOICES['uk'], 'en-GB-SoniaNeural')
        self.assertEqual(VOICES['us'], 'en-US-AriaNeural')


class SynthesizeTests(unittest.TestCase):
    def setUp(self):
        FakeCommunicate.calls = []
        fake = types.ModuleType("edge_tts")
        fake.Communicate = FakeCommunicate
        self._patch = patch.dict(sys.modules, {"edge_tts": fake})
        self._patch.start()
        self.addCleanup(self._patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_synthesizes_and_caches(self):
        first = synthesize("Hello world.", "us", 1.0, cache_dir=self.root)
        self.assertTrue(first.exists())
        self.assertEqual(len(FakeCommunicate.calls), 1)
        text, voice, rate = FakeCommunicate.calls[0]
        self.assertEqual(text, "Hello world.")
        self.assertEqual(voice, "en-US-AriaNeural")
        self.assertEqual(rate, "+0%")
        second = synthesize("Hello world.", "us", 1.0, cache_dir=self.root)
        self.assertEqual(first, second)
        self.assertEqual(len(FakeCommunicate.calls), 1)

    def test_network_failure_raises_and_leaves_no_part_file(self):
        class Boom:
            def __init__(self, *args, **kwargs):
                pass
            async def save(self, path):
                raise OSError("no network")
        with patch.object(sys.modules["edge_tts"], "Communicate", Boom):
            with self.assertRaises(NeuralSpeechError):
                synthesize("Trip wire.", "uk", 0.75, cache_dir=self.root)
        self.assertEqual(list(self.root.rglob("*.part")), [])

    def test_empty_text_is_rejected(self):
        with self.assertRaises(NeuralSpeechError):
            synthesize("   \n  ", "us", 1.0, cache_dir=self.root)


if __name__ == "__main__":
    unittest.main()
