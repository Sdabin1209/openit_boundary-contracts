# 계약 2.0.0: 학습 데이터셋 v2의 LoRA-A/LoRA-B 입출력 (D74)

상태: **2.0.0 반영 완료(D75 반영 포함), 헤드 검토 대기**(브랜치 `contracts-v2-draft`). 헤드가 검토하기 전에는 main에 합치지 않고 태그를 붙이지 않고 push하지 않는다. 아래 1~9장은 초안 때 작성한 근거 기록이고(확인한 데이터, 문서와 데이터의 차이, 영향 분석), 0장이 헤드의 결정과 그 반영 결과, 10장이 열린 항목이다. 변경 목록과 v1에서 옮기는 방법은 `CHANGELOG.md`.

## 0. 헤드의 결정과 반영 결과

| 결정 | 반영 |
|---|---|
| 계약을 **2.0.0(MAJOR)**으로 올린다. v1 형식은 병행 없이 폐기한다(v1.3.3은 태그로 남는다) | `pyproject.toml` 2.0.0, `PIPELINE_SCHEMA_VERSION` "2.0", 모든 예시 2.0. 클라이언트는 MAJOR 1 레코드를 `UNSUPPORTED_VERSION`으로 거부(시험). CONVENTIONS 1-4에 병행 예외를 적음 |
| 스키마 이름은 `ActionExtraction` 계열을 유지한다 | 4장의 이름 그대로 |
| B 응답은 학습한 형식 그대로 텍스트(`text/plain`)이고 대체 응답 여부는 `X-Openit-Outcome`로 알린다 | HTTP.md I9의 `respond`. 클라이언트 `HttpModelRuntime.respond` |
| 새 reason 4종, 괄호 없는 술 키, 부분 선채움 문항으로의 NEXT는 계약으로 인정한다 | `ActionExtraction` 스키마의 설명에 명시하고 시험 추가 |
| `ParserSample`, `GeneratorSample` 삭제 | 스키마·예시 삭제, 시험으로 부재를 확인 |
| I8(turn-engine) 폐기 | rc1에서는 폐기 표시. D75로 "출력 검증 라이브러리로 대체"가 되었다(10장) |
| I9를 v2로 | `parse`/`generate` -> `extract`/`respond` (HTTP.md, INTERFACES.md I9 라이브러리 절) |
| `FailureCase.expected_kind`, `DatasetManifest` 역할 | 둘 다 `LORA_A`/`LORA_B`(제안: 게이트·릴리스 계열이 이미 쓰는 역할 어휘와 통일). `FailureCase.expected`는 객체 또는 문자열 |
| `SlotRef` 반복 키 규약 충돌 | CONVENTIONS 10절: SlotRef 문자열과 모델 키 문법을 둘로 구분해 적음. `ChangeClassification`은 그대로 |

`PUBLIC_API.md`는 읽었고 영향이 없다(공개 API는 `FrontendInput`, `SessionState` 등 문진 스키마 쪽 타입만 쓰고 모델 입출력을 다루지 않음). `METRICS.md`는 **영향이 있으나 수정하지 않았다**: `LORA_A 파서 (UtteranceParserOutput)`, `LORA_B 생성기 (ResponseGeneratorOutput)` 절의 제목과 지표 정의(`risk_signal_*`, `intent_accuracy`, `is_fallback` 비율 등)가 v1 출력을 가정한다. 지표 이름은 자유 문자열이라 계약은 깨지지 않으며, 문서는 학습 담당자가 검토하는 "제안"이다(10장).

표기: **확인**은 이번 작업에서 파일이나 데이터를 읽어 본 것, **제안**은 초안의 선택, **미정**은 근거가 없거나 결정이 필요한 것.

## 1. 기준 데이터와 읽은 범위

- 확인: 학습 서버(`openit`)를 읽기 전용으로 탐색했다. 읽은 것은 `~/WS/dataset/docs/IO_SPEC.md`, `docs/LABEL_TABLES.md`, `README.md`(4장 포함), `~/taehyeon/data/dataset_10_14/lora_{a,b}_{train,val,test}.jsonl` 6개 전수다. `scripts/labels.py`는 읽지 않았다(문서가 기준 구현이라고 적었을 뿐이다). 서버에는 아무것도 쓰지 않았고 파일을 받지 않았다. JSON 줄을 ssh 표준출력으로 흘려 이 PC에서 집계·검증했다.
- 규모(확인): LoRA-A 3,982 / 549 / 546 = 5,077행, LoRA-B 4,069 / 560 / 558 = 5,187행(START 110행 포함, A는 START 제외).
- 행 형태(확인): `{human_review, messages[system,user,assistant], scenario_id, split}`. `human_review`는 `auto_only` 4,194 / `pending` 883(A). 시스템 프롬프트는 A·B 각각 전 행이 같은 한 가지다(A 1종, B 1종). user 내용은 입력 JSON 문자열, assistant 내용은 A는 출력 JSON 문자열, B는 응답 문장이다.

