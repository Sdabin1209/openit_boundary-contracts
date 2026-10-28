# 0011. 정지 사유를 optional `pause_reason`으로 더하고 `PAUSED_RISK` 이름은 유지한다 (CR-H002)

- 상태: 수용(2.1.0, 헤드 CR-H002)
- 관련: D95 / `PUBLIC_API.md` H절

## 맥락

위험 신호 정지와 되묻기 한도(N=3 초과, D95) 정지가 모두 `PAUSED_RISK`이고 응답 모양이 같다. 직원 콘솔과 운영 지표가 "환자가 위험해서"와 "시스템이 못 알아들어서"를 구분하지 못한다. 전자는 환자 안전, 후자는 모델·질문 품질 문제라 대응이 다르다.

## 결정

optional `pause_reason`(`RISK`, `REASK_LIMIT`, `OTHER`)을 `SessionState`, `StaffAlert`(이 리포 스키마)에 더하고, 같은 이름·열거로 `TurnFailureSignal`·`StaffSessionView`(survey-service의 문진 스키마)에 더하도록 survey-service에 맡긴다. 읽는 쪽은 모르는 값·없는 값을 `OTHER`/미상으로 취급한다. 상태 이름 `PAUSED_RISK`는 바꾸지 않는다.

## 왜

- 열거 확장과 optional 추가는 MINOR이고(CONVENTIONS 1절 2항, ADR 0004) 기존 소비자는 모르는 필드를 무시한다.
- 지금의 구분 수단(환자 문장, 알림 `kind`)은 표시용·부분적이라 지표 집계에 못 쓴다.
- 읽기 모드 스키마(`_relax`)가 null을 허용하는 열거에서도 모르는 값을 받아들이도록 고쳤다(그렇지 않으면 새 값에서 클라이언트가 `INTEGRITY_ERROR`를 낸다).
- `TurnFailureSignal`은 CR 초안이 건드리지 말자고 했으나 헤드 결정이 정지 신호에도 사유를 싣는 것으로 확정했다. 그 스키마는 이 리포 소유가 아니므로 필드 이름만 정하고 반영은 survey-service가 한다(워크스페이스 규칙: 스키마 소유자가 수정).

## 검토한 대안과 버리는 이유

| 대안 | 버리는 이유 |
|---|---|
| 상태를 `PAUSED_REASK_LIMIT`로 분리 | 기존 소비자는 `PAUSED_RISK`만 알아 정지를 알아보지 못한다. `SessionResult.status` 규약까지 바뀐다 |
| `StaffAlert.kind`만 구분 | 알림 없는 경로·세션 조회에서 안 보이고 `kind`는 알림 종류이지 정지 사유가 아니다 |
| 환자 문장으로 구분 유지 | 문구 변경에 깨지고 집계에 못 쓴다 |
| ops-feedback의 추정 | 틀릴 수 있고 직원 콘솔은 추정 입력도 없다 |
| `PAUSED_RISK` 이름 변경 | MAJOR |

## 결과

- 얻는 것: 직원 콘솔·ops-feedback의 사유별 구분.
- 감수하는 것: 새 클라이언트 + 옛 서버는 필드가 없으므로 미상으로 폴백해야 한다. `PAUSED_RISK`라는 이름이 되묻기 정지에도 쓰이는 어색함은 남는다.

## 되돌리는 조건

다음 MAJOR에서 상태 이름을 정리할 때 이 필드를 상태로 흡수할 수 있다.
