import unittest

from src.dictation import compare, tokens


class DictationTests(unittest.TestCase):
    def test_tokens_ignore_case_punctuation_and_keep_numbers(self):
        self.assertEqual(tokens("E-waste harms 62 million, human health!"),
                         ["e-waste", "harms", "62", "million", "human", "health"])

    def test_apostrophe_style_does_not_change_the_word(self):
        self.assertEqual(compare("Don't do it.", "dont do it")["accuracy"], 1.0)

    def test_exact_sentence_is_fully_correct(self):
        result = compare("Recycling rates stay very low.", "recycling rates stay very low")
        self.assertEqual(result["accuracy"], 1.0)
        self.assertEqual(result["statuses"], ["ok"] * len(result["expected"]))
        self.assertEqual(result["extra"], [])

    def test_missing_words_are_flagged_as_missing(self):
        result = compare("The report also notes nearly 91 billion.",
                         "the report nearly billion")
        self.assertEqual(result["statuses"].count("ok"), 4)
        self.assertEqual(result["statuses"].count("missing"), 3)
        self.assertEqual(result["extra"], [])

    def test_substituted_word_is_wrong_and_shows_as_extra(self):
        result = compare("Only 22 percent was recycled.", "only twenty-two percent was recycled")
        self.assertEqual(result["statuses"], ["ok", "wrong", "ok", "ok", "ok"])
        self.assertEqual(result["extra"], ["twenty-two"])

    def test_nothing_typed_counts_every_word_missing(self):
        result = compare("E-waste harms health.", "")
        self.assertEqual(result["accuracy"], 0.0)
        self.assertEqual(result["statuses"], ["missing", "missing", "missing"])

    def test_empty_expected_sentence_is_fully_accurate(self):
        self.assertEqual(compare("", "anything")["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
