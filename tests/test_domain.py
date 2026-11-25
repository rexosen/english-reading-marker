import unittest

from src.domain import (
    find_selected_phrase,
    find_selected_word,
    normalize_article_text,
    python_offset_to_qt,
    qt_offset_to_python,
    trim_range,
)


class DomainTests(unittest.TestCase):
    def test_normalize_article_text_preserves_paragraphs_and_normalizes_newlines(self):
        source = "  First paragraph.\r\n\r\nSecond paragraph.  "

        self.assertEqual(
            normalize_article_text(source),
            "First paragraph.\n\nSecond paragraph.",
        )

    def test_find_selected_word_returns_only_the_selected_repeated_occurrence(self):
        article = "Students learn. Other students work."
        first_start = article.index("Students")
        second_start = article.index("students")

        first = find_selected_word(article, first_start, first_start + len("Students"))
        second = find_selected_word(article, second_start, second_start + len("students"))

        self.assertEqual(first, (first_start, first_start + len("Students"), "Students"))
        self.assertEqual(second, (second_start, second_start + len("students"), "students"))

    def test_find_selected_word_accepts_english_apostrophe_words(self):
        article = "It's often impersonal."
        start = article.index("It's")

        self.assertEqual(find_selected_word(article, start, start + 4), (start, start + 4, "It's"))

    def test_find_selected_word_accepts_hyphenated_terms(self):
        article = "face-to-face interaction"

        self.assertEqual(find_selected_word(article, 0, len("face-to-face")), (0, 12, "face-to-face"))

    def test_find_selected_word_rejects_a_selection_that_contains_multiple_words(self):
        article = "Online classes help students."

        self.assertIsNone(find_selected_word(article, 0, len("Online classes")))

    def test_find_selected_word_rejects_invalid_ranges(self):
        self.assertIsNone(find_selected_word("word", -1, 2))
        self.assertIsNone(find_selected_word("word", 0, 9))
        self.assertIsNone(find_selected_word("word", 2, 2))

    def test_sentence_for_range_returns_last_sentence_when_there_is_no_punctuation(self):
        from src.domain import sentence_for_range

        self.assertEqual(sentence_for_range("A term at the end", 10, 13), "A term at the end")

    def test_offsets_account_for_non_bmp_characters_before_a_word(self):
        text = "😀students"

        qt_start = python_offset_to_qt(text, 1)

        self.assertEqual(qt_start, 2)
        self.assertEqual(qt_offset_to_python(text, qt_start), 1)


    def test_find_selected_phrase_accepts_multi_word_terms(self):
        article = "By contrast, fossil fuel plastic was more expensive."
        start = article.index("fossil fuel")

        self.assertEqual(find_selected_phrase(article, start, start + 11),
                         (start, start + 11, "fossil fuel"))
        # 拖选常带首尾空格：范围收到文字本身，位置仍与原文严格对应
        padded = find_selected_phrase(article, start - 1, start + 12)
        self.assertEqual(padded, (start, start + 11, "fossil fuel"))
        self.assertEqual(article[padded[0]:padded[1]], padded[2])

    def test_find_selected_phrase_accepts_hyphens_apostrophes_and_digits(self):
        for text, term in (("newly-made plastic is cheap", "newly-made plastic"),
                           ("don't give up now", "don't give up"),
                           ("the price is mp3 level", "mp3 level"),
                           ("e.g. recycled plastic works", "e.g. recycled plastic")):
            start = text.index(term)
            self.assertEqual(find_selected_phrase(text, start, start + len(term)),
                             (start, start + len(term), term))

    def test_find_selected_phrase_rejects_sentences_and_partial_words(self):
        article = "The price increase of recycled plastic could cost sustainable manufacturers an extra year."
        self.assertIsNone(find_selected_phrase(article, 0, len("The price increase of recycled plastic could cost")))
        self.assertIsNone(find_selected_phrase(article, 4, 11), "cutting inside a word must not count")
        self.assertIsNone(find_selected_phrase(article, 5, 9), "'rice' 是从 price 中间截的")
        self.assertIsNone(find_selected_phrase(article, -1, 5))
        self.assertIsNone(find_selected_phrase(article, 0, 999))
        self.assertIsNone(find_selected_phrase("  ", 0, 2))
        self.assertIsNone(find_selected_phrase("price, increase", 0, len("price, increase")), "标点不算词组")

    def test_find_selected_phrase_honours_the_word_limit(self):
        text = "one two three four five six seven"
        self.assertIsNotNone(find_selected_phrase(text, 0, len("one two three four five six")))
        self.assertIsNone(find_selected_phrase(text, 0, len(text)))
        self.assertIsNotNone(find_selected_phrase(text, 0, len(text), max_words=7))

    def test_trim_range_skips_surrounding_whitespace(self):
        text = "  word  "
        self.assertEqual(trim_range(text, 0, len(text)), (2, 6))
        self.assertEqual(trim_range("a\n\tb\n", 0, 5), (0, 4))


if __name__ == "__main__":
    unittest.main()
