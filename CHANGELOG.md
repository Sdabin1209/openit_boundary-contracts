# 변경 이력

버전은 `pyproject.toml`의 패키지 버전이고 MAJOR.MINOR는 `pipeline_schema_version`과 같다.

## 3.4.1 (PATCH, 와이어 변경 없음 — 영역 사이 호출 TLS 전용, U99; 사용자 원칙 2026-11-03 "모든 영역은 배치와 무관, 통신은 공통으로 안전")
왜: 클라이언트가 `http://상대` 를 받아, 서버를 나누거나 설정을 손으로 바꾸면 영역 사이 통신이 평문이 될 수 있었다.
- `boundary_contracts.clients` 의 모든 HTTP 클라이언트는 `https://` 만 받는다. 같은 기계 안(loopback: `localhost`, `127.0.0.0/8`, `::1`)만 `http://` 허용. 그 밖은 생성 시 `ValueError`(fail fast). 허용 스위치는 없다.
- 같은 규칙을 공개 함수 `boundary_contracts.clients.require_tls_url(url)` 로 낸다. 클라이언트를 거치지 않는 직접 호출(`/healthz` 도달성 확인, 추론 호출 등)도 호출 전에 이 함수를 거친다.
- 루트 신뢰는 표준 `SSL_CERT_FILE`(urllib 기본 컨텍스트). 검증 끄기 경로 없음(기존과 같음).
- 영향: 설정에 loopback 밖 `http://` 를 둔 배포는 기동 시 실패한다. 배포 설정은 전부 `https://` 로(deploy U98·U99).

## 3.4.0 (MINOR, 와이어 추가 — 결과 도착 웹 푸시, U92; 사용자 결정 2026-11-03 "도착 알림")
왜: 3.2.0은 결과 도착을 의사 화면이 열려 있을 때(SSE)만 알렸다. 화면을 닫은 의사는 결과가 와도 몰랐다.
- `StaffPushPayload.kind`에 `RESULT_READY`(본문 session_id·kind만, tag `result-`+session_id).
- `Exposure.auth.kind` 에 `authenticated`(로그인한 계정이면 역할 무관, 데이터 없는 화면 정적 파일용; 승인 대기 안내를 보이려면 화면이 열려야 한다).
- 사람 신원·역할 규약(CONVENTIONS 6절, U82·head ADR 0014): 게이트웨이가 `X-Openit-User`와 `X-Openit-Roles`(고정 역할 목록)를 붙이고 역할 없는 사용자는 403 ACCOUNT_PENDING_APPROVAL. `QuestionAuthoringEnv.QA_USER_ROLES` 삭제(서비스가 사용자→역할 표를 갖지 않는다).
- `OpsFeedbackServerEnv.OPS_DB_SCHEMA` 기본 apply → verify, 설명 정정(L08: ops-feedback DB 계정 분리, 서버·잡은 apply 거부).
- PUBLIC_API: 푸시 구독 본문에 선택 `topics`(`alerts`=staff, `results`=clinician, 기본 `alerts`). 세션이 `ENDED_*`면 `results` 구독자에게 웹 푸시. B절의 "웹 푸시로는 보내지 않는다" 삭제.

## 3.3.0 (MINOR, 와이어 형식 변경 — 문진표 여러 개와 세션별 선택; 사용자 결정 2026-11-03)
왜: 배포에 문진표가 하나뿐이었고, 세션이 문진표를 고를 길이 없었고, 순서·건너뛰기가 문진표가 아닌 고정 파일(survey-service `question_flow.json`)에서 왔다. 제품의 핵심 흐름(저자가 올린 문진표로 환자마다 문진한다)이 성립하지 않았다.
- `_common.QuestionSetRef`(ArtifactRef + `title`) 신설. `ReleaseManifest.question_sets[]`(1개 이상, QuestionSetRef)가 단수 `question_set`을 대체. `GateSubmissionRequest`·`GateSubmission`·`GateDecision`·`ReviewReport`의 `subject.question_sets[]`(ArtifactRef)가 단수를 대체. `find_decisions`의 문진표 질의는 목록 중 하나와 맞으면 반환.
- I4 `get_release_question_bank(release_id, question_set_id=None)`: `?question_set_id=` 세트별 조회, 응답에 `question_set_id`(둘 이상이면 필수, 없으면 400 INVALID_RECORD/QUESTION_SET_REQUIRED). `load_bundle` tar는 `question_banks/<id>.json`(세트마다), `ReleaseBundle.question_banks`(id -> QuestionBank).
- `QuestionFlowTable.skips[].op` 여섯 연산자(`==,!=,>,>=,<,<=`): 문진표 `prerequisite`(묻는 조건)의 부정을 표현한다. `action_rules.holds()` 평가, `fill_next_item`·`check_action_extraction` 반영. 표는 survey-service가 세션의 문진표(order·prerequisite)에서 만든다.
- `DeviceConfig.question_set_id`, `KioskStartFragment.question_set_id`(기기 배치, 조각이 먼저).
- I10(PUBLIC_API I절): `GET /v1/question-sets` 활성 문진표 목록, `SESSION_START.question_set_id`(하나면 생략 가능, 둘 이상이면 필수, 없는 ID 400 INVALID_RECORD/UNKNOWN_QUESTION_SET), `SessionResult.question_set_id`·`question_set_title`. 클라이언트 `HttpPublicApi.list_question_sets()`, `start_session(question_set_id=)`. 참조 서버 모사.
- `TraceEnvelope.question_set_id`(선택): 세션이 쓴 문진표. 릴리스에 문진표가 여럿이라 ops-feedback이 FailureCase.question_set을 고르는 데 필요하다(흐름 명세 7단계에서 발견).
- `ResponseRequest` START의 `next.question_id`를 `Q1.D01` 고정에서 임의 문항 ID로(문진표마다 첫 문항이 다르다).
- 문진 스키마(survey-service 소유) 4.0.0과 짝: `QuestionBank.question_set_id`·`title` 필수, `Prerequisite{slot, op, value}`, `SessionResult`·`StaffSessionView`·`SESSION_START` 필드, `QuestionFlow`·`question_flow.json` 삭제. 정수 runtime_contract_version 은 1 유지 — 모델 입출력이 바뀌지 않았다. CONVENTIONS 12절을 개정해 정수(모델 입출력 계약 번호)와 문진 스키마 패키지 semver 를 분리했다.

