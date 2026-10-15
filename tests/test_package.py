import json
import unittest

from boundary_contracts import load_schema, schema_dir, validator, PIPELINE_SCHEMA_VERSION


class Package(unittest.TestCase):
    def test_스키마는_패키지_안에_있다(self):
        names = sorted(p.name for p in schema_dir().glob("*.schema.json"))
        self.assertIn("ReleaseManifest.schema.json", names)
        self.assertIn("_common.schema.json", names)
        self.assertEqual(len([n for n in names if not n.startswith("_")]), 19)

    def test_모르는_계약은_KeyError(self):
        with self.assertRaises(KeyError):
            load_schema("Nope")

    def test_validator는_예시를_통과시킨다(self):
        root = schema_dir().parent.parent / "examples"
        rec = json.loads((root / "ReleaseManifest.json").read_text())
        self.assertEqual(list(validator("ReleaseManifest").iter_errors(rec)), [])
        rec["pipeline_schema_version"] = "1"
        self.assertTrue(list(validator("ReleaseManifest").iter_errors(rec)))

    def test_버전_상수(self):
        self.assertEqual(PIPELINE_SCHEMA_VERSION, "1.3")


if __name__ == "__main__":
    unittest.main()
