# 변경 이력


## 5.0.0 (2026-11-08, MAJOR: ID 타입 통일·계약 JSON 공통 규칙·envelope_id 정본 함수·사람 입구 입력 상한 — 병행 기간 없음, CONVENTIONS 1.4 기록)
왜 MAJOR 인가: 패턴·상한·수 규칙이 좁아져 4.x 에서 통과하던 값 일부를 거부한다(아래 '거부하게 된 값'). 4.0.0 과 같이 병행 기간 없이 모든 영역이 함께 올린다. `PIPELINE_SCHEMA_VERSION` 은 "5.0".

- **ID 타입 통일(결함 대장 #22, D117 '같은 뜻의 타입은 한 번만').** 같은 이름의 ID 칸 19개가 서로 다른 정의를 갖고 있었다(session_id 6종, turn_id 64자 대 128자 등). 계약 칸은 모두 공통 타입을 참조한다.
  - `_common.$defs.SessionId` 신설: 4.x 공개 형식 `[A-Za-z0-9_-]{1,64}` 와 `Id` 의 **교집합**(첫 글자 영문·숫자, 이후 영문·숫자·`_`·`-`, 1~64자). `.`·`:` 로 넓히지 않았다. 공개 입구(PublicApiRequests)·HttpWire.SessionId·StaffAlert·SessionState·StaffPushPayload·ResultReadyEvent·TraceEnvelope·IngestResult 의 session_id 가 참조한다. SessionId 값은 Id 이므로 `envelope_id` 가 바꾸지 않는다(봉투 session_id 칸도 SessionId).
  - `_common.$defs.QuestionId` 신설(`^Q[0-9]+(\.D[0-9]{2})?(_[0-9]+)?$`): ActionExtractionInput·ResponseRequest(START 의 then 가지 포함)·SignalsResponse 가 참조한다.
  - turn_id·question_set_id·release_id·submission_id·decision_id·approval_id·alert_id·request_id·to_release_id·source_release_id 의 사본(인라인 패턴·`minLength 1`·`type string`)을 `Id` 참조로. null 허용 칸은 `anyOf [null, Id]`. HttpWire.Id 는 `_common.Id` 별칭. AuthoringResponses 의 flag_id 사본 셋과 요청 쪽 사본을 `$defs.FlagId` 하나로, BackupJobResult.snapshot_id 사본 둘을 `$defs.SnapshotId` 하나로.
  - 점검 `tools/check_id_defs.py`(verify.py 가 부른다). 범위는 이름이 `_id` 로 끝나거나 `id` 인 칸뿐이다(version·커서 등 이름이 다른 의미상 ID 는 범위 밖). 같은 이름 칸이 다른 정의(끝점 + 경로 위 좁히기 전파)에 닿거나, 인라인 정의가 두 곳 이상이거나, then/else 가지에서 다른 정의를 쓰면 실패. `id` 칸은 위치별 뜻·끝점 목록(id_registry)과 대조. 허용 목록 `tools/id_defs_allowlist.json` 은 생성물(비식별 뷰)을 파일 통째가 아니라 파일·이름·끝점 종류 단위로 면제하고, 항목마다 근거가 필수이며 쓰이지 않는 항목은 실패다.
- **계약 JSON 공통 규칙(CONVENTIONS 10절 첫 항목, I-JSON RFC 7493).** 정본 `boundary_contracts.strict_json`(`loads`·`dumps`·`check_json_value`)과 `boundary_contracts.validate(name, value)`. NaN·Infinity·배정밀도 오버플로(1e999)·±2^53 밖 정수·중복 키·짝 없는 서로게이트 거부, 깊이 64(루트=1, 근거 link 0.3.0 max_json_depth), 본문 1 MiB·값 2^19(근거 link DEFAULT_MAX_BODY). `validator` 의 number·integer 는 무한대·NaN 을 받지 않는다. `canonicalize` 는 깊이 64 를 넘으면 RecursionError 대신 ValueError.
- **envelope_id 정본 함수(결함 대장 #18).** CONVENTIONS 116행 규칙의 구현 `boundary_contracts.envelope_id`·`is_id` 와 적합성 벡터 `conformance/vectors/envelope_id.json`(12건, 기대값은 SHA-256 을 실행해 만든 값). 영역은 자기 사본을 지운다.
- **사람 입구 입력 상한(결함 대장 #10).** 알림 커서·SSE Last-Event-ID·실패 사례 version 18자리(BIGINT 에 항상 들어가는 자릿수, Results.cursor 선례). 결정 조회 version 128자. 자료 filename 255(설계 상한, 코드 포인트; 저장소는 파일 이름을 경로로 쓰지 않는다). 푸시 endpoint 는 경로 ASCII 표시 문자 + format uri(RFC 3986 문법, rfc3986-validator). topics 최대 2. flag_ids·edits 5000(question-authoring MAX_FLAGS, 설계 상한). 사유(AddReviewRequest·DiscardRequest·ApprovalRequest·RollbackRequest.reason) 2000자, 롤백 evidence_refs 100, 제출 question_sets 100(설계 상한, 측정 안 함). 공백만인 폐기 사유 거부. signals review_status 는 ops-feedback Cases.review_status 열거. RollbackRequest.requested_by_role 은 GateExt 타입(역할≠토큰 403 은 INTERFACES 96행).
- **실패 사례 검토 값(CaseReviewRequest.expected·reviewed_input).** ops-feedback 코드에만 있던 거부를 계약으로: 공개 검사 `boundary_contracts.review_input.review_value_problems`(문자열 20,000자, 이메일·전화·주민번호 패턴, 규칙 data/review_input_rules.json)와 INTERFACES I7 의 원문 포함 판정 기준. ActionExtraction targets·values·key 의 개수·길이 도메인 상한은 넣지 않았다: 정본 labels(reference/openit-server/scripts/labels.py)에 숫자 상한이 없고 값이 문항 은행의 칸에서만 나온다는 구조적 상한뿐이다. 사람 입구 경로에서는 공통 JSON 규칙(1 MiB·깊이 64)과 위 검사가 묶는다.
- **거부하게 된 값.** 첫 글자 `_`·`-` 인 세션 ID(4.x 공개 형식은 통과), 65~128자이거나 `.`·`:` 가 들어간 세션 ID(4.x 의 ResultReadyEvent·TraceEnvelope·IngestResult 는 Id 라 통과) / 공백·비ASCII 가 섞인 alert_id·submission_id·source_release_id 등 ID / Q 패턴이 아닌 START 첫 문항 ID / 19자리 이상 커서·Last-Event-ID·사례 version / 비ASCII 또는 URI 문법을 어기는 푸시 endpoint / 256자 이상 자료 파일 이름, 2001자 이상 사유, 공백만인 폐기 사유 / 알 수 없는 signals review_status / 첫 글자가 영문이 아닌 requested_by_role / NaN·Infinity·1e999·±2^53 밖 정수·깊이 65 이상·1 MiB 초과 JSON. 넓어진 것: 직원 호출 재시도·보고의 turn_id 상한 64→128.
- **이전(헤드 결정 2026-11-08).** 5.0.0 은 운영 배포 전이므로 **새 환경을 전제한다: 4.x 저장 데이터(survey outbox·세션, ops-feedback 실패 사례, release-gate 제출·결정·활성 포인터, 모델 패키지·데이터셋 매니페스트)는 이전하지 않는다.** 4.x 데이터가 남은 환경에서 기동하면 조용히 섞이지 않고 실패해야 한다: 영역 사이 응답의 `pipeline_schema_version` MAJOR 가 4 이면 받는 쪽은 `UNSUPPORTED_VERSION`(HTTP.md 15행), 자기 저장소의 4.x 레코드를 읽은 영역은 그 레코드를 계약 스키마로 다시 내보낼 수 없으므로 준비(`/readyz`) 실패나 잡 실패로 드러낸다(영역 영향 목록). 모든 영역: 계약 태그 v5.0.0 으로 올리고 잠금 갱신, 생성 타입 재생성. survey-service: 자체 envelope_id 삭제·문진 스키마 MAJOR(survey-schema 5.x)로 계약 타입에 위임. ops-feedback: 계약 envelope_id·review_input·strict_json 사용. link: _strict_json 을 계약 strict_json 으로(같은 값). 상세 영향표는 헤드 기록.

## 4.0.5 (2026-11-08, PATCH: 문서·openapi 서술 빈칸, DeviceConfig.subject_ref 제거·SURVEY_MODEL_BACKEND enum 으로 받던 값 일부를 거부 — 비호환 범위는 아래 각 항목)
- openapi: model-serving extract·respond 200 응답에 `X-Openit-Outcome`(필수, extract 는 ok, respond 는 ok|fallback)·`X-Openit-Attempts`(양의 정수)·`X-Openit-Protections`(선택, 코드 문법은 SDK 와 같다)를 선언했다(HTTP.md I9 에만 있었다). 모든 서비스의 409·429·503 응답에 선택 헤더 `Retry-After`(delta-seconds)를 선언했다(PUBLIC_API 오류 표에만 있었다).
- DeviceConfig.subject_ref 를 없앴다: `/config.json` 은 기기마다 같은 정적 파일이고 공개 입구에서 인증 없이 읽혀 환자 참조가 노출될 수 있었다(교차검토 지적). 환자 참조는 시작 URL 조각(KioskStartFragment)으로만 넘긴다. **비호환 범위:** DeviceConfig 는 additionalProperties:false 라 `subject_ref` 가 든 기존 `/config.json` 은 이제 계약 위반이다. deploy 설정·데모는 이 키를 쓰지 않는다. deploy 시험 1건(scripts/test_config_contract_gate.py)은 위반 기대값을 고쳐야 한다. 이행: 기기 설정에서 `subject_ref` 를 지우고 환자 참조는 시작 URL 조각 `#subject_ref=` 로 넘긴다. 소비자 kiosk-frontend 는 config 의 subject_ref 읽기를 지운다.
- SurveyServiceEnv.SURVEY_MODEL_BACKEND 를 `enum ["fake"]` 로 좁혔다(설명은 내장 이름만이라 했으나 스키마는 임의 문자열을 받았다; 구현 link_inference.py KNOWN_BACKENDS 와 일치). **비호환 범위:** 'fake' 밖의 값(옛 '모듈:함수')을 거부한다. deploy·영역 운영 설정은 이 값을 쓰지 않는다(survey 스모크는 fake).
- PUBLIC_API 프론트 규칙: TLS 핸드셰이크 거부를 '재시도 없음'이라 했던 것을 R3.13·R3.15·MATRIX-CELLS C15 와 맞춰 네트워크 오류와 같은 재시도로 고쳤다(브라우저는 원인을 구분하지 못한다).
- 문서: RUNTIME R3.23·CONVENTIONS 13절의 없어진 `machine-token` 서술과 R3.23 의 "기기 토큰 경로는 Bearer", CONVENTIONS 13절의 INGRESS_DEVICE_TOKENS_DIR, PUBLIC_API 의 폐지된 `skipped`(→ `skipped_details`), CONVENTIONS 10절의 `ext."synthetic-data".dataset_digest`(ext 는 만드는 영역 소유라 계약이 선언하지 않음)를 바로잡았다. 문서 토큰 전수 분류(506건)에서 나온 계약 쪽 결함이다.
- 계약 리포 md 12개 전부(토큰 6489개)를 다시 분류한 2차 검증의 지적: SurveyServiceEnv.SURVEY_MODEL_BACKEND 설명의 없앤 '모듈:함수' 팩토리, KioskStartFragment 설명의 낡은 경로와 우선순위, RUNTIME-MATRIX-CELLS 의 정본 열 정의("갱신(정본)" 열만 정본, 인용 열은 대조 시점 기록), README 의 스키마 개수 복사와 낡은 미정 항목·U14 상태, V2_DRAFT 상태 줄(2.0.2 시점 기록), R3.23 의 닫히지 않은 괄호.

## 4.0.4 (2026-11-08, PATCH: 계약 확정 — 전수 감사의 계약 쪽 항목)
- PUBLIC_API F절: 게이트웨이→survey-service 구간의 서비스 토큰(키오스크 경로 포함)이 필수임을 명시했다. 4.0.0 의 "범위 밖이며 그대로" 문구 때문에 deploy 가 키오스크 경로의 서비스 토큰을 빼는 것과 서비스가 그 토큰을 요구하는 것이 둘 다 계약을 따른다고 읽혔다(감사 1번).
- 알림 SSE 쿼리 `topics`를 없앴다(`HttpQueries.$defs.Stream`, openapi 매개변수). 받는 쪽도 보내는 쪽도 쓰지 않았고, 이벤트는 역할로 거른다는 실제 규칙을 PUBLIC_API 에 적었다.
- `StaffAlert.kind` 알려진 값과 PUBLIC_API D절 문구(kind = RISK_STOP, severity 는 별도)를 맞췄다.
- 정상 흐름 전수 대조(독립 검토)의 계약 쪽 지적 반영: D절 알림 kind·pause_reason 규칙(RISK→RISK_STOP/RISK, CALL_STAFF→CALL_STAFF/OTHER), F절 서비스 토큰 읽는 방법(SURVEY_API_TOKEN_ENV), 세션 상태 확인 시점(응답만으로 확정할 수 없으면 GET /state), 세션 종료 멱등, SessionStartBody.subject_ref 는 문자열만(null 제거, FrontendMessage 와 일치), Exposure upstream_token·user_header 의미(같은 경로 중복 선언 규칙, set 은 User·Roles 둘 다), 기기 토큰 폐지 뒤 남은 문구(HTTP.md·PUBLIC_API 8(session_id)·40·60·124행, clients·conformance 문구, SurveyReadyz 예시의 기기별 토큰 권고), SSE id 순번 규칙, SurveyServiceEnv 의 I6 표기, BoundaryError.details 의 reason·http_status·attempts 문서화, HTTP.md 의 없는 SDK 메서드 표기, /readyz 전달기 문구.
- 개발 환경 설치(scripts/setup-env.sh)의 문진 스키마 고정이 survey-schema-v4.1.1 로 낡아 있었다: survey-schema-v4.1.4 로 맞췄다.

## 4.0.3 (2026-11-08, PATCH: 읽기 모드 검증기 결함 — 정상 응답 거절)
- `clients` 의 읽기 모드 검증(`_reader`, CONVENTIONS 1절 3항)이 모든 자리의 문자열 열거를 넓혀 `if`·`not`·`oneOf`·`contains` 의 뜻을 바꿨다. ActionExtraction 의 조건 규칙이 늘 참이 되어 정상 FailureCase 를 INTEGRITY_ERROR 로 거절했다(synthetic-data CR-S-003, model-lab 변경 요청).
- 새 구현 `clients/_reader_schema.py`: 불변식 엄격 ⊆ 읽기. 조건 자리(if·not·contains)와 그 안의 `$ref`(같은 문서·다른 계약·문진 스키마)는 엄격 사본으로 평가하고, 넓힌 사본은 포인터 자리를 보존한다. 지원하지 않는 구문(동적 참조, oneOf 안 포인터, 비계층 URI)은 조용히 넘기지 않고 멈추며, 계약·문진 스키마에 없음을 시험이 확인한다. 스키마 변경 없음.

## 4.0.2 (2026-11-08, PATCH: 4.0.1 문구 한정)
- 4.0.1 의 "응답 못 받은 세션은 유휴 만료로 닫힌다"는 `SURVEY_SESSION_IDLE_SECONDS=0`(만료 끔, 허용 값)과 모순이었다. 만료가 켜진 경우로 한정했다. 스키마 변경 없음.

## 4.0.1 (2026-11-08, PATCH: 4.0.0 의미 빈칸 두 곳)
- 4.0.0 에서 제거하기로 예고한 `DELETE /v1/staff/push-subscriptions?endpoint=`의 정의가 openapi 와 PUBLIC_API 에 남아 있었다. 경로 정의와 그것만 쓰던 `HttpQueries.$defs.Endpoint`를 지웠다(4.0.0 의 제거 약속을 완결하는 것이며 새 제거가 아니다). 해지는 `POST /v1/staff/push-subscriptions/unsubscribe`뿐이다.
- 서버 발급 세션 ID(4.0.0)와 "같은 `turn_id` 재전송은 같은 응답" 규칙이 세션 시작에서 충돌했다. 멱등 범위를 `(session_id, turn_id)`로 명시하고 세션 시작은 멱등이 아님을 적었다. `SessionStartBody.turn_id`는 새 세션의 첫 턴 ID로 기록할 뿐이다.

## 4.0.0 (2026-11-07, MAJOR: 계약 전수 검토 수정 — 병행 기간 없음, CONVENTIONS 1.4 기록)

전수 검토(헤드·Codex 교차검증)에서 찾은 결함을 고친다. 허용 범위 축소·필드 삭제·의미 변경이 있어 MAJOR 다. 운영 데이터가 없어 3.x 를 읽는 병행 경로를 두지 않는다(PIPELINE_SCHEMA_VERSION 4.0).
- 기기 인증은 mTLS 하나(D136): DeviceAllowlist 신설, DeviceConfig.device_token·KioskStartFragment.device·INGRESS_DEVICE_TOKENS_DIR·SURVEY_KIOSK_DEVICE_TOKENS(_FILE)·SurveyReadyz.kiosk_tokens.device_tokens 제거, Exposure auth device-token→device, 인증서 없음·목록 밖 403. Exposure auth machine-token 제거(4.0.0 예고).
- 잡 설정의 구현 모듈 경로 factory 제거(D135): _common.HttpClientSettings, SURVEY_STAFF_CONSOLE·RESULT_DISPATCHER·RISK_SOURCE·GATE_I1/I3_FACTORY 제거.
- 세션 ID 는 서버 발급만(SessionStartBody.session_id 제거), GATE_READ_TOKEN·_FILE 제거, GateJobEnv 분리.
- 공통 정의: ServiceUrl(R1.1)·HttpsOrigin·HttpsUrl·TcpPort·BindPort·RelativePath·ImageRef·LoopbackHostPort·FailureType, ArtifactRef·QuestionSetRef·매니페스트 version 은 Id.
- 모든 pattern 의 끝 고정을 $(?![\s\S]) 로(끝 개행 통과 차단), SDK 수기 정규식 \Z, check_ref 는 계약 검증기.
- 비식별 뷰는 생성물(tools/gen_deid_view.py + data/deid_rules.json), Deid 정책은 공개 규칙 안에서만.
- 조건부 규칙을 스키마로: FailureCase·CaseReviewRequest expected_kind, GateDecision PASS 필수 검사, BackupJobResult status↔error·retryable, AddReviewRequest reason, AuthoringResponses 상태별 필수 키.
- 닫음·통일: PushSubscription 본문 하나로, SurveyQuestionBankRead·OpsFeedbackFailureCaseExt·Readyz 안쪽·Synthetic 보고서 안쪽, TraceEnvelope.trace→TurnTrace v1, serving_config→ServingConfig, Env 접두사 오타 거부, 설명 없는 스키마 10개·영문 설명 정리, 빈칸 표지 정리.
- BoundaryError: 빈 message 와 계약 위반 레코드 직렬화 거부.

## 3.6.5 (2026-11-07, PATCH: 토큰 파일 이름 규칙)

- StepCaEnv: 토큰 파일 이름 규칙을 명시한다 — STEP_TOKENS_DIR/<이름>.ott(이름 = STEP_TOKEN_NAMES 항목 = STEP_CERT_NAME). 이름을 파일 이름으로 쓰므로 DnsName·DnsNameList 의 길이 상한을 253 에서 251 바이트로 둔다(POSIX NAME_MAX 255 - '.ott'). 3.6.4 는 253바이트 이름을 허용해 <이름>.ott 가 257바이트가 되어 저장할 수 없었다(2026-11-07 교차검증).

## 3.6.4 (PATCH: complete the gateway failure response contract)

- GatewayErrorResponse combines the 503/504 status, GatewayError body and required Retry-After: 5 header into one machine-verifiable HTTP envelope. Application responses remain unchanged (R2.1).


## 3.6.3 (PATCH: deployment input contract omissions)

- Add SyntheticJobEnv for run/import secret-file paths; reject server-only settings, direct secret values, relative and NUL-containing file paths.
- ContainerInputs job profiles can bind config directory paths by RFC 6901 JSON Pointer, with explicit read/write access and required/optional presence. Service profiles cannot declare job-config bindings.
- Clarify Exposure.auth scope: public entrance policy does not remove a peer route from the receiving area's gateway. Service token validation remains with the receiver (R3.23).

## 3.6.2

- BackupJobEnv 저장소 URI의 기존 유효한 포트 표기(앞의 0, 빈 포트)를 유지한다. 빈 포트는 HTTPS 기본 포트이며, 숫자 포트는 선행 0과 무관하게 1..65535다. 포트 0..65536을 보통/선행 0 표기로 전수 대조한다.

## 3.6.1

- BackupJobEnv의 검증 누락을 수정한다: R9.1에 없는 OPENIT_ 입력 이름, D84에 어긋나는 URL 인증정보, TCP 포트 범위 밖의 저장소 주소, POSIX 경로에 들어갈 수 없는 NUL을 거부한다. URI query/fragment 문법은 유지한다. 같은 기반 계약을 참조하는 백업 Env 9개에도 적용된다.
- 정상 URL과 잘못된 입력을 기반·파생 계약 모두에서 대조한다. 이 수정은 이미 정한 입력 규칙의 검증 결함 수정이며 새 환경 변수나 필수 입력을 추가하지 않는다.

## 3.6.0 (2026-11-06)

- ModelServingEnv.MODEL_RUNTIME_ALLOW_FAKE는 빈 값(비활성)과 1(명시 허용)을 구분한다. vllm 구성에서 compose가 보내는 빈 값은 유효하고, fake/mimic은 여전히 정확히 1이어야 한다. 허용 범위 확장이므로 MINOR를 올렸다.
- 패키지와 PIPELINE_SCHEMA_VERSION의 MAJOR.MINOR를 3.6으로 맞췄다.

## 3.5.1 (2026-11-06)

- 서버 기동 환경과 잡 환경을 분리한다: BackupJobEnv와 영역별 백업/복구 Env, IdentityUsersEnv를 추가했다. 기존 필드의 값 규칙은 $ref로 공유하고 잡이 쓰지 않는 서버 필수 조건은 가져오지 않는다.
- PIPELINE_SCHEMA_VERSION을 패키지의 MAJOR.MINOR인 3.5와 일치시킨다. 3.5.0에서 상수가 3.4에 남아 있었다.
- propertyNames 적합성 시험도 계약 레지스트리를 사용해 참조된 규칙을 검증한다.

## 3.5.0 (2026-11-06)

- 새 계약 `ContainerInputs`(세 번째 계약 = 영역 밖에서 컨테이너에 주입하는 것 전부): 숫자 실행 사용자, 읽는 파일(경로·경로 변수·종류·필수, 시작 프로세스가 연다), 쓰는 경로(유지 여부·쓰는 사용자), 추가 권한, sysctls, 절대 경로 argv 실행 규칙, 역할별(role_env)·잡별 묶음. 이미지 라벨 `io.openit.inputs` 로 싣고 **모든 영역 이미지에 필수**다(ImageLabels.required). 배치 영역은 이 선언과 정확히 같게 주입한다. 왜: 파일 권한·쓰기 경로·실행 사용자·argv 가 문장 규칙뿐이라 두 영역이 각자 해석했고 2026-11-06 E2E 기동 실패가 모두 그 어긋남이었다.
- `CommonEnv.SSL_CERT_FILE` 정의(3.4.4 는 표준 이름이라며 칸을 두지 않아 주입 값 하나가 계약 밖이었다).
- 형식(`format`) 강제: 스키마에 쓴 형식(date-time, uri, email, regex)의 검증기가 없으면 검증기를 만들지 않고 실패한다(jsonschema 는 검증기가 없으면 조용히 건너뛴다). 의존 `jsonschema[format-nongpl]`. 영역 잠금에 rfc3339-validator·rfc3986-validator 가 있어야 한다.
- SDK `require_egress_proxy` 가 따로 들고 있던 규칙을 지우고 `CommonEnv.OPENIT_EGRESS_PROXY` 로 검증한다(루프백 주소의 옥텟·포트 범위를 계약에서 바로잡음).

## 3.4.21

- StepCaEnv의 토큰 이름과 인증서 이름을 같은 DNS 호스트 이름 규칙으로 정의한다. 서비스 이름만 허용하던 계약은 외부 추론 서버 host.docker.internal을 거부했다. 라벨·전체 길이 및 빈 목록·잘못된 구분자·경로·개행 거부를 시험한다.


## 3.4.20 (2026-11-06)

- 3.4.19 결함 수정(영역 시험이 드러냄, 와이어는 합의 문서대로):
  - question-authoring `GET /v1/question-sets/{id}/versions/{version}/reviews`: 목록 공통 규칙(HTTP.md)대로 `cursor`·`limit` 쿼리를 받는다. 3.4.19 는 쿼리를 하나도 정하지 않아 계약 클라이언트의 페이지 읽기를 거부했다.
  - survey-service `POST /v1/results/{session_id}/ack`: 본문은 빈 객체 `{}`다(PUBLIC_API.md 82행, admin-console 이 보내는 값). 3.4.19 는 "본문 없음"으로 정해 실제 확인 요청을 400 으로 거부했다. 새 정의 `PublicApiRequests#/$defs/ResultAckBody`.

## 3.4.19

- 충돌하던 단일 OpenAPI를 서비스별 계약과 catalog로 대체한다. 정의는 코드에서 생성하지 않고 명시적으로 편집하며 head 도구는 구현 경로를 대조한다.
- HTTP 요청·응답·쿼리·행위자·역할 바인딩·매체·오류 상태를 기계 계약으로 선언한다. 공개 API DTO와 목록 항목은 JSON Schema 원본을 참조한다.
- immutable referencing registry로 로컬·설치된 소유자 스키마만 해석한다. 인터넷 및 이웃 작업 폴더 fallback은 없다.
- JSON Schema와 OpenAPI의 최종 공존 정책은 미정이며 이번 변경은 참조 기반 구성이다.


버전은 `pyproject.toml`의 패키지 버전이고 MAJOR.MINOR는 `pipeline_schema_version`과 같다.

## 3.4.18 (2026-11-05)

- 문서(HTTP.md·PUBLIC_API.md)와 클라이언트 함수에만 있던 응답 모양 6개를 계약 스키마로 옮긴다. md 는 정본이 아니다(헤드 OPEN_GAPS G-HTTP-MD-CANONICAL 첫 단계). 와이어 모양은 바뀌지 않는다.
  - `ArtifactRef`: I1 latest 응답. `clients._http.check_ref` 와 같은 규칙이다.
  - `ActivePointerItem`: I4 `GET /v1/active-pointer` 의 `{"item": ActivePointer|null}` 감싸기.
  - `ChangeClassificationItem`: I1 change 의 `{"item": ChangeClassification|null}` 감싸기.
  - `QuestionSetList`: 공개 API `GET /v1/question-sets` 응답.
  - `PushSubscriptionResult`: 푸시 구독 추가(201)와 삭제(200) 응답.
  - `RiskSignalResult`: 위험 신호 응답 `{"alert_id","session_status"}`.

## 미출시 (문서만, 와이어·코드 변경 없음)

- `openapi/openapi.json`(OpenAPI 3.1)을 영역 사이 HTTP 엔드포인트(경로·메서드·요청·응답 스키마 $ref)의 정본으로 둔다. HTTP.md·PUBLIC_API.md 의 표는 설명이다. 만드는 도구는 head/scripts/build-openapi.py 이고, 영역 서버의 실제 경로 선언에서 만든다. md 에만 있는 경로가 0개, 분류되지 않은 응답이 0개일 때만 통과한다. 계약 JSON 스키마가 아닌 응답(바이트, text/plain, SSE, 문진 스키마)은 그 종류를 적는다.
- (3.4.4 에서 RUNTIME.md 를 입출력 형식으로 다시 썼다. 아래 줄은 그 전의 기록이다.)
- `RUNTIME.md` 신설: 중계(게이트웨이·TLS 종단)·배치(서버 분리)·재시작을 거쳐도 CONVENTIONS 9절의 의미가 바뀌지 않는다는 조항(R1~R8)과 실패 경우 표. 배포는 조항마다 구현·정적 점검·단독 시험·E2E 단계를 대응시킨 표를 deploy 리포에 둔다.

## 3.4.17 (PATCH, 와이어 변경 없음 — 영역 이미지는 스스로 서고 deploy 는 환경만 구성한다)
왜: deploy 가 platform step-ca·감시 이미지의 역할을 compose command(이미지 부명령)로 고르고, 이미지 사용자 번호(user)와 상태 확인 명령(healthcheck)을 직접 적었다(구조 규칙 1 위반, 헤드 경계 점검 규칙 8 이 77건 찾음). 역할을 고르는 계약 입력과, 이미지가 HEALTHCHECK·USER 를 갖는다는 조항이 없었다.
- StepCaEnv: STEP_ROLE(serve·root·token·cert), STEP_CERT_NAME, STEP_TOKEN_NAMES, STEP_CERT_GID(기본 10100).
- MonitoringEnv: MONITORING_ROLE(prometheus·alertmanager·blackbox·json·node; 없으면 이미지가 시작 거부, 스키마 필수는 아님 — PATCH 호환).
- 3.4.16 결함 수정: PublicIngressEnv.propertyNames 허용 목록에 INGRESS_ROOT_EXPORT_DIR 이 빠져 있었다(3.4.11 과 같은 종류). 모든 스키마의 properties 가 propertyNames 를 통과하는지 보는 시험을 더했다.
- CONVENTIONS 13절: 영역 이미지는 진입점·HEALTHCHECK·USER 를 갖고 역할은 Env 로 고른다. deploy 는 영역 이미지에 command·entrypoint·healthcheck·user·volumes_from·exec 를 쓰지 않는다.
- 시험 tests/test_image_roles_3417.py.

## 3.4.16 (PATCH, 와이어 변경 없음 — deploy 가 platform 이미지 내부 명령에 기대던 것을 입력·잡으로)
왜: deploy 가 공개 입구 이미지의 부명령(export-root)으로 루트 인증서를 꺼내고, identity 컨테이너 안의 kcadm 과 관리 계정으로 사용자를 만들었다(구조 규칙 1·6 위반). deploy 는 환경을 한 번 구성할 뿐 이미지 안 도구를 부르지 않는다.
- PublicIngressEnv.INGRESS_ROOT_EXPORT_DIR(기본 /etc/openit/root-out): 공개 입구가 루트 인증서를 써 두는 출력 폴더.
- IdentityUsersConfig(신규): identity 이미지의 사용자 등록 잡 설정(JobsDeclaration 의 잡이 config.schema 로 가리킨다).
- 시험 tests/test_ingress_root_users_3416.py.

## 3.4.15 (PATCH, 와이어 변경 없음 — 파일 저장소 주인 영역의 백업 잡 자원)
왜: 파일 저장소(models-data, datasets-data, gateway-data, pki-ca)의 주인 영역이 RUNTIME R10.1·DATA_OWNERSHIP 대로 자기 백업·복구 잡을 낼 자원 이름이 JobsDeclaration.needs 에 없어, deploy 가 대신 볼륨을 복사하고 있었다(계약 위반, 헤드 누락).
- JobsDeclaration.needs: models-data, datasets-data, gateway-data, pki-ca.
- 시험 tests/test_jobs_needs_3415.py.

## 3.4.14 이후 문서 보충(패키지·와이어 변경 없음, 태그 없음)
- CONVENTIONS 13절: 서비스 이름 = 게시 이미지 이름(PublishRequest.service). ops-feedback 서버는 `ops-feedback`.

## 3.4.14 (PATCH, 와이어 변경 없음 — 공개 입구 호스트는 DNS 이름만)
왜: 3.4.13 에서 기본 기기 인증(mTLS)을 필수로 켜자 공개 입구가 Host 와 TLS SNI 일치를 요구했다(RFC 9110 421). SNI 에는 IP 리터럴을 쓸 수 없어(RFC 6066 3절) IP 로 접속하면 421 이다. 계약 GATEWAY_HOSTS 가 IP 를 받아 표준과 어긋났다(platform 담당이 찾음).
- PublicIngressEnv.GATEWAY_HOSTS: IP 리터럴 금지.

## 3.4.13 (PATCH, 와이어 변경 없음 — 키오스크 기본 기기 인증 입력)
왜: platform 담당이 기기 mTLS(PUBLIC_API F절의 기본 기기 인증)를 켜는 입력이 PublicIngressEnv 에 없음을 찾았다. deploy 구성도 이것을 넘기지 않아 기본 기기 인증이 꺼진 채 배치될 수 있었다. 헤드 경계 점검은 'deploy 가 넘기는 것 ⊆ 계약'만 보고 '계약이 요구하는 것 ⊆ deploy 가 넘기는 것'을 보지 않았다(점검 보강).
- PublicIngressEnv.INGRESS_DEVICE_CA_FILE(필수, 기본 /etc/openit/device-ca.pem).

## 3.4.12 (PATCH, 와이어 변경 없음 — 헤드 경계 전수 점검이 찾은 빈칸)
왜: head/scripts/check-boundary-coverage.py(deploy 구성의 서비스마다 이미지·환경·마운트를 계약과 대조)가 StepCaEnv 의 인증서·토큰·상태 폴더와 MonitoringEnv 의 node 역할 폴더가 계약에 없음을 찾았다.
- StepCaEnv: STEP_CERTS_DIR(/certs), STEP_TOKENS_DIR(/tokens), STEP_CA_HOME(/home/step).
- MonitoringEnv: MONITORING_NODE_HOST_ROOT(/host), MONITORING_NODE_TEXTFILE_DIR(/textfile).

## 3.4.11 (PATCH, 와이어 변경 없음 — 3.4.10 결함 수정)
왜: 3.4.10 에서 ImageLabels.properties 에 io.openit.database 를 두면서 propertyNames 허용 목록에는 넣지 않아 DB 이미지 라벨이 거부됐다(release-gate 담당이 찾음, 헤드 결함 — 라벨 검증 시험이 없었다).
- ImageLabels propertyNames 에 database.
- 시험 tests/test_image_labels_3411.py: properties 의 모든 라벨을 propertyNames 가 받는지.

## 3.4.10 (PATCH, 와이어 변경 없음 — deploy 가 넘기는 입력을 계약에, 헤드 누락 수정)
왜: 헤드가 deploy compose 의 환경 변수를 계약 Env 스키마와 대조하니 platform 이미지·사람 인증(Keycloak·oauth2-proxy 내부 설정 41개)·영역 DB 초기화 입력이 계약에 없었다. deploy 가 이웃 영역의 내부 구조를 알고 있었다(구조 규칙 1·6 위반). 오늘 platform 영역·Database per Service(D126·D127)를 정하면서 deploy 쪽 입력을 끝까지 따라가지 않은 헤드 누락.
- 새 스키마: AreaGatewayEnv, PublicIngressEnv, MonitoringEnv, BackupStoreEnv, StepCaEnv, IdentityEnv, IdentityProxyEnv, AreaDatabaseEnv, DatabaseDeclaration.
- ImageLabels 에 `io.openit.database`. PublishRequest.service 에 identity·identity-proxy·identity-db·survey-db·question-authoring-db·ops-feedback-db·release-gate-db.
- 키오스크 기기 토큰은 기기마다 비밀 파일 하나(INGRESS_DEVICE_TOKENS_DIR). 파생 값(공개 입구 호스트 이름 목록, Keycloak·oauth2-proxy 설정, DB 계정·권한)은 받는 이미지가 만든다.
- CONVENTIONS 13절: deploy 입력은 모두 받는 쪽 Env 스키마에.

## 3.4.9 (PATCH, 와이어 변경 없음 — 시험용 문 삭제, 공개 입구 경로 표 규칙 명시)
왜: survey-service 담당이 SurveyServiceEnv 에서 사설 주소 푸시를 허용하는 시험용 설정(R3.18 SSRF 방지 우회)을 찾았다. platform 담당이 공개 입구 생성기에서 영역 상태 경로·같은 공개 경로 충돌을 어떻게 다룰지 물었다(규칙은 CONVENTIONS 2절·HTTP I1 에 있었으나 Exposure 설명과 13절에 없었다).
- `SurveyServiceEnv` 에서 `SURVEY_PUSH_ALLOW_PRIVATE_HOSTS` 삭제(survey-service 코드는 이미 읽지 않음).
- `Exposure` auth `none` 설명, CONVENTIONS 13절: 공개 입구는 denied·machine-token·영역 상태 경로를 내보내지 않고, 같은 공개 경로를 두 영역이 열면 시작하지 않는다.

## 3.4.8 (PATCH, 와이어 변경 없음 — 게시할 수 있는 서비스 이름에 platform 이미지)
왜: 3.4.4 에서 platform 영역을 만들었는데 PublishRequest.service 목록에 platform 이미지 이름이 없어 deploy 가 digest 잠금에 올릴 수 없었다(deploy 담당 CR-publish-platform-images, 헤드 누락).
- `PublishRequest.service` 에 area-gateway·public-ingress·monitoring·backup-store·step-ca.

## 3.4.7 이후 문서 보충(패키지·와이어 변경 없음, 태그 없음)
- RUNTIME R10.11: 정적 화면 서버(kiosk-frontend·admin-console)는 `/metrics` 를 두지 않고 감시는 `/readyz` 탐침으로 본다(kiosk-frontend 담당이 찾은 빈칸).

## 3.4.7 (PATCH, 와이어 변경 없음 — Exposure 경로의 본문 상한·영역 안 상류, machine-token 정정)
왜: platform 담당이 공개 입구·영역 게이트웨이 설정을 Exposure 선언에서 만들려다 찾은 빈칸 3건(헤드 누락): 경로별 본문 상한이 선언에 없었고, 영역 안 컴포넌트가 여럿일 때 상류를 정할 값이 없었고, machine-token 경로의 토큰 대조 주체가 3.4.5 와 스키마 설명이 달랐다.
- `Exposure.routes[].max_body_bytes`(없으면 8MiB), `upstream_port`(선택). R3.5 가 이 값을 가리킨다.
- machine-token: 게이트웨이는 대조하지 않고 공개 입구는 내보내지 않는다(R3.23).
- question-authoring 담당이 찾은 빈칸: `QuestionAuthoringEnv` 에 release-gate(I4) 호출 이름 QA_GATE_URL·QA_GATE_TOKEN_ENV·QA_GATE_TOKEN_FILE·QA_GATE_TOKEN·QA_GATE_TIMEOUT_SECONDS, 저작 API 의 판정 조회(`DecisionsQuery`→`Decisions`)·문진표 버전 목록(`QuestionSetVersionsQuery`→`QuestionSetVersions`). 공통 `BackupJobResult`(백업 잡 마지막 줄, 종료 코드 0·75·1).

## 3.4.6 (PATCH, 와이어 변경 없음 — 데이터 주인 표, ext 쓰기 규칙, 소비자 정정)
왜: 사용자 지시 '여러 영역이 읽고 쓰는 데이터는 누가 갖는가 — 전부 확인'. 전수 확인에서 (1) `ext` 규칙이 남의 레코드에도 덧붙일 수 있는 것처럼 읽혀 '쓰는 영역은 하나'와 부딪혔고, (2) 3.4.4 에 헤드가 넣은 x-consumers 중 admin-console 이 실제로 읽지 않는 스키마 7개가 있었다(설명문만 보고 넣음; admin-console 코드의 호출 경로로 대조).
- DATA_OWNERSHIP.md 신설: 영역 사이 데이터 전부의 주인·쓰기 경로·읽기 경로.
- CONVENTIONS 1절 1항: `ext.<영역>` 은 그 레코드의 주인만 쓴다. 6절에서 DATA_OWNERSHIP.md 를 정본으로.
- 호출 관계를 영역 코드와 대조: model-lab·release-gate 는 I9 HTTP 를 부르지 않는다(라이브러리) → 호출 C40·C42 뺌, RuntimeInfo 소비자 정정. model-lab·question-authoring 은 후보를 제출하지 않는다 → 제출 역할·생산자에서 뺌(최소 권한). model-lab·question-authoring 의 I4 판정 조회는 브리프에 있는 미구현 기능이라 남기고 소비자는 GateDecision 만(ActivePointer·ReleaseManifest 에서 뺌).
- x-consumers 에서 admin-console 제거: ReviewRecord·ChangeClassification·QuestionAuthoringExt·GateDecision·GateSubmission·EvaluationReport·OpsFeedbackFailureCaseExt.

## 3.4.5 (PATCH, 와이어 변경 없음 — 백업 출력 이름)
왜: 3.4.4 가 데이터베이스를 영역 컴포넌트로 하고 백업을 영역이 platform 백업 저장소로 보내게 했는데, 그 주소·자격을 받을 이름이 계약에 없었다(ops-feedback 담당이 코드 단계에서 찾음, 헤드 누락).
- CONVENTIONS 6절: "게이트웨이 토큰" = 그 서비스의 Exposure upstream_token 으로 선언된 토큰 전부(3.4.4 의 '역할 이름 gateway' 정정; 서비스마다 토큰 파일 구성이 달라 맞지 않았다, survey-service 담당이 찾음). 관련 문장 HTTP.md I5·PUBLIC_API F절·INTERFACES I5·클라이언트 설명.
- 준비 확인 스키마 `GateReadyz`·`OpsFeedbackReadyz`·`QuestionAuthoringDeployInterface.ReadyzResponse` 가 정본 `not_ready` 도 받는다(3.4.4 가 HealthStatus 에서 정본을 정했는데 영역 스키마가 옛 표기만 허용해 정본을 쓸 수 없었다, ops-feedback 담당이 찾음).
- `CommonEnv`: `OPENIT_BACKUP_URL`·`OPENIT_BACKUP_CREDENTIALS_FILE`·`OPENIT_BACKUP_REPO_PASSWORD_FILE`(선택). RUNTIME R10.1 에 이름·프로토콜(restic REST)·실패 출력.

## 3.4.4 (PATCH, 와이어 변경 없음 — 실행 시 계약을 입출력 형식으로, 영역 사이만; 잡 시간 상한 선언)
왜: RUNTIME.md 가 서술형이었고, 영역 사이 계약 리포에 deploy 영역 안 컴포넌트 사이의 구조(중계 재시작·인증서 갱신·감시 경보·배치 도구·백업)를 적고 있었다(구조 규칙 5·6 위반, 헤드 결함). 잡의 시간 상한·겹침 규칙은 영역 잡과 deploy 스케줄러 사이의 계약인데 deploy 문서에 두라고 적었다(반대 방향 위반).
- `RUNTIME.md`: 0절에 입력(요청·실행 설정·비밀·루트·이름·시각·잡 실행·상황)과 출력(응답·클라이언트 결과·네트워크 오류·스트림·잡 출력·로그·내보내는 파일)을 정의하고, 모든 조항을 입력 → 출력 행으로 다시 썼다. deploy 내부만 정하던 R2.3·R4.2·R4.4·R4.5·R5.2·R5.3·R8.2·R10.7·R10.10 은 폐지(번호 재사용 안 함). R2.1 은 게이트웨이가 더할 수 있는 헤더 목록을 계약 안에 적었다(전에는 deploy 문서를 정본으로 가리켰다). R2.4 는 ping 15초(PUBLIC_API)를 출력으로 적었다. R9.2 는 잡 선언(`JobsDeclaration`)이 잡 입력·시간 상한의 정본이다. 끝 절은 deploy 컴포넌트 목록 대신 영역 일반의 대응 의무.
- `RUNTIME-MATRIX.md`: 호출 목록에서 deploy 내부 호출 C25·C26·C28·C31·C32·C35 를 뺐다(번호 재사용 안 함).
- 모든 스키마(94개)에 최상위 `x-producers`·`x-consumers`(누구의 출력·누구의 입력). 시험 `test_schema_owners_344.py`(빠짐·모르는 이름 거부, 변이 확인 2건).
- CONVENTIONS 13절: 영역 게이트웨이(영역의 모든 입출력은 그 게이트웨이를 지남), 유일한 예외(deploy 의 배포 때 환경 설정·빌드·게시·컨테이너를 언제 어떤 명령으로 띄우는가), platform 영역(공개 입구·사람 인증·인증서 발급·DB 서버·감시·백업), 공유 DB 통합 금지, 계약의 주인 칸.
- 새 스키마 `HealthStatus`(R5.1, OPEN_GAPS U101 닫음): 모든 /healthz·/readyz 본문의 공통 최소 모양. 영역마다 달랐던 '아님' 표기('not ready'·'not-ready')를 정본 `not_ready` 로 정하고 옛 표기는 같은 뜻으로 받는다(생산자는 옮긴다). 시험 test_health_status_344.py(영역 준비 확인 예시 전부가 공통 모양도 통과).
- RUNTIME 행마다 "출력하는 쪽 → 받는 쪽" 칸. 중계 표현을 영역 게이트웨이·platform 공개 입구로.
- 호출 × 실패 칸 810개 확정(RUNTIME-MATRIX-CELLS.md). 열린 칸을 닫는 계약 행: RUNTIME R3.19~R3.27(R3.22 는 R3.10 에 합침)·R9.3·R10.13 신설, R1.5·R1.6·R3.3·R3.10·R3.12·R3.13·R3.17·R3.18·R4.6·R9.2·R10.2·R10.3(10초, 코드·사슬과 같게)·R10.4·R10.6·R10.11 보충, 게이트웨이 `Retry-After: 5`. CONVENTIONS 3절 CONFLICT·4절 동시 도착·I6 중복 예외·6절 승인 대기·9절 기계 호출 헤더와 클라이언트 Retry-After 문장 정정·시간 사슬 56초 행. HTTP.md I5 activate 멱등·롤백 REJECTED 200·approver_id 400, I6 중복, I9 401. PUBLIC_API 키오스크 408·413, 결과 resync·updated_after 뜻.
- 영역 게이트웨이의 나가는 쪽(CONVENTIONS 13절, RUNTIME R1.8·IN-EGRESS): 공통 환경 변수 `OPENIT_EGRESS_PROXY`, 클라이언트 `egress_proxy` 인자·`egress_proxy_from(environ)`·`require_egress_proxy`(loopback http 만). 표준 HTTP CONNECT 터널(RFC 9110 9.3.6), TLS 는 끝까지. 시험 test_egress_proxy_344.py(CONNECT 대상 기록·거절·미도달·형식, 변이 확인).
- 독립 검토 A(34건)·B(28건) 반영(/tmp 검토 원문의 번호를 각 문장에 적음):
  - 새 스키마: `ResultReadyEvent`·`HeartbeatEvent`·`ResyncEvent`(SSE `data:`), `PushSubscriptionRequest`(endpoint SSRF 방지), `HumanAuthEndpoints`·`HumanUserInfo`(platform 로그인 경로·userinfo), `CommonEnv`(`OPENIT_EGRESS_PROXY`), `GatewayError`(`UPSTREAM_UNAVAILABLE`). `EXTERNAL_SCHEMAS.json`: 정본이 문진 스키마인 영역 사이 스키마 6개와 주인(헤드 cross-area-check 가 존재 대조).
  - 결정: 데이터베이스는 영역의 컴포넌트(Database per Service, CONVENTIONS 13절, R10.1; 호출 C24 를 영역 사이 표에서 뺌). 영역 게이트웨이 출구 거절은 `PERMISSION_DENIED`/`EGRESS_DENIED`(클라이언트 수정). 서비스 토큰의 401·403 은 받는 서비스가 낸다. 사람 신원 헤더는 `gateway` 역할 토큰 요청에서만 믿는다. 모든 401 에 `WWW-Authenticate`. R10.8 은 내용이 다르면 409.
  - 출력이 없던 입력: 활성 릴리스 없음 503 `NO_ACTIVE_RELEASE`, 배치 문진표가 목록에 없음, 제출 해시 422·구조 `REJECTED_AUTO`, `lineage.question_sets` 없으면 FAIL, 키오스크의 NOT_COMMITTED·4xx 화면 동작, SSE 역할 필터·최대 수명(`SURVEY_SSE_MAX_SECONDS`)·상태 확인 탐침, 추론 서버 404 재적재, 비 /v1 미인증 401.
  - 낡은 문장 정정: INTERFACES I4·I5·I8·I10, PUBLIC_API 인증·폐기 예정·REASK_LIMIT·"아직 정하지 않은 것", HTTP.md 저작 API 지위·I1 목록 경로·approver_id·(ADR 0010 R7), CONVENTIONS 6·9·10절·시간 사슬(56초 행 서버 마감 50초, 이웃 호출 10초 행, 근거 표기), 3.3.0 MAJOR 예외 기록, RFC 9110 9.2.2 인용 정정, CELLS 의 R10.3 인용·감시/스케줄러 표기·머리 주석.
  - 호출 표: C30 인증 없음, C34 정의, C37~C42 추가(칸 162개는 같은 인터페이스·같은 호출자 종류의 기존 칸에서 옮김).
- 전수 대조(945칸, 2026-11-04 05:00, P1~P6) 결함 반영: 저장소 실패는 R3.10(턴의 NOT_COMMITTED 는 마감·모델 실패만), SSE 끊김은 R3.25 밖, deploy 예외에 OUT-FILE, 출구 허용 목록 정본은 `Exposure.egress`, `gateway` 역할은 `*_TOKENS` 안, 승인자 식별은 gateway 토큰 + `X-Openit-Roles`, I9 소비자 범위(model-lab·release-gate 는 info·readyz), 중복 제출 202·활성화 멱등, 웹 푸시 시간 한도 3초·재시도 3번/60초·endpoint IP 리터럴 거부(RFC 6890), `/metrics` 수집 실패 출력, 쿠키 401 챌린지 근거, machine-token 대조는 받는 서비스, 처음 적재 때 기기 인증서 거절, R3.12 범위, SSE 탐침 경로, tar 스트림 상한을 형식에서 계산(클라이언트 `tar_stream_cap`, 시험·변이 확인), `HumanUserInfo.groups` 관대 읽기, `ResultReadyEvent` 소비자, EXTERNAL_SCHEMAS 에 InterventionDecision·RiskSignal, `lineage` 재게시, JobsDeclaration 기본 상한 문장.
- 클라이언트 `extract_tar`: 호출자 쪽 쓰기 실패(OSError)는 `UNAVAILABLE`(전에는 `INTEGRITY_ERROR` 로 재시도를 막았다, R3.27). 시험 test_extract_tar_disk_344.py(변이 확인).
- `JobsDeclaration.job.timeout_seconds`(선택, 정수 ≥ 1): 잡 한 번 실행의 시간 상한. 선택인 이유는 기존 선언과의 하위 호환. 3.4.2 의 Env 선택 필드처럼 레코드 와이어가 아니라 선언이라 PATCH.

## 3.4.3 (PATCH, 와이어 변경 없음 — 정적 서버 바인드 주소, 예시 정정, U99)
왜: 3.4.2 에서 세 서버만 보고 정적 서버(kiosk-frontend·admin-console)의 바인드 방식을 확인하지 않았다(헤드 누락). 둘 다 모든 인터페이스에 고정으로 붙었다.
- `KioskFrontendEnv.KIOSK_HOST`(선택, 기본 0.0.0.0). 새 `AdminConsoleEnv`(`ADMIN_HOST`, 선택, 기본 0.0.0.0). 배포는 사이드카 뒤에서 127.0.0.1.
- 예시 `ActionExtractionRules.json` 에 `next_item.derived_by: "server"`(3.1.3 에서 필수가 됐는데 예시가 낡아 verify 가 실패하고 있었다).

## 3.4.2 (PATCH, 와이어 변경 없음 — 서버 바인드 주소 설정, U99)
왜: TLS 사이드카가 앱과 같은 네트워크 공간에서 HTTPS 를 끝내도, 앱이 0.0.0.0 에 고정으로 붙으면 같은 망의 다른 컨테이너가 앱 포트로 평문 접속할 수 있었다. 표준 사이드카 구성은 앱이 loopback 에만 붙는 것이다. QA_HOST·MODEL_RUNTIME_HOST·MODEL_REGISTRY_HOST·DATASET_STORE_HOST 는 이미 있었고 세 서버만 없었다.
- `SurveyServiceEnv.SURVEY_HOST`, `GateEnv.GATE_HOST`, `OpsFeedbackServerEnv.env.OPS_HOST`(선택, 기본 `0.0.0.0`). 배포는 사이드카 뒤에서 `127.0.0.1` 을 준다.

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
(3.4.4 기록: 이 판은 필수 필드 추가·필드 삭제를 포함해 CONVENTIONS 1절 2항으로는 MAJOR 였다. 데모 단계라 MINOR 로 냈고 병행 기간 없이 3.2.x 레코드를 읽지 않는다 — CONVENTIONS 1절 4항 예외에 적었다.)
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
