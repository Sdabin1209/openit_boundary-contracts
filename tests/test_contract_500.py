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

    def test_벡터_기대값을_독립으로_다시_계산한다(self):
        # 기대값을 파일에서 믿지 않고, 스키마 검증기(Id)와 hashlib 로 다시 계산해 파일·함수 둘 다와 대조한다
        import hashlib
        v = _frag("_common", "$defs", "Id")
        doc = json.loads((ROOT / "conformance/vectors/envelope_id.json").read_text(encoding="utf-8"))
        for c in doc["cases"]:
            want = c["raw"] if v.is_valid(c["raw"]) else "x-" + hashlib.sha256(c["raw"].encode("utf-8")).hexdigest()[:32]
            with self.subTest(c["name"]):
                self.assertEqual(c["expected"], want)
                self.assertEqual(envelope_id(c["raw"]), want)

    def test_문자열이_아니면_TypeError(self):
        with self.assertRaises(TypeError):
            envelope_id(None)


class IdTypes(unittest.TestCase):
    def test_SessionId_는_Id_이면서_64자(self):
        v = _frag("_common", "$defs", "SessionId")
        self.assertTrue(v.is_valid("0f" * 32))
        self.assertTrue(v.is_valid("a_b-c"))
        for bad in ("_abc", "-abc", "a" * 65, "", "abc\n", "a.b", "a:b"):
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


class SessionIdEnvelope(unittest.TestCase):
    def test_SessionId_값은_envelope_id_가_바꾸지_않는다(self):
        v = _frag("_common", "$defs", "SessionId")
        for sid in ("0f" * 32, "s1", "A", "a_b-c", "Z" * 64):
            self.assertTrue(v.is_valid(sid), sid)
            self.assertEqual(envelope_id(sid), sid)


class InputBounds(unittest.TestCase):
    def test_알림_커서와_Last_Event_ID_는_18자리(self):
        for v in (_frag("HttpQueries", "$defs", "Alerts", "properties", "cursor"), _frag("HttpWire", "$defs", "EventId")):
            self.assertTrue(v.is_valid("9" * 18))
            self.assertFalse(v.is_valid("9" * 19))

    def test_푸시_endpoint_경로는_ASCII(self):
        v = _frag("PushSubscriptionRequest", "properties", "endpoint")
        self.assertTrue(v.is_valid("https://push.example.com/abc-DEF_1%20"))
        self.assertFalse(v.is_valid("https://push.example.com/" + "가" * 10))
        self.assertFalse(v.is_valid("https://push.example.com/a%zz"), "format uri(RFC 3986) 위반: 잘못된 퍼센트 인코딩")

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

    def _edit(self, d, rel, fn):
        p = d / rel
        doc = json.loads(p.read_text(encoding="utf-8")); fn(doc); p.write_text(json.dumps(doc), encoding="utf-8")

    def test_근거_없는_허용_항목은_실패(self):
        d = self._copy()
        self._edit(d, "tools/id_defs_allowlist.json", lambda a: a["refinements"][0].update(reason=" "))
        self.assertEqual(self._run(d).returncode, 1)

    def test_낡은_허용_항목은_실패(self):
        d = self._copy()
        self._edit(d, "tools/id_defs_allowlist.json", lambda a: a["refinements"].append({"file": "schemas/StaffAlert.schema.json", "pointer": "/properties/alert_id", "reason": "시험"}))
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("낡은", r.stdout)

    def test_우회1_별칭_칸의_좁히기가_전파된다(self):
        # KioskStartFragment.question_set_id 는 DeviceConfig 칸의 별칭이다. 중간 칸(DeviceConfig)에 단언을 더하면 별칭 쪽에도 전파되어 실패해야 한다
        d = self._copy()
        self._edit(d, "schemas/DeviceConfig.schema.json", lambda o: o["properties"]["question_set_id"].update(maxLength=5))
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("KioskStartFragment", r.stdout)

    def test_우회2_then_가지의_다른_정의(self):
        d = self._copy()
        self._edit(d, "schemas/ResponseRequest.schema.json", lambda o: o["allOf"][0]["then"]["properties"]["next"]["properties"].update(question_id={"type": "string", "minLength": 1}))
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("question_id", r.stdout)

    def test_우회3_같은_모양_인라인_사본_둘(self):
        d = self._copy()
        flag = {"type": "string", "pattern": "^fl-[0-9a-f]+(-[0-9]+)?$(?![\\s\\S])"}
        def two(o):
            o["$defs"]["Flag"]["properties"]["flag_id"] = dict(flag)
            o["$defs"]["Draft"]["properties"]["flags"]["items"]["properties"]["flag_id"] = dict(flag)
            o["$defs"]["Preview"]["properties"]["open_flags"]["items"]["properties"]["flag_id"] = dict(flag)
        self._edit(d, "schemas/AuthoringResponses.schema.json", two)
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("인라인 정의가", r.stdout)

    def test_우회4_등록_안_된_id_칸(self):
        d = self._copy()
        self._edit(d, "tools/id_defs_allowlist.json", lambda a: a.update(id_registry=a["id_registry"][1:]))
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("id_registry 에 없다", r.stdout)

    def test_우회5_생성물_안의_다른_끝점(self):
        d = self._copy()
        self._edit(d, "schemas/OpsFeedbackDeidentifiedTrace.schema.json", lambda o: o["properties"].update(session_id={"type": "string"}))
        r = self._run(d)
        self.assertEqual(r.returncode, 1); self.assertIn("생성물", r.stdout)

    def test_if_판별은_정의가_아니다(self):
        d = self._copy()
        r = self._run(d)
        self.assertNotIn("REASK_STREAK", r.stdout)


if __name__ == "__main__":
    unittest.main()
