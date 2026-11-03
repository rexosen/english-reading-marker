import json
import unittest
from unittest.mock import patch
from urllib.error import URLError

from src.dictionary import DictionaryError, lookup_chinese


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class DictionaryTests(unittest.TestCase):
    def setUp(self):
        self.cache_patch = patch("src.dictionary.cached_translation", return_value=None)
        self.cache_patch.start()
        self.addCleanup(self.cache_patch.stop)

    def test_lookup_translates_only_the_requested_word(self):
        response = FakeResponse({"responseStatus": 200, "responseData": {"translatedText": "不频繁的"}})

        with patch("src.dictionary.urlopen", return_value=response) as open_url:
            translation = lookup_chinese("infrequent")

        self.assertEqual(translation, "不频繁的")
        request = open_url.call_args.args[0]
        self.assertIn("q=infrequent", request.full_url)
        self.assertIn("tl=zh-CN", request.full_url)

    def test_lookup_reports_a_missing_result(self):
        response = FakeResponse({"responseStatus": 200, "responseData": {"translatedText": "unknownword"}})

        with patch("src.dictionary.urlopen", return_value=response):
            with self.assertRaises(DictionaryError):
                lookup_chinese("unknownword")

    def test_lookup_reports_network_errors(self):
        with patch("src.dictionary.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(DictionaryError):
                lookup_chinese("infrequent")


if __name__ == "__main__":
    unittest.main()
