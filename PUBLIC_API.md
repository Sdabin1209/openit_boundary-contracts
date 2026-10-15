# 공개 API (I10) — 키오스크 프론트 ↔ 문진 서비스 (D55)

**독자: 프론트 개발자.** 키오스크 프론트는 이 API만 호출한다. 서버 쪽은 survey-service가 구현한다. 아래는 헤드가 정한 **제안 계약 v1**이며, 프론트 쪽 사정으로 바꿔야 할 점이 있으면 알려 주면 된다.

## 원칙
- 요청-응답 HTTP/JSON(UTF-8). 프론트는 **STT로 음성을 텍스트로 바꾼 문장**을 보낸다. 서버는 음성을 받지 않는다.
- 세션 ID는 **프론트가 발급**한다(`session_id`, 문자열 1~64자, 영문·숫자·`-_`). 환자 번호나 개인 식별 정보는 보내지 않는다.
- 인증: `Authorization: Bearer <서비스 토큰>`. 토큰은 운영 때 배포 담당이 전달한다.
- 오류는 `BoundaryError` 본문과 상태 코드이고, **클라이언트는 상태 코드로 분기한다**(D66):

| 상태 | `BoundaryError.code` | 뜻 | 재시도 |
| --- | --- | --- | --- |
| 400 | `INVALID_RECORD` | 형식 오류 | 안 함 |
| 401 | `PERMISSION_DENIED` | 토큰이 없거나 틀림 | 안 함 |
| 403 | `PERMISSION_DENIED` | 토큰은 맞지만 그 호출 권한이 없음 | 안 함 |
| 404 | `NOT_FOUND` | 모르는(또는 만료된) 세션 | 안 함 |
| 409 | `CONFLICT` | 순서 어긋남(끝난 세션에 발화, 멈추지 않은 세션에 개입, 같은 `turn_id`에 다른 내용) | 안 함 |
| 429 | `UNAVAILABLE` | 과다 요청 | 함. `Retry-After`(초, 정수)를 따른다 |
| 503 | `UNAVAILABLE` | 일시 불가 | 함. `Retry-After`가 있으면 따르고 없으면 1초 |

## 호출
| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 세션 시작 | `POST /v1/sessions` 본문 `{"session_id": "...", "kind": "SESSION_START"}` | `FrontendInput` (`response_text`: 첫 안내 문장) |
| 환자 발화 | `POST /v1/sessions/{session_id}/turns` 본문 `{"session_id", "kind": "UTTERANCE", "utterance": "STT 텍스트", "turn_id": "..."}` | `FrontendInput` |
| 세션 종료 | `POST /v1/sessions/{session_id}/end` 본문 `{"session_id", "kind": "SESSION_END"}` | `FrontendInput` (`response_text`는 null일 수 있음) |
| 세션 상태 (D66) | `GET /v1/sessions/{session_id}/state` | `SessionState`. 키오스크가 위험 정지 중에 2초 간격으로 폴링한다. 직원이 재개하면 `state=ACTIVE`와 `resume_text`(이어서 할 안내 문장)가 오고, 다음 발화 턴이 접수되면 `resume_text`는 null이 된다. 직원이 종료하면 `ENDED` |
| 상태 확인 | `GET /healthz`, `GET /readyz` | 200 |

`turn_id`는 프론트가 만든 턴별 고유 문자열이며 **API 봉투 필드**다: 문진 스키마(`FrontendMessage`, `InterventionDecision`)에는 없고, 서버는 본문에서 `turn_id`를 떼어 낸 나머지를 해당 스키마로 검증한다. 클라이언트도 같은 방식으로 검증한다(D66). **같은 `turn_id`로 다시 보내면 서버는 같은 응답을 돌려주고 한 번만 처리한다**(네트워크 재시도 안전).

## 응답 `FrontendInput`
- `response_text`: 화면에 보이고 읽어 줄 문장. null이면 말할 것이 없다(예: 세션 종료).
- `turn_failure_signal`: null이 아니면 이번 턴 처리에 문제가 있었다는 뜻이다. `write_committed`(기록이 저장됐는지: COMMITTED/NOT_COMMITTED)와 `staff_alert`(직원 호출이 전달됐는지: NONE/DELIVERED/DELIVERY_FAILED)를 담는다. 프론트는 `DELIVERY_FAILED`이면 **현장 직원을 직접 부르는 화면**을 보여야 한다.
- 스키마 원문은 `boundary_contracts` 패키지의 문진 스키마(`FrontendMessage`, `FrontendInput`, `TurnFailureSignal`)다.

