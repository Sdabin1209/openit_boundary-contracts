"""영역 사이 계약의 공통 기준 구현. 해시는 반드시 이 모듈로 계산한다(CONVENTIONS.md 2절)."""
from .errors import BoundaryError
from .schemas_api import schema_dir, load_schema, validator, validate, format_checker, PIPELINE_SCHEMA_VERSION
from .secrets import read_secret, secret_source, SecretError
from .metrics_registry import metrics, metric_name_problems
from .canonical import canonicalize, sha256_hash, content_hash, file_hash, directory_hash
from .ids import envelope_id, is_id
from .schema_sources import contract_uri, CONTRACT_URI
from . import strict_json, review_input

__all__ = ["format_checker", "BoundaryError", "schema_dir", "load_schema", "validator", "PIPELINE_SCHEMA_VERSION", "canonicalize", "sha256_hash", "content_hash", "file_hash", "directory_hash", "read_secret", "secret_source", "SecretError", "metrics", "metric_name_problems", "envelope_id", "is_id", "validate", "strict_json", "review_input", "contract_uri", "CONTRACT_URI"]
