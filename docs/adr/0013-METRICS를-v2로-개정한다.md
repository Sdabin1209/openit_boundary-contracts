# 0013. METRICS.md를 v2로 개정한다 (D96·D97·D98)

- 상태: 수용(2.1.0). 정의는 학습 담당 확인 전의 임시 기본값
- 관련: D53, D59, D74, D75, D94, D96, D97, D98 / `METRICS.md` / 헤드 `docs/metrics-v2-proposal.md`

## 맥락

v1 지표(`risk_signal_*`, `intent_accuracy` 등)는 v2 출력(`ActionExtraction`: 위험 신호·의도 필드 없음)에 근거가 없어 계산할 수 없다. 제약 디코딩으로 형식 통과율은 변별력이 낮다(gpu-dev 48/48, 학습 안 된 모델).

## 결정

- v1 지표를 폐기·대체로 표시하고 `value_precision/recall`, `action/reason/status/next_item_accuracy`, `output_invalid_rate`, `ungrounded_number_rate`(평가 지표로만, D94), `material_coverage`, `semantic_violation_rate`(D97)를 정한다. slice 기준에 `ACTION`·`REASON`을 더하고 `INTENT`를 폐기 표시한다.
- D96 기본값: (key, value, status) 일치로 센다, `precision` 일치는 따로 보고, `next_item_accuracy`는 action별 분모, `schema_valid_raw`는 제약 디코딩 켠/끈 값 모두, 금지 표현 목록이 없으면 `n=0`, `length_p95_ms` 이름 유지. 임계치는 정하지 않는다.
- `EvaluationReport`의 slice `kind`는 열거가 아니라 자유 문자열이므로 스키마 변경 없이 설명 문구만 갱신한다.

## 왜

- 분류 평가의 표준 정의(정밀도·재현율은 예측 단위의 정확 일치로 센다)를 따른다. 키만 맞는 경우를 맞다고 세면 오답을 놓친다.
- 의미 위반율은 운영 실패율과 같은 규칙(같은 검증기 `validate_extraction`)으로 재야 지표의 타당성이 선다(D97). turn-engine은 순수 함수 라이브러리이고 model-lab이 이미 계보 기록용으로 의존한다. 기준 시험(학습 데이터 A 출력 전수 위반 0)이 지표와 검증기 중 어느 쪽 결함인지 가른다.
- 지표 이름은 자유 문자열이라 계약이 깨지지 않는다. `length_p95_ms`처럼 이름이 어색해도 바꾸지 않는다(소비자 보호).
- `response_length_chars_p95`의 `unit`은 `count`(글자 수)다: `EvaluationReport`의 unit 열거(ratio/count/ms/score)에 `chars`가 없어 검증이 실패하므로, 스키마를 넓히지 않고(MINOR라도 열거 확장은 소비자 영향) 기존 값으로 맞췄다. 이름의 `chars`가 단위를 말한다.
- 측정하지 않았다: 어떤 지표의 값도, 임계치도 이 리포는 정하지 않는다.

## 검토한 대안과 버리는 이유

| 대안 | 버리는 이유 |
|---|---|
| v1 지표 유지 | 계산 불가 지표가 남는다 |
| 런타임 숫자 검사(G1) | 오탐 비용을 측정하지 못한 채 도입해야 한다(D94) |
| `INTENT` slice를 지우기 | 이전 보고서가 읽히지 않을 수 있다. 폐기 표시만 한다 |
| `kind`를 열거로 바꿔 검증 | 모르는 kind를 받아들이는 읽기 규칙(CONVENTIONS 1절)과 어긋나고 MAJOR 후보다 |

## 결과

- 얻는 것: model-lab이 구현할 지표 목록이 확정된다(임시 기본값).
- 감수하는 것: 담당자가 정의를 바꾸면 따라야 한다. model-lab의 turn-engine 의존이 하나 늘고 버전 고정이 필요하다.

## 되돌리는 조건

충돌 규칙이 확인돼 `validate_extraction` 의존이 막히면 서비스의 `validation_violations`(TurnTrace) 수집으로 대체한다(D97).
