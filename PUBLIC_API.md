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
| 409 | `CONFLICT` | 순서 어긋남(끝난 세션에 발화, 멈추지 않은 세션에 개입, 같은 `turn_id`에 다른 내용) | 안 함. 단 `details.reason`이 `TURN_IN_PROGRESS`이면(같은 `turn_id`가 아직 처리 중, `Retry-After` 헤더 동봉) 같은 `turn_id`로 `Retry-After` 뒤 다시 보낸다 |
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

`turn_id`는 프론트가 만든 턴별 고유 문자열이며 **API 봉투 필드**다: 문진 스키마(`FrontendMessage`, `InterventionDecision`)에는 없고, 서버는 본문에서 `turn_id`를 떼어 낸 나머지를 해당 스키마로 검증한다. 클라이언트도 같은 방식으로 검증한다(D66). **같은 `turn_id`로 다시 보내면 서버는 확정된 턴이면 같은 응답을 돌려주고 한 번만 처리한다**(네트워크 재시도 안전). **확정되지 못한 턴**(`write_committed`가 `NOT_COMMITTED`)은 결과를 고정하지 않아 같은 `turn_id` 재전송이 **다시 처리**된다(D86: 일시 장애로 실패한 턴이 영구 실패로 굳지 않게). 처리 중인 같은 `turn_id`는 409 `TURN_IN_PROGRESS`다. 위험 선별(D88)은 재전송에도 알림을 중복 만들지 않는다(알림은 세션·턴 기준 멱등).

## 응답 `FrontendInput`
- `response_text`: 화면에 보이고 읽어 줄 문장. null이면 말할 것이 없다(예: 세션 종료).
- `turn_failure_signal`: null이 아니면 이번 턴 처리에 문제가 있었다는 뜻이다. `write_committed`(기록이 저장됐는지: COMMITTED/NOT_COMMITTED)와 `staff_alert`(직원 호출이 전달됐는지: NONE/DELIVERED/DELIVERY_FAILED)를 담는다. 프론트는 `DELIVERY_FAILED`이면 **현장 직원을 직접 부르는 화면**을 보여야 한다.
- 스키마 원문은 `boundary_contracts` 패키지의 문진 스키마(`FrontendMessage`, `FrontendInput`, `TurnFailureSignal`)다.

## 직원 콘솔 (D58, D64: 웹 화면 + 푸시 알림, 가정이며 바뀔 수 있음)
위험 신호로 멈춘 세션은 직원이 풀어야 한다. 직원이 쓰는 웹 화면(직원 콘솔)과 푸시 알림을 가정한다. 이 호출들은 역할 `staff` 토큰만 쓸 수 있다(키오스크 토큰은 403). 서버 쪽만 정하며 화면 자체는 이 계약의 범위 밖이다.

| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 알림 목록 | `GET /v1/staff/alerts?status=OPEN\|RESOLVED&limit=&cursor=` | `StaffAlertPage`(`limit` 기본 50, 최대 200, 최신부터, `next_cursor`는 불투명 문자열 또는 null) |
| 알림 실시간 구독 | `GET /v1/staff/alerts/stream` (`text/event-stream`) | 이벤트 이름 `alert`(새 알림)와 `resolved`(해결), `id:`는 이벤트 순번(알림과 해결 이벤트가 각각 증가하는 번호를 받는다), `data:`는 `StaffAlert` JSON이다. 15초마다 `: ping` 주석 줄을 보낸다. 끊기면 `Last-Event-ID`로 이어 받는다. 추가 이벤트(하위 호환, 모르는 클라이언트는 무시한다, `id:`가 없어 `Last-Event-ID`를 바꾸지 않는다): `heartbeat`(`data: {"ts": "<UTC ISO>"}`, 연결 직후 한 번과 이후 주기마다 — 브라우저 `EventSource`는 주석 줄을 보여 주지 않으므로 앱이 연결 생존을 알 수 있게 한다)와 `resync`(`data: {"reason": "EVENTS_NOT_RESUMABLE"}`, `Last-Event-ID`로 이어 받을 수 없는 재연결에 한 번 — 클라이언트는 `GET /v1/staff/alerts?status=OPEN`으로 다시 맞춘다) |
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
- 응답이 없거나 일시 장애(429·502·503·504·네트워크 오류)면 같은 `turn_id`로 지수 백오프(지터 포함)로 재시도하고, 총 재시도 예산(기본 약 20초, 잠정)을 넘기면 직원 호출 화면을 보인다. 요청 타임아웃은 10초다.
- 한 세션의 요청은 순서대로 하나씩 보낸다(동시에 두 턴을 보내지 않는다).

