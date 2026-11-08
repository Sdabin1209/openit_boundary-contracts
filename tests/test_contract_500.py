"""계약 5.0.0: ID 타입 통일(D117)·envelope_id 정본 함수·사람 입구 입력 상한(결함 대장 #10·#18·#22)."""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

import jsonschema

from boundary_contracts import envelope_id, format_checker, is_id, load_schema, schema_dir

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/check_id_defs.py"


def _frag(name, *path):
    """스키마 안 조각을 같은 디렉터리 $ref 가 풀리게 검증하는 검증기."""
    from referencing import Registry, Resource
    reg = Registry()
    for p in schema_dir().glob("*.json"):
        doc = json.loads(p.read_text(encoding="utf-8"))
        reg = reg.with_resource(p.name, Resource.from_contents(doc))
    ref = f"{name}.schema.json#/" + "/".join(path)
    sch = {"$schema": "https://json-schema.org/draft/2020-12/schema", "$ref": ref}
    return jsonschema.Draft202012Validator(sch, registry=reg, format_checker=format_checker(load_schema(name)))


class EnvelopeIdVectors(unittest.TestCase):
    def test_적합성_벡터(self):
        doc = json.loads((ROOT / "conformance/vectors/envelope_id.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(doc["cases"]), 10)
        for c in doc["cases"]:
            with self.subTest(c["name"]):
                self.assertEqual(envelope_id(c["raw"]), c["expected"])
                self.assertTrue(is_id(envelope_id(c["raw"])), "변환 결과는 항상 Id 다")

    def test_문자열이_아니면_TypeError(self):
        with self.assertRaises(TypeError):
            envelope_id(None)


class IdTypes(unittest.TestCase):
    def test_SessionId_는_Id_이면서_64자(self):
        v = _frag("_common", "$defs", "SessionId")
        self.assertTrue(v.is_valid("0f" * 32))
        for bad in ("_abc", "-abc", "a" * 65, "", "abc\n"):
            with self.subTest(bad=bad):
                self.assertFalse(v.is_valid(bad))

    def test_공개_입구_세션_ID_는_SessionId(self):
        v = _frag("PublicApiRequests", "$defs", "UtteranceBody")
        ok = {"session_id": "s1", "turn_id": "t1", "utterance": "네"}
        base = [e.message for e in v.iter_errors(ok)]
        bad = dict(ok, session_id="_s1")
        self.assertGreater(len(list(v.iter_errors(bad))), len(base))

    def test_직원_호출_보고의_turn_id_는_Id_128(self):
        v = _frag("StaffCallReport", "properties", "turn_id")
        self.assertTrue(v.is_valid("t" * 128))
        self.assertFalse(v.is_valid("t" * 129))

    def test_QuestionId(self):
        v = _frag("_common", "$defs", "QuestionId")
        for ok in ("Q1", "Q1.D01", "Q4_1"):
            self.assertTrue(v.is_valid(ok), ok)
        for bad in ("Q4.answer", "q1", "Q1\n"):
            self.assertFalse(v.is_valid(bad), bad)


class InputBounds(unittest.TestCase):
    def test_알림_커서와_Last_Event_ID_는_18자리(self):
        for v in (_frag("HttpQueries", "$defs", "Alerts", "properties", "cursor"), _frag("HttpWire", "$defs", "EventId")):
            self.assertTrue(v.is_valid("9" * 18))
            self.assertFalse(v.is_valid("9" * 19))

    def test_푸시_endpoint_경로는_ASCII(self):
        v = _frag("PushSubscriptionRequest", "properties", "endpoint")
        self.assertTrue(v.is_valid("https://push.example.com/abc-DEF_1%20"))
        self.assertFalse(v.is_valid("https://push.example.com/" + "가" * 10))

    def test_자료_파일_이름은_255자(self):
        v = _frag("AuthoringRequests", "$defs", "MaterialQuery", "properties", "filename")
        self.assertTrue(v.is_valid("a" * 255))
        self.assertFalse(v.is_valid("a" * 256))

    def test_폐기_사유는_공백만이면_거부(self):
        v = _frag("AuthoringRequests", "$defs", "DiscardRequest", "properties", "reason")
        self.assertTrue(v.is_valid(" 중복 "))
        self.assertFalse(v.is_valid("   "))
        self.assertFalse(v.is_valid(""))

    def test_결정_조회_version_128자(self):
        v = _frag("AuthoringRequests", "$defs", "DecisionsQuery", "properties", "version")
        self.assertTrue(v.is_valid("1" * 128))
        self.assertFalse(v.is_valid("1" * 129))


class CheckIdDefsTool(unittest.TestCase):
    def _copy(self):
        d = pathlib.Path(tempfile.mkdtemp()); self.addCleanup(shutil.rmtree, d)
        for sub in ("schemas", "openapi"):
            shutil.copytree(ROOT / "boundary_contracts" / sub, d / sub)
        (d / "tools").mkdir(); shutil.copy(ROOT / "tools/id_defs_allowlist.json", d / "tools/id_defs_allowlist.json")
        return d

    def _run(self, d):
        return subprocess.run([sys.executable, str(TOOL), "--root", str(d)], capture_output=True, text=True)

    def test_현재_계약은_통과(self):
        r = self._run(self._copy())
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_같은_이름_다른_정의는_실패(self):
        d = self._copy(); p = d / "schemas/StaffAlert.schema.json"
        doc = json.loads(p.read_text(encoding="utf-8")); doc["properties"]["session_id"] = {"type": "string", "minLength": 1}
        p.write_text(json.dumps(doc), encoding="utf-8")
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("session_id", r.stdout)

    def test_근거_없는_좁히기는_실패(self):
        d = self._copy(); p = d / "schemas/StaffAlert.schema.json"
        doc = json.loads(p.read_text(encoding="utf-8")); doc["properties"]["alert_id"]["maxLength"] = 10
        p.write_text(json.dumps(doc), encoding="utf-8")
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("좁히기", r.stdout)

    def test_근거_없는_허용_항목은_실패(self):
        d = self._copy(); p = d / "tools/id_defs_allowlist.json"
        a = json.loads(p.read_text(encoding="utf-8")); a["excluded_names"].append({"name": "session_id", "reason": " "})
        p.write_text(json.dumps(a), encoding="utf-8")
        self.assertEqual(self._run(d).returncode, 1)

    def test_낡은_허용_항목은_실패(self):
        d = self._copy(); p = d / "tools/id_defs_allowlist.json"
        a = json.loads(p.read_text(encoding="utf-8")); a["refinements"].append({"file": "schemas/StaffAlert.schema.json", "pointer": "/properties/alert_id", "reason": "시험"})
        p.write_text(json.dumps(a), encoding="utf-8")
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("낡은", r.stdout)


if __name__ == "__main__":
    unittest.main()
