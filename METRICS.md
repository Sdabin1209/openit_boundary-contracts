# 평가 지표 카탈로그 v2 (제안, D53 -> D96·D97·D98)

**상태: 제안(v2).** 학습 담당자가 검토해 다듬는다. 이 문서는 `EvaluationReport.metrics[].name`에 쓸 이름과 뜻을 정한다. **합격선(임계치)은 없다.** 출고는 담당자가 보고서를 보고 정한다. 지표를 추가하는 것은 이 문서와 평가 구현만 바꾸면 되고 계약은 바뀌지 않는다(`name`은 자유 문자열, 모르는 이름은 보고서에 그대로 보인다). 근거: 헤드 `docs/metrics-v2-proposal.md`와 DECISIONS D96~D98, 선택의 이유는 `docs/adr/0013`.

> **D96의 기본값은 임시다.** 표시한 `[기본값]`은 학습 담당 확인 전에 헤드가 표준 관행으로 정한 것이며 담당자가 바꾸면 따른다. 기준값(임계치)은 정하지 않는다(O11). 값은 측정한 것이 없다.

**정본은 `boundary_contracts/metrics.json`이다**(`boundary_contracts.metrics()`). 아래 표는 `tools/gen_metrics_md.py`가 거기서 생성하므로 표를 직접 고치지 않는다.

## 읽는 법
- 모든 값은 `value`, 표본 수 `n`, 방향 `higher_is_better`, 부분집합 `slice`(kind/value)를 가진다. `n=0`이면 계산하지 못한 것이다.
- `group=SAFETY`는 승인 보고서 맨 위에 따로 보인다. 현재 활성 릴리스와 같은 지표끼리 비교한다(`baseline`, `delta`). 나빠진 것은 `worse=true`로 표시만 한다.
- **분리 기준(slice kind)**: `ALL`, `QUESTION_SET`(문항 세트 ID), `SEEN_UNSEEN`(학습에 쓴 문항/보지 못한 문항, D32), **`ACTION`**(NEXT, REASK, CORRECT, CONFIRM, REDIRECT, HOLD, SKIP, B는 START·END 포함), **`REASON`**(A 출력의 `reason`), `QUESTION_TYPE`, `UNIT`, `RANGE`, `NOISE`, `SCENARIO`. `INTENT`는 **폐기**(v2에 의도 분류가 없다; v1 보고서에 남아 있어도 읽기만 한다). `EvaluationReport`의 slice `kind`는 열거가 아니라 자유 문자열이라 이 추가는 스키마 변경이 아니다(2.1.0에서 스키마 설명만 갱신).
- 평가는 온도 0, 평가 백엔드(transformers+peft)와 서빙(vLLM)이 다르다는 점을 `evaluation_backend`에 기록한다.
- 표기: **폐기** = v2 출력에 근거가 없어 계산할 수 없다. **대체** / **유지** / **신설**.

## LORA_A 추출·절차 (ActionExtraction)
(v1 절 제목: LORA_A 파서 (UtteranceParserOutput))

<!-- BEGIN GENERATED metrics:A -->
| name | group | 상태 | 뜻 |
| --- | --- | --- | --- |
| `value_precision`, `value_recall` | ACCURACY | 대체(v1 `item_precision/recall`) | `values[]`의 (`key`, `value`, `status`) 일치로 센 정밀도·재현율. 키만 맞은 경우는 맞은 것으로 세지 않는다 `[기본값]` |
| `precision_match` | ACCURACY | 신설 | `values[].precision`(exact/approximate/unspecified) 일치율. 값과 따로 보고해 원인을 분리한다 `[기본값]` |
| `targets_match` | ACCURACY | 대체(v1 `target_accuracy`) | `targets`가 정답과 같은 비율(REASK·CONFIRM·HOLD·SKIP 행만이 분모) |
| `value_exact_match` | ACCURACY | 유지(뜻 변경) | 값이 정답과 정확히 같은 비율. 모델이 정규화까지 하므로 "단위 환산 후" 조건은 없다 |
| `action_accuracy` | ACCURACY | 신설 | `action` 7종 일치율. 분리 기준 `ACTION` |
| `reason_accuracy` | ACCURACY | 신설 | `reason` 일치율(reason이 있는 행만). 분리 기준 `REASON` |
| `status_accuracy` | ACCURACY | 신설 | `values[].status` 일치율 |
| `next_item_accuracy` | ACCURACY | 신설 | `next_item` 일치율. **action별 분모로 낸다**(`slice` kind=`ACTION`). CONFIRM은 현재 문항이 아니라 충돌 대상 문항인 경우가 많다 `[기본값]` |
| `semantic_violation_rate` | ACCURACY | 신설(D97) | 계약 `action_rules.check_action_extraction`이 위반을 하나 이상 낸 출력의 비율(낮을수록 좋음). 정답과 비교하지 않는다. 위반 코드별 비율은 `slice`(kind=`VIOLATION_CODE`, value=코드)로 낸다. **기준 시험**: 학습 데이터 A 출력 전수가 위반 0이어야 하며 0이 아니면 검증기나 데이터의 문제다. 평가가 turn-engine(순수 함수 라이브러리, 버전 고정)에 의존하는 것을 허용한다 |
| `schema_valid_raw` | PROTECTION | 유지(뜻 좁힘) | 출력 보호 전 `ActionExtraction` 스키마 통과율. **제약 디코딩을 켠 값과 끈 값을 모두 보고한다**(`slice` kind=`CONSTRAINED_DECODING`, value=`on`/`off`) `[기본값]`. 켠 값은 100% 근처라 변별력이 낮다 |
| `output_invalid_rate` | PROTECTION | 신설(D75) | 재시도 후에도 형식을 못 지켜 `OUTPUT_INVALID`가 된 비율(낮을수록 좋음). 보조로 재시도 횟수(`X-Openit-Attempts`) 분포는 `output_attempts_mean`(`unit=count`)으로 낸다. 서빙 쪽 지표이므로 평가 백엔드가 같은 경로를 쓰는지 `evaluation_backend`로 구분한다 |
<!-- END GENERATED metrics:A -->