## 아직 정하지 않은 것(프론트와 협의 필요 없이 우리가 정함, 바뀔 수 있음)
- 서비스 주소와 토큰 전달 방법(운영 배포 때), 세션 유휴 만료 시간(제안 5분).

---

# 추가 인터페이스 (2026-10-27, D85: 사용자 지시와 표준안)

아래는 서비스(survey-service), 게이트웨이(deploy), 프론트(kiosk-frontend, admin-console), 게이트(release-gate)가 같은 모양으로 구현하는 합의다. 세션 응답 스키마는 survey-service의 문진 스키마(`schema/schemas/`)에 둔다.

## A. 환자 참조 `subject_ref` (세션 시작)
- `POST /v1/sessions` 본문에 선택 필드 `"subject_ref"`: 병원이 정한 **불투명 문자열**(환자·방문을 가리키는 참조, 1~128자, `[A-Za-z0-9._:/#=+-]`). 서비스는 의미를 해석하지 않는다. 프론트가 시작 때 가지고 있는 값(병원 접수가 키오스크를 띄울 때 넘긴 값)을 그대로 보낸다.
- 서비스는 세션별로 저장한다(세션 문서 스키마를 바꾸지 않고 세션 메타로). 설정 `SURVEY_REQUIRE_SUBJECT_REF`가 켜져 있으면 없을 때 400(`INVALID_RECORD`). 기본은 꺼짐(데모용).
- `subject_ref`는 환자를 식별하는 값이다: 로그·알림 본문·푸시에 넣지 않고, 아래 조회 API와 접근 기록(세션 ID 기준)에서만 다룬다.

## B. 결과 조회 API (병원/의사 시스템용, 읽기 전용)
역할 `result-reader` 토큰. 호출마다 접근 기록(시각, 역할 이름, 게이트웨이가 인증한 행위자 `X-Openit-User`가 있으면 그 계정 ID, session_id 또는 조회 조건, 결과; 토큰·발화 제외)을 남기고, 기록을 못 남기면 데이터를 주지 않는다(503).
- `GET /v1/results/{session_id}` → `SessionResult`: `{"session_id", "subject_ref": str|null, "status": "IN_PROGRESS|PAUSED_RISK|ENDED_COMPLETE|ENDED_STAFF|ENDED_LEFT|ENDED_USER_STOP", "started_at": ISO|null, "ended_at": ISO|null, "release_id": str|null, "question_bank_version": str|null, "answers": [{"key","value","status","precision"}], "skipped": [str]}`. 끝나지 않은 세션과 직원·이탈로 끝난 세션의 **부분 결과도 상태와 함께** 돌려준다. 환자 발화 원문과 대화 로그는 포함하지 않는다(직원 세션 조회에만 있다).
- **`status`의 뜻** (survey-service CR-014 반영): `ENDED_COMPLETE` 문진을 끝까지 마침(**완료는 이것뿐**). `ENDED_LEFT` 환자가 끝나기 전에 떠남(키오스크 종료 요청 또는 유휴 만료). `ENDED_STAFF` 직원이 종료. `ENDED_USER_STOP` 예약된 값으로 지금 만들어지지 않는다. `IN_PROGRESS`·`PAUSED_RISK` 아직 끝나지 않음. 완료가 아닌 상태의 `answers`는 그때까지 저장된 부분 결과이고, `skipped`는 건너뛴 문항 ID일 뿐 미응답 문항 목록이 아니다. 완료 여부는 `status == "ENDED_COMPLETE"`로만 판단한다.
- `GET /v1/results?subject_ref=&status=&updated_after=&limit=&cursor=` → `{"items": [SessionResult], "next_cursor": str|null}` (`limit` 기본 50 최대 200).
- 오류: 401/403(`PERMISSION_DENIED`), 404(`NOT_FOUND`), 400(`INVALID_RECORD`), 503(`UNAVAILABLE`).
- 결과를 병원으로 **밀어 넣는** 전달기(Result Dispatcher)는 수신처가 정해질 때까지 붙이지 않는다. `/readyz`의 `result_dispatcher`는 `attached:false, status:NO_TARGET`.