## 3.2.0 (MINOR, 와이어 형식 추가·선언 강화 — 영역 사이 이름을 전부 스키마 안으로)
- **U73 영역 사이 설정 이름 선언**: 서비스별 환경 변수 선언 스키마 신설 `ModelServingEnv`(40) `GateEnv`(39) `ModelRegistryEnv`(16) `DatasetStoreEnv`(19) `KioskFrontendEnv`(3), 개정 `SurveyServiceEnv`(모든 이름에 뜻·형식·기본값, 91) `OpsFeedbackServerEnv`(설명 채움, `OPS_GATE_*` 선언, 퇴역 `TURN_ENGINE_VERSION` 삭제) `QuestionAuthoringEnv`(독립 스키마 31, DeployInterface 의 Environment 는 $ref). 규칙: deploy 는 선언된 이름만 주고, 서비스는 기동 때 자기 environ 을 자기 선언으로 검증한다(접두사 이름 중 미선언은 거부). 뜻은 각 영역의 설정 로더·runbook 에서 옮겼고 모르는 것은 "미정"으로 표시했다(GateEnv 2건).
- **U67** `Exposure.auth.kind` 에 `machine-token` 추가(D122 추론 서버 → release-gate 읽기 경로).
- **U71** `METRICS.md` 운영 소요 시간 지표 절(턴·모델 호출·엔진·큐 대기, next_item 덮어쓰기 횟수).
- **U80** CONVENTIONS 11절: 모델 입력 `state` 키 순서 규칙. **G11** CONVENTIONS 12절: 문진 스키마 정수 버전 규칙.
- **L11** 위험 감지 미사용: `SurveyServiceEnv.SURVEY_RISK_DEFAULT_RULES` 기본값 off(사용자 결정 2026-11-03). 위험 신호 스키마·API 는 유지하되 제품은 입력원을 설정하지 않는다.
- **L12 검토용 발화 보존**(사용자 결정 2026-11-03): 새 스키마 `OpsFeedbackReviewTrace`(비식별 trace 와 같되 발화 두 칸만 원문 ≤1000자)와 I7 경로 `GET /v1/review-traces/{ref}`(reviewer 전용, 접근 기록). `OpsFeedbackJobConfig.deid.review_utterance{keep,max_chars}`. 기존 `get_trace` 는 마스킹 유지. 왜: 발화 없이는 검토가 불가능했다.
- **CR-012·L07** `OpsFeedbackJobConfig.rollback.counted_review_statuses` 는 `CONFIRMED` 만(자동 탐지만으로 롤백 요청 금지).
- OpsFeedbackServerEnv 설명 정정(OPS_DEID_SALT 이름 고정, OPS_FAILURE_DB 와 읽기 토큰). GateEnv: GATE_SUPPORTED_RUNTIME_CONTRACT_VERSION 필수. QuestionAuthoringEnv: 운영 구성은 저자 토큰 또는 게이트웨이 토큰(코드와 일치), 기본값 보강.
- **L13** `QuestionAuthoringEnv.QA_REQUIRE_TWO_PERSON` 기본 false(사용자 결정 2026-11-03).
- **U83 결과 전달**(사용자 결정 2026-11-03): PUBLIC_API B절 — 결과 읽기 경로를 역할 `clinician` 에 열고(게이트웨이), `POST /v1/results/{id}/ack`(확인 표시, SessionResult 에 acknowledged_by/at 선택 필드), SSE `result_ready` 이벤트, 결과 접근 기록 365일. FHIR 내보내기는 다음 판 옵션.
- **CR-007(model-runtime)** `RuntimeProfile.engine.enable_prefix_caching`(boolean) 추가, `ModelServingEnv` 에 HF_HUB_DISABLE_TELEMETRY·HF_DATASETS_OFFLINE 선언.
- **U36·G12 빈칸 처리**: 되묻기 한도 뒤 정지 대신 빈칸(skipped_details.reason=REASK_LIMIT). SessionState.pause_reason 의 REASK_LIMIT 는 폐기 예정 표기. PUBLIC_API B절 예시 skipped → skipped_details.
- 3.1.3 의 변경(next_item 은 서버가 정한다, ADR 0014)을 포함한다. 3.1.3 태그는 배포되지 않았다.

## 3.1.3 (PATCH, 와이어 형식 변경 없음 — `next_item`의 책임을 서버로)
- `ActionExtraction.next_item`은 추론 서버가 `action`·`targets`·`values`와 문항 순서표(flow)로 정해 채운다(규칙 데이터 `next_item.derived_by: "server"`, 기준 구현 `fill_next_item`). 모델이 낸 값은 덮어쓴다. 왜: 다음 문항 선택은 문진의 항법이지 발화 이해가 아니다. 모델에게 맡기면 학습 안 된 모델은 없는 문항을 내고(UNKNOWN_ITEM, 2026-11-02 데모), 학습된 모델도 순서표가 바뀌면 틀린다(U74).
- `check_action_extraction`은 그대로다: 채운 값이 규칙에 맞는지 확인만 한다(기준 구현끼리의 교차 검사).
- 시험: `tests/test_action_rules.py` FillNextItem.

## 3.1.2 (PATCH, 스키마·와이어 형식 변경 없음 — 클라이언트 결함과 문서만)
- 클라이언트: 409·429·503 응답의 `Retry-After` 머리글(초)을 `BoundaryError.details.retry_after_s`로 넘긴다(PUBLIC_API "Retry-After를 따른다"; 이전엔 읽지 않았다). 날짜 형식·범위 밖은 무시.
- 클라이언트: `HttpGateService.list_submissions`가 다른 목록처럼 봉투(`ListEnvelope`)와 원소(`SubmissionView`)를 계약으로 본다(이전엔 응답이 객체가 아니면 AttributeError). `get_submission` 경로 인용을 다른 호출과 같게.
- 문서: CONVENTIONS 시간표의 모델 행(합 8.0초, 턴 9초), PUBLIC_API 키오스크 대기 12초·재시도 예산 약 24초, HTTP.md 호출 상한, README 개수를 D119에 맞춤. CONVENTIONS 3절에 생산자 출력 검증(R7)과 계약 출력 위반 처리.
- 시험: `tests/test_client_312.py`.

## 3.1.1 (PATCH, 와이어 형식 변경 없음. 이 버전에서 계약을 고정한다)
- `SurveyServiceEnv`: `SURVEY_RELEASE_READER`·`SURVEY_TRACE_INGEST` 값 형식('http' 또는 '모듈:함수')과 'http'일 때 `*_URL` 필수, `SURVEY_INFERENCE_URL` 형식을 스키마로 적는다(survey-service가 설정에서 이미 거부하던 조건, deploy 설정은 이미 지킨다).
- 참조 서버: 토큰 오류 401+`WWW-Authenticate`(D106), 승인에 `X-Openit-User`가 없으면 401, 승인 멱등(200 / 409 `ALREADY_DECIDED`), packages·submissions·traces 요청을 계약으로 검증.
- 문서를 실제와 맞춘다: HTTP.md I9(extract 본문 셋 다 필수, `/v1/info`=`RuntimeInfo`), 검토 게시에 사람 머리글이 없으면 401(서버 실제 동작), INTERFACES.md의 turn-engine·`turn_engine_version`·`extract` 서명, README, PUBLIC_API.md 기기 토큰은 호환용으로 남긴다(3.0.0 제거 약속 철회).