## 2. 확정한 실제 형태 (데이터가 기준)

### 2.1 LoRA-A 입력 (`ActionExtractionInput`)

| 필드 | 타입 | 필수 | 데이터에서 본 것 |
|---|---|---|---|
| `question_id` | string | 예 | 31개 문항 전부 나옴. 형태 `Q1.D01`, `Q3`, `Q4_1`, `Q10` |
| `current_question` | string | 예 | 모두 문자열 |
| `user_utterance` | string | 예 | 모두 문자열 |
| `state` | object | 예 | 항상 객체. 비어 있는 것 288행, 항목 수 최대 9. 항목은 `{value, status}`만. status는 ANSWERED 9,374 / UNCLEAR 202 / MISSING 182. value는 bool·int·float·str·null |

### 2.2 LoRA-A 출력 (`ActionExtraction`)

| 필드 | 타입 | 필수 | 데이터에서 본 것 |
|---|---|---|---|
| `values[]` | 배열 | 예 | 항목 수 0~4. 0개는 REDIRECT 232행뿐 |
| `values[].key` | string | 예 | `문항.칸` 또는 `문항[종류].칸`. 종류는 soju 568, beer 370, wine 262, spirits 214, makgeolli 118. 같은 행에 중복 key 없음 |
| `values[].value` | bool/숫자/string/null | 예 | 아래 2.4 |
| `values[].precision` | enum | 예 | exact 6,057 / approximate 721 / unspecified 1,298 |
| `values[].status` | enum | 예 | ANSWERED 5,901 / CORRECTION 489 / MISSING 419 / CONFLICT 388 / UNKNOWN 320 / REJECTED 281 / UNCLEAR 278 |
| `values[].save` | bool | 예 | **save = (status가 ANSWERED 또는 CORRECTION)**, 예외 없음 |
| `action` | enum | 예 | NEXT 3,073 / REASK 601 / CORRECT 446 / CONFIRM 333 / REDIRECT 232 / HOLD 225 / SKIP 167 (START 없음) |
| `reason` | enum | NEXT·CORRECT에는 없음 | 아래 2.3 |
| `targets` | string[] | REASK·CONFIRM·HOLD·SKIP만 | 1~4개. **없을 때는 키 자체가 없다**(빈 배열 아님). 모든 target은 같은 행 values의 key |
| `note` | string | OUT_OF_SCHEMA만 | 97행. 다른 곳에는 없음 |
| `next_item` | string | 예 | 문항 ID 또는 `END`(185행) |

값의 null 규칙(확인): status가 MISSING·UNCLEAR·UNKNOWN·REJECTED이면 value는 항상 null, precision은 항상 unspecified. ANSWERED·CORRECTION은 value가 null이 아니다. CONFLICT는 value가 있고 save는 false다. 출력의 키 순서는 사전순(`action, next_item, reason, targets, values`)이다.

### 2.3 action과 reason (A·B 같음)

| action | reason 값(확인, 건수) |
|---|---|
| NEXT, CORRECT, START | 없음 |
| REASK | MISSING 325, OUT_OF_RANGE 64, UNKNOWN_UNIT 61, OTHER_BEVERAGE 45, BEVERAGE_MISSING 44, VAGUE_QUANTITY 36, RANGE_SPANS_OPTIONS 9, COUNT_EXCEEDS_DAYS 7, MISSING_NUMBER 6, UNPARSED_VALUE 2, INVALID_OPTION 2 |
| CONFIRM | CONFLICT_WITH_PREVIOUS 279, CONFLICT_MAX_BELOW_USUAL 53, CONFLICT_DOES_NOT_DRINK 1 |
| HOLD | UNCERTAIN 225 |
| SKIP | REQUEST_SKIP 82, REFUSED 85 |
| REDIRECT | OUT_OF_SCHEMA 97, OFF_TOPIC 70, ASK_PURPOSE 65 |

`next_item`의 규칙(확인): REASK 601/601과 REDIRECT 232/232는 입력 `question_id`와 같다. **CONFIRM은 333건 중 55건만 같고, 나머지는 targets 칸의 문항이다**(정정·충돌 흐름에서 앞 문항을 되짚기 때문). NEXT·CORRECT·HOLD·SKIP은 문항 순서와 건너뛰기 규칙의 다음 문항이다.