## C. 직원 세션 조회 (CR-013 반영)
`GET /v1/staff/sessions/{session_id}` (역할 staff) → `StaffSessionView`. 모양과 의미는 survey-service `docs/change-requests/CR-013-staff-session-view-public-api.md`의 문구 그대로이고, 아래 두 가지를 더한다: 응답 최상위에 `"subject_ref": str|null`, `alerts[]`에 `"resolved_by": str|null`(해결한 직원 ID). 시각·turn_id가 null일 수 있고 `values[].status`는 `ANSWERED|CORRECTION`이라는 CR-013의 제안을 채택한다.

## D. 위험 신호 입력 API (입력원은 외부에 있다)
위험을 **감지하는 쪽**(키워드 규칙, 별도 분류 모델, LoRA-A 출력 확장 등)이 서비스에 신호를 쏜다.
- `POST /v1/sessions/{session_id}/risk-signals` (역할 `risk-source` 토큰) 본문 `RiskSignal`: `{"signal_id": str(1~64, 감지기가 만드는 고유값), "source": str(1~64, 감지기 이름), "code": str(1~64, 규칙·분류 코드), "severity": "RISK"|"CALL_STAFF"(기본 RISK), "occurred_at": ISO8601(선택)}`. 환자 발화·자유 문장 필드는 없다.
- 효과: 기존 위험 처리와 같다. 알림(`kind` = severity 값, `rule_id`에 `source:code`)을 만들고 세션을 `PAUSED_RISK`로 멈추며, **직원 콘솔(SSE/푸시)이 받고** 직원이 `GET /v1/staff/sessions/{id}`로 기록을 본다. 응답 201 `{"alert_id","session_status"}`. 같은 `signal_id` 재전송은 200과 같은 `alert_id`(멱등).
- 오류: 404(세션 없음), 409(이미 끝난 세션), 400, 401/403.
- 서비스 내부 규칙 엔진(`SURVEY_RISK_RULES_FILE`)은 같은 경로로 신호를 만드는 기본 감지기 하나일 뿐이다.

## E. 직원·운영자 식별
- 게이트웨이가 직원·운영자를 개별 계정으로 인증하고 `X-Openit-User: <계정 ID>`를 붙인다(클라이언트가 보낸 같은 이름의 헤더는 지운다). **본문 값은 신뢰하지 않는다.**
- `POST /v1/sessions/{id}/intervention`: 서비스가 헤더의 계정 ID를 `staff_id`로 개입 기록(대화 로그의 개입 항목, 알림 `resolved_by`)에 남긴다. 헤더가 없으면 401.
- 릴리스 `activate`, `rollback`: 게이트웨이가 `/v1/activate`, `/v1/rollback`(POST)을 **운영자 역할 계정 뒤에서만** 연다. release-gate는 요청 본문의 `requested_by_role`을 믿지 않고 헤더로 행위자(`requested_by`)와 역할을 정해 기록한다.
- 인증 방식의 표준은 OIDC(SSO)다. 병원 IdP가 정해지기 전에는 게이트웨이가 개별 계정(암호는 비밀 파일)으로 인증하고, OIDC로 바꿔도 위 헤더 규칙은 그대로다.

## F. 키오스크 기기 인증
- 키오스크 앱은 기기별 토큰을 `Authorization: Bearer`로 보낸다(기기 토큰은 URL 쿼리에 두지 않는다. 시작 때 URL 조각(`#`)이나 기기 설정으로 한 번 받아 메모리에만 둔다). 게이트웨이는 기기 토큰 목록(비밀 파일, 기기마다 파일 하나, 파일을 지우면 폐기)과 대조해 통과시키고 **서비스에는 받은 기기 토큰을 그대로 전달한다**(D88 U8, `Authorization`을 바꾸지 않는다). 서비스는 같은 기기 토큰 표로 다시 검증하고 세션을 만든 기기 토큰만 그 세션에 접근하게 한다(다른 기기는 404). 공유 서비스 토큰은 하위 호환 경로로만 남고 서비스 `/readyz`의 `shared_kiosk_token`으로 경고한다. 게이트웨이에 닿는 누구나 호출할 수 있는 상태를 없앤다. 병원 내부망 제한은 배포 설정으로 병행한다.