## 직원 콘솔 (D58, D64: 웹 화면 + 푸시 알림, 가정이며 바뀔 수 있음)
위험 신호로 멈춘 세션은 직원이 풀어야 한다. 직원이 쓰는 웹 화면(직원 콘솔)과 푸시 알림을 가정한다. 이 호출들은 역할 `staff` 토큰만 쓸 수 있다(키오스크 토큰은 403). 서버 쪽만 정하며 화면 자체는 이 계약의 범위 밖이다.

| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 알림 목록 | `GET /v1/staff/alerts?status=OPEN\|RESOLVED&limit=&cursor=` | `StaffAlertPage`(`limit` 기본 50, 최대 200, 최신부터, `next_cursor`는 불투명 문자열 또는 null) |
| 알림 실시간 구독 | `GET /v1/staff/alerts/stream` (`text/event-stream`) | 이벤트 이름 `alert`(새 알림)와 `resolved`(해결), `id:`는 이벤트 순번(알림과 해결 이벤트가 각각 증가하는 번호를 받는다), `data:`는 `StaffAlert` JSON이다. 15초마다 `: ping` 주석 줄을 보낸다. 끊기면 `Last-Event-ID`로 이어 받는다 |
| 푸시 설정 | `GET /v1/staff/push-config` | `PushConfig`(웹 푸시 공개키). `vapid_public_key`가 null이면 푸시는 꺼져 있고 SSE만 동작한다 |
| 푸시 구독 등록 | `POST /v1/staff/push-subscriptions` 본문 웹 푸시 구독 객체(`endpoint`, `keys`) | 201. 같은 `endpoint`는 갱신(멱등). `DELETE /v1/staff/push-subscriptions?endpoint=`로 해지 |
| 개입 결정 | `POST /v1/sessions/{session_id}/intervention` 본문 `{"session_id", "decision": "RESUME"\|"END", "turn_id": "..."}` | `FrontendInput` (RESUME이면 이어서 할 안내 문장, END면 종료) |

- `StaffAlert`: `alert_id`, `session_id`, `kind`(`RISK_STOP` 등 모르는 값은 그대로 보여 줌), `created_at`, `status`(`OPEN`/`RESOLVED`), `resolved_by_decision`(`RESUME`/`END`/null), `resolved_at`. 환자 발화나 개인 정보는 담지 않는다(세션 ID와 종류만).
- 위험으로 멈춘 세션은 유휴 만료로 닫지 않는다(직원이 처리할 때까지 유지).
- 위험 정지가 나면 서버는 알림을 영속 저장하고 구독자(SSE, 웹 푸시)에게 보낸다. 개입 결정이 성공하면 해당 알림이 `RESOLVED`가 된다.
- `TurnFailureSignal.staff_alert`: 알림이 저장되고 **전달 경로가 하나 이상 살아 있을 때**(SSE 연결 또는 푸시 서비스가 접수) `DELIVERED`, 아니면 `DELIVERY_FAILED`다. 저장된 알림은 `DELIVERY_FAILED`여도 목록에서 조회된다. 프론트는 `DELIVERY_FAILED`이면 현장 직원 호출 화면을 보여야 한다.
- 웹 푸시의 서버 키(VAPID)는 비밀 값이며 환경 변수로만 받는다. 푸시 본문에는 세션 ID와 종류만 넣는다.
- `turn_id` 규칙은 발화와 같다(같은 값 재전송은 같은 응답). 멈추지 않은 세션에 개입을 보내면 409.

## 프론트가 지킬 것
- STT 결과가 비었거나 신뢰할 수 없으면 서버로 보내지 않고 "다시 말씀해 주세요"를 프론트에서 안내해도 된다.
- 응답이 없으면(타임아웃 기본 10초) 같은 `turn_id`로 재시도하고, 3회 실패하면 직원 호출 화면을 보인다.
- 한 세션의 요청은 순서대로 하나씩 보낸다(동시에 두 턴을 보내지 않는다).

## 아직 정하지 않은 것(프론트와 협의 필요 없이 우리가 정함, 바뀔 수 있음)
- 서비스 주소와 토큰 전달 방법(운영 배포 때), 세션 유휴 만료 시간(제안 5분).