## 3.1.0 (MINOR, 추가만. 기존 영역의 레코드·호출은 그대로 통과한다)
독립 검토(2026-10-30)가 찾은 계약 결함을 와이어 형식을 깨지 않는 범위에서 고친다.
- 새 스키마 `GateSubmissionRequest`(POST /v1/submissions 본문, 그동안 HTTP.md에 글로만 있었다). `submit_candidate()`가 보내기 전에 검사한다.
- `SurveyReadyz.reask_limit`{active, max_consecutive, effective?}를 정의한다. 이웃은 서비스의 한도 계산 규칙을 흉내 내지 않고 `effective`만 읽는다(구조 규칙 4).
- `SetupEnvReport.environment.test_command`를 필수로 둔다(3.0.0 CHANGELOG가 선언했으나 스키마에 빠졌던 것. 생산자 10곳 모두 이미 낸다).
- 클라이언트: `user=` 인자로 `X-Openit-User`를 싣는다(비공개 속성 없이). `activate()`가 `ActivateRequest`로 검사한다. `get_review_report_with_hash()`가 보고서와 `X-Openit-Report-Hash`를 함께 준다. `decide()`는 `report_hash`를 필수로 받고 스스로 다시 받지 않는다(3.0.3의 자동 채움은 STALE_REPORT 검사를 무력화했다). `get_release_question_bank()`가 content_hash 없는 응답을 KeyError 대신 INTEGRITY_ERROR로. `HttpStaffCall`이 서버 발급 세션 ID(첫 글자 -·_ 가능)를 거부하지 않는다. `start_session()`의 session_id는 선택(서버 발급, D106).
- 참조 서버: activate·rollback 요청을 계약으로 검증한다.
- 문서: HTTP.md I5 승인 본문을 `ApprovalRequest`대로(approver_id 없음, report_hash 필수), PUBLIC_API.md 세션 시작 본문의 모순 정리.
- 시험 `test_client_outgoing_schemas`: 쓰기 메서드가 본문을 계약 스키마로 검사하지 않으면 실패한다(예외는 이유와 함께 목록에).

## 3.0.3 (PATCH, 클라이언트·참조 서버 결함 수정, 와이어 스키마 변경 없음)
- `HttpGateService.decide()`가 계약 `ApprovalRequest`를 어기던 것을 고친다(U53): 본문에 `approver_id`를 싣지 않는다(D88: 승인자 신원은 `X-Openit-User`로만, HTTP.md I5). `report_hash`는 필수이므로 주지 않으면 `GET /v1/submissions/{id}/review-report`의 `X-Openit-Report-Hash` 값을 그대로 쓴다(해시를 계산하지 않는다). 보내기 전에 `ApprovalRequest`로 검사한다. `approver_id` 인자는 호환을 위해 받기만 하고 쓰지 않는다(4.0에서 제거 후보).
- 참조 서버(`conformance/servers.py`): `/v1/approvals`를 `ApprovalRequest`로 검증하고, 승인자 ID를 `X-Openit-User`(없으면 토큰 역할)에서 정하며, 보고서 해시가 다르면 CONFLICT(`STALE_REPORT`). review-report 응답에 `X-Openit-Report-Hash`를 싣는다. 이전에는 참조 서버가 본문 `approver_id`를 요구해 계약 시험이 클라이언트 결함을 잡지 못했다.
- 영향: Python 계약 클라이언트의 `decide()`를 부르는 영역은 없다(2026-10-30 확인: admin-console은 자기 TS 클라이언트, deploy E2E는 계약대로 직접 보낸다). 영역 고정을 올릴 필요는 없다.

## 3.0.2 (PATCH, 계약 결함 수정)
- `SurveyServiceEnv`: 추론 연결 필수 조건을 `SURVEY_MODEL_BACKEND` 단독에서 "`SURVEY_INFERENCE_URL` 또는 `SURVEY_MODEL_BACKEND` 중 하나"로 바로잡는다(D62부터의 survey-service 동작: 운영은 원격 추론 URL, 내장 백엔드는 fake뿐). 3.0.0 전환에서 survey-service가 이 계약으로 설정을 엄격히 검증하자 원격 추론 배포가 '필수 환경 변수가 없다: SURVEY_MODEL_BACKEND'로 기동하지 못했다(E2E 2026-10-30 11:01). 받던 설정을 더 받는 완화라 깨지는 소비자 없음.

## 3.0.1 (PATCH, 와이어 스키마 변경 없음, 설명만)
- `ImageLabels`의 `io.openit.contracts.survey-schema` 뜻을 정한다: 문진 스키마 **패키지 버전의 주 번호**(survey-schema-v2.0.0 → "2"), 이미지에 실제로 들어간 패키지에서 찍는다(U50). 문진 스키마의 정수 `CONTRACT_VERSION`(모델 런타임 호환 번호, survey-service ADR-0044)과 다르다. 3.0.0 전환 때 영역마다 두 값 중 하나를 찍어 라벨이 엇갈렸다(synthetic-data "2", ops-feedback "1").

## 3.0.0 (MAJOR, 깨지는 변경. `PIPELINE_SCHEMA_VERSION` "3.0". 2.x 레코드는 클라이언트가 UNSUPPORTED_VERSION으로 거부한다)
2.x에서 하위 호환 때문에 미룬 변경을 한 번에 낸다(헤드 `docs/proposals/계약-3.0.0-후보.md`).
1. **`turn_engine_version` → `action_rules_version`(D109).** ReleaseManifest·DatasetManifest·ModelPackageManifest·GateReadyz·SyntheticJobConfigRun/Import. 값은 계약 `ActionExtractionRules.rules_version`(지금 "2"). 계보 일치 검사는 이 값으로 한다. `BuildImageRequest.versions.turn_engine`과 이미지 라벨 `io.openit.turn-engine` 제거(라벨이 남아 있으면 ImageLabels가 거부).
2. **I9 extract 본문은 `ExtractRequest{input, flow, fields}`만**(D108, D115). 옛 `ActionExtractionInput` 그대로의 본문과 fields 없는 요청은 400 INVALID_RECORD. 클라이언트 `HttpModelRuntime.extract(release_id, request, flow, fields)`는 flow·fields가 필수 인자다. 서버가 흐름 규칙과 값 규칙을 항상 보증하므로 받는 쪽은 다시 검사하지 않는다(R7).
3. **`SetupEnvReport`: status가 ok면 `environment`(test_command 포함) 필수**(U43).
4. **`sdk.ReleaseReader` Protocol에 `get_release_question_bank`**(U47, 2.7.0에서 미룸).
5. **`OpsFeedbackJobConfig.deid`에서 계약 밖 출력을 내던 선택지 제거**(U25, ops-feedback CR-008 안 2): `scrub_string_keys`·`scrub_patterns`, `unlisted_string_action: drop`(이제 `mask`만), `count_map_key_pattern`.
6. **`StaticImageInterface` 제거**(U47): port·user·env는 OCI 이미지 설정(EXPOSE·USER·ENV)이 표준으로 담고 경로는 `Exposure` 라벨이 담는다.
- 영역 이행: 저장된 2.x 레코드(매니페스트 등)는 3.0 클라이언트가 읽지 않는다. 시연·시험 저장소는 3.0으로 다시 만든다(운영 데이터 없음, 2026-10-30 기준).

## 2.8.0 (MINOR, 추가형. `PIPELINE_SCHEMA_VERSION` "2.8". 클라이언트는 MAJOR만 비교)
- **`SurveyRiskRulesFile`(OPEN_GAPS U48, 구조 규칙 1).** survey-service 위험 감지 규칙 파일(`SURVEY_RISK_RULES_FILE`)의 형식을 계약으로 둔다. deploy E2E가 시험용 규칙 파일을 만들어 주입하고(deploy CR-U48 안 A), 영역 내부 `risk_rules.py`를 읽지 않는다. 스키마로 표현 못 하는 id 중복·정규식 유효성은 survey-service가 시작 때 거부한다.

