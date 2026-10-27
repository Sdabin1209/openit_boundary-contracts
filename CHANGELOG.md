# 변경 이력

버전은 `pyproject.toml`의 패키지 버전이고 MAJOR.MINOR는 `pipeline_schema_version`과 같다.

## main (v2.0.2 태그 이후, 미태그, 문서만)

스키마와 패키지 코드는 바뀌지 않았다. 아래는 `PUBLIC_API.md`·`CONVENTIONS.md`·`HTTP.md`의 문서 정정과 하위 호환 추가다. 새 태그는 내지 않았다(패키지 내용이 같아서). 의존 영역은 `v2.0.2`를 그대로 쓴다.

- `PUBLIC_API.md`: 상태 값 의미(B절), 409 `CONFLICT`에 `details.reason: TURN_IN_PROGRESS`와 `Retry-After`(처리 중인 같은 `turn_id`, D86), 직원 알림 SSE의 `heartbeat`·`resync` 이벤트(D87, 하위 호환), 알림 스트림 설명.
- `CONVENTIONS.md`: 401/403, 429, 재시도 의미(`details.reason`), gateway의 `UPSTREAM_UNAVAILABLE`, 토큰을 파일로 받는다는 서술(D84와 일치시킴).
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