### 2.4 칸과 값의 형태 (키 규칙)

- 문항 ID: `Q1.D01`~`Q1.D11`, `Q2.D01`~`Q2.D05`, `Q3`, `Q4`, `Q4_1`, `Q5`, `Q5_1`, `Q6`, `Q6_1`, `Q7`, `Q7_1`, `Q7_2`, `Q8_1`, `Q8_2`, `Q9_1`, `Q9_2`, `Q10`(31개).
- 칸 이름과 값의 형태(확인): `diagnosed`·`on_medication`·`family_history`·`answer`(Q4·Q5·Q6)·`does_not_drink`는 bool(또는 null). `Q3.answer`는 문자열 yes 27 / no 72 / unknown 1. `Q4_1.status`·`Q5_1.status`는 current / former. `Q6_1.use_pattern`은 days_1_2 / days_3_9 / days_10_29 / daily. `Q7.unit`은 week / month / year. `Q7_1`·`Q7_2`의 `unit`은 glass / bottle / can / cc. 숫자 칸(`total_years`, `daily_count`, `years_since_quit`, `Q7.frequency`, `amount`, `days`, `duration_minutes`)은 정수가 대부분이고 소수도 나온다(예: 반년 0.5, 어림값).
- 술 칸은 `Q7_1[soju].amount`처럼 종류가 괄호로 붙는다. **종류를 모르는 경우(BEVERAGE_MISSING) 괄호 없는 `Q7_1.amount`·`Q7_1.unit`(null)이 나온다**(`targets`에 Q7_1 74건, Q7_2 55건).
- `.beverage` 칸은 데이터에 한 번도 없다.

### 2.5 LoRA-B 입력 (`ResponseRequest`)과 출력 (`ResponseText`)

| action | 있는 키(확인, 이 외에는 없음) | next.type |
|---|---|---|
| START (110) | action, topic, next | NEXT (question_id는 Q1.D01) |
| NEXT (3,073), CORRECT (446) | action, topic, user_utterance, known, next | NEXT 또는 END |
| REASK (601) | + reason, ask | SAME |
| CONFIRM (333) | + reason, ask, previous, current. **known은 항상 빈 문자열** | SAME |
| HOLD (225), SKIP (167) | + reason, hold | NEXT 또는 END |
| REDIRECT (232) | + reason. OUT_OF_SCHEMA 97건에는 note | SAME |

- `next`: NEXT·SAME은 `{type, question_id, text}`, END는 `{type}`만(185건).
- `known`은 문자열이고 빈 문자열이 가능하다(REASK 206건, REDIRECT 232, HOLD 225, SKIP 167, CONFIRM 333). NEXT·CORRECT에서는 비어 있지 않다.
- `topic`은 START를 포함해 5,187행 모두 있다.
- 출력은 JSON이 아니라 문자열이다. 길이는 24~122자(전수, 확인).
- CONFLICT_WITH_PREVIOUS 279건의 `ask`는 모두 같은 틀 문장 `이번에 말한 값(current)이 맞는지, 아까 말한 값(previous)이 맞는지`다(괄호 속 영문이 글자 그대로 들어 있다, 확인). 틀 표 설계 때 알아야 한다.

## 3. 문서와 데이터가 다른 곳