## 2.7.0 (MINOR, 추가형. `PIPELINE_SCHEMA_VERSION` "2.7". 클라이언트는 MAJOR만 비교)
- **I4 `get_release_question_bank`(OPEN_GAPS U47, SurveyQuestionBankRead).** `GET /v1/releases/{id}/question-bank` → `{release_id, content_hash, question_bank}`. 어댑터 없이 릴리스에 묶인 문항 세트만 준다(survey-service가 문항 세트를 얻으려고 어댑터까지 받던 SV-16). PASS가 아닌 릴리스는 412, 클라이언트가 문항 세트 해시를 검증한다. 기준 서버 구현 포함.
- `sdk.ReleaseReader` Protocol에는 아직 넣지 않는다(release-gate 구현이 생기기 전에 넣으면 isinstance 검사가 깨진다). 3.0.0에서 넣는다.

## 2.6.0 (MINOR, 추가·완화형. `PIPELINE_SCHEMA_VERSION` "2.6". 클라이언트는 MAJOR만 비교)
- **U43(구조 규칙 1): 영역이 시험 환경과 잡 설정을 선언한다.** deploy가 이웃의 `.venv`·`node_modules`·시험 도구·잡 설정 파일 모양을 짐작하지 않게 한다(deploy CR-D30).
  - `SetupEnvReport.environment`: '[제안]'을 떼고 `test_command`(리포 루트에서 영역 시험 전체를 돌리는 argv) 추가. 2.x에서는 선택(없으면 deploy가 '검증 안 함'), 3.0.0에서 필수. 영역 `scripts/setup-env.sh`가 표준 출력 마지막 줄에 이 한 줄을 낸다.
  - `JobsDeclaration` 잡에 `env`(비밀이 아닌 설정 환경 변수 이름 목록) 추가. 비밀은 `secret_files`(NAME_FILE)로만(D84). 설정은 환경 변수로 받는다는 12-factor 관행을 따른다.
- **U45 나머지:** `ListEnvelope.items` 원소를 객체로만 두던 제한을 푼다(ID 문자열 목록 API가 있다). 계약 클라이언트의 목록 손 검사를 계약 스키마 검증으로 바꾼다.

## 2.5.1 (PATCH, 와이어 스키마 변경 없음, `PIPELINE_SCHEMA_VERSION` "2.5" 그대로)
- 고침(OPEN_GAPS U45, U23 감사): 계약 클라이언트가 응답을 손 검사 대신 계약 스키마로 검증한다.
  - `HttpModelRuntime` 적재 상태(`ReleaseLoadStatus`)와 `info()`(`RuntimeInfo`).
  - ops `get_trace`가 객체인지만 보던 것을 `OpsFeedbackDeidentifiedTrace`로(비식별 결과가 계약을 어기면 받는 쪽이 원문 조각을 쓰지 않게).
- 기준 서버·시험 고정값이 계약을 어기던 것을 고쳤다: 기준 runtime `/v1/info`에 `system_prompt_sha256` 등 빠진 필드(이제 계약 예시를 바탕으로 낸다), 시험의 비식별 Trace가 `session_id`도 없고 `turn_id`도 가명 형식이 아니었다.
- 남김: 목록 `ListEnvelope`는 스키마가 `items`를 객체로만 두지만 ID 문자열 목록을 내는 API가 있다(질문 세트·데이터셋·어댑터 목록). 스키마를 넓히는 것은 와이어 변경이라 다음 MINOR로 미루고, 그때까지 같은 규칙을 손으로 본다.

## 2.5.0 (MINOR, 와이어 스키마 변경. `PIPELINE_SCHEMA_VERSION` "2.5". 클라이언트는 MAJOR만 비교)
- **영역 빌드 진입점 확정(OPEN_GAPS U42, 구조 규칙 1).** `BuildImageRequest`/`BuildImageResult`의 '[제안]'을 뗀다. deploy는 요청 JSON 파일 하나로 영역 `scripts/build-image.sh <요청 파일>`을 부르고, 영역은 Dockerfile 인자 이름·빌드 컨텍스트·라벨 값을 스스로 정해 표준 출력 마지막 줄에 결과 JSON 한 줄을 낸다. 지금까지 deploy `build-images.sh`가 영역마다 다른 인자 이름과 빌드 산출 파일을 직접 알았다.
- `BuildImageRequest` 바뀐 점(제안을 쓰는 곳이 없어 깨지는 소비자 없음):
  - `versions.turn_engine` 필수 해제(D109 폐기, 받기만 함, 3.0.0에서 뺀다). `versions.survey_schema` 추가(vX.Y.Z). `versions`는 `boundary`만 필수이고 모르는 키는 거부.
  - `dependency_sources` 추가: 공유 라이브러리(boundary, model_runtime, survey_schema)의 해당 버전 소스 트리 절대 경로. 영역이 이웃 리포 경로(`../model-runtime`)나 빌드 중 네트워크(SSH) 대신 쓴다.
  - `variant` 추가: 한 리포가 이미지를 여럿 낼 때(예: model-runtime `gpu`).
  - 최상위 모르는 키 거부(deploy가 인자 이름을 넘기는 길을 막는다).
- `BuildImageResult`: 설명만 확정(필드 그대로).

## 2.4.2 (PATCH, 와이어 스키마 변경 없음, `PIPELINE_SCHEMA_VERSION` "2.4" 그대로)
- 고침(OPEN_GAPS U29): 계약 클라이언트가 본문을 쓰다 연결이 끊겨도(EPIPE·ECONNRESET) 서버가 먼저 보낸 응답을 읽는다. waitress는 본문 상한을 넘은 업로드에 본문을 읽지 않고 413을 보낸 뒤 닫아, 2.4.1까지는 경쟁 조건에서 413 대신 `UNAVAILABLE`(재시도)이 나왔다(2.2.2 규칙 위반). 이제 `INVALID_RECORD`(`details.http_status` 413)다. 쓰기가 끊긴 뒤 받은 성공 응답(2xx·3xx)은 잘린 요청이 처리됐을 수 있어 믿지 않고 `UNAVAILABLE`로 낸다. 응답도 못 읽으면 전처럼 `UNAVAILABLE`. 근거: RFC 9112 9.5(본문을 보내는 클라이언트는 오류 응답을 살핀다). `Expect: 100-continue`는 waitress 3.0.2가 상한 초과에도 100을 먼저 보내 해결이 안 됨을 측정했다(2026-10-30 gpu-dev, 30/30).
- 추가(OPEN_GAPS U21): HTTP 오류 응답에서 만든 `BoundaryError`는 `details.http_status`에 원래 상태를 남긴다. 401(토큰 오류)과 403(권한 오류)이 같은 `PERMISSION_DENIED`라 운영 로그에서 구분할 수 없었다. 서버가 준 `details`의 다른 키는 그대로다. 추가형이라 PATCH로 둔다(MAJOR.MINOR는 와이어 스키마 버전과 같게 두는 규칙, 이 파일 머리).

## 2.4.1 (PATCH, 와이어 스키마 변경 없음, `PIPELINE_SCHEMA_VERSION` "2.4" 그대로)
- 고침: 계약 클라이언트 `HttpModelRuntime.extract(release_id, request, flow=None, fields=None)`. 2.4.0은 `ExtractRequest.fields`를 정했지만 클라이언트가 보낼 수 없었다(survey-service CR-020). fields는 flow와 함께만 보낼 수 있다(아니면 INVALID_RECORD, 보내지 않음).
- 기준 서버(`RuntimeReferenceServer`)가 fields가 오면 `apply_value_rules`를 적용한다(영역 시험용).