---

# 2.1.0 추가 (D93~D103, CR-H001·CR-H002 채택) — 모두 추가형이다

기존 요청·응답의 의미는 바뀌지 않는다. 새 필드는 optional이고 새 경로만 더한다. 모르는 필드를 무시하는 읽기 규칙(CONVENTIONS 1절)을 따르는 기존 클라이언트는 깨지지 않는다. 근거와 대안은 `docs/adr/0010`, `0011`.

## G. 직원 호출 재알림과 실패 기록 (CR-H001)
`TurnFailureSignal.staff_alert`가 `DELIVERY_FAILED`이면 키오스크는 현장 직원 호출 화면을 보여 주면서 아래 두 호출을 쓸 수 있다. 역할은 키오스크이고 **그 세션을 만든 기기 토큰만** 호출할 수 있다(다른 기기는 404, 직원 토큰은 403, F절). 두 호출 모두 환자 발화나 자유 문장을 받지 않는다.

| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 재알림 | `POST /v1/sessions/{session_id}/staff-call/retry` 본문 `StaffCallRetryRequest` `{"turn_id"}` | 200 `StaffCallRetryResult` `{"alert_id","staff_alert":"DELIVERED"\|"DELIVERY_FAILED","delivery_attempts":n,"retry_after_s":s}` |
| 실패 기록 | `POST /v1/sessions/{session_id}/staff-call/report` 본문 `StaffCallReport` `{"outcome":"STAFF_NOTIFIED_MANUALLY"\|"NOT_NOTIFIED","turn_id"}` | 200 `StaffAlert`(`manual_notice_outcome`, `manual_notice_reported_at`이 채워짐) |

