import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from _fixtures import FILES_A, READ, WRITE, OTHER, make_server, package_manifest
from boundary_contracts import BoundaryError, directory_hash
from boundary_contracts.clients import HttpModelRegistry


def adapter_dir(root, files=FILES_A):
    for p, d in files.items():
        f = Path(root) / p
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(d)
    return Path(root)


class Models(unittest.TestCase):
    def setUp(self):
        self.srv = make_server().start()
        self.addCleanup(self.srv.stop)
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(__import__("shutil").rmtree, self.tmp, True)
        self.w = HttpModelRegistry(self.srv.url, OTHER)  # 쓰기 역할 model-lab
        self.r = HttpModelRegistry(self.srv.url, READ)
        self.adir = adapter_dir(self.tmp / "src")
        self.m = package_manifest()

    def code(self, fn, *a, **k):
        with self.assertRaises(BoundaryError) as cm:
            fn(*a, **k)
        return cm.exception.code

    def test_게시_조회_어댑터_왕복(self):
        self.assertEqual(self.w.publish(self.m, self.adir, b"report"), self.m)
        self.assertEqual(self.r.get_manifest("lora-a", "1.2.0"), self.m)
        self.assertEqual(self.r.list_ids(), (["lora-a"], None))
        self.assertEqual(self.r.list_versions("lora-a"), ["1.2.0"])
        self.assertEqual(self.r.get_eval_report("eval-7"), b"report")
        out = self.r.open_adapter("lora-a", "1.2.0", dest=self.tmp / "dst")
        self.assertEqual(directory_hash(out), self.m["adapter_hash"])
        self.assertEqual((out / "sub" / "weights.bin").read_bytes(), b"\x00\x01\x02")

    def test_멱등과_충돌(self):
        self.w.publish(self.m, self.adir, b"r")
        self.w.publish(self.m, self.adir, b"r")  # 같은 내용: 성공
        other = package_manifest()
        other["created_at"] = "2026-10-16T00:00:00Z"
        from conformance.servers import sealed
        other = sealed({k: v for k, v in other.items() if k != "content_hash"})
        self.assertEqual(self.code(self.w.publish, other, self.adir, b"r"), "CONFLICT")

    def test_읽기_토큰은_게시_거부(self):
        self.assertEqual(self.code(self.r.publish, self.m, self.adir, b"r"), "PERMISSION_DENIED")

    def test_게시_전_검증(self):
        (self.adir / "extra").write_bytes(b"x")
        self.assertEqual(self.code(self.w.publish, self.m, self.adir, b"r"), "INTEGRITY_ERROR")
        self.assertEqual(self.code(self.w.publish, {"version": "1"}, self.adir, b"r"), "INVALID_RECORD")
        self.assertEqual([p for _, p, _ in self.srv.requests if p == "/v1/packages"], [])

    def test_없는_패키지(self):
        self.assertEqual(self.code(self.r.get_manifest, "x", "1"), "NOT_FOUND")
        self.assertEqual(self.code(self.r.get_eval_report, "nope"), "NOT_FOUND")

    def test_변조된_어댑터는_INTEGRITY_ERROR이고_파일을_지운다(self):
        self.w.publish(self.m, self.adir, b"r")
        self.srv.packages[("lora-a", "1.2.0")]["files"]["sub/weights.bin"] = b"tampered"
        dst = self.tmp / "dst"
        self.assertEqual(self.code(self.r.open_adapter, "lora-a", "1.2.0", dest=dst), "INTEGRITY_ERROR")
        self.assertEqual(list(dst.rglob("*")), [])

    def test_시스템_프롬프트가_어댑터와_짝이다(self):
        # 프롬프트 파일이 없으면 게시 전에 거부한다(어댑터 해시를 다시 맞춰도 마찬가지)
        import copy
        from conformance.servers import adapter_digest, sealed
        files = {k: v for k, v in FILES_A.items() if k != "system_prompt.txt"}
        m = {k: v for k, v in self.m.items() if k != "content_hash"}
        m["adapter_hash"] = adapter_digest(files)
        self.assertEqual(self.code(self.w.publish, sealed(m), adapter_dir(self.tmp / "noprompt", files), b"r"), "INTEGRITY_ERROR")
        # 파일 내용이 manifest의 sha256과 다르면 거부
        files2 = dict(FILES_A, **{"system_prompt.txt": "다른 프롬프트".encode()})
        m2 = copy.deepcopy(self.m)
        m2["adapter_hash"] = adapter_digest(files2)
        m2 = sealed({k: v for k, v in m2.items() if k != "content_hash"})
        self.assertEqual(self.code(self.w.publish, m2, adapter_dir(self.tmp / "otherprompt", files2), b"r"), "INTEGRITY_ERROR")
        # 서버에 올라간 뒤 프롬프트만 바뀌면(어댑터 해시도 맞춰 두어도) 열 때 거부
        self.w.publish(self.m, self.adir, b"r")
        pkg = self.srv.packages[("lora-a", "1.2.0")]
        pkg["files"]["system_prompt.txt"] = "바뀐 프롬프트".encode()
        pkg["manifest"] = sealed({**{k: v for k, v in pkg["manifest"].items() if k != "content_hash"},
                                  "adapter_hash": adapter_digest(pkg["files"])})
        self.assertEqual(self.code(self.r.open_adapter, "lora-a", "1.2.0", dest=self.tmp / "dst2"), "INTEGRITY_ERROR")

    def test_변조된_매니페스트는_INTEGRITY_ERROR(self):
        self.w.publish(self.m, self.adir, b"r")
        self.srv.packages[("lora-a", "1.2.0")]["manifest"]["role"] = "LORA_B"
        self.assertEqual(self.code(self.r.get_manifest, "lora-a", "1.2.0"), "INTEGRITY_ERROR")

    def test_경로에_쓸_수_없는_ID는_거부(self):
        self.assertEqual(self.code(self.r.open_adapter, "../x", "1", dest=self.tmp), "INVALID_RECORD")

    def test_위험한_tar는_INTEGRITY_ERROR(self):
        self.w.publish(self.m, self.adir, b"r")
        path = "/v1/packages/lora-a/versions/1.2.0/adapter"
        dst = self.tmp / "dst"

        def tar(setup):
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:") as tf:
                setup(tf)
            return buf.getvalue()

        def reg(tf, name, data=b"x"):
            i = tarfile.TarInfo(name)
            i.size = len(data)
            tf.addfile(i, io.BytesIO(data))

        def link(tf, kind, name="evil"):
            i = tarfile.TarInfo(name)
            i.type = kind
            i.linkname = "/etc/passwd"
            tf.addfile(i)

        cases = {
            "상위 경로": lambda tf: reg(tf, "../escape"),
            "중간 상위 경로": lambda tf: reg(tf, "a/../../escape"),
            "절대 경로": lambda tf: reg(tf, "/abs/file"),
            "심볼릭 링크": lambda tf: link(tf, tarfile.SYMTYPE),
            "하드 링크": lambda tf: link(tf, tarfile.LNKTYPE),
            "특수 파일": lambda tf: link(tf, tarfile.FIFOTYPE),
            "중복": lambda tf: (reg(tf, "a"), reg(tf, "a")),
        }
        for label, setup in cases.items():
            with self.subTest(label):
                self.srv.overrides[path] = (200, "application/x-tar", tar(setup))
                self.assertEqual(self.code(self.r.open_adapter, "lora-a", "1.2.0", dest=dst), "INTEGRITY_ERROR")
                self.assertFalse((dst / "lora-a").exists())
        self.assertFalse((self.tmp / "escape").exists())
        with self.subTest("tar가 아님"):
            self.srv.overrides[path] = (200, "application/x-tar", b"not a tar" * 100)
            self.assertEqual(self.code(self.r.open_adapter, "lora-a", "1.2.0", dest=dst), "INTEGRITY_ERROR")

    def test_tar_크기_상한(self):
        self.w.publish(self.m, self.adir, b"r")
        self.r.max_tar_bytes = 5  # FILES_A는 11바이트
        self.assertEqual(self.code(self.r.open_adapter, "lora-a", "1.2.0", dest=self.tmp / "dst"), "INTEGRITY_ERROR")
        self.assertEqual(list((self.tmp / "dst").rglob("*")), [])

    def test_여러_쪽(self):
        for i in range(4):
            self.srv.packages[(f"p{i}", "1")] = {"manifest": {}, "files": {}}
        first, cur = self.r.list_ids(limit=3)
        self.assertEqual((len(first), cur), (3, "3"))
        self.assertEqual(self.r.list_ids(cursor=cur, limit=3), (["p3"], None))


if __name__ == "__main__":
    unittest.main()