## 2.4.0 (MINOR, 추가형. `PIPELINE_SCHEMA_VERSION` "2.4". 클라이언트는 MAJOR만 비교)
- **LoRA-A 출력 값 규칙(OPEN_GAPS U32·U33, 헤드 초안 `head/docs/proposals/2026-10-29-계약-2.4.0-칸-규격과-값-규칙.md`).** 새 스키마 `QuestionFieldSpec`(칸 자료형·단위·범위·선택지·반복 키, 값은 데이터셋 `docs/SQL.md` question_fields와 같게). I9 `ExtractRequest`에 선택 필드 `fields`.
- 규칙 데이터 `action_extraction_rules.json` `rules_version` "2": `value_rules`(범위 밖 → `REASK/OUT_OF_RANGE`, 기간보다 많은 횟수 → `REASK/COUNT_EXCEEDS_DAYS`, 최대량<평소량 mL 비교 → `CONFIRM/CONFLICT_MAX_BELOW_USUAL`, 안 마심+횟수 → '마심'으로 정정, 안 마심+양 → `CONFIRM/CONFLICT_DOES_NOT_DRINK`). 값과 환산표는 정규화기 `openit-normalizer`(normalize.py R1~R3, mappings.VOLUME_ML·PERIOD_MAX·MAX_MINUTES_PER_DAY)에서 옮겼다.
- 해석기 `apply_value_rules(input, output, fields, flow=None, rules=None) -> (출력, 위반, 적용 사유)`: 규칙에 걸리면 데이터셋이 같은 상황에서 낸 정답 모양으로 바꾼다. 데이터셋에 정답이 없는 위반(자료형 불일치 `VALUE_TYPE_MISMATCH`, 최소값 미만 `VALUE_BELOW_MINIMUM`)은 바꾸지 않고 돌려준다(서버는 `OUTPUT_INVALID`).
- 이 판의 규칙은 선택지 칸으로 바뀐 숫자(예: Q6_1 '32일' → `days_10_29`)를 잡지 못한다(원래 숫자가 출력에 없다).

## 2.3.0 (MINOR, 추가형. `PIPELINE_SCHEMA_VERSION` "2.3". 클라이언트는 MAJOR만 비교)
- **키오스크 기기 인증을 게이트웨이 클라이언트 인증서(mTLS)로(ADR 0012, D113).** 게이트웨이가 확인한 기기 ID를 `X-Openit-Device`로 넘기고 서비스는 그 값을 믿는다(PUBLIC_API.md F절). 기기 토큰(`Authorization: Bearer`)과 `DeviceConfig.device_token`은 폐기 예정(3.0.0에서 제거).
- `HttpPublicApi(base_url, token=None, timeout, device_id=None)`: 토큰은 선택, 내부망 직접 호출은 `device_id`로 헤더를 싣는다. `HttpClientBase`는 토큰이 없으면 `Authorization`을 싣지 않는다.
- 기준 서버 `PublicApiReferenceServer`가 `X-Openit-Device`로 키오스크를 식별한다(`trust_device_header`).

## 2.2.2 (PATCH, 와이어 스키마 변경 없음, `PIPELINE_SCHEMA_VERSION` "2.2" 그대로)
- 고침: `boundary_contracts.clients`가 전송 계층 한도 응답(413·414·431)을 본문과 무관하게 `INVALID_RECORD`(재시도 안 함, `details.http_status`)로 읽는다. 2.2.1까지는 예상 밖 상태로 보고 `UNAVAILABLE`(재시도)로 바꿔, 너무 큰 본문을 다시 보낼 수 있었다(waitress 교체 중 synthetic-data 보고, 2026-10-29). CONVENTIONS 9절에 규칙 추가.
- 문서: `GateJobResult` 설명의 종료 코드 문장을 표와 맞췄다(설정 오류 1, 예기치 못한 예외 75; OPEN_GAPS U27).

## 2.2.1 (PATCH, 와이어 스키마 변경 없음, `PIPELINE_SCHEMA_VERSION` "2.2" 그대로)
- 고침: `HttpModelRuntime.extract(release_id, request, flow=None)`. 2.2.0은 I9 문서가 정한 `ExtractRequest{input, flow}`를 클라이언트가 보낼 수 없었다(보내기 전 검증이 `ActionExtractionInput`만 허용). flow를 주면 `ExtractRequest`로 검증해 보낸다(survey-service 보고, 2026-10-29).
- 기준 구현 `RuntimeReferenceServer`가 두 본문을 모두 받고, flow가 있으면 `check_action_extraction` 위반 출력을 503 OUTPUT_INVALID로 낸다(HTTP.md I9 규칙 보증).

## 2.2.0 (MINOR, 추가형. `PIPELINE_SCHEMA_VERSION` "2.2". 클라이언트는 MAJOR만 비교하므로 2.1 레코드와 섞여도 동작한다)
- **추가 스키마(D107):** 영역 경계 스키마 49개(admin-console, deploy, kiosk-frontend, model-lab, model-runtime, ops-feedback, question-authoring, release-gate, survey-service, synthetic-data). 예시는 `examples/`(통과)와 `conformance/examples_invalid/`(거부), 출처 매니페스트는 `conformance/promoted/`. 이 예시는 각 영역이 낸 값이며 이웃이 실제로 그 모양을 읽는지는 확인하지 않았다.
- **LoRA-A 출력 의미 규칙(ADR 0010, D104):** 규칙 명세 데이터 `boundary_contracts/data/action_extraction_rules.json`(스키마 `ActionExtractionRules`)과 기준 검사기 `boundary_contracts.action_rules.check_action_extraction(input, output, flow)`.
- **I9 extract 요청 확장(D108):** `ExtractRequest{input, flow}`, `QuestionFlowTable`. 2.x는 옛 본문(`ActionExtractionInput`)도 받으며 flow가 있을 때만 서버가 규칙을 보증한다. 3.0.0에서 `ExtractRequest`만 남는다.
- **`ImageLabels`(D108):** 필수 4개(service, revision hex, contracts.boundary, contracts.survey-schema), turn-engine·model-runtime·langgraph 선택, 값 없음은 `n/a`, 버전은 `v` 접두사.
- **동작 변경(D106 문서의 구현):** `directory_hash`가 심볼릭 링크를 `INTEGRITY_ERROR`로 거부한다(CONVENTIONS 8절). 401/403 규칙, 서버 발급 세션 ID, 푸시 해지 본문 방식, 모델 호출 시간 예산 배분은 2.2.0 문서로 확정한다.
- 바뀌지 않은 것: 기존 31개 스키마의 와이어 모양.

## 2.1.1 (PATCH, 와이어 스키마 변경 없음, `PIPELINE_SCHEMA_VERSION`은 "2.1" 그대로)
- 추가(데이터·도구·문서): `boundary_contracts/metrics.json`과 `metrics()`/`metric_name_problems()`, `HttpPublicApi`와 `PublicApiReferenceServer`, `conformance` 패키지를 설치본에 포함(이웃 영역이 참조 서버를 가져다 쓴다), `HTTP.md` I8·I10 절, `PUBLIC_API.md` G절 동작 의미, `CONVENTIONS.md`의 `/readyz` 총 2초와 시간 상한 사슬, 예시의 폐기 지표 교체.

