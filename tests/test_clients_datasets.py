import json
import shutil
import tempfile
import unittest
from pathlib import Path

from _fixtures import OTHER, READ, TOKENS, WRITE, example
from boundary_contracts import BoundaryError, file_hash
from boundary_contracts.clients import HttpDatasetStore
from conformance.servers import ReferenceServer, sealed

SYN = "fake-synthetic-token"


def build(tmp: Path, eval_scenario="s9", n_train=2):
    """올바른 데이터셋: (manifest, {경로: 파일})."""
    lines = {"lora_a/train.jsonl": [json.dumps({"scenario_id": f"s{i}", "x": i}) for i in range(n_train)],
             "lora_a/eval.jsonl": [json.dumps({"scenario_id": eval_scenario})]}
    files = {}
    for p, ls in lines.items():
        f = tmp / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("\n".join(ls) + "\n", encoding="utf-8")
        files[p] = f
    m = example("DatasetManifest")
    m["files"] = [dict(m["files"][0], path="lora_a/train.jsonl", sample_count=n_train, content_hash=file_hash(files["lora_a/train.jsonl"])),
                  dict(m["files"][1], path="lora_a/eval.jsonl", sample_count=1, content_hash=file_hash(files["lora_a/eval.jsonl"]))]
    return sealed({k: v for k, v in m.items() if k != "content_hash"}), files


class Datasets(unittest.TestCase):
    def setUp(self):
        self.srv = ReferenceServer({READ: "reader", SYN: "synthetic-data"}).start()
        self.addCleanup(self.srv.stop)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.w, self.r = HttpDatasetStore(self.srv.url, SYN), HttpDatasetStore(self.srv.url, READ)
        self.m, self.files = build(self.tmp / "src")

    def code(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception.code

    def test_게시_조회_파일_묶음_왕복(self):
        self.assertEqual(self.w.publish(self.m, self.files), self.m)
        self.assertEqual(self.r.get_manifest("ds-1", "1"), self.m)
        self.assertEqual(self.r.list_ids(), (["ds-1"], None))
        self.assertEqual(self.r.list_versions("ds-1"), ["1"])
        self.assertEqual(self.r.open_file("ds-1", "1", "lora_a/eval.jsonl").read(), self.files["lora_a/eval.jsonl"].read_bytes())
        out = self.r.download("ds-1", "1", dest=self.tmp / "dst")
        self.assertEqual(file_hash(out / "lora_a" / "train.jsonl"), self.m["files"][0]["content_hash"])

    def test_멱등과_충돌(self):
        self.w.publish(self.m, self.files)
        self.assertEqual(self.w.publish(self.m, self.files), self.m)  # 같은 내용: 성공(200)
        m2, f2 = build(self.tmp / "src2", n_train=3)
        self.assertEqual(self.code(self.w.publish, m2, f2), "CONFLICT")

    def test_읽기_토큰은_게시_거부(self):
        self.assertEqual(self.code(self.r.publish, self.m, self.files), "PERMISSION_DENIED")

    def test_게시_전_검증(self):
        self.files["lora_a/train.jsonl"].write_text('{"scenario_id":"s0"}\n', encoding="utf-8")  # 해시가 달라짐
        self.assertEqual(self.code(self.w.publish, self.m, self.files), "INTEGRITY_ERROR")
        self.assertEqual(self.code(self.w.publish, self.m, {"lora_a/train.jsonl": self.files["lora_a/train.jsonl"]}), "INVALID_RECORD")

    def test_EVAL_시나리오가_학습과_겹치면_거부(self):
        m, f = build(self.tmp / "ov", eval_scenario="s0")
        self.assertEqual(self.code(self.w.publish, m, f), "INVALID_RECORD")

    def test_서버도_같은_검증을_한다(self):
        # 클라이언트 사전 검증을 우회해 서버의 거부를 본다: 줄 수가 다른 매니페스트
        m, f = build(self.tmp / "bad")
        m = sealed({**{k: v for k, v in m.items() if k != "content_hash"}, "files": [dict(m["files"][0], sample_count=9), m["files"][1]]})
        from boundary_contracts.clients import datasets as d
        orig = d.check_publish
        d.check_publish = lambda *a, **k: None
        try:
            self.assertEqual(self.code(self.w.publish, m, f), "INVALID_RECORD")
        finally:
            d.check_publish = orig

    def test_없는_것은_NOT_FOUND(self):
        self.assertEqual(self.code(self.r.get_manifest, "nope", "1"), "NOT_FOUND")
        self.w.publish(self.m, self.files)
        self.assertEqual(self.code(self.r.open_file, "ds-1", "1", "other.jsonl"), "NOT_FOUND")

    def test_변조된_파일과_묶음은_INTEGRITY_ERROR(self):
        self.w.publish(self.m, self.files)
        self.srv.datasets[("ds-1", "1")]["files"]["lora_a/eval.jsonl"] = b'{"scenario_id":"zz"}\n'
        self.assertEqual(self.code(self.r.open_file, "ds-1", "1", "lora_a/eval.jsonl"), "INTEGRITY_ERROR")
        self.assertEqual(self.code(self.r.download, "ds-1", "1", dest=self.tmp / "d2"), "INTEGRITY_ERROR")
        self.assertFalse((self.tmp / "d2" / "ds-1").exists())

    def test_경로_탈출은_거부(self):
        m, f = build(self.tmp / "p")
        m["files"][0]["path"] = "../evil.jsonl"
        self.assertEqual(self.code(self.w.publish, m, {"../evil.jsonl": f["lora_a/train.jsonl"], "lora_a/eval.jsonl": f["lora_a/eval.jsonl"]}), "INVALID_RECORD")

    def test_토큰_없음은_PERMISSION_DENIED(self):
        self.assertEqual(self.code(HttpDatasetStore(self.srv.url, "wrong").list_ids), "PERMISSION_DENIED")


if __name__ == "__main__":
    unittest.main()
