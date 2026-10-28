# boundary-contracts

문진 시스템의 영역 사이에 오가는 데이터의 형식(계약)과, 그 계약을 지키는지 확인하는 공유 파이썬 패키지다. 소유자는 헤드다.

이 리포지토리는 **서비스가 아니다**. 실행되는 서버가 없고 이미지도 없다. 하는 일은 (1) 영역 사이 레코드의 JSON Schema 31개와 예시를 정하고, (2) 영역 사이 HTTP 호출의 경로·요청·응답을 문서로 정하고, (3) 그 호출을 하는 클라이언트(`boundary_contracts.clients`)와 시험용 참조 서버(`conformance/`)를 제공하고, (4) 해시 계산과 비밀 읽기 같은 공통 코드를 한 곳에 두는 것이다. 하지 않는 것: 문진 내부 계약(`../survey-service/schema`, survey-service 소유)의 수정, 서버 구현(각 소유 영역), 모델·데이터 처리.

> 이 README는 2026-10-27 기준 리포지토리 안의 파일을 읽고 쓴 것이다. 이 리포지토리에는 `CLAUDE.md`가 없다(미확인이 아니라 확인한 사실). 문서는 루트의 `*.md`에 있고, `docs/`에는 구조 선택의 근거(ADR)만 있다(아래 7절). 워크스페이스 공통 규칙은 `../CLAUDE.md`.

## 1. 전체 속의 위치

각 영역은 서로의 코드를 가져오지 않고, 여기 있는 스키마와 HTTP 규약만 믿고 개발한다(`INTERFACES.md`). 영역 이름은 `INTERFACES.md` 표 기준.

| 인터페이스 | 제공(소유) | 읽는 쪽 | HTTP 절(`HTTP.md`) |
| --- | --- | --- | --- |
| I1 QuestionReader | question-authoring | synthetic-data, model-lab, release-gate | `## I1` |
| I2 DatasetStore | synthetic-data | model-lab | `## I2` (2.1.0, D100) |
| I3 ModelRegistry | model-lab | release-gate | `## I3` |
| I4 ReleaseReader | release-gate | survey-service, ops-feedback, question-authoring, model-lab | `## I4` |
| I5 GateService | release-gate | (쓰는 쪽: operator, ops-feedback) | `## I5` |
| I6 TraceIngest | ops-feedback | (쓰는 쪽: survey-service) | `## I6` |
| I7 FailureStore | ops-feedback | synthetic-data, model-lab, question-authoring | `## I7` |
| I8 출력 검증(2.0.0에서 대체) | turn-engine | survey-service | 라이브러리, HTTP 없음 |
| I9 model-runtime 추론 | model-runtime | survey-service, model-lab, release-gate | `## I9` |
| I10 공개 API | survey-service | Frontend(미정) | `PUBLIC_API.md` |

이 영역 자체의 입력은 헤드의 변경 결정이고, 출력은 태그가 붙은 패키지(`v2.1.0`이 최신 태그, 로컬. 원격 push는 헤드가 검증 뒤 한다)다. 다른 영역은 이 패키지를 태그로 설치한다.

## 2. 구조

| 경로 | 역할 |
| --- | --- |
| `schemas/` | JSON Schema(Draft 2020-12) 31개 + `_common.schema.json`. 실체는 `boundary_contracts/schemas/`의 링크 |
| `examples/` | 스키마마다 통과해야 하는 예시(45개 파일) |
| `verify.py` | 스키마 유효성, 예시 통과, 위반 예시 거부 검사 |
| `boundary_contracts/canonical.py` | JCS 정규화와 SHA-256 해시의 기준 구현 |
| `boundary_contracts/errors.py` | 모든 경계 호출이 던지는 `BoundaryError` |
| `boundary_contracts/sdk.py` | I1~I7의 `typing.Protocol` |
| `boundary_contracts/secrets.py` | `read_secret(NAME)`, `secret_source(NAME)` (D84) |
| `boundary_contracts/clients/` | HTTP 클라이언트(표준 라이브러리만): questions, datasets(I2), models, releases, ops, runtime, staffcall(직원 호출 재알림) |
| `conformance/servers.py` | HTTP.md대로 응답하는 참조 서버(패키지에는 안 들어감) |
| `tests/` | unittest 시험 13개 파일(+ `_fixtures.py`) |
| `tools/` | 학습 데이터셋 v2 검증(`validate_dataset_v2.py`), 거부 변형 목록(`negatives_v2.py`) |
핵심 흐름(소비 영역이 계약을 쓰는 방식):

```
 헤드 --(스키마·HTTP.md 수정, 태그)--> boundary-contracts
                                          |  pip install ...@<태그>
        +-------------+-------------------+----------------+
        v             v                                    v
   소유 영역(서버)   소비 영역                         검증/시험
   HTTP.md대로      boundary_contracts.clients로 호출    verify.py, tests/,
   구현             응답을 읽기 모드로 검증,             conformance 참조 서버
                    해시 재계산, 실패는 BoundaryError
```