## v2.1.0 태그 이후 추가 (데이터 추가, 스키마 변경 없음, 미태그)
- **지표 레지스트리 `boundary_contracts/metrics.json`** 이 평가 지표 이름의 정본이다(이름, group, unit[기존 `EvaluationReport` unit 열거 값만], higher_is_better, status ACTIVE|DEPRECATED, replaced_by, applies_to A|B|both). 내용은 METRICS.md v2와 같다(D96~D98). 로더 `boundary_contracts.metrics()`(이름 -> 읽기 전용 항목)와 `metric_name_problems(report)`(EvaluationReport/ReviewReport의 폐기·모르는 이름 검사). `EvaluationReport` 스키마는 그대로라 `name`은 여전히 자유 문자열이고 검사는 레지스트리 몫이다.
- METRICS.md의 지표 표 3개는 `tools/gen_metrics_md.py`가 레지스트리에서 생성한다(표식 `<!-- BEGIN GENERATED metrics:A|B|COMMON -->`). `--check`로 커밋된 파일과 같은지 확인하고 unittest와 verify.py가 이를 시험한다.
- **패키지 데이터로는 다음 릴리스부터 나간다.** v2.1.0 태그에는 `metrics.json`이 없다. 소비 영역은 다음 태그를 기다리거나 개발 중에는 리포지토리 파일을 읽는다.
- 방향(higher_is_better): `protection_intervened`, `fallback_rate`, `output_attempts_mean`, `coverage_seen_unseen_gap`는 false(낮을수록 좋음), `response_length_chars_p95`는 null(방향 미정, 짧은 쪽이 음성 출력에 유리하다는 설명뿐). 근거: 헤드 결정, 임상·학습 담당 확인 전 임시.
- **I10 공개 API 클라이언트·참조 서버(데이터·코드 추가, 스키마 변경 없음)**: `boundary_contracts.clients.HttpPublicApi`(세션 시작·발화·종료·상태·개입 결정·`/healthz`)와 Protocol `sdk.PublicApi`·`sdk.StaffCall`, 참조 서버 `conformance.servers.PublicApiReferenceServer`(`StaffCallReferenceServer`를 확장해 중복 없음), 시험 `tests/test_publicapi.py`. `HttpStaffCall`을 Protocol 적합성 쌍에 추가. 참조 서버의 429를 PUBLIC_API.md G절대로 맞췄다(간격 초과 `details.reason: INTERVAL`+`Retry-After`, 상한 초과 `RETRY_LIMIT`은 `Retry-After` 없음; 전에는 `TOO_SOON`이었다).
- **`conformance`가 설치 패키지에 들어간다(다음 릴리스부터)**: pyproject `packages`에 `conformance`와 `conformance/examples`(리포지토리 `examples/`의 심볼릭 링크)를 추가했다. v2.1.0 태그의 패키지에는 없다. 이웃 영역(survey-service 등)은 다음 태그부터 참조 서버를 복사하지 않고 `conformance.servers`를 가져다 쓴다.
- 문서: INTERFACES I10 절을 PUBLIC_API.md를 가리키게 고치고(모순 해소) README의 I10 읽는 쪽을 kiosk-frontend로 정정, HTTP.md에 `## I10`과 `## I8`(HTTP 없음) 추가.
- 시험 버전 리터럴 정리: 시험이 `PIPELINE_SCHEMA_VERSION`·설치된 패키지 버전에서 값을 읽는다.

## 2.1.0 (MINOR, 추가형: CR-H001·CR-H002·D96~D98·D100)
- (v2.1.0 태그 뒤 문서·예시 보정, 스키마 변경 없음) PUBLIC_API G절에 재전달 신호(`delivery_attempts` 증가)·해결된 알림·429 두 종류·turn_id 재사용 규칙을 명시, CONVENTIONS에 `/readyz` 총 2초 규칙, INTERFACES의 I10 읽는 쪽 정정, 예시의 폐기 지표 이름(`risk_signal_recall`)을 `action_accuracy`로 교체.

기존 클라이언트가 깨지지 않는다. 모든 변경은 optional 필드·새 경로·문서 개정이다. `PIPELINE_SCHEMA_VERSION` "2.0" -> "2.1"(2.0 레코드는 계속 읽힌다).

- **직원 호출 재알림·실패 기록(CR-H001)**: `POST /v1/sessions/{id}/staff-call/retry`, `POST .../staff-call/report`(PUBLIC_API G절). 새 스키마 `StaffCallRetryRequest`, `StaffCallRetryResult`, `StaffCallReport`. `StaffAlert`에 optional `delivery_attempts`, `last_delivery_status`, `manual_notice_outcome`, `manual_notice_reported_at`. 재알림 간격·횟수는 서비스 설정(권고 30초·10회, 측정 안 함). 클라이언트 `HttpStaffCall`, 참조 서버 `StaffCallReferenceServer`. ADR 0010.
- **정지 사유(CR-H002)**: optional `pause_reason`(`RISK`/`REASK_LIMIT`/`OTHER`)을 `SessionState`, `StaffAlert`에 추가. `TurnFailureSignal`·`StaffSessionView`는 문진 스키마라 survey-service가 같은 이름으로 반영한다. `PAUSED_RISK` 이름은 유지. ADR 0011.
- **METRICS.md v2(D96·D97·D98)**: v1 지표 폐기·대체 표시, `value_precision/recall`, `action/reason/status/next_item_accuracy`, `output_invalid_rate`, `ungrounded_number_rate`(평가 지표), `material_coverage`, `semantic_violation_rate`, slice 기준 `ACTION`·`REASON`. `EvaluationReport`의 slice `kind`는 자유 문자열이라 스키마 설명 문구만 갱신. ADR 0013.
- **I2 DatasetStore HTTP(D100)**: `HTTP.md ## I2`, 클라이언트 `HttpDatasetStore`(게시·조회·파일 묶음), 참조 서버. ADR 0012.
- 클라이언트: 429를 `UNAVAILABLE`로 매핑(`Retry-After` 규약, 전에는 상태 불명 `UNAVAILABLE`로 `details.status`만 남았다). 읽기 모드가 null을 허용하는 열거(`pause_reason` 등)의 모르는 값도 받아들인다.
- 결함 정정(같은 2.1.0): `StaffAlertPage.items`가 `StaffAlert`를 인라인 복제해 새 필드를 거부하던 것을 `$ref`로 바꿨다. 다른 스키마에 StaffAlert·SessionState 인라인 복제는 없고, SSE 이벤트 봉투 스키마는 없다(data는 StaffAlert). `verify.py`의 스키마 저장소를 전체 스키마로 넓혔다. 참조 서버에 `GET /v1/staff/alerts`를 추가했다.
- 시험: unittest 110 -> 134, `verify.py` OK 102 -> 112.

## v2.0.2 이후 v2.1.0 이전의 문서 정정 (v2.1.0에 포함됨) (v2.0.2 태그 이후, 미태그, 문서만)

스키마와 패키지 코드는 바뀌지 않았다. 아래는 `PUBLIC_API.md`·`CONVENTIONS.md`·`HTTP.md`의 문서 정정과 하위 호환 추가다. 새 태그는 내지 않았다(패키지 내용이 같아서). 의존 영역은 `v2.0.2`를 그대로 쓴다.