| 항목 | 문서 | 데이터(기준) |
|---|---|---|
| B 입력의 `topic`, `current`, `hold` | IO_SPEC 본문 4.1 표에는 없고 머리말에서 "더했다"고만 적음. README 4.5는 있다고 적음 | **세 키 모두 있다**. topic 5,187행(START 포함), current·previous 333행(CONFIRM), hold 392행(HOLD 225 + SKIP 167) |
| reason 값 | IO_SPEC 1장 표에 14종(+START 없음) | **OTHER_BEVERAGE, MISSING_NUMBER, UNPARSED_VALUE, INVALID_OPTION 4종이 더 있다**(REASK, 합 55건). 문서의 14종은 모두 데이터에 있다 |
| BEVERAGE_MISSING의 action | HOLD의 사유로 적힘 | **데이터는 REASK 44건뿐**. HOLD는 UNCERTAIN만 225건 |
| 술 칸 예시 | `Q7_1[whisky].beverage`, `"위스키"`, 단위 `"잔"` | 종류 코드는 `spirits`(위스키 코드 아님), 단위는 `glass`, `.beverage` 칸 없음. 문서 예시는 다른 형식을 쓴 옛 초안이다 |
| 종류 불명 술 칸 | 언급 없음 | 괄호 없는 `Q7_1.amount` 키가 나온다(`targets`에서 129건) |
| CONFIRM의 next_item | "REASK·CONFIRM·REDIRECT는 현재 문항" | CONFIRM은 현재 문항이 아니라 **충돌 대상 칸의 문항**인 경우가 278/333 |
| `targets`가 없는 action | "REASK·CONFIRM·HOLD·SKIP에서" | 일치. 다만 빈 배열이 아니라 **키가 없다** |
| Q10 END 건수 | Q10 NEXT 70, 정정 12, 모름 5, 거절 5 | END 185건 = NEXT 151, CORRECT 18, HOLD 8, SKIP 8. 문서의 수치는 옛 데이터의 것 |
| START B 데이터 | 150~200건 새로 생성 | 이 폴더에는 110건 |
| `note` | OUT_OF_SCHEMA에 넣는다 | 일치(97/97). 다른 reason에는 없음 |
| `current_question` | "인사·되짚기가 붙어 있을 수 있음" | 길이는 모두 150자 미만(확인). 되짚기가 붙은 형태가 얼마나 있는지는 길이만으로 알 수 없어 확인하지 못했다(README 7장은 대부분 문항 은행 질문이라고 적음) |
| 건너뛰기 규칙 | 순서와 6개 규칙 | 일치. 단 **57행**은 같은 말에서 일부 칸이 이미 채워진 문항으로 넘어간다(Q4 예 + `Q4_1.status`=former 등, NEXT인데 next_item이 Q4_1·Q5_1). 이 경우 `next.text`가 받은 내용을 다시 묻는 문제는 impact-d74.md가 이미 적은 미결과 같은 현상으로 보인다(제안: 같은 원인) |

문서에는 있는데 데이터에 없는 필드: 이번 전수 검사에서는 **없었다**(topic·current·hold는 데이터에 있다). 문서 예시 쪽에 있고 데이터에 없는 것은 `.beverage` 칸과 한글 단위 `"잔"`이다.

## 4. 초안 스키마

위치: `boundary_contracts/schemas/`(저장소 루트 `schemas`는 이 디렉터리의 링크). 예시는 `examples/`. 모든 예시는 학습 서버 val 파일의 실제 행에서 뽑았다(환자 말은 합성 데이터).

| 새 스키마 | 무엇 | 대응하는 v1 |
|---|---|---|
| `ActionExtractionInput` | LoRA-A 입력 | `UtteranceParserInput`(문진 스키마) |
| `ActionExtraction` | LoRA-A 출력 | `ParserOutput`(문진 스키마) + 정규화기·판정기·Plan의 일부 |
| `ResponseRequest` | LoRA-B 입력(START 포함) | `ResponseGeneratorInput`(문진 스키마) |
| `ResponseText` | LoRA-B 출력(문자열) | `GeneratorOutput` |
| `ActionExtractionSample` | A 데이터셋 한 줄 | `ParserSample` |
| `ResponseSample` | B 데이터셋 한 줄 | `GeneratorSample` |

이름을 이렇게 정한 이유(제안): CONVENTIONS.md에는 명명 규칙이 따로 없다. 기존 관례는 PascalCase 명사, 모델 입출력은 `<역할>Input`/`<역할>Output`, 데이터셋 줄은 `<역할>Sample`이다. 파서가 이제 추출·정규화·절차 선택까지 하므로 `Parser`라는 이름은 거짓이 되어 `ActionExtraction`(추출+절차)으로 했다. B 입력은 "응답을 요청한다"는 뜻의 `ResponseRequest`, 출력은 값이 문자열이라 `ResponseText`다. 대안: `LoraAInput`·`LoraAOutput`처럼 역할 기반 이름(모델 교체와 무관하게 유지되는 장점, 의미는 약함). 미정.