## 3. 실행 방법
전제: 파이썬 3 (`python3`), `jsonschema>=4.10`(`pyproject.toml`의 유일한 의존). Docker는 필요 없다(서비스가 아니므로 Dockerfile·`/healthz`·이미지 해당 없음).

```bash
cd boundary-contracts
python3 -m venv .venv && . .venv/bin/activate     # .venv는 커밋하지 않는다
pip install -e .                                   # 개발 설치 (또는 pip install jsonschema)
python3 verify.py                                  # 스키마·예시·거부 검사
python3 -m unittest discover -s tests              # 단위·클라이언트 시험
# 다른 영역에서 쓸 때(태그 설치, D18):
pip install git+ssh://git@github.com/Sdabin1209/openit_boundary-contracts.git@v2.1.0
```
비밀(D84): 서비스 토큰 등은 환경 변수에 직접 넣지 않고 `NAME_FILE`에 파일 경로를 주면 `boundary_contracts.secrets.read_secret("NAME")`이 그 파일을 먼저 읽는다. 파일이 없으면 환경 변수 `NAME`(개발·시험용)을 쓴다. 오류 메시지에 값을 넣지 않는다(`CHANGELOG.md` 2.0.2).
이 세션에서 돌려 본 것과 아닌 것:

| 명령 | 이 세션 |
| --- | --- |
| `python3 verify.py` | 돌림. OK 110줄(옆 폴더 `../survey-service/schema`가 없는 새 clone에서는 TraceEnvelope.trace 검증을 건너뛰어 109줄), 실패 0(출력 중 'FAIL' 글자는 시험 이름 "FAIL 검사 포함"에 들어 있는 것). 시스템 파이썬과, 새 clone + 새 venv(jsonschema만 설치) 두 곳 |
| `python3 -m unittest discover -s tests` | 돌림. `Ran 133 tests ... OK`. 같은 두 환경 |
| venv 생성, `pip install -e .`, 태그 설치 | 안 돌림 |
| 이미지 빌드, E2E | 해당 없음 / 안 돌림 |

## 4. 현재 상태
확인한 것(이 세션에서 직접):
- 패키지 버전 2.1.0(`pyproject.toml`), 태그 v1.3.3, v2.0.0-rc1, v2.0.0, v2.0.1, v2.0.2, v2.1.0이 로컬에 있다(`git tag`). v2.1.0은 push 전이며 헤드가 검증 뒤 push한다.
- `schemas/`에 스키마 31개 + `_common`. `verify.py` 110 OK, unittest 133 통과(위 표).
- 2.0.1은 `ActionExtraction`의 `properties`를 사전순으로 고쳤다(제약 디코딩이 순서대로 키를 내기 때문). 2.0.2는 `read_secret` 추가. 2.1.0은 직원 호출 재알림·실패 기록(CR-H001), `pause_reason`(CR-H002), METRICS v2, I2 HTTP를 더했다(`CHANGELOG.md`).
- 헤드 STATUS는 이 패키지 `v2.0.2`를 v0.7.0 열차의 일부로 기록한다(2.1.0 반영은 헤드)(`../head/docs/STATUS.md` 10행).
확인하지 못한 것:
- 깨끗한 두 번째 환경(새 venv, 다른 머신)에서의 통과. 워크스페이스 규칙(두 번째 환경 검증)에 따라 아직 완료로 보지 않는다. OPEN_GAPS U12도 같은 취지.
- 태그가 원격(GitHub)에 push되어 있는지. 로컬 태그만 확인했다.
- 소비 영역들이 실제로 v2.0.2(또는 v2.1.0) 잠금으로 설치되는지(각 영역 리포지토리를 읽지 않았다).
- 참조 서버(`conformance/`)와 실제 서비스 서버들의 적합성은 각 영역이 돌린다. 여기서는 확인하지 않았다.

### 태그 규칙

- 릴리스 태그는 **주석 태그**(`git tag -a`)로 만든다. 한 번 push한 태그는 옮기거나 지우지 않는다. 고칠 것이 있으면 새 PATCH 태그를 낸다.
- v1.3.0~v1.3.3은 경량 태그다(과거 기록). 이미 의존 영역이 참조했을 수 있어 바꾸지 않는다. 앞으로는 만들지 않는다.
- 태그 서명은 하지 않는다(서명 키 관리는 사용자 결정이 필요하다). 무결성은 의존 영역의 잠금 파일에 고정된 태그와 커밋 해시로 확인한다.
- 문서만 바뀐 `main`은 태그 없이 둔다(`CHANGELOG.md`의 'main' 절에 적는다). 스키마·패키지 코드가 바뀌면 태그를 낸다.

## 5. 이 영역의 열린 항목

`../head/docs/OPEN_GAPS.md`를 읽기 전용으로 읽어 이 영역과 직접 관련된 것만 골랐다. 대장의 영역 칸에 boundary-contracts가 적힌 항목은 없다(관련성은 내용으로 판단한 것이며 확정이 아니다).

