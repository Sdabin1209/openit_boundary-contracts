#!/usr/bin/env bash
# 영역 환경 준비의 정본(deploy/scripts/prepare-areas.sh 가 모든 영역의 이 파일을 차례로 부른다).
# 왜: 새 머신으로 옮길 때 영역마다 달랐던 설치법을 영역 한 곳(이 파일)으로 모은다. 설치 명령을 deploy 나 문서에 복사하지 않는다.
# 개발 환경이므로 시험 도구(pytest)를 함께 둔다: deploy 의 check-all 이 이 리포의 .venv 에서 pytest 를 찾는다(docs/SETUP.md F절).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
[ -d .venv ] || python3 -m venv .venv
install() { .venv/bin/pip install -q -e . pytest; }
# 왜 한 번 재시도: 네트워크가 잠깐 끊겨 받기 실패하는 경우가 흔하다. 두 번째도 실패하면 이유를 내고 멈춘다.
install || { echo "setup-env: 설치 실패, 5초 뒤 한 번 다시 시도한다" >&2; sleep 5; install || { echo "setup-env: 설치 실패(네트워크 또는 pip 오류). 위 pip 출력을 본다" >&2; exit 20; }; }
echo "setup-env: 완료 (.venv)"
