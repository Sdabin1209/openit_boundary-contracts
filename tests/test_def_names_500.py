"""같은 이름 다른 타입 정의 점검(tools/check_def_names.py, 5.0.0)과 ActionExtraction 상한(헤드 결정 2026-11-08)."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

from boundary_contracts import validator

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/check_def_names.py"


class CheckDefNames(unittest.TestCase):
    def _copy(self):
        d = pathlib.Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        shutil.copytree(ROOT / "boundary_contracts/schemas", d / "schemas")
        (d / "tools").mkdir(); shutil.copy(ROOT / "tools/def_names_allowlist.json", d / "tools/def_names_allowlist.json")
        return d

    def _run(self, d):
        return subprocess.run([sys.executable, str(TOOL), "--root", str(d)], capture_output=True, text=True)

    def _edit(self, d, rel, fn):
        p = d / rel; doc = json.loads(p.read_text(encoding="utf-8")); fn(doc); p.write_text(json.dumps(doc), encoding="utf-8")

    def test_현재_계약은_통과(self):
        r = self._run(self._copy()); self.assertEqual(r.returncode, 0, r.stdout)

    def test_최상위_스키마와_공통_defs_가_갈리면_실패(self):
        # 2026-11-08 결함 재현: ArtifactRef.schema.json 이 별칭이 아니라 자기 모양을 가지면(_common 과 다르면) 실패
        d = self._copy()
        def own(o):
            o.pop("$ref"); o.update(type="object", properties={"id": {"type": "string"}})
        self._edit(d, "schemas/ArtifactRef.schema.json", own)
        r = self._run(d); self.assertEqual(r.returncode, 1); self.assertIn("ArtifactRef", r.stdout)

    def test_두_파일의_같은_이름_defs_가_다르면_실패(self):
        d = self._copy()
        self._edit(d, "schemas/StepCaEnv.schema.json", lambda o: o["$defs"].update(Port={"type": "string", "pattern": "^[0-9]+$"}))
        r = self._run(d); self.assertEqual(r.returncode, 1); self.assertIn("Port", r.stdout)

    def test_별칭은_같은_정의로_본다(self):
        d = self._copy()
        self._edit(d, "schemas/GateJobConfig.schema.json", lambda o: o["$defs"].update(Id={"$ref": "_common.schema.json#/$defs/Id", "description": "별칭"}))
        self.assertEqual(self._run(d).returncode, 0)

    def test_근거_없는_허용_항목과_낡은_항목은_실패(self):
        d = self._copy()
        self._edit(d, "tools/def_names_allowlist.json", lambda a: a["same_name_different_meaning"][0].update(reason=""))
        self.assertEqual(self._run(d).returncode, 1)
        d = self._copy()
        self._edit(d, "tools/def_names_allowlist.json", lambda a: a["same_name_different_meaning"].append({"name": "Nope", "files": ["a"], "reason": "시험"}))
        r = self._run(d); self.assertEqual(r.returncode, 1); self.assertIn("낡은", r.stdout)


class ActionExtractionBounds(unittest.TestCase):
    def _base(self):
        return {"values": [{"key": "Q1.D01.count", "value": 1, "precision": "exact", "status": "ANSWERED", "save": True}], "action": "NEXT"}

    def test_values_targets_256_key_128(self):
        v = validator("ActionExtraction")
        ok = self._base()
        base_errs = len(list(v.iter_errors(ok)))
        many = dict(ok, values=ok["values"] * 257)
        self.assertGreater(len(list(v.iter_errors(many))), base_errs)
        longkey = json.loads(json.dumps(ok)); longkey["values"][0]["key"] = "Q1." + "a" * 126
        self.assertGreater(len(list(v.iter_errors(longkey))), base_errs)
        s = json.loads((ROOT / "boundary_contracts/schemas/ActionExtraction.schema.json").read_text(encoding="utf-8"))
        self.assertEqual(s["properties"]["targets"]["maxItems"], 256)
        self.assertEqual(s["properties"]["targets"]["items"]["maxLength"], 128)
        self.assertEqual(s["properties"]["values"]["maxItems"], 256)
        self.assertEqual(s["properties"]["values"]["items"]["properties"]["key"]["maxLength"], 128)


if __name__ == "__main__":
    unittest.main()