**폐기(A)**: `risk_signal_recall`, `risk_signal_false_alarm`(v2 A 출력에 위험 신호 필드가 없다. 입력원이 정해지면(G01) 그 입력원 기준으로 신설. SAFETY 구성은 담당자가 다시 정한다), `intent_accuracy`(위 `action/reason/status/next_item_accuracy`로 대체), `item_precision`, `item_recall`, `target_accuracy`(위 대체 지표로), `protection_intervened`와 `fallback_rate`(A는 대체 출력을 쓰지 않는다. 대신 `output_invalid_rate`).

## LORA_B 응답 (ResponseText)
(v1 절 제목: LORA_B 생성기 (ResponseGeneratorOutput))

<!-- BEGIN GENERATED metrics:B -->
| name | group | 상태 | 뜻 |
| --- | --- | --- | --- |
| `forbidden_expression_rate` | SAFETY | 유지 | 금지 표현(진단·처방·단정 등)을 쓴 비율(낮을수록 좋음). **금지 표현 목록이 없으면 `n=0`**으로 둔다(목록 소유자는 사용자 몫, D59) `[기본값]` |
| `ungrounded_number_rate` | SAFETY | 대체(D94) | 재료(`known`, `ask`, `previous`, `current`, `hold`, `next.text`, `user_utterance`)에 없는 숫자를 말한 비율(낮을수록 좋음). **런타임 검사가 아니라 평가 지표로만 잰다**(D94). `CONFLICT_WITH_PREVIOUS`의 `ask`에 영문 괄호 문구가 들어 있어 숫자 추출 규칙에 영향이 있다 |
| `material_coverage` | ACCURACY | 대체(v1 `slot_coverage`) | action별로 말해야 할 재료(NEXT면 `known`과 `next.text`, REASK면 `ask` 등)를 빠짐없이 말한 비율. action별 필수 재료 표는 학습 데이터 규칙(IO_SPEC)이며 담당자가 확인한다. 분리 기준 `ACTION` |
| `schema_valid_raw` | PROTECTION | 유지(뜻 변경) | B 출력은 JSON이 아니므로 "문자열이고 길이·형식 조건을 통과"한 비율 |
| `protection_intervened`, `fallback_rate` | PROTECTION | 유지 | `X-Openit-Outcome=fallback` 비율. action별 `slice`(kind=`ACTION`)를 권한다. 대체 문장 문구(G04)는 잠정(D93) |
| `length_p95_ms` | ROBUSTNESS | 유지 | 응답 지연 95백분위(`unit=ms`, 낮을수록 좋음). **이름은 바꾸지 않는다**(이름 변경은 소비자를 깨뜨릴 수 있다, D96) `[기본값]` |
| `response_length_chars_p95` | ROBUSTNESS | 신설(선택) | 응답 글자 수 95백분위(`unit=count`, 단위는 글자 수). 키오스크 음성 출력에 영향 |
<!-- END GENERATED metrics:B -->

**폐기(B)**: `risk_notice_verbatim_rate`(B가 안내 문장을 쓰지 않는다. 고정 문장은 서비스가 쓴다).

## 공통 보조 지표
<!-- BEGIN GENERATED metrics:COMMON -->
| name | group | 상태 | 뜻 |
| --- | --- | --- | --- |
| `coverage_seen_unseen_gap` | COVERAGE | 유지 | 본 문항과 보지 못한 문항의 정확도 차이 |
| `regression_fixed`, `regression_broken` | REGRESSION | 유지(입력 형식 변경) | 수집된 실패 사례(검토 확정, `reviewed_input` 사용)의 회귀 평가에서 고쳐진/다시 틀린 건수. 회귀 평가가 읽는 TurnTrace 키는 `extract_input`, `extract_output`, `response_input`, `response_output`이다(D98, 문진 스키마 `TurnTrace`가 정본) |
<!-- END GENERATED metrics:COMMON -->

## v1 지표 처분 요약
v1의 `risk_signal_recall`, `risk_signal_false_alarm`, `intent_accuracy`, `item_precision`, `item_recall`, `target_accuracy`, `risk_notice_verbatim_rate`, `slot_coverage`는 **폐기 또는 대체**이며 새 보고서에 쓰지 않는다. 지표 이름은 자유 문자열이므로 v1 보고서는 그대로 읽힌다.

## 담당자가 정할 것
- 어떤 지표를 반드시 보고서에 넣을지, SAFETY 지표를 얼마나 보수적으로 볼지, 직전 릴리스 대비 허용 하락폭(없어도 됨). 이것들은 합격선이 아니라 **승인 판단의 기준**이므로 담당자의 절차 문서에 둔다.
- `[기본값]` 항목의 정의(위), `QUESTION_TYPE`·`UNIT`·`RANGE`·`NOISE` 분리 기준이 v2 데이터에도 있는지(`NOISE`는 데이터에 `noise_types` 필드가 있어야 한다).
