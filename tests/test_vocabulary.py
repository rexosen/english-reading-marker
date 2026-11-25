import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from src.repository import ReaderRepository
from src.study import StudyRepository, set_study
from src.vocabulary import (AUTO_LISTENING, AUTO_READING, VocabularyCategories, category_from_title,
                            word_key, word_of_key)


def add_word(repository, article_id, word, definition="释义"):
    text = repository.get_article(article_id)["text"]
    start = text.index(word)
    return repository.add_vocabulary(article_id, start, start + len(word), word, definition)


class VocabularyCategoryTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repository = ReaderRepository(Path(self.temp_dir.name) / "reader.sqlite3")
        self.study = StudyRepository(self.repository)
        self.categories = VocabularyCategories(self.study)
        self.reading = self.repository.create_article("阅读:在线课程的局限与教育质量",
                                                      "Online classes are far more compatible for busy people.")
        self.listening = self.repository.create_article("听力:非洲简界智能手机",
                                                        "These devices are genuinely cheap.")
        self.plain = self.repository.create_article("无前缀文章", "Students learn at their own pace.")

    def tearDown(self):
        self.repository.close()
        self.temp_dir.cleanup()

    def test_titles_decide_the_builtin_categories(self):
        self.assertEqual(category_from_title("听力:非洲简界智能手机"), AUTO_LISTENING)
        self.assertEqual(category_from_title("阅读：课程局限"), AUTO_READING)
        self.assertEqual(category_from_title("Listening: Section C"), AUTO_LISTENING)
        self.assertEqual(category_from_title("Reading — Section B"), "")
        self.assertEqual(category_from_title("无前缀文章"), "")

    def test_records_are_annotated_without_touching_the_database(self):
        add_word(self.repository, self.reading, "compatible")
        add_word(self.repository, self.listening, "genuinely")
        add_word(self.repository, self.plain, "pace")
        info = {article["id"]: {"title": article["title"], "group": ""} for article in self.repository.list_articles()}
        annotated = {record["word"]: record["category"]
                     for record in self.categories.annotate(self.repository.list_vocabulary(), info)}
        self.assertEqual(annotated["compatible"], AUTO_READING)
        self.assertEqual(annotated["genuinely"], AUTO_LISTENING)
        self.assertEqual(annotated["pace"], "")

    def test_article_group_is_the_fallback_when_the_title_has_no_prefix(self):
        key = self.categories.create("听力")
        self.assertEqual(key, AUTO_LISTENING, "a category named 听力 is the built-in one")
        add_word(self.repository, self.plain, "pace")
        info = {self.plain: {"title": "无前缀文章", "group": "听力"}}
        annotated = self.categories.annotate(self.repository.list_vocabulary(), info)
        pace = [record for record in annotated if record["word"] == "pace"][0]
        self.assertEqual(pace["category"], AUTO_LISTENING)
        self.assertEqual(pace["category_name"], "听力")

    def test_manual_assignment_wins_and_is_shared_per_word(self):
        first = add_word(self.repository, self.reading, "compatible")
        second_article = self.repository.create_article("听力:第二篇", "The cable is compatible with all models.")
        second = add_word(self.repository, second_article, "compatible")
        custom = self.categories.create("必背")
        self.categories.assign("Compatible", custom)
        self.assertEqual(self.categories.manual("compatible"), custom, "case and spacing insensitive")
        info = {article["id"]: {"title": article["title"], "group": ""} for article in self.repository.list_articles()}
        keys = {record["id"]: record["category"]
                for record in self.categories.annotate(self.repository.list_vocabulary(), info)}
        self.assertEqual(keys[first], custom)
        self.assertEqual(keys[second], custom)
        self.assertEqual(self.repository.connection.execute(
            "SELECT COUNT(*) FROM study_items WHERE key LIKE 'vcat:%'").fetchone()[0], 1)

    def test_clearing_an_assignment_falls_back_to_the_title(self):
        add_word(self.repository, self.reading, "compatible")
        custom = self.categories.create("易混")
        self.categories.assign("compatible", custom)
        self.categories.assign("compatible", "")
        self.assertEqual(self.categories.manual("compatible"), "")
        self.assertEqual(self.categories.resolve("compatible", "阅读:在线课程的局限与教育质量"), AUTO_READING)

    def test_category_names_are_unique_and_builtin_names_are_protected(self):
        custom = self.categories.create("必背")
        self.assertEqual(self.categories.create("必 背"), custom, "names are matched ignoring spacing")
        with self.assertRaises(ValueError):
            self.categories.rename(AUTO_READING, "跳过")
        with self.assertRaises(ValueError):
            self.categories.delete(AUTO_LISTENING)
        self.categories.rename(custom, "只识不拼")
        self.assertEqual(self.categories.name(custom), "只识不拼")

    def test_deleting_a_category_returns_its_words_to_auto(self):
        add_word(self.repository, self.reading, "compatible")
        custom = self.categories.create("必背")
        self.categories.assign("compatible", custom)
        self.assertEqual(len(self.categories.every_assignment()), 1)
        self.categories.delete(custom)
        self.assertNotIn(custom, self.categories.all())
        self.assertEqual(self.categories.every_assignment(), {}, "the stale word record must be removed too")
        self.assertEqual(self.categories.manual("compatible"), "")
        info = {article["id"]: {"title": article["title"], "group": ""} for article in self.repository.list_articles()}
        annotated = [record for record in self.categories.annotate(self.repository.list_vocabulary(), info)
                     if record["word"] == "compatible"][0]
        self.assertEqual(annotated["category"], AUTO_READING)

    def test_phrase_words_survive_the_key_grammar(self):
        article = self.repository.create_article("阅读:第三篇", "The course is in demand now.")
        add_word(self.repository, article, "in demand")
        custom = self.categories.create("短语")
        self.categories.assign("in demand", custom)
        self.assertEqual(word_of_key(word_key("in demand")), "in demand")
        self.assertEqual(self.categories.manual("in demand"), custom)

    def test_study_records_reject_unknown_categories_and_bad_keys(self):
        with self.assertRaises(ValueError):
            set_study(self.repository.connection, word_key("pace"), {"word": "pace", "group": "vgroup:none"})
        with self.assertRaises(ValueError):
            set_study(self.repository.connection, "vcat:not allowed", {"word": "pace", "group": AUTO_READING})

    def test_word_category_syncs_as_a_study_record(self):
        from src.lan_sync import snapshot

        before = self.repository.sync_revision()
        add_word(self.repository, self.reading, "compatible")
        custom = self.categories.create("必背")
        self.categories.assign("compatible", custom)
        state = snapshot(self.repository.connection, "test-client")
        self.assertGreater(state["revision"], before)
        stored = {key: value for key, value in state["study"].items() if key.startswith(("vgroup:", "vcat:"))}
        self.assertEqual(list(stored.values()), [{"name": "必背"}, {"word": "compatible", "group": custom}])


    def test_manual_entries_join_the_review_queue(self):
        add_word(self.repository, self.reading, "compatible")
        vocabulary_id = self.repository.add_manual_vocabulary("in demand", "有需求的", "Jobs are in demand.")
        custom = self.categories.create("必背")
        self.categories.assign("in demand", custom)
        cards = {card["word"]: card for card in self.study.review_cards(all_cards=True)}
        self.assertIn("in demand", cards)
        card = cards["in demand"]
        self.assertEqual(card["key"], f"review:manual:{vocabulary_id}")
        self.assertIsNone(card["sync_id"])
        self.assertTrue(card["manual"])
        self.study.grade(card, "hard")
        record = self.study.items()[card["key"]]
        self.assertEqual((record["manual"], record["vocabulary_id"], record["grade"]), (True, vocabulary_id, "hard"))
        # an article-bound word still uses the position-based key
        article_card = [entry for entry in self.study.review_cards(all_cards=True) if entry["word"] == "compatible"][0]
        self.assertTrue(article_card["key"].startswith("review:"))
        self.assertNotIn("manual", article_card["key"])

    def test_manual_review_records_are_validated(self):
        from datetime import datetime, timezone

        vocabulary_id = self.repository.add_manual_vocabulary("take over", "接管")
        schedule = {"grade": "hard", "due": datetime.now(timezone.utc).isoformat(), "interval": 1.0, "count": 1}
        set_study(self.repository.connection, f"review:manual:{vocabulary_id}", {"manual": True, "vocabulary_id": vocabulary_id, **schedule})
        with self.assertRaises(ValueError):
            set_study(self.repository.connection, "review:manual:99999", {"manual": True, "vocabulary_id": 99999, **schedule})
        article_word = [entry for entry in self.repository.list_vocabulary() if not entry["manual"]]
        self.assertEqual(article_word, [])

    def test_word_keys_match_the_android_encoder(self):
        # 这些字面量同时被 tests/mobile_vocabulary.test.cjs 断言，两端共用一套编号
        expected = {"don’t": "don%E2%80%99t", "don't": "don%27t", "in demand": "in%20demand", "e.g.": "e.g.",
                    "a-b~c": "a-b~c", "what (really)!": "what%20%28really%29%21", "take over*": "take%20over%2A",
                    "x_y.z~1": "x_y.z~1", "50%": "50%25", "A+B": "a%2Bb"}
        for word, key in expected.items():
            self.assertEqual(word_key(word), "vcat:" + key)
            self.assertEqual(word_of_key(word_key(word)), word.casefold())

    def test_category_names_are_stored_collapsed_and_compared_loosely(self):
        key = self.categories.create(" 必  背 ")
        self.assertEqual(self.categories.name(key), "必 背")
        self.assertEqual(self.categories.create("必背"), key)
        self.assertEqual(self.categories.find_by_name("必 背"), key)

    def test_manual_entries_have_no_auto_category_until_assigned(self):
        self.repository.add_manual_vocabulary("put off", "推迟")
        info = {article["id"]: {"title": article["title"], "group": ""} for article in self.repository.list_articles()}
        record = [entry for entry in self.categories.annotate(self.repository.list_vocabulary(), info)
                  if entry["word"] == "put off"][0]
        self.assertEqual(record["category"], "")
        custom = self.categories.create("易混")
        self.categories.assign("put off", custom)
        assigned = [entry for entry in self.categories.annotate(self.repository.list_vocabulary(), info)
                    if entry["word"] == "put off"][0]
        self.assertEqual((assigned["category"], assigned["category_name"]), (custom, "易混"))


if __name__ == "__main__":
    unittest.main()