- `PUBLIC_API.md`: 상태 값 의미(B절), 409 `CONFLICT`에 `details.reason: TURN_IN_PROGRESS`와 `Retry-After`(처리 중인 같은 `turn_id`, D86), 직원 알림 SSE의 `heartbeat`·`resync` 이벤트(D87, 하위 호환), 알림 스트림 설명.
- `CONVENTIONS.md`: 401/403, 429, 재시도 의미(`details.reason`), gateway의 `UPSTREAM_UNAVAILABLE`, 토큰을 파일로 받는다는 서술(D84와 일치시킴).
- `PUBLIC_API.md`(2026-10-28 후속): `turn_id` 재전송 문구를 정확히(확정된 턴만 같은 응답, NOT_COMMITTED는 재처리), 키오스크 재시도 문구를 예산 방식으로, 게이트웨이가 기기 토큰을 서비스에 그대로 전달하고 서비스가 기기 토큰 표로 재검증한다는 서술(D88 U8)로 정정.
- `HTTP.md`·`PUBLIC_API.md`(D88): 승인(`POST /v1/approvals`)은 `X-Openit-User`가 없으면 401(이전: 본문 `approver_id`를 썼음, **동작 변경**: 소비 영역의 호출 경로를 헤더 기준으로 맞춰야 한다), 직원 접근 기록에 행위자 계정 ID를 남긴다.
- `HTTP.md`: 서버 토큰을 `<이름>_TOKENS_FILE`로 받는다는 서술(D84).

## 2.0.2 (PATCH, D84)

- `boundary_contracts.secrets`를 추가했다: `read_secret(NAME)`은 `NAME_FILE`(파일 경로)을 먼저 읽고, 없으면 환경 변수 `NAME`(개발·시험용)을 쓴다. 오류 메시지에 값을 넣지 않고, `secret_source(NAME)`은 값 없이 출처('file'|'env'|'unset')만 말한다. 이유: 서비스 토큰이 환경 변수라 `docker exec env`/`inspect`로 평문이 노출되는 구조였다(gpu-dev 측정 중 실제 노출). 영역마다 읽기 코드를 따로 만들면 같은 실수가 반복되므로 공유 패키지에 한 번만 둔다. 스키마 변경 없음.

## 2.0.1 (PATCH, D83 후속)

- `ActionExtraction`의 `properties` 순서를 사전순으로 고쳤다(최상위: action, next_item, note, reason, targets, values / values 항목: key, precision, save, status, value). 검증 의미는 같다. 이유: xgrammar는 `properties` 순서대로 키를 내도록 강제하므로, 계약과 학습 데이터의 사전순과 어긋나면 학습된 모델의 올바른 출력도 제약 디코딩이 막는다(gpu-dev 조사, model-runtime 0.6.5 시험에서 발견).
- `examples/TraceEnvelope.json`의 `trace`를 v2 키(`extract_*`, `validation_*`, `response_*`)로 바꿨다. survey-service의 TurnTrace(97e44de)가 v2 키를 필수로 하면서 `verify.py`가 깨져 있었다(v2.0.0 태그 시점에는 통과, 이후 survey-service 스키마가 바뀌며 실패). 값은 모두 null이다.

## 2.0.0 (D74, D75; 태그 v2.0.0-rc1 이후의 확정분 포함, 태그는 헤드가 붙인다)

학습 데이터셋 v2에 서비스 구조를 맞춘다. 정규화·절차·다음 문항은 LoRA-A가 내고, 서비스는 표 찾기만 한다. v1 형식은 **병행 없이 폐기**했다(이유: v1 계약은 없어진 단계를 기술하고, 학습된 모델은 v2 형식만 말하며, 운영 데이터가 없는 데모 단계). 이전 형식은 태그 `v1.3.3`으로 남는다. 근거와 열린 항목은 `V2_DRAFT.md`.

### 깨지는 변경 (MAJOR)
- `ParserSample`, `GeneratorSample` 스키마와 예시를 삭제했다.
- `DatasetManifest.files[].role`: `PARSER`/`GENERATOR` -> `LORA_A`/`LORA_B`.
- `FailureCase.expected_kind`: `PARSER`/`GENERATOR` -> `LORA_A`/`LORA_B`. `FailureCase.expected`는 객체 또는 문자열(LORA_B의 정답은 문장).
- `INTERFACES.md` I8(turn-engine: `normalize`, `judge`, `write_record`, `plan`)을 폐기했다.
- `HTTP.md` I9: `parse`/`generate` 경로를 `extract`/`respond`로 바꾸고, 입출력과 출력 검증 규칙을 바꿨다(`respond`의 응답은 JSON이 아니라 `text/plain`).
- `PIPELINE_SCHEMA_VERSION` "1.3" -> "2.0". 클라이언트는 MAJOR 1 레코드를 `UNSUPPORTED_VERSION`으로 거부한다.

### D75로 확정한 것 (rc1 이후)
- `extract`가 끝내 형식을 못 지키면 503 `UNAVAILABLE`, `details.reason="OUTPUT_INVALID"`. 대체 출력은 만들지 않는다. 라이브러리는 `ModelOutputInvalid`. survey-service는 한 번 재시도하고 그래도 안 되면 `turn_failure_signal`로 처리하며 세션 상태를 바꾸지 않는다. 클라이언트 `is_output_invalid(err)`, 참조 서버가 같은 규칙을 따른다. `BoundaryError.details.reason` 규약을 CONVENTIONS 10절에 적었다.
- `runtime_contract_version`은 의미 유지(모델 패키지가 학습된 문진 스키마의 정수 버전, 소유 survey-service). 필드 그대로.
- `INTERFACES.md` I8: 폐기가 아니라 **출력 검증 라이브러리로 대체**. 형식은 model-runtime, 의미(targets, next_item, 건너뛰기 순서, save)는 turn-engine의 순수 함수 `validate_extraction`(시그니처 초안만 문서에 있고 코드는 turn-engine 영역).
- **시스템 프롬프트는 모델 패키지의 일부**: `ModelPackageManifest.system_prompt {path, sha256}`가 **필수 필드로 추가**되었다(`_common`의 `SystemPromptRef`). 같은 값을 `ReleaseManifest.adapters[LORA_A|LORA_B].system_prompt`(필수)로 게이트가 복사한다(서비스가 I3를 읽지 않아도 되게 하려는 이 작업의 판단이며, 지시 범위인 패키지 매니페스트 밖의 추가다). 파일은 어댑터 디렉터리 안에 있고 `adapter_hash`에도 포함된다. 클라이언트(`publish`, `open_adapter`, `load_bundle`)가 파일 존재와 해시를 확인한다. `serving_config`의 프롬프트 템플릿 버전(조립 규칙)과는 별개다.

### 더한 것
- 스키마 6개: `ActionExtractionInput`, `ActionExtraction`, `ActionExtractionSample`(LoRA-A), `ResponseRequest`, `ResponseText`, `ResponseSample`(LoRA-B). 스키마는 모두 28개.
- 계약으로 인정한 것: reason 4종(OTHER_BEVERAGE, MISSING_NUMBER, UNPARSED_VALUE, INVALID_OPTION), 괄호 없는 술 키(`Q7_1.amount`), 부분 선채움 문항으로의 NEXT.
- `boundary_contracts.clients.HttpModelRuntime`(I9: 적재, 상태, info, `extract`, `respond`)과 `conformance.servers.RuntimeReferenceServer`.
- 응답 헤더 `X-Openit-Outcome`: `extract`는 `ok`, `respond`는 `ok` 또는 `fallback`(서버가 대체 문장을 냈다). `X-Openit-Attempts`, `X-Openit-Protections`는 선택.
- CONVENTIONS 10절: 모델 키 문법과 `SlotRef` 문자열을 구분. 모델 입출력은 `ext`·버전이 없는 엄격한 스키마.
- `tools/validate_dataset_v2.py`(학습 데이터셋 v2 JSONL 검증), `tools/negatives_v2.py`(거부 변형 목록; `verify.py`와 시험이 공유).

