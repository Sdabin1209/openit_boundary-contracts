"""비밀 값 읽기(D84). 비밀은 환경 변수가 아니라 파일로 받는다.

규칙: 설정 이름 NAME에 대해 NAME_FILE 환경 변수가 있으면 그 경로의 파일 내용을 읽는다(앞뒤 공백·줄바꿈 제거).
NAME_FILE이 없으면 NAME 환경 변수를 쓴다(개발·시험용 호환). 둘 다 있으면 NAME_FILE이 이긴다.
값은 어떤 오류 메시지·로그에도 넣지 않는다. 이름과 경로만 쓴다.
"""
from __future__ import annotations

import os
from typing import Mapping, Optional


class SecretError(RuntimeError):
    """비밀을 읽지 못했다. 메시지에는 설정 이름과 경로만 있고 값은 없다."""


def read_secret(name: str, *, environ: Optional[Mapping[str, str]] = None, required: bool = False) -> Optional[str]:
    env = os.environ if environ is None else environ
    path = env.get(name + "_FILE")
    if path:
        try:
            with open(path, "r", encoding="utf-8") as f:
                value = f.read().strip()
        except OSError as e:
            raise SecretError(f"{name}_FILE={path} 파일을 읽지 못했다({type(e).__name__})") from None
        if not value:
            raise SecretError(f"{name}_FILE={path} 파일이 비어 있다")
        return value
    value = env.get(name)
    if value is not None and value.strip():
        return value.strip()
    if required:
        raise SecretError(f"비밀 {name}이(가) 없다: {name}_FILE(파일 경로) 또는 {name}(개발용 환경 변수)을 설정한다")
    return None


def secret_source(name: str, *, environ: Optional[Mapping[str, str]] = None) -> str:
    """값을 드러내지 않고 출처만 말한다: 'file' | 'env' | 'unset'. /readyz나 진단 출력에 쓴다."""
    env = os.environ if environ is None else environ
    if env.get(name + "_FILE"):
        return "file"
    if (env.get(name) or "").strip():
        return "env"
    return "unset"


# 비밀 파일 내용 형식(5.0.1). Env 스키마는 이 칸들을 'type string, minLength 1'(+형식 설명)로만 받는다 — 4.x/5.0.0 의 허용 집합을
# 좁히면 MAJOR 라서 스키마는 그대로 두고, 정확한 문법은 이 함수로 만든 쪽(deploy gen-secrets)과 읽는 쪽이 같은 정의를 쓴다(D117).
import re as _re

# 문자 규칙: 제어 문자(U+0000–U+001F, U+007F)는 어디에도 없다. 구분자 규칙은 실제 소비 코드의 나누기와 같다(codex 검토 2026-11-09):
#  token_list 는 ',' 로만 나눈다(토큰 안의 '='·':' 허용 — 패딩된 bearer 토큰), role_token_list 는 항목을 ',' 로 나눈 뒤 **첫 '='** 에서
#  역할과 토큰을 나눈다(토큰 쪽 '=' 보존: model-lab service/app.py, clients/_http.py, link server.py), token_actor_role_list 는
#  ':' 로 정확히 셋(question-authoring __main__.py), credentials_line 은 한 줄을 **첫 ':'** 에서 나누고 암호 안의 공백은 허용한다
#  (survey link_backup.py 는 암호를 URL 인코딩, platform backup-store 는 그대로 htpasswd 에 넘긴다).
_C = r"\x00-\x1f\x7f"
_ITEM = rf"[^,\s{_C}]+"
_ROLE = rf"[^,=\s{_C}]+"
_PART = rf"[^,:\s{_C}]+"
SECRET_FORMATS = {
    "token_list": _re.compile(rf"{_ITEM}(,{_ITEM})*"),
    "role_token_list": _re.compile(rf"{_ROLE}={_ITEM}(,{_ROLE}={_ITEM})*"),
    "token_actor_role_list": _re.compile(rf"{_PART}:{_PART}:{_PART}(,{_PART}:{_PART}:{_PART})*"),
    "credentials_line": _re.compile(rf"[^:{_C}]+:[^{_C}]+"),
}


def secret_format_problems(kind: str, value: str) -> list:
    """비밀 값(read_secret 이 앞뒤 공백을 지운 뒤)이 형식 kind 에 맞지 않으면 문제 코드 목록. 값은 싣지 않는다."""
    if kind not in SECRET_FORMATS:
        raise ValueError(f"알 수 없는 비밀 형식: {kind}")
    if not isinstance(value, str) or not value:
        return ["EMPTY"]
    return [] if SECRET_FORMATS[kind].fullmatch(value) else ["FORMAT"]
