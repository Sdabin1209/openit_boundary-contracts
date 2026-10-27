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
