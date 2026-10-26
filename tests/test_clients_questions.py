import unittest

from _fixtures import READ, make_server
from boundary_contracts import BoundaryError
from boundary_contracts.clients import HttpQuestionReader


class Questions(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.c = HttpQuestionReader(self.srv.url, READ)

    def test_정상_경로(self):
        ids, nxt = self.c.list_ids()
        self.assertEqual((ids, nxt), (["qs-main", "qs-other"], None))
        refs, _ = self.c.list_versions("qs-main")
        self.assertEqual([r["version"] for r in refs], ["1", "2", "3"])
        self.assertEqual(self.c.latest("qs-main")["version"], "3")
        self.assertEqual(self.c.latest("qs-main", reviewed_only=True)["version"], "2")
        bank = self.c.get_question_bank(refs[1])
        self.assertEqual(bank["version"], 2)
        self.assertEqual(len(self.c.get_reviews(refs[1])), 1)
        self.assertIsNone(self.c.get_change(refs[0]))
        self.assertEqual(self.c.get_change(refs[2])["pipeline_schema_version"], "2.0")

    def test_없으면_NOT_FOUND(self):
        with self.assertRaises(BoundaryError) as cm:
            self.c.latest("nope")
        self.assertEqual(cm.exception.code, "NOT_FOUND")
        ref = dict(self.c.list_versions("qs-main")[0][0], version="9")
        with self.assertRaises(BoundaryError) as cm:
            self.c.get_question_bank(ref)
        self.assertEqual(cm.exception.code, "NOT_FOUND")

    def test_승인된_버전이_없으면_NOT_FOUND(self):
        with self.assertRaises(BoundaryError) as cm:
            self.c.latest("qs-other", reviewed_only=True)
        self.assertEqual(cm.exception.code, "NOT_FOUND")

    def test_변조된_QuestionBank는_INTEGRITY_ERROR(self):
        ref = self.c.list_versions("qs-main")[0][1]
        self.srv.question_sets["qs-main"][1]["bank"]["questions"][0]["text"] = "바뀐 질문"
        with self.assertRaises(BoundaryError) as cm:
            self.c.get_question_bank(ref)
        self.assertEqual(cm.exception.code, "INTEGRITY_ERROR")

    def test_ref_형식_위반은_INVALID_RECORD(self):
        with self.assertRaises(BoundaryError) as cm:
            self.c.get_question_bank({"id": "qs-main"})
        self.assertEqual(cm.exception.code, "INVALID_RECORD")

    def test_스키마_위반_리뷰는_INTEGRITY_ERROR(self):
        ref = self.c.list_versions("qs-main")[0][1]
        self.srv.question_sets["qs-main"][1]["reviews"][0] = {"review_id": "x"}
        with self.assertRaises(BoundaryError) as cm:
            self.c.get_reviews(ref)
        self.assertEqual(cm.exception.code, "INTEGRITY_ERROR")

    def test_페이지네이션(self):
        for i in range(5):
            from _fixtures import bank
            self.srv.add_question_set(f"qs-x{i}", bank(1))
        seen, cur, pages = [], None, 0
        while True:
            items, cur = self.c.list_ids(cursor=cur, limit=3)
            seen += items
            pages += 1
            if cur is None:
                break
        self.assertEqual((len(seen), pages), (7, 3))
        self.assertEqual(seen, sorted(seen))
        self.assertTrue(any("cursor=3" in p and "limit=3" in p for _, p, _ in self.srv.requests))


if __name__ == "__main__":
    unittest.main()