규칙 요약(`ActionExtraction`, `ResponseRequest`):
- `additionalProperties: false`(쓰기는 엄격). 모델이 내는 JSON이므로 `ext`를 두지 않았다. 샘플 레코드 쪽에는 `ext`가 있다(CONVENTIONS 1-1).
- action별 필수·금지 키와 reason 허용값을 `allOf`/`if/then`으로 적었다. `save`와 `status`의 관계, null 규칙도 같은 방식이다. **HTTP.md I9가 적은 대로 제약 디코딩 엔진이 `if/then`을 무시할 수 있으므로 이 규칙들은 사후 검증(model-runtime)이 맡는다.** 같은 스키마를 프롬프트·디코딩용 평면 스키마로도 써야 하면 `if/then`을 뺀 평면 스키마를 따로 내야 한다(미정).
- 스키마로 표현하지 못해 의미 검사로 둔 것: targets가 values의 key 부분집합, `REASK`·`REDIRECT`의 `next_item`이 입력 `question_id`와 같음, CONFIRM의 `next_item`이 targets 문항, 건너뛰기 순서. `tools/validate_dataset_v2.py`가 이 검사를 한다.
- 샘플 레코드: `pipeline_schema_version`(초안은 `2.0`), `sample_id`, `scenario_id`, `split`, `origin`, `input`, `expected`가 필수. `question_set`, `human_review`, `seed_case_id`(FAILURE_CASE_SEED면 필수), `ext`는 선택. v1의 `runtime_contract_version`, `style_guide_version`, `noise_types`는 뺐다. 학습 서버 데이터에는 이 필드들이 없고(확인), v2에서 어떤 값을 넣을지 정해진 바가 없다(미정).
- 범위 답 저장값, `ask` 문장 틀 표, 칸 설명표는 IO_SPEC 7장에서도 미정이라 스키마에 넣지 않았다. B 입력의 `known`·`ask`·`previous`·`current`·`hold`는 사람 말 문자열이다(문장 틀 표가 정해지면 그 표는 계약 밖 문진 스키마 쪽이다. 제안).

## 5. 검증 결과

- `python3 verify.py`: **통과**(OK 74, FAIL 0, 종료 코드 0). 새 스키마 6개가 모두 Draft 2020-12로 유효하고 예시 19개가 통과한다.
- `python3 tools/verify_v2.py`(새 파일): 거부되어야 할 변형 22개가 모두 거부됨.
- `python3 -m unittest discover -s tests`: 74개 중 **1개 실패**. `tests/test_package.py`가 스키마 수를 24로 고정하고 있어 30이 되며 실패한다. 초안을 더한 데서 오는 예상된 결과다. 기존 시험은 고치지 않았다(병합할 때 기대 개수를 고쳐야 한다. 제안).
- 데이터 전수 검증(`tools/validate_dataset_v2.py`, 서버 파일을 ssh로 흘려 이 PC에서 실행):

| 파일 | 행 | 통과 | 실패 |
|---|---|---|---|
| lora_a_train | 3,982 | 3,982 | 0 |
| lora_a_val | 549 | 549 | 0 |
| lora_a_test | 546 | 546 | 0 |
| lora_b_train | 4,069 | 4,069 | 0 |
| lora_b_val | 560 | 560 | 0 |
| lora_b_test | 558 | 558 | 0 |

  합계 10,264행 중 실패 0. 스키마가 데이터를 보고 만든 것이라 통과는 "스키마가 데이터를 받아들인다"는 뜻이지 "데이터가 옳다"는 뜻이 아니다. 의미 검사도 모두 통과했고, 참고로 센 것은 위 3장의 57행(부분 선채움 문항으로의 NEXT, 실패 아님)뿐이다.
  - 처음에는 7건이 의미 검사에서 걸렸으나 검사 로직의 오류(한 말에 여러 문항 값이 나오면 가장 뒤 문항을 기준으로 해야 함)여서 고쳤다. 데이터 쪽 문제가 아니다.
  - 검증하지 못한 것: A 출력과 B 입력의 짝(A의 next_item = B의 next.question_id)은 두 파일을 짝지어 보지 않았다. 마스터 레코드(`train.jsonl` 등)는 읽지 않았다. 학습 서버의 `human_review`가 `pending`인 883행은 사람 검수 전이다.

## 6. I9(model-runtime) 변경안

현재 HTTP.md I9: `PUT /v1/releases/{id}`로 적재, `parse`(본문 `UtteranceParserInput` → `ParserOutput`), `generate`(`ResponseGeneratorInput` → `GeneratorOutput`), `X-Openit-Outcome/Attempts/Protections` 헤더. 아래는 **제안**이며 HTTP.md·INTERFACES.md는 고치지 않았다.

