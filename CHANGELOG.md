# 변경 이력

버전은 `pyproject.toml`의 패키지 버전이고 MAJOR.MINOR는 `pipeline_schema_version`과 같다.

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
