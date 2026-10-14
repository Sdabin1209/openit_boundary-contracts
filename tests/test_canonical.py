import json
import tempfile
import unittest
from pathlib import Path

from boundary_contracts import canonicalize, content_hash, directory_hash, file_hash, sha256_hash


class RFC8785Vectors(unittest.TestCase):
    def test_숫자_직렬화(self):  # RFC 8785 3.2.2의 값
        cases = {1e30: "1e+30", 4.5: "4.5", 0.002: "0.002", 1e-27: "1e-27",
                 333333333.33333329: "333333333.3333333", 1e21: "1e+21", 0.0: "0", -0.0: "0",
                 1.0: "1", 123456789012345680000.0: "123456789012345680000", 1e-6: "0.000001",
                 1e-7: "1e-7", 0.1: "0.1", -2.5: "-2.5", 5e-324: "5e-324"}
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(canonicalize(value).decode(), expected)

    def test_키_정렬은_UTF16_코드단위_순서(self):  # RFC 8785 3.2.3
        obj = {"€": "Euro Sign", "\r": "Carriage Return", "דּ": "Hebrew Letter Dalet With Dagesh",
               "1": "One", "\U0001f600": "Emoji: Grinning Face", "\u0080": "Control", "ö": "Latin Small Letter O With Diaeresis"}
        self.assertEqual(list(json.loads(canonicalize(obj))), ["\r", "1", "\u0080", "ö", "€", "\U0001f600", "דּ"])

    def test_문자열_이스케이프(self):
        self.assertEqual(canonicalize("a\"b\\c\n\x1fé/").decode(), '"a\\"b\\\\c\\n\\u001fé/"')

    def test_공백_없음과_중첩(self):
        self.assertEqual(canonicalize({"b": [1, {"d": None, "c": True}], "a": "x"}).decode(), '{"a":"x","b":[1,{"c":true,"d":null}]}')

    def test_거부(self):
        for bad in (float("nan"), float("inf"), 2**53 + 1, {1: "x"}, {"a": {1, 2}}, "\ud800"):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    canonicalize(bad)


class Hashes(unittest.TestCase):
    def test_알려진_값(self):  # 빈 객체 {} 의 SHA-256
        self.assertEqual(sha256_hash({}), "sha256:44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a")

    def test_content_hash는_자기_필드를_뺀다(self):
        rec = {"a": 1, "content_hash": "sha256:" + "0" * 64}
        self.assertEqual(content_hash(rec), sha256_hash({"a": 1}))
        rec["content_hash"] = "sha256:" + "f" * 64
        self.assertEqual(content_hash(rec), sha256_hash({"a": 1}))

    def test_디렉터리_해시는_경로와_내용에_민감하고_순서에_무관(self):
        with tempfile.TemporaryDirectory() as t:
            r = Path(t)
            (r / "b").mkdir(); (r / "a.txt").write_text("1"); (r / "b" / "c.txt").write_text("2")
            h1 = directory_hash(r)
            self.assertEqual(h1, directory_hash(r))
            (r / "a.txt").write_text("changed")
            self.assertNotEqual(h1, directory_hash(r))
            (r / "a.txt").write_text("1")
            self.assertEqual(h1, directory_hash(r))
            (r / "b" / "c.txt").rename(r / "b" / "d.txt")
            self.assertNotEqual(h1, directory_hash(r))
            self.assertTrue(file_hash(r / "a.txt").startswith("sha256:"))


if __name__ == "__main__":
    unittest.main()