### 그대로인 것
`LORA_A`/`LORA_B` 역할을 쓰는 `ModelPackageManifest`, `EvaluationReport`, `ReleaseManifest`, `GateDecision`, `GateApproval`, `ReviewReport`, `SubmissionView`, `ActivePointer`, `RollbackRequest`, `RollbackReceipt`와 `TraceEnvelope`(봉투), 공개 API(`PUBLIC_API.md`), `ChangeClassification`(SlotRef 문자열). 이 레코드들은 버전 문자열만 "2.0"이 되었다.

### v1에서 옮기는 방법

대응은 의미가 같은 것끼리만 짝지었다(확인: `survey-service/schema`의 v1 타입 필드를 읽고 대조). 1:1이 아닌 것은 "없어짐"으로 적었다. v1 필드의 값을 v2 값으로 자동 변환하는 규칙은 두지 않는다(v2는 모델이 추출·정규화·절차를 한 번에 내기 때문이다).

LoRA-A 입력 (`UtteranceParserInput` -> `ActionExtractionInput`):

| v1 | 2.0.0 |
|---|---|
| `utterance` | `user_utterance` |
| `last_directive`, `awaiting_questions`, `question_names`, `guide_list` | 없어짐. 대신 지금 묻는 문항을 `question_id`(문항 ID)와 `current_question`(문장)으로 준다 |
| `answered_slots` | `state`: `{"<모델 키>": {"value", "status": ANSWERED\|UNCLEAR\|MISSING}}` (항상 객체, 빈 객체 가능) |

LoRA-A 출력 (`ParserOutput` + `AnswerNormalizerInput/NormalizerOutput`, `AnswerJudgeInput/JudgeOutput`, `DialoguePlannerInput/PlannerOutput` -> `ActionExtraction`):

| v1 | 2.0.0 |
|---|---|
| `ParserOutput.items[]` (`item_no`, `target`, `value`(문자열), `source_text`, `intent`, `progress_op`, `guide_id`, `evidence`) | `values[]` (`key`, `value`(불리언·숫자·문자열·null), `precision`, `status`, `save`). `item_no`, `source_text`, `evidence`, `progress_op`, `guide_id`는 없어짐 |
| `intent` (ANSWERED_INTENT, CORRECTION_MARKED, SAYS_UNKNOWN, SAYS_REFUSAL, OUT_OF_SCOPE 등) | `values[].status`(ANSWERED, CORRECTION, UNKNOWN, REJECTED 등)와 `action`(CORRECT, SKIP, REDIRECT 등)으로 나뉘어 표현됨. 의도 12종과 1:1 대응은 없다. RISK_SIGNAL, USER_CALLED_STAFF, GUIDE_REQUEST, PROGRESS_OP 같은 의도는 v2 모델 출력에 대응하는 표현이 없다(서비스가 어떻게 다룰지는 survey-service 몫이며 열린 항목) |
| 정규화기의 값 변환(단위, 범위) | 모델이 `values[].value`에 정규화된 값으로 낸다(서비스에 정규화 코드가 없다) |
| 판정기의 저장 여부 | `values[].save` (= `status`가 ANSWERED 또는 CORRECTION) |
| `PlannerOutput.directive` (`Action` 16종: ASK_NEXT, ASK_MISSING, ASK_CLARIFY, ASK_CONFIRM, ...) | `action` 7종(NEXT, CORRECT, REASK, CONFIRM, HOLD, SKIP, REDIRECT)과 `reason`. 대략 ASK_NEXT -> NEXT, ASK_MISSING·ASK_CLARIFY -> REASK, ASK_CONFIRM -> CONFIRM, ASK_AFTER_UNKNOWN -> HOLD, ASK_AFTER_REFUSAL -> SKIP, REDIRECT -> REDIRECT (제안, 의미 대응이며 변환 규칙이 아니다). 안내·종료·직원 호출류(RISK_NOTICE, STAFF_NOTICE, FAREWELL 등)는 v2 출력에 없다 |
| Planner의 대상 칸·다음 문항 | `targets[]`(REASK·CONFIRM·HOLD·SKIP만, 없으면 키를 뺀다), `next_item`(문항 ID 또는 `END`) |
| `flow`, `staff_alert`, `progress_record_update`, `planner_record_update` | 없어짐(모델 출력에 없다) |

LoRA-B (`ResponseGeneratorInput`/`GeneratorOutput` -> `ResponseRequest`/`ResponseText`):

| v1 | 2.0.0 |
|---|---|
| `ResponseGeneratorInput {directive, utterance}` (`directive`의 문장 재료) | `ResponseRequest`: `action`(START 포함), `topic`, `user_utterance`, `known`, `next{type: NEXT\|SAME\|END, question_id, text}`, 그리고 action별로 `reason`, `ask`, `previous`, `current`, `hold`, `note`. 서비스가 A 출력에서 표 찾기로 조립한다 |
| `GeneratorOutput {response_text, is_fallback}` | 응답 문장 그대로의 텍스트. 대체 여부는 응답 헤더 `X-Openit-Outcome: fallback` |
| 시작 안내 | 서비스가 A를 부르지 않고 `action=START`로 B만 부른다 |

데이터셋과 평가:

| v1 | 2.0.0 |
|---|---|
| `ParserSample`(`question_set`, `runtime_contract_version`이 필수; `noise_types` 등) | `ActionExtractionSample`: `sample_id`, `scenario_id`, `split`, `origin`, `input`, `expected`가 필수. `question_set`, `human_review`, `seed_case_id`, `ext`는 선택. `runtime_contract_version`, `style_guide_version`, `noise_types`는 없다 |
| `GeneratorSample` | `ResponseSample` (`expected`는 문자열) |
| `ModelPackageManifest` | `system_prompt {path, sha256}` 필수 추가. 기존 패키지는 어댑터 디렉터리에 프롬프트 파일을 넣고 매니페스트를 새 버전으로 다시 게시한다 |
| `ReleaseManifest.adapters[role]` | `system_prompt`(필수) 추가 |
| `DatasetManifest.files[].role` PARSER/GENERATOR | LORA_A/LORA_B |
| `FailureCase.expected_kind` PARSER/GENERATOR | LORA_A/LORA_B |
| `POST .../parse`, `.../generate` | `POST .../extract`, `.../respond` |
| `SlotRef` 문자열 `<문항>.<칸>` | 변경 없음(`ChangeClassification`). 모델 키는 술 칸에 `[종류]`가 붙는 별도 문법 |

### 알려진 한계
- `DatasetManifest.turn_engine_version`·`generator_version` 필수 필드는 그대로 남아 있다(`V2_DRAFT.md` 10장).
- `METRICS.md`는 v1 출력을 가정한 채 남아 있다(제안 문서, 계약은 영향 없음).