| ID | 요약 | 막는 것 |
| --- | --- | --- |
| U14 | 제약 디코딩이 `values[].key`를 현재 문항의 유효 slot으로 못 제한한다. 풀려면 `ActionExtractionInput` 계약 변경(허용 slot 목록) 필요 | 헤드 판단 대기(지금 하지 않음). 학습된 어댑터 시험은 H2(GPU) |
| U11 | A 출력 의미 위반율 지표를 평가에 넣지 않았다. boundary 규칙과 충돌, 허락 필요 | 사용자/헤드 허락, 학습 담당 확인 |
| D-C | `METRICS.md` v2는 반영됨(2.1.0). `[기본값]` 항목은 학습 담당 확인 대기 | 학습 담당 |
| D-B | 원문 정규화 담당자의 변경이 계약에 미치는 영향 | 사용자 확인 후 헤드 |
| D-E | 회귀 평가가 읽는 v2 TurnTrace 입력 키 이름은 추정 | survey-service 확정 대기 |
| G11 | 문진 스키마 정수 버전 1 안의 비호환 변경. `TraceEnvelope.trace`가 이것을 담는다 | 다른 영역 의존(survey-service, ops-feedback 동시 배포) |
| H2 | 학습된 LoRA-A/B로 한 턴 통과 시험 | GPU (U07, U14와 연결) |

`V2_DRAFT.md` 10절에도 아직 정해지지 않은 것 7건(예: 제약 디코딩용 평면 스키마를 따로 낼지, `DatasetManifest.turn_engine_version` 필수 유지)이 있다. 대장 ID는 아직 없다.

## 6. 더 자세한 문서

| 문서 | 내용 |
| --- | --- |
| `INTERFACES.md` | 영역 경계 I1~I10의 시그니처, 받는 것/내는 것, 영역별 책임 요약 |
| `HTTP.md` | 영역 사이 HTTP API(경로, 요청, 응답, 적합성) |
| `CONVENTIONS.md` | 공통 규약: 진화 규칙, ID·시각·해시, 오류, 멱등성, 인증, SDK 형태 |
| `CHANGELOG.md` | 버전별 변경, v1에서 2.0.0으로 옮기는 방법 |
| `V2_DRAFT.md` | 2.0.0의 근거(확인한 데이터, 문서와 데이터의 차이, 영향)와 열린 항목 |
| `PUBLIC_API.md` | 화면 ↔ survey-service 공개 API(I10) |
| `METRICS.md` | 승인 보고서 지표 카탈로그 v2(제안, 2.1.0, D96~D98) |
| `../head/docs/` | 설계·결정 기록(DECISIONS, STATUS, OPEN_GAPS). 읽기 전용 |

## 7. 구조 선택의 근거 (ADR, D89)

| ADR | 내용 |
| --- | --- |
| [0001](docs/adr/0001-JSON-Schema를-계약-언어로-쓴다.md) | JSON Schema를 계약 언어로 쓴 이유 |
| [0002](docs/adr/0002-pip-패키지와-Git-태그로-배포한다.md) | pip 패키지와 Git 태그로 배포하는 이유 |
| [0003](docs/adr/0003-버전-규칙.md) | 버전 규칙(MAJOR.MINOR = pipeline_schema_version, PATCH) |
| [0004](docs/adr/0004-하위-호환-규칙.md) | 하위 호환 규칙(ext, MINOR는 추가만, 읽기 관대) |
| [0005](docs/adr/0005-HTTP-면을-HTTP.md와-PUBLIC_API.md로-나눈다.md) | HTTP 면을 HTTP.md와 PUBLIC_API.md로 나눈 이유 |
| [0006](docs/adr/0006-멱등성과-오류-코드-체계.md) | 멱등성과 오류 코드 체계 |
| [0007](docs/adr/0007-SDK는-Protocol과-원격-구현과-참조-서버를-함께-낸다.md) | Protocol, 원격 클라이언트, 참조 서버(메모리 구현은 소유 영역) |
| [0008](docs/adr/0008-모델-입출력은-레코드로-만들지-않는다.md) | 모델 입출력을 레코드로 만들지 않은 이유 |
| [0009](docs/adr/0009-비밀은-read_secret으로-파일에서-읽는다.md) | read_secret(NAME_FILE), D84 |
| [0010](docs/adr/0010-직원-호출-재알림과-실패-기록을-API로-더한다.md) | 직원 호출 재알림·실패 기록 API (CR-H001) |
| [0011](docs/adr/0011-정지-사유를-pause_reason으로-더한다.md) | `pause_reason` (CR-H002) |
| [0012](docs/adr/0012-I2-DatasetStore를-HTTP로-한다.md) | I2 DatasetStore HTTP (D100) |
| [0013](docs/adr/0013-METRICS를-v2로-개정한다.md) | METRICS v2 (D96~D98) |
