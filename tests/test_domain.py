import unittest

from src.domain import (
    find_selected_word,
    normalize_article_text,
    python_offset_to_qt,
    qt_offset_to_python,
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


if __name__ == "__main__":
    unittest.main()
