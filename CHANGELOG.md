# 변경 이력

버전은 `pyproject.toml`의 패키지 버전이고 MAJOR.MINOR는 `pipeline_schema_version`과 같다.

## 2.0.0 (D74, 검토 대기: 태그는 헤드가 붙인다)

학습 데이터셋 v2에 서비스 구조를 맞춘다. 정규화·절차·다음 문항은 LoRA-A가 내고, 서비스는 표 찾기만 한다. v1 형식은 **병행 없이 폐기**했다(이유: v1 계약은 없어진 단계를 기술하고, 학습된 모델은 v2 형식만 말하며, 운영 데이터가 없는 데모 단계). 이전 형식은 태그 `v1.3.3`으로 남는다. 근거와 열린 항목은 `V2_DRAFT.md`.

### 깨지는 변경 (MAJOR)
- `ParserSample`, `GeneratorSample` 스키마와 예시를 삭제했다.
- `DatasetManifest.files[].role`: `PARSER`/`GENERATOR` -> `LORA_A`/`LORA_B`.
- `FailureCase.expected_kind`: `PARSER`/`GENERATOR` -> `LORA_A`/`LORA_B`. `FailureCase.expected`는 객체 또는 문자열(LORA_B의 정답은 문장).
- `INTERFACES.md` I8(turn-engine: `normalize`, `judge`, `write_record`, `plan`)을 폐기했다.
- `HTTP.md` I9: `parse`/`generate` 경로를 `extract`/`respond`로 바꾸고, 입출력과 출력 검증 규칙을 바꿨다(`respond`의 응답은 JSON이 아니라 `text/plain`).
- `PIPELINE_SCHEMA_VERSION` "1.3" -> "2.0". 클라이언트는 MAJOR 1 레코드를 `UNSUPPORTED_VERSION`으로 거부한다.

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

LoRA-A 입력 (`UtteranceParserInput` -> `ActionExtractionInput`):

| v1 (문진 스키마) | 2.0.0 |
|---|---|
| 현재 문항의 식별자와 문장 | `question_id`, `current_question` (둘 다 필수) |
| 환자 발화 | `user_utterance` |
| 직전까지의 기록 | `state`: `{ "<모델 키>": {"value", "status": ANSWERED\|UNCLEAR\|MISSING} }` (항상 객체, 빈 객체 가능) |

LoRA-A 출력 (`ParserOutput` + 정규화기·판정기·Plan -> `ActionExtraction`):

| v1 | 2.0.0 |
|---|---|
| 파서의 항목 목록(의도, 대상, 값) | `values[]`: `key`, `value`, `precision`(exact\|approximate\|unspecified), `status`(ANSWERED\|CORRECTION\|MISSING\|UNCLEAR\|CONFLICT\|UNKNOWN\|REJECTED), `save` |
| 정규화기가 한 값 변환(단위, 범위) | 모델이 `values[].value`에 정규화된 값으로 낸다. 서비스에 정규화 코드가 없다 |
| 판정기의 저장 여부 | `values[].save` (= status가 ANSWERED 또는 CORRECTION) |
| Plan의 다음 행동 | `action`(NEXT, CORRECT, REASK, CONFIRM, HOLD, SKIP, REDIRECT)과 `reason` (NEXT·CORRECT에는 reason 없음) |
| Plan의 대상 칸 | `targets[]` (REASK·CONFIRM·HOLD·SKIP만, 없으면 키 자체를 뺀다) |
| Plan의 다음 문항 | `next_item` (문항 ID 또는 `END`) |
| 문진표에 없는 말 | `action=REDIRECT`, `reason=OUT_OF_SCHEMA`, `note` |

LoRA-B (`ResponseGeneratorInput`/`GeneratorOutput` -> `ResponseRequest`/`ResponseText`):

| v1 | 2.0.0 |
|---|---|
| 생성기 입력(문장 재료) | `ResponseRequest`: `action`(START 포함), `topic`, `user_utterance`, `known`, `next{type: NEXT\|SAME\|END, question_id, text}`, 그리고 action별로 `reason`, `ask`, `previous`, `current`, `hold`, `note`. 서비스가 A 출력에서 표 찾기로 조립한다 |
| `GeneratorOutput {response_text, is_fallback}` | 응답 문장 그대로의 텍스트. 대체 여부는 응답 헤더 `X-Openit-Outcome: fallback` |
| 시작 인사 | 서비스가 A를 부르지 않고 `action=START`로 B만 부른다 |

데이터셋과 평가:

| v1 | 2.0.0 |
|---|---|
| `ParserSample` (`runtime_contract_version`, `question_set`, `noise_types`가 필수 또는 있음) | `ActionExtractionSample`: `sample_id`, `scenario_id`, `split`, `origin`, `input`, `expected`가 필수. `question_set`, `human_review`, `seed_case_id`, `ext`는 선택 |
| `GeneratorSample` | `ResponseSample` (`expected`는 문자열) |
| `DatasetManifest.files[].role` PARSER/GENERATOR | LORA_A/LORA_B |
| `FailureCase.expected_kind` PARSER/GENERATOR | LORA_A/LORA_B |
| `POST .../parse`, `.../generate` | `POST .../extract`, `.../respond` |
| `SlotRef` 문자열 `<문항>.<칸>` | 변경 없음(`ChangeClassification`). 모델 키는 술 칸에 `[종류]`가 붙는 별도 문법 |

### 알려진 한계
- `extract`가 끝내 깨질 때의 처리(503 `OUTPUT_INVALID`), `runtime_contract_version`의 의미, `DatasetManifest.turn_engine_version`·`generator_version` 필수 필드는 열린 항목이다(`V2_DRAFT.md` 10장).
- `METRICS.md`는 v1 출력을 가정한 채 남아 있다(제안 문서, 계약은 영향 없음).
