import json
import unittest
from pathlib import Path

import jsonschema

from boundary_contracts import BoundaryError
from boundary_contracts import sdk

SCHEMAS = Path(__file__).resolve().parent.parent / "schemas"


class Errors(unittest.TestCase):
    def test_retryable은_UNAVAILABLE만(self):
        for code in ("NOT_FOUND", "INVALID_RECORD", "UNSUPPORTED_VERSION", "CONFLICT", "INTEGRITY_ERROR",
                     "FAILED_PRECONDITION", "PERMISSION_DENIED"):
            self.assertFalse(BoundaryError(code, "m").retryable)
        self.assertTrue(BoundaryError("UNAVAILABLE", "m").retryable)

    def test_알_수_없는_코드는_거부(self):
        with self.assertRaises(ValueError):
            BoundaryError("WHATEVER", "m")

    def test_레코드는_스키마를_통과하고_왕복한다(self):
        schema = json.loads((SCHEMAS / "BoundaryError.schema.json").read_text())
        store = {"file://" + str(SCHEMAS) + "/_common.schema.json": json.loads((SCHEMAS / "_common.schema.json").read_text())}
        v = jsonschema.Draft202012Validator(schema, resolver=jsonschema.RefResolver("file://" + str(SCHEMAS) + "/", schema, store=store))
        err = BoundaryError("CONFLICT", "같은 ID에 다른 내용", {"id": "x"})
        rec = err.to_record()
        self.assertEqual(list(v.iter_errors(rec)), [])
        back = BoundaryError.from_record(rec)
        self.assertEqual((back.code, back.message, back.details), (err.code, err.message, err.details))

    def test_Protocol_목록(self):
        names = [n for n in dir(sdk) if n[0].isupper() and n != "Protocol" and getattr(getattr(sdk, n), "_is_protocol", False)]
        self.assertEqual(sorted(names), ["DatasetStore", "FailureStore", "GateService", "ModelRegistry", "PublicApi",
                                          "QuestionReader", "ReleaseReader", "StaffCall", "TraceIngest"])


if __name__ == "__main__":
    unittest.main()