| 항목 | 제안 |
|---|---|
| A 호출 | `POST /v1/releases/{id}/extract`, 본문 `ActionExtractionInput`, 응답 `ActionExtraction`(JSON). `parse`는 v1 병행 기간 동안 유지 |
| B 호출 | `POST /v1/releases/{id}/respond`, 본문 `ResponseRequest`. 응답 형식은 둘 중 하나를 정해야 한다: (가) `text/plain` 문장 그대로(스트리밍, 데이터 형식과 일치), (나) `{"response_text", "is_fallback"}` JSON(v1 `GeneratorOutput`과 비슷). **미정**. 데이터는 문장 그대로이므로 (가)는 계약과 모델 출력이 일치하고 (나)는 `is_fallback` 표시를 유지한다 |
| 시작(START) | A를 부르지 않고 B만 부른다(D74). `ResponseRequest.action=START`의 입력은 서비스가 만든다 |
| 시스템 프롬프트 | 학습 때 쓴 시스템 프롬프트 한 종(A, B 각각)이 데이터에 박혀 있고 서빙이 같은 문장을 써야 한다(확인: 전 행 동일). 이를 `serving_config`의 프롬프트 템플릿 버전으로 고정할지, 문진 스키마·계약에 문장을 넣을지 **미정** |
| 출력 보호(D36) | v1 보호는 `ParserOutput`의 항목 규칙에 묶여 있다. A가 action과 next_item까지 정하므로 "형식을 못 지키면 빈 목록" 같은 대체 출력이 의미가 없다. 대체 출력(예: REASK/REDIRECT로 현재 문항 유지)은 **미정**이고 survey-service·model-runtime과 정해야 한다 |
| `X-Openit-*` 헤더 | 유지 가능(제안). 보호 규칙 코드(P*, G*)는 새로 정해야 한다 |
| 기반 모델 | 어댑터가 Qwen3 4B/8B/14B 기반이므로 `supported_contract_versions`뿐 아니라 기반 모델 식별이 `/v1/info`에 필요할 수 있다(`ModelPackageManifest.base_model`은 이미 있다, 확인) |

## 7. 영향 분석

### 7.1 v1 계약의 운명 (제안)

| 대상 | 판정 | 이유 |
|---|---|---|
| `ParserSample`, `GeneratorSample` | **폐기 예정**(병행 기간 유지) | input/expected가 문진 스키마의 `UtteranceParserInput`/`ParserOutput` 등을 가리키는데 v2는 이 스키마에서 나온 형식이 아니다. 새 `*Sample`이 대체 |
| `FailureCase.expected_kind`(`PARSER`/`GENERATOR`), `expected`·`reviewed_input` 설명 | **변경**(의미 변경 → MAJOR 요인) | 설명이 `ParserOutput`/`GeneratorOutput`, `UtteranceParserInput`/`ResponseGeneratorInput`을 가리킴. 열거값 추가(MINOR)로 `EXTRACTOR`/`RESPONDER`를 더하고 옛 값을 병행하는 길이 있다 |
| `DatasetManifest`(role `PARSER`/`GENERATOR`, `generator_version`, `runtime_contract_version`) | **변경 후보** | 역할 열거값과 "문진 스키마 정수 `runtime_contract_version`" 의존이 v2 샘플에는 없다 |
| `INTERFACES.md` I8(turn-engine: normalize/judge/write_record/plan) | **폐기 예정** | D74: 정규화기·Plan 코드를 서비스에 두지 않는다. 남는 것(A 출력 검증, 저장 규칙, 건너뛰기 검산)이 turn-engine의 새 함수인지 서비스 코드인지 **미정** |
| `INTERFACES.md` I9, `HTTP.md` I9 | **변경**(위 6장) | parse/generate 입출력과 보호의 의미가 바뀜 |
| `CONVENTIONS.md` 10절의 `SlotRef` 직렬화(반복 키 없음) | **충돌** | v2의 key는 `문항[종류].칸`을 쓴다. SlotRef(구조 타입)와 문자열 키의 대응을 다시 적어야 함. 제안: v2 key는 "모델 키 문법"으로 따로 정의 |
| `EvaluationReport`, `ModelPackageManifest`, `ReleaseManifest`, `GateDecision`, `ActivePointer`, `GateApproval`, `ReviewReport`, `SubmissionView`, `BoundaryError`, `IngestResult`, `RollbackRequest`, `RollbackReceipt`, `ReviewRecord`, `ChangeClassification`, `SessionState`, `StaffAlert`, `StaffAlertPage`, `PushConfig`, `ArtifactRef` 등 | **유지** | 역할 `LORA_A`/`LORA_B`는 그대로 쓸 수 있음(확인: 이 스키마들의 역할 열거값이 `LORA_A`/`LORA_B`). 다만 `EvaluationReport`의 지표 이름은 v2 평가 항목(action 일치율 등)에 맞출지 **미정** |
| `TraceEnvelope` | **유지**(봉투) | 본문 `trace`는 문진 스키마 `TurnTrace`. 단 Trace 키(`normalizer_*`, `judge_*`, `planner_*`)가 바뀌면 `TurnTrace`는 survey-service의 계약 변경이다(확인: `graph.py`에 해당 키 목록) |
| `PUBLIC_API.md`, `METRICS.md` | **유지 추정** | 이번에 읽지 않았다(미확인). 공개 API가 그대로면 영향 없다는 impact-d74.md의 제안과 같다 |

