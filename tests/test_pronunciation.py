import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from src.pronunciation import pronunciation_file,PronunciationError

class AudioResponse:
    def __init__(self,data):self.data=data
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,*args):return self.data

class PronunciationTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()

    def test_american_word_is_cached_and_not_downloaded_twice(self):
        audio=b'ID3'+b'a'*200
        with patch('src.pronunciation.urlopen',return_value=AudioResponse(audio)) as request:
            first=pronunciation_file('Online','us',self.root)
            second=pronunciation_file('online','us',self.root)
            self.assertEqual(first,second);self.assertEqual(first.read_bytes(),audio)
            self.assertEqual(request.call_count,1)
            self.assertIn('type=2',request.call_args.args[0].full_url)

    def test_uk_and_us_audio_use_separate_cache_entries(self):
        with patch('src.pronunciation.urlopen',return_value=AudioResponse(b'ID3'+b'a'*200)) as request:
            us=pronunciation_file('online','us',self.root)
            uk=pronunciation_file('online','uk',self.root)
            self.assertNotEqual(us,uk)
            self.assertIn('type=1',request.call_args.args[0].full_url)

    def test_html_error_is_not_saved_as_audio(self):
        with patch('src.pronunciation.urlopen',return_value=AudioResponse(b'<html>'+b'a'*200)):
            with self.assertRaises(PronunciationError):pronunciation_file('online','us',self.root)
        self.assertEqual(list(self.root.glob('*.mp3')),[])

    def test_sentence_does_not_get_sent_to_word_audio_service(self):
        with patch('src.pronunciation.urlopen') as request:
            with self.assertRaises(PronunciationError):pronunciation_file('A long sentence.','us',self.root)
            request.assert_not_called()

    def test_network_failure_produces_fallback_reason(self):
        with patch('src.pronunciation.urlopen',side_effect=TimeoutError()):
            with self.assertRaisesRegex(PronunciationError,'系统英文语音'):pronunciation_file('online','us',self.root)