- **재알림**은 그 세션의 `OPEN` 알림을 **새로 만들지 않고 같은 `alert_id`로** 구독자(SSE `alert` 이벤트, 웹 푸시)에게 다시 보낸다. 직원 콘솔은 같은 `alert_id`의 `alert` 이벤트를 중복으로 보고 합쳐야 한다(새 이벤트 이름을 만들지 않는다: 모르는 콘솔은 무시하므로 목적을 못 이룬다). `OPEN` 알림이 없으면 409(`CONFLICT`, `details.reason: NO_OPEN_ALERT`). 이미 `RESOLVED`인 알림은 다시 보내지 않는다.
- **호출 간격 하한**: `retry_after_s`초 안의 재요청은 429(`UNAVAILABLE`, `Retry-After` 헤더). 키오스크는 이 값만큼 버튼을 비활성화한다. **간격과 횟수 상한의 값은 계약이 아니라 서비스 설정이다.** 계약의 기본 권고는 간격 30초, 세션당 상한 10회(상한 초과도 429 `details.reason: RETRY_LIMIT`)이며 **측정하지 않은 자리 표시값**이다(근거: 현장 흐름 자료 없음, ADR 0010). 서비스는 값을 영역 ADR에 근거와 함께 적는다(D89).
- **멱등**: 같은 `turn_id`의 재전송은 같은 응답을 주고 시도 횟수를 늘리지 않는다. 같은 `turn_id`에 다른 `outcome`은 409.
- **실패 기록**은 알림에 `manual_notice_outcome`/`manual_notice_reported_at`을 남기고 접근 기록(감사)에도 남긴다. 세션은 직원이 개입 결정으로 풀 때까지 그대로 `PAUSED_RISK`다. `NOT_NOTIFIED` 뒤 키오스크 화면 동작(재알림 계속 여부, 환자 안내 문구)은 계약이 아니라 kiosk-frontend와 현장 판단이다(임상 확인 필요, 미정).
- **`StaffAlert`에 optional 필드**: `delivery_attempts`(첫 전달 포함 시도 횟수), `last_delivery_status`(`DELIVERED`/`DELIVERY_FAILED`), `manual_notice_outcome`, `manual_notice_reported_at`. 직원 콘솔은 전달 실패 알림을 눈에 띄게 보일 수 있다.
- **호환**: 새 키오스크 + 옛 서버는 두 경로가 404/405이므로 키오스크는 기능 감지로 현재 동작("직접 알리셨나요?" 화면만)으로 물러난다. 옛 키오스크 + 새 서버는 새 경로를 쓰지 않을 뿐이다. 배포 순서는 survey-service 먼저, 키오스크 나중.
- 키오스크가 알림 목록 읽기나 직원 확인(ack)을 쓰는 것은 이번 범위가 아니다(후속 후보).
- **재전달 신호(동작 의미)**: 재알림이 전달되면 같은 `alert_id`의 `alert` 이벤트가 **새 이벤트 번호**로 다시 나가고, 그 `StaffAlert.delivery_attempts`는 이전 값보다 커진다. 직원 콘솔은 목록을 `alert_id`로 합치되 `delivery_attempts`가 커졌을 때만 '다시 알림'(배너·푸시 재알림)으로 처리한다. 같은 번호 이하의 이벤트(Last-Event-ID 이어받기로 다시 온 것)는 재알림으로 보지 않는다.
- **해결된 알림**: 이미 `RESOLVED`인 알림은 재알림하지 않는다(409 `NO_OPEN_ALERT`). 실패 기록(report)은 `RESOLVED` 알림에도 남기며 이때도 같은 `alert_id`의 `alert` 이벤트(status `RESOLVED` 가능)가 나가므로 직원 콘솔은 이를 합쳐 보여야 한다. 직원이 해결(`intervention`)한 뒤에는 `resolved` 이벤트 다음에 같은 알림의 OPEN `alert` 이벤트가 나가지 않는다.
- **429의 두 종류**: 간격 초과(`details.reason: INTERVAL`)는 `Retry-After`가 붙고, 상한 초과(`RETRY_LIMIT`)와 report 상한 초과는 기다려도 풀리지 않으므로 `Retry-After`가 없다. 클라이언트는 `details.reason`을 먼저 본다.
- **turn_id**: 응답을 받지 못한 재전송에만 같은 `turn_id`를 쓰고(멱등), 응답을 받은 뒤의 새 호출은 새 `turn_id`를 쓴다. 5xx와 시간 초과는 처리 여부를 모르는 경우이므로 같은 `turn_id`를 유지한다.
- **키오스크 안전 규칙(권고)**: report 결과가 `NOT_NOTIFIED`이거나 재알림이 상한·`NO_OPEN_ALERT`에 닿아도 직원 호출 화면을 끝내지 않고 '접수처로 직접 알려 달라'는 안내를 유지하며, 환자가 세션을 임의로 끝낼 수 없다(직원 개입으로만 해제). 안내 문구는 임상 검토 전 임시이다.

## H. 정지 사유 `pause_reason` (CR-H002)
- 값: `RISK`(위험 신호로 정지), `REASK_LIMIT`(되묻기 한도 N 초과로 정지, D95), `OTHER`(그 밖). **읽는 쪽은 모르는 값과 값이 없는 경우를 `OTHER`/미상으로 취급한다**(열거 확장 대비).
- 붙는 곳(모두 optional): `SessionState`(`GET /v1/sessions/{id}/state`, `state=PAUSED_RISK`일 때만 의미가 있고 그 밖의 상태에서는 null/생략), `StaffAlert`, 직원 세션 조회 `StaffSessionView`, 그리고 `TurnFailureSignal`.
- `TurnFailureSignal`과 `StaffSessionView`는 문진 스키마(`../survey-service/schema`, survey-service 소유)에 있으므로 **이 리포가 고치지 않는다.** 이 문서가 정한 필드 이름·열거 값(`pause_reason`: `RISK|REASK_LIMIT|OTHER`, optional)을 survey-service가 자기 스키마에 반영한다(D21). `SessionState`·`StaffAlert`는 이 리포 스키마다.
- 상태 이름 `PAUSED_RISK`는 바꾸지 않는다(MAJOR가 되고 `SessionResult.status` 소비자가 깨진다). `SessionResult.status` 규약도 그대로다.
- 새 클라이언트 + 옛 서버는 필드가 없으므로 미상으로 폴백한다.