### 7.2 MAJOR 여부 (제안)

**MAJOR(2.0.0)**로 올릴 것을 제안한다. 근거: CONVENTIONS 1-2는 필드 삭제·의미 변경을 MAJOR로 정한다. 새 스키마를 더하는 것만이면 MINOR지만, (1) `ParserSample`/`GeneratorSample` 폐기, (2) I8 폐기, (3) I9 호출의 입출력 교체, (4) `FailureCase`·`DatasetManifest`의 `PARSER`/`GENERATOR` 의미 변경이 함께 들어간다. 1-4는 한 릴리스 주기 동안 v1 읽기 경로를 유지한다. (초안 당시의 서술. 병행 기간 제안은 헤드가 철회했고 0장이 현재 상태다.) 병합과 태그(`v2.0.0`)는 헤드 결정이다.

### 7.3 영역별 영향

| 영역 | 확인한 것 | 제안 / 미정 |
|---|---|---|
| survey-service | `survey_service/graph.py`에 parse·normalize·judge·write_record·plan 노드와 Trace 키 `normalizer_*`·`judge_*`·`record_writer_*`·`planner_*`가 있음. `remote.py`가 `ParserOutput`·`GeneratorOutput`으로 응답을 검증하고 `parse`/`generate`를 부름. `docs/inference-server-spec.md`가 있음(읽지 않음) | 제안: 노드 통합, B 입력 조립(known·ask·previous·current·hold·next.text는 표 찾기), 시작 경로. 미정: A 출력 사후 검증 위치, `ask`·칸 설명 표, 대체 출력 규칙 |
| turn-engine | `ENGINE_VERSION`, normalize/judge/write_record/plan 구성(INTERFACES I8). 본 작업에서 코드는 grep으로 파일 목록만 확인 | 제안: I8 축소 또는 폐기. 미정: A 출력 검증을 어디에 둘지 |
| model-runtime | `schema_guard.py`·`prompts` 관련 파일이 `ParserOutput`/`GeneratorOutput`을 참조함(grep). `docs/change-requests/003-inference-http-api.md`가 I9의 기준 | 제안: extract/respond 경로, 프롬프트를 학습 시스템 프롬프트로 고정, B는 텍스트 출력. 미정: 보호 규칙, 제약 디코딩이 `if/then`을 못 쓰는 문제 |
| model-lab | `model_lab/datasets.py:15`가 `{"PARSER": "ParserSample", "GENERATOR": "GeneratorSample"}`로 샘플을 검증(확인). `transform.py`·`evaluate.py`·`regression.py`가 v1 용어를 씀(grep) | 제안: 샘플 계약 교체, 학습 서버의 `messages` 형식 ↔ `*Sample` 변환기. 미정: 학습 서버 코드와 이 리포의 관계(impact-d74.md 6장과 같음) |
| synthetic-data | `store/base.py:28`, `quality.py:20`이 `ParserSample`/`GeneratorSample`로 줄을 검증(확인). `labeler.py`·`plans.py`는 v1 정규화 용어를 씀(grep) | 제안: 데이터 생성은 학습 서버의 v2 파이프라인이 이미 하고 있어 이 영역의 역할 재정의가 필요. 미정: 이 영역을 유지할지 |
| release-gate | `release_gate/checks.py`·`gate.py`가 model_runtime/평가 보고서를 다룸(grep으로 파일만 확인). 계약 호환 검사가 `runtime_contract_version`에 의존한다고 INTERFACES I4에 적힘 | 미정: v2의 `runtime_contract_version`(문진 스키마 정수)이 무엇을 뜻하는지. 계약 검사와 골든 케이스가 v1 입출력인지 읽지 못함 |
| ops-feedback | `FailureCase.expected_kind`를 쓰는 `review.py`·`api.py`, 비식별 TurnTrace 사본(`_schemas/survey/v1/TurnTrace.json`)이 있음(확인) | 제안: `expected_kind` 열거값 추가. 미정: 실패 유형 분류가 정규화·판정 단계에 묶여 있는지(읽지 않음) |
| deploy | `scripts/e2e_steps.py`가 I9 흐름(`PUT` 적재 → parse → generate)과 `parser_input`을 쓴다(확인). `test/ops-job` 등 | 제안: E2E 단계를 extract/respond로 바꿈, Qwen3 프로파일. 미정: 시험용 가짜 모델의 고정 출력 |

