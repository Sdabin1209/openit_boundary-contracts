"""Resolve schemas from their installed owner packages; never fetch from the network."""
from __future__ import annotations
import importlib
from typing import Mapping, Callable

SURVEY_URI = "https://openit.example/survey/v1/"
# 계약 스키마의 안정 URI(5.0.1, CONVENTIONS 10절). 설치 경로(file://)와 무관하게 외부 문서(문진 스키마 5.x)가 계약 타입을
# $ref 로 가리키는 주소. 경로에는 MAJOR 만 둔다(MINOR·PATCH 는 호환이라 같은 주소, MAJOR 가 바뀌면 주소도 바뀐다).
# 네트워크로 조회하지 않는다: schema_registry()·reader 가 설치본 파일을 이 주소로도 오프라인 등록한다.
CONTRACT_MAJOR = 5
CONTRACT_URI = f"https://openit.example/contracts/v{CONTRACT_MAJOR}/"


def contract_uri(name: str) -> str:
    """계약 스키마 이름(예: _common, SessionState)의 안정 URI."""
    return f"{CONTRACT_URI}{name}.schema.json"


def external_schema(uri: str, sources: Mapping[str, Callable] | None = None) -> dict:
    if not uri.startswith(SURVEY_URI):
        raise ValueError("schema reference has no registered owner")
    name = uri[len(SURVEY_URI):].removesuffix(".json")
    if not name or "/" in name or "#" in name:
        raise ValueError("invalid external schema identifier")
    if sources and "survey" in sources:
        return {**sources["survey"](name), "$id": uri}
    # This owner is optional for consumers that do not exchange survey records.
    # A consumer of such a record must install the pinned owner schema package.
    try:
        owner = importlib.import_module("survey_schema")
    except ImportError as error:
        raise ValueError("openit-survey-schema is required to validate this contract") from error
    return {**owner.load_schema(name, version=1), "$id": uri}
