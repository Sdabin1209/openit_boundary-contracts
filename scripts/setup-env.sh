#!/usr/bin/env bash
# 영역 환경 준비의 정본(deploy/scripts/prepare-areas.sh 가 모든 영역의 이 파일을 차례로 부른다).
# 왜: 새 머신으로 옮길 때 영역마다 달랐던 설치법을 영역 한 곳(이 파일)으로 모은다. 설치 명령을 deploy 나 문서에 복사하지 않는다.
# 규약(계약 SetupEnvReport, 3.0.0): 진행 기록은 표준 오류, 표준 출력 마지막 줄은 SetupEnvReport JSON 한 줄. 실패해도 status fail 보고를 낸다.
# 개발 환경이므로 시험 도구(pytest)를 함께 둔다. 시험 명령은 보고의 environment.test_command 로 알린다(deploy 가 짐작하지 않게).
set -uo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
start=$(date +%s)
report() {   # $1 status, $2 exit_code
  local env=""
  [ "$1" = ok ] && env=',"environment":{"kind":"python-venv","path":".venv","test_command":[".venv/bin/python","-m","pytest","-q"]}'
  printf '{"area":"boundary-contracts","status":"%s","exit_code":%d,"seconds":%d%s}\n' "$1" "$2" "$(( $(date +%s) - start ))" "$env"
}
{ [ -d .venv ] || python3 -m venv .venv; } >&2 || { report fail 20; exit 20; }
install() { .venv/bin/pip install -q -e . pytest >&2; }
# 왜 한 번 재시도: 네트워크가 잠깐 끊겨 받기 실패하는 경우가 흔하다. 두 번째도 실패하면 이유를 내고 멈춘다.
if ! install; then
  echo "setup-env: 설치 실패, 5초 뒤 한 번 다시 시도한다" >&2; sleep 5
  install || { echo "setup-env: 설치 실패(네트워크 또는 pip 오류). 위 pip 출력을 본다" >&2; report fail 20; exit 20; }
fi
echo "setup-env: 완료 (.venv)" >&2
report ok 0
