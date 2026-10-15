# 공개 API (I10) — 키오스크 프론트 ↔ 문진 서비스 (D55)

**독자: 프론트 개발자.** 키오스크 프론트는 이 API만 호출한다. 서버 쪽은 survey-service가 구현한다. 아래는 헤드가 정한 **제안 계약 v1**이며, 프론트 쪽 사정으로 바꿔야 할 점이 있으면 알려 주면 된다.

## 원칙
- 요청-응답 HTTP/JSON(UTF-8). 프론트는 **STT로 음성을 텍스트로 바꾼 문장**을 보낸다. 서버는 음성을 받지 않는다.
- 세션 ID는 **프론트가 발급**한다(`session_id`, 문자열 1~64자, 영문·숫자·`-_`). 환자 번호나 개인 식별 정보는 보내지 않는다.
- 인증: `Authorization: Bearer <서비스 토큰>`. 토큰은 운영 때 배포 담당이 전달한다.
- 오류는 `BoundaryError` 본문과 상태 코드: 400 형식 오류, 401 토큰이 없거나 틀림, 403 토큰은 맞지만 그 호출 권한이 없음, 404 모르는 세션, 409 순서 어긋남, 429 과다 요청, 503 일시 불가(재시도 가능).

## 호출
| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 세션 시작 | `POST /v1/sessions` 본문 `{"session_id": "...", "kind": "SESSION_START"}` | `FrontendInput` (`response_text`: 첫 안내 문장) |
| 환자 발화 | `POST /v1/sessions/{session_id}/turns` 본문 `{"session_id", "kind": "UTTERANCE", "utterance": "STT 텍스트", "turn_id": "..."}` | `FrontendInput` |
| 세션 종료 | `POST /v1/sessions/{session_id}/end` 본문 `{"session_id", "kind": "SESSION_END"}` | `FrontendInput` (`response_text`는 null일 수 있음) |
| 상태 확인 | `GET /healthz`, `GET /readyz` | 200 |

`turn_id`는 프론트가 만든 턴별 고유 문자열이다. **같은 `turn_id`로 다시 보내면 서버는 같은 응답을 돌려주고 한 번만 처리한다**(네트워크 재시도 안전).

## 응답 `FrontendInput`
- `response_text`: 화면에 보이고 읽어 줄 문장. null이면 말할 것이 없다(예: 세션 종료).
- `turn_failure_signal`: null이 아니면 이번 턴 처리에 문제가 있었다는 뜻이다. `write_committed`(기록이 저장됐는지: COMMITTED/NOT_COMMITTED)와 `staff_alert`(직원 호출이 전달됐는지: NONE/DELIVERED/DELIVERY_FAILED)를 담는다. 프론트는 `DELIVERY_FAILED`이면 **현장 직원을 직접 부르는 화면**을 보여야 한다.
- 스키마 원문은 `boundary_contracts` 패키지의 문진 스키마(`FrontendMessage`, `FrontendInput`, `TurnFailureSignal`)다.

## 직원 콘솔 (위험으로 멈춘 세션 풀기, D58)
위험 신호로 멈춘 세션은 직원이 풀어야 한다. 직원 콘솔(또는 이를 대신하는 도구)이 호출한다. 키오스크 토큰으로는 호출할 수 없다(역할 `staff`, 403).

| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 개입 결정 | `POST /v1/sessions/{session_id}/intervention` 본문 `{"session_id", "decision": "RESUME"\|"END", "turn_id": "..."}` | `FrontendInput` (RESUME이면 이어서 할 안내 문장, END면 종료) |

`turn_id` 규칙은 발화와 같다(같은 값 재전송은 같은 응답). 멈추지 않은 세션에 보내면 409.

## 프론트가 지킬 것
- STT 결과가 비었거나 신뢰할 수 없으면 서버로 보내지 않고 "다시 말씀해 주세요"를 프론트에서 안내해도 된다.
- 응답이 없으면(타임아웃 기본 10초) 같은 `turn_id`로 재시도하고, 3회 실패하면 직원 호출 화면을 보인다.
- 한 세션의 요청은 순서대로 하나씩 보낸다(동시에 두 턴을 보내지 않는다).

## 아직 정하지 않은 것(프론트와 협의 필요 없이 우리가 정함, 바뀔 수 있음)
- 서비스 주소와 토큰 전달 방법(운영 배포 때), 세션 유휴 만료 시간(제안 5분).