## 8. 결정이 필요한 것

1. 새 스키마 이름(4장), 특히 `ActionExtraction`을 쓸지 역할 기반 이름(`LoraA*`)을 쓸지.
2. B 응답의 HTTP 형식: 문장 그대로(text/plain)냐 JSON이냐(6장).
3. v2에서 `runtime_contract_version`이 가리킬 것. 모델 입출력이 문진 스키마를 떠나므로 이 정수를 누가 소유하는지.
4. 4개 새 reason(OTHER_BEVERAGE, MISSING_NUMBER, UNPARSED_VALUE, INVALID_OPTION)과 괄호 없는 술 키(`Q7_1.amount`)를 정식 계약으로 인정할지, 데이터셋 담당자에게 정리를 요청할지. 초안은 데이터가 기준이라 인정했다.
5. 57행의 "부분 선채움 문항으로의 NEXT"를 계약으로 허용할지.
6. A 출력 사후 검증과 대체 출력 규칙의 소유(turn-engine / model-runtime / survey-service).
7. MAJOR 2.0.0과 병행 기간(7.2).

## 9. 초안에 포함된 파일

- 스키마 6개: `boundary_contracts/schemas/{ActionExtractionInput,ActionExtraction,ResponseRequest,ResponseText,ActionExtractionSample,ResponseSample}.schema.json`
- 예시 19개: `examples/ActionExtraction*.json`, `examples/ResponseRequest*.json`, `examples/ResponseText.json`, `examples/ResponseSample.json` 등
- 도구: `tools/validate_dataset_v2.py`(stdin 또는 파일을 읽어 검증), `tools/verify_v2.py`(거부 시험)
- 이 문서: `V2_DRAFT.md`

## 10. 열린 항목과 D75 결정

D75(사용자 위임, 헤드 결정, `head/docs/DECISIONS.md`)로 정리했다.

| 항목 | 결정 | 반영 |
|---|---|---|
| `extract`가 끝내 깨질 때 | 503 `UNAVAILABLE`, `details.reason=OUTPUT_INVALID` 확정. survey-service는 1회 재시도 후 `turn_failure_signal`, 세션 상태 불변 | HTTP.md I9, INTERFACES.md I9, CONVENTIONS 10절, 참조 서버·클라이언트·시험 |
| `runtime_contract_version` | 의미 유지: 모델 패키지가 학습된 문진 스키마 정수 버전, 소유 survey-service. 필드 유지 | CONVENTIONS 10절, INTERFACES.md I9 |
| A 출력 사후 검증 | 형식은 model-runtime, 의미는 turn-engine 순수 함수(`validate_extraction`)를 survey-service가 호출 | INTERFACES.md I8(대체: 출력 검증 라이브러리). 코드는 turn-engine 영역 |
| 시스템 프롬프트 | 모델 패키지의 일부. `ModelPackageManifest.system_prompt {path, sha256}` | 스키마(필수), 예시, 시험, CHANGELOG. 같은 값을 `ReleaseManifest.adapters[role]`에도 복사(이 작업의 판단) |
| 데이터셋 정리 요청(새 reason 4종, 괄호 없는 술 키, 부분 선채움 NEXT, IO_SPEC과 데이터의 차이) | 데이터셋 담당에게 가는 요청이며 `head/docs/dataset-requests.md`에 있다. 계약은 현재 데이터를 기준으로 인정한다 | 스키마 설명에 명시 |

아직 정해지지 않은 것:
1. `respond`의 대체 문장 규칙과 `X-Openit-Protections`의 규칙 코드(P*, G*)는 model-runtime이 정한다(계약 밖).
2. `DatasetManifest.turn_engine_version`, `generator_version`은 필수 필드로 남아 있다(바꾸면 MAJOR 변경).
3. `if/then`을 뺀 평면 스키마를 제약 디코딩용으로 따로 낼지(엔진이 `allOf`/`if/then`을 무시한다).
4. `METRICS.md`를 v2 평가 항목으로 고칠지(학습 담당자).
5. `TraceEnvelope.trace`(문진 스키마 `TurnTrace`)의 키(`parser_*`, `normalizer_*`, `judge_*`, `planner_*`)는 survey-service의 계약 변경이다.
6. v1 의도 중 v2 출력에 대응이 없는 것(위험 신호, 직원 호출, 안내 요청)을 서비스가 어떻게 다룰지(survey-service).
7. 서버 데이터 재검증: 이번에도 서버에 접속하지 않았다. 데이터가 갱신되면 `tools/validate_dataset_v2.py`로 다시 돌린다.
