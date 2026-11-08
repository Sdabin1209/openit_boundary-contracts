"""시험의 하위 프로세스에 넘길 최소 환경(RUNTIME R9.1: 상속 환경을 통째로 넘기지 않는다).
허용 목록은 head check-container-inputs 의 최소 집합과 같다."""
import os

ALLOWED = ("PATH", "HOME", "LANG", "TMPDIR")


def minimal_env(**extra):
    env = {k: os.environ[k] for k in ALLOWED if k in os.environ}
    env.update(extra)
    return env
