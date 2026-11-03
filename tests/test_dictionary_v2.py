import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from src.dictionary import cached_translation, lookup_chinese, _chunks

class TranslationV2Tests(unittest.TestCase):
    def test_online_local_dictionary_does_not_request_network(self):
        with patch("src.dictionary.urlopen") as network:
            self.assertIn("联机", lookup_chinese("online"))
            network.assert_not_called()

    def test_repeated_sentence_uses_persistent_cache(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "cache.sqlite3"
            with patch("src.dictionary._cache_path", return_value=path):
                with patch("src.dictionary._translate_chunk", return_value="这是一个句子。") as remote:
                    self.assertEqual(lookup_chinese("This is a test sentence."), "这是一个句子。")
                    self.assertEqual(lookup_chinese("This is a test sentence."), "这是一个句子。")
                    self.assertEqual(remote.call_count, 1)

    def test_paragraphs_are_split_within_provider_byte_limit(self):
        text = "These online classes help students learn. " * 60
        chunks = _chunks(text)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(part.encode("utf-8")) <= 450 for part in chunks))
        self.assertEqual(" ".join(chunks), text.strip())
