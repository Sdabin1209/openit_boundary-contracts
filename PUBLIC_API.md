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
- 응답이 없으면(타임아웃 기본 10초) 같은 `turn_id`로 재시도하고, 3회 실패하면 직원 호출 화면을 보인다.
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
역할 `result-reader` 토큰. 호출마다 접근 기록(시각, 역할 이름, session_id 또는 조회 조건, 결과; 토큰·발화 제외)을 남기고, 기록을 못 남기면 데이터를 주지 않는다(503).
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
- 키오스크 앱은 기기별 토큰을 `Authorization: Bearer`로 보낸다(기기 토큰은 URL 쿼리에 두지 않는다. 시작 때 URL 조각(`#`)이나 기기 설정으로 한 번 받아 메모리에만 둔다). 게이트웨이는 기기 토큰 목록(비밀 파일, 기기마다 파일 하나, 파일을 지우면 폐기)과 대조해 통과시키고 서비스 호출에는 서비스 키오스크 토큰을 붙인다. 게이트웨이에 닿는 누구나 호출할 수 있는 상태를 없앤다. 병원 내부망 제한은 배포 설정으로 병행한다.
