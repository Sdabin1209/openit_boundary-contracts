# 평가 지표 카탈로그 (제안, D53)

**상태: 제안.** 학습 담당자가 검토해 다듬는다. 이 문서는 `EvaluationReport.metrics[].name`에 쓸 이름과 뜻을 정한다. **합격선(임계치)은 없다.** 출고는 담당자가 보고서를 보고 정한다. 지표를 추가하는 것은 이 문서와 평가 구현만 바꾸면 되고 계약은 바뀌지 않는다(`name`은 자유 문자열, 모르는 이름은 보고서에 그대로 보인다).

## 읽는 법
- 모든 값은 `value`, 표본 수 `n`, 방향 `higher_is_better`, 부분집합 `slice`(kind/value)를 가진다. `n=0`이면 계산하지 못한 것이다.
- `group=SAFETY`는 승인 보고서 맨 위에 따로 보인다. 현재 활성 릴리스와 같은 지표끼리 비교한다(`baseline`, `delta`). 나빠진 것은 `worse=true`로 표시만 한다.
- 분리 기준(slice kind): `ALL`, `QUESTION_SET`(문항 세트 ID), `SEEN_UNSEEN`(학습에 쓴 문항/보지 못한 문항, D32), `INTENT`, `QUESTION_TYPE`, `UNIT`, `RANGE`, `NOISE`(STT 오류 등 입력 잡음 종류), `SCENARIO`.
- 평가는 온도 0, 평가 백엔드(transformers+peft)와 서빙(vLLM)이 다르다는 점을 `evaluation_backend`에 기록한다.

## LORA_A 파서 (UtteranceParserOutput)
| name | group | 뜻 |
| --- | --- | --- |
| `risk_signal_recall` | SAFETY | 정답에 위험 신호가 있는 발화 중 모델이 위험 신호를 잡은 비율 |
| `risk_signal_false_alarm` | SAFETY | 위험 신호가 없는데 잡은 비율(낮을수록 좋음) |
| `item_precision`, `item_recall` | ACCURACY | 추출한 항목(문항/값 쌍)의 정밀도·재현율 |
| `target_accuracy` | ACCURACY | 항목이 가리키는 대상 문항을 맞춘 비율 |
| `value_exact_match` | ACCURACY | 값이 정답과 정확히 같은 비율(숫자는 단위 환산 후) |
| `intent_accuracy` | ACCURACY | 의도 분류 정확도 |
| `schema_valid_raw` | PROTECTION | 출력 보호(D36) 전 문진 스키마를 통과한 비율 |
| `protection_intervened` | PROTECTION | 보호가 대체 출력을 쓴 건수(`unit=count`; 낮을수록 좋음) |
| `fallback_rate` | PROTECTION | `is_fallback` 출력 비율(낮을수록 좋음) |

## LORA_B 생성기 (ResponseGeneratorOutput)
| name | group | 뜻 |
| --- | --- | --- |
| `forbidden_expression_rate` | SAFETY | 금지 표현(진단·처방·단정 등)을 쓴 비율(낮을수록 좋음) |
| `risk_notice_verbatim_rate` | SAFETY | 안내 문장(RISK_NOTICE)이 원문 그대로 들어간 비율 |
| `ungrounded_number_rate` | SAFETY | 재료에 없는 숫자를 말한 비율(낮을수록 좋음) |
| `slot_coverage` | ACCURACY | 말해야 할 재료를 빠짐없이 말한 비율 |
| `schema_valid_raw`, `protection_intervened`, `fallback_rate` | PROTECTION | 파서와 같은 뜻 |
| `length_p95_ms` | ROBUSTNESS | 응답 지연 95백분위(`unit=ms`, 낮을수록 좋음) |

## 공통 보조 지표
| name | group | 뜻 |
| --- | --- | --- |
| `coverage_seen_unseen_gap` | COVERAGE | 본 문항과 보지 못한 문항의 정확도 차이 |
| `regression_fixed`, `regression_broken` | REGRESSION | 수집된 실패 사례(검토 확정, `reviewed_input` 사용)의 회귀 평가에서 고쳐진/다시 틀린 건수 |

## 담당자가 정할 것
- 어떤 지표를 반드시 보고서에 넣을지, SAFETY 지표를 얼마나 보수적으로 볼지, 직전 릴리스 대비 허용 하락폭(없어도 됨). 이것들은 합격선이 아니라 **승인 판단의 기준**이므로 담당자의 절차 문서에 둔다.
