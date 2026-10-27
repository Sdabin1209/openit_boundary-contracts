import os
import tempfile
import unittest

from boundary_contracts import read_secret, secret_source, SecretError


class ReadSecretTest(unittest.TestCase):
    def _file(self, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "s")
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)
        return p

    def test_file_wins_and_strips(self):
        p = self._file("abc123\n")
        self.assertEqual(read_secret("T", environ={"T_FILE": p, "T": "other"}), "abc123")
        self.assertEqual(secret_source("T", environ={"T_FILE": p, "T": "other"}), "file")

    def test_env_fallback(self):
        self.assertEqual(read_secret("T", environ={"T": " v "}), "v")
        self.assertEqual(secret_source("T", environ={"T": "v"}), "env")

    def test_unset_and_required(self):
        self.assertIsNone(read_secret("T", environ={}))
        self.assertEqual(secret_source("T", environ={}), "unset")
        with self.assertRaises(SecretError):
            read_secret("T", environ={}, required=True)

    def test_missing_or_empty_file_errors_without_value(self):
        with self.assertRaises(SecretError) as c:
            read_secret("T", environ={"T_FILE": "/nonexistent/x"})
        self.assertIn("T_FILE", str(c.exception))
        p = self._file("  \n")
        with self.assertRaises(SecretError):
            read_secret("T", environ={"T_FILE": p})

    def test_error_never_contains_value(self):
        p = self._file("TOPSECRETVALUE")
        os.chmod(p, 0)
        try:
            read_secret("T", environ={"T_FILE": p})
        except SecretError as e:
            self.assertNotIn("TOPSECRETVALUE", str(e))
        except Exception:
            raise
        finally:
            os.chmod(p, 0o600)


if __name__ == "__main__":
    unittest.main()
