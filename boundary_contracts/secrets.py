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

_TOKEN = r"[^,=:\s]+"
SECRET_FORMATS = {
    # 역할 없는 토큰 쉼표 목록(QuestionAuthoringEnv.TokenList, 예: QA_GATEWAY_TOKENS)
    "token_list": _re.compile(rf"{_TOKEN}(,{_TOKEN})*"),
    # '역할=토큰' 쉼표 목록(각 *Env 의 RoleTokenList)
    "role_token_list": _re.compile(rf"{_TOKEN}={_TOKEN}(,{_TOKEN}={_TOKEN})*"),
    # '토큰:actor-id:역할' 쉼표 목록(QA_AUTHOR_TOKENS)
    "token_actor_role_list": _re.compile(rf"{_TOKEN}:{_TOKEN}:{_TOKEN}(,{_TOKEN}:{_TOKEN}:{_TOKEN})*"),
    # 한 줄 '사용자:암호'(CommonEnv.OPENIT_BACKUP_CREDENTIALS_FILE)
    "credentials_line": _re.compile(r"[^:\s]+:\S+"),
}


def secret_format_problems(kind: str, value: str) -> list:
    """비밀 값(read_secret 이 앞뒤 공백을 지운 뒤)이 형식 kind 에 맞지 않으면 문제 코드 목록. 값은 싣지 않는다."""
    if kind not in SECRET_FORMATS:
        raise ValueError(f"알 수 없는 비밀 형식: {kind}")
    if not isinstance(value, str) or not value:
        return ["EMPTY"]
    return [] if SECRET_FORMATS[kind].fullmatch(value) else ["FORMAT"]
