# 공개 API (I10) — 키오스크 프론트 ↔ 문진 서비스 (D55)
> HTTP 기계 정본: `openapi/survey-service.json`. 데이터 정의는 JSON Schema를 `$ref`로 공유한다.

**독자: 프론트 개발자.** 키오스크 프론트는 이 API만 호출한다. 서버 쪽은 survey-service가 구현한다. 아래는 헤드가 정한 **제안 계약 v1**이며, 프론트 쪽 사정으로 바꿔야 할 점이 있으면 알려 주면 된다.

## 원칙
- 요청-응답 HTTP/JSON(UTF-8). 프론트는 **STT로 음성을 텍스트로 바꾼 문장**을 보낸다. 서버는 음성을 받지 않는다.
- 세션 ID는 **서버가 발급한다**(D106, 2.2.0): `POST /v1/sessions` 본문에서 `session_id`를 생략하면 서버가 CSPRNG로 만든 값을 응답의 `session_id`로 돌려준다(문자열 1~64자, 영문·숫자·`-_`; OWASP 세션 관리 권고: 예측할 수 없는 값, 원문 대조 전). **프론트가 `session_id`를 보내는 방식은 폐기 예정 방식**이다(3.x 에서는 받는다; 3.0.0 제거 약속은 지키지 않았고 제거는 다음 MAJOR 4.0.0). 환자 번호나 개인 식별 정보는 어느 쪽이든 넣지 않는다.
- 인증: 키오스크는 기기 인증서(mTLS, F절), 직원·의사 화면은 사람 로그인(E절, CONVENTIONS 6절, `HumanAuthEndpoints`). 기기 토큰(F-1)은 4.0.0 에서 없앴다(D136).
- 오류는 `BoundaryError` 본문과 상태 코드이고, **클라이언트는 상태 코드로 분기한다**(D66):

| 상태 | `BoundaryError.code` | 뜻 | 재시도 |
| --- | --- | --- | --- |
| 400 | `INVALID_RECORD` | 형식 오류 | 안 함 |
| 401 | `PERMISSION_DENIED` | 로그인 세션 없음(직원·의사 화면), 기기 토큰(호환)·서비스 토큰이 없거나 틀림. 키오스크 기본 인증(mTLS)의 실패는 401 이 아니라 TLS 거부(RUNTIME R3.13) | 안 함 |
| 403 | `PERMISSION_DENIED` | 토큰은 맞지만 그 호출 권한이 없음 | 안 함 |
| 404 | `NOT_FOUND` | 모르는(또는 만료된) 세션 | 안 함 |
| 409 | `CONFLICT` | 순서 어긋남(끝난 세션에 발화, 멈추지 않은 세션에 개입, 같은 `turn_id`에 다른 내용) | 안 함. 단 `details.reason`이 `TURN_IN_PROGRESS`이면(같은 `turn_id`가 아직 처리 중, `Retry-After` 헤더 동봉) 같은 `turn_id`로 `Retry-After` 뒤 다시 보낸다 |
| 429 | `UNAVAILABLE` | 과다 요청 | 함. `Retry-After`(초, 정수)를 따른다 |
| 503 | `UNAVAILABLE` | 일시 불가 | 함. `Retry-After`가 있으면 따르고 없으면 1초 |

## 호출
| 목적 | 요청 | 응답 |
| --- | --- | --- |
| 활성 문진표 목록 (3.3.0, I절) | `GET /v1/question-sets` | `{"items": [{"question_set_id", "title", "version"}]}` 활성 릴리스의 문진표 전부(`ReleaseManifest.question_sets`, 1개 이상). 인증은 `/v1/sessions`와 같다. 활성 릴리스가 없으면(활성 포인터 없음, 또는 적재가 끝난 릴리스가 없음) 503 `UNAVAILABLE` + `details.reason=NO_ACTIVE_RELEASE` + `Retry-After` 다(빈 목록 200 이 아니다). `POST /v1/sessions` 도 같다(3.4.4, 검토 B-01) |
| 세션 시작 | `POST /v1/sessions` 본문 `{"kind": "SESSION_START", "question_set_id"?: "..."}`(`session_id`는 생략한다: 서버가 발급해 응답의 `session_id`로 돌려준다, 위 7행·D106. `question_set_id`(3.3.0, I절): 이 세션의 문진표. 활성 문진표가 하나면 생략 가능, 둘 이상이면 필수. 생략·불일치는 400 `INVALID_RECORD`에 `details.reason` `QUESTION_SET_REQUIRED`·`UNKNOWN_QUESTION_SET`) | `FrontendInput` (`response_text`: 첫 안내 문장, 그 문진표 순서의 첫 문항) |
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
| 알림 실시간 구독 | `GET /v1/staff/alerts/stream` (`text/event-stream`) | 이벤트 이름 `alert`(새 알림), `resolved`(해결), `result_ready`(문진 결과 도착, 3.2.0 U83; B절), `id:`는 이벤트 순번(알림과 해결 이벤트가 각각 증가하는 번호를 받는다). `data:`는 이벤트 이름별 스키마다(3.4.4, 검토 B-05): `alert`·`resolved`는 `StaffAlert`, `result_ready`는 `ResultReadyEvent`, `heartbeat`는 `HeartbeatEvent`, `resync`는 `ResyncEvent`. 스트림은 연결한 계정의 `X-Openit-Roles`로 이벤트를 거른다(B-06, 최소 권한): `staff`에는 `alert`·`resolved`, `clinician`에는 `result_ready`, 둘 다 있으면 둘 다, `heartbeat`·`resync`는 모두에게. 15초마다 `: ping` 주석 줄을 보낸다. 스트림의 최대 수명은 `SURVEY_SSE_MAX_SECONDS`(기본 300초, 시작값·측정 안 함)이고 platform 의 세션 갱신 주기(RUNTIME R3.12) 이하로 둔다(검토 P6-R6-11), 그 시각에 서버가 정상 종료한다: 클라이언트는 새로 연결하고, 인증이 끝났으면 그 연결은 401(RUNTIME R2.4·R3.23, B-08). `EventSource` 는 상태 코드를 알려 주지 않으므로(WHATWG) 연결이 닫혀 다시 열리지 않으면 같은 인증으로 `GET /v1/staff/alerts?status=OPEN&limit=1` 을 한 번 불러 상태와 `Retry-After` 만 읽는다(구독이 아니라서 `staff_alert` 전달 판정에 세지 않는다, 검토 P6-R6-3)(401 → 로그인, 429·503 → `Retry-After` 뒤 새 연결). 끊기면 `Last-Event-ID`로 이어 받는다. 추가 이벤트(하위 호환, 모르는 클라이언트는 무시한다, `id:`가 없어 `Last-Event-ID`를 바꾸지 않는다): `heartbeat`(`data: {"ts": "<UTC ISO>"}`, 연결 직후 한 번과 이후 15초마다(ping 과 같은 주기) — 브라우저 `EventSource`는 주석 줄을 보여 주지 않으므로 앱이 연결 생존을 알 수 있게 한다)와 `resync`(`data: {"reason": "EVENTS_NOT_RESUMABLE"}`, `Last-Event-ID`로 이어 받을 수 없는 재연결에 한 번 — 클라이언트는 `GET /v1/staff/alerts?status=OPEN`으로 다시 맞춘다) |
| 푸시 설정 | `GET /v1/staff/push-config` | `PushConfig`(웹 푸시 공개키). `vapid_public_key`가 null이면 푸시는 꺼져 있고 SSE만 동작한다 |
| 푸시 구독 등록 | `POST /v1/staff/push-subscriptions` 본문 `PushSubscriptionRequest`(웹 푸시 구독 객체 `endpoint`, `keys`와 선택 `topics`; `endpoint` 는 https·포트 443·공인 주소만, 아니면 400 `INVALID_RECORD` — SSRF 방지, RUNTIME R3.18)(3.4.0: `["alerts"]`·`["results"]`·둘 다, 없으면 `["alerts"]`. `alerts`는 staff 역할, `results`는 clinician 역할만 등록할 수 있고 다른 역할이면 403) | 201. 같은 `endpoint`는 갱신(멱등). 해지는 `POST /v1/staff/push-subscriptions/unsubscribe` 본문 `{"endpoint": "..."}`(2.2.0, 204. 푸시 엔드포인트 URL은 그 자체가 푸시 권한을 주는 값이라 URL에 싣지 않는다). `DELETE /v1/staff/push-subscriptions?endpoint=`는 폐기 예정 방식이다(3.x 에서는 받는다; 3.0.0 제거 약속은 지키지 않았고 제거는 다음 MAJOR 4.0.0, CONVENTIONS 1절 2항) |
| 개입 결정 | `POST /v1/sessions/{session_id}/intervention` 본문 `{"session_id", "decision": "RESUME"\|"END", "turn_id": "..."}` | `FrontendInput` (RESUME이면 이어서 할 안내 문장, END면 종료) |

- `StaffAlert`: `alert_id`, `session_id`, `kind`(알려진 값 `RISK_STOP`, `CALL_STAFF`, `USER_CALLED_STAFF`. 모르는 값은 그대로 보여 줌. 목록 `StaffAlert`와 세션 보기 `StaffSessionView.alerts[]`는 같은 이름을 쓴다. `pause_reason`의 `RISK`와는 다른 필드다), `created_at`, `status`(`OPEN`/`RESOLVED`), `resolved_by_decision`(`RESUME`/`END`/null), `resolved_at`. 환자 발화나 개인 정보는 담지 않는다(세션 ID와 종류만).
- 위험으로 멈춘 세션은 유휴 만료로 닫지 않는다(직원이 처리할 때까지 유지).
- 위험 정지가 나면 서버는 알림을 영속 저장하고 구독자(SSE, 웹 푸시)에게 보낸다. 개입 결정이 성공하면 해당 알림이 `RESOLVED`가 된다.
- `TurnFailureSignal.staff_alert`: 알림이 저장되고 **전달 경로가 하나 이상 살아 있을 때**(SSE 연결 또는 푸시 서비스가 접수) `DELIVERED`, 아니면 `DELIVERY_FAILED`다. 저장된 알림은 `DELIVERY_FAILED`여도 목록에서 조회된다. 프론트는 `DELIVERY_FAILED`이면 현장 직원 호출 화면을 보여야 한다.
- 웹 푸시의 서버 키(VAPID)는 비밀 값이며 파일로만 받는다(`SURVEY_VAPID_PRIVATE_KEY_FILE`, D84). 푸시 본문에는 세션 ID와 종류만 넣는다. 발송 실패 처리는 RUNTIME R3.18.
- 직원·의사 화면의 SSE 연결: 브라우저 `EventSource` 는 200 이 아닌 응답이면 연결을 닫고 스스로 다시 잇지 않는다(WHATWG HTML Server-sent events). 클라이언트는 연결이 닫히면(readyState CLOSED) 지수 백오프로 새로 연결하고, 401 이면 로그인으로, 429·503 이면 `Retry-After` 를 따른다. 서버는 동시 SSE 연결 상한(서비스 설정)을 넘으면 429 `UNAVAILABLE` + `Retry-After` 로 거절한다.
- `turn_id` 규칙은 발화와 같다(같은 값 재전송은 같은 응답). 멈추지 않은 세션에 개입을 보내면 409.

## 프론트가 지킬 것
- STT 결과가 비었거나 신뢰할 수 없으면 서버로 보내지 않고 "다시 말씀해 주세요"를 프론트에서 안내해도 된다.
- 응답이 없거나 일시 장애(429·502·503·504·네트워크 오류)면 같은 `turn_id`로 지수 백오프(지터 포함)로 재시도하고, 총 재시도 예산(120초 = 대기의 2배, CONVENTIONS 시간 상한 사슬 D125)을 넘기면 직원 호출 화면을 보인다. 요청 타임아웃(키오스크 대기)은 60초다(D125, D119 대체). 401(기기 인증 실패)은 재시도로 풀리지 않으므로 재시도 없이 직원 호출 화면을 보인다(RUNTIME R3.13).
- 408 을 받거나 요청이 한도 안에 도착하지 못해 연결이 끊기면 일시 장애와 같다(같은 `turn_id`, 위 재시도 규칙). 413·414·431 은 재시도하지 않고(같은 요청은 같은 결과) 401 과 같이 직원 호출 화면을 보인다(RFC 9110 15.5.9·15.5.14, RUNTIME R3.5·R3.6·R3.17).
- 한 세션의 요청은 순서대로 하나씩 보낸다(동시에 두 턴을 보내지 않는다).
- 200 이고 `turn_failure_signal.write_committed=NOT_COMMITTED` 이면(RUNTIME R3.20) 일시 장애와 같게 같은 `turn_id` 로 재시도한다(총 예산 120초 뒤 직원 호출 화면). 400·403·404·409(`TURN_IN_PROGRESS` 제외; 이것은 잠시 뒤 같은 `turn_id` 로 재시도)·422 는 재시도 없이 직원 호출 화면을 보이고, 다음 환자는 새 세션으로 시작한다(같은 요청은 같은 결과, 검토 A-18).

## 정한 값 (3.4.4: 이전의 "아직 정하지 않은 것" 절을 닫음, 검토 A-18·A-26)
- 서비스 주소: 키오스크·화면은 같은 출처의 platform 공개 입구 상대 경로를 쓴다. 자격 전달: 키오스크는 기기 인증서(F절), 사람 화면은 로그인(E절, `HumanAuthEndpoints`).
- 세션 유휴 만료: `SURVEY_SESSION_IDLE_SECONDS` 기본 300초(5분; 시작값, 측정 안 함 — 접수 대기 중 자리를 비우는 경우를 고려한 값이며 근거 표준 없음). 만료된 세션의 요청은 404 이고 키오스크는 위 규칙대로 직원 호출 화면.

---

# 추가 인터페이스 (2026-10-27, D85: 사용자 지시와 표준안)

아래는 서비스(survey-service), 게이트웨이(deploy), 프론트(kiosk-frontend, admin-console), 게이트(release-gate)가 같은 모양으로 구현하는 합의다. 세션 응답 스키마는 survey-service의 문진 스키마(`schema/schemas/`)에 둔다.

## A. 환자 참조 `subject_ref` (세션 시작)
- `POST /v1/sessions` 본문에 선택 필드 `"subject_ref"`: 병원이 정한 **불투명 문자열**(환자·방문을 가리키는 참조, 1~128자, `[A-Za-z0-9._:/#=+-]`). 서비스는 의미를 해석하지 않는다. 프론트가 시작 때 가지고 있는 값(병원 접수가 키오스크를 띄울 때 넘긴 값)을 그대로 보낸다.
- 서비스는 세션별로 저장한다(세션 문서 스키마를 바꾸지 않고 세션 메타로). 설정 `SURVEY_REQUIRE_SUBJECT_REF`가 켜져 있으면 없을 때 400(`INVALID_RECORD`). 기본은 꺼짐(데모용).
- `subject_ref`는 환자를 식별하는 값이다: 로그·알림 본문·푸시에 넣지 않고, 아래 조회 API와 접근 기록(세션 ID 기준)에서만 다룬다.

## B. 결과 조회 API (병원/의사 시스템용)
3.2.0(U83, 사용자 결정 2026-11-03): 문진 결과는 **의사가 본다**. 게이트웨이는 아래 읽기 두 경로와 확인 표시 경로를 역할 `clinician`(사람 계정, Exposure kind account)에 열고, 상류에는 `result-reader` 토큰을 붙이고 `X-Openit-User`(인증 계정)를 넘긴다. 다른 역할·무인증은 403/401. 결과 화면은 admin-console 의 "문진 결과" 탭(목록·상세·인쇄·확인 표시). FHIR `QuestionnaireResponse` 내보내기는 EMR 연동 옵션으로 다음 판.
- 확인 표시: `POST /v1/results/{session_id}/ack` 본문 `{}` → `SessionResult`(갱신본). 결과에 `acknowledged_by`(계정 ID, 게이트웨이의 X-Openit-User)·`acknowledged_at`(ISO)이 채워진다(문진 스키마 SessionResult 의 선택 필드, 정수 버전 1 호환 추가). 두 번째 호출은 멱등(처음 값 유지).
- 도착 알림: 세션이 `ENDED_*` 로 끝나면 직원·의사 콘솔 SSE(`GET /v1/staff/alerts/stream`)에 이벤트 `result_ready`(본문 `{"session_id", "status", "ended_at"}`; subject_ref 는 넣지 않는다)를 보낸다. 같은 때 `topics`에 `results`가 있는 푸시 구독자(clinician)에게 웹 푸시 `StaffPushPayload{session_id, kind: "RESULT_READY"}`를 보낸다(3.4.0, U92: 화면을 닫은 의사도 도착을 안다). 본문에 subject_ref·결과 값은 넣지 않는다. 발송 실패는 직원 알림과 같은 재시도 규칙을 따른다. 콘솔이 SSE 에서 `resync`(`EVENTS_NOT_RESUMABLE`)를 받으면 직원 알림은 `GET /v1/staff/alerts?status=OPEN`, 결과 도착은 `GET /v1/results?updated_after=<마지막으로 받은 heartbeat 의 ts>` 로 다시 맞춘다. `updated_after` 는 세션 결과가 마지막으로 바뀐 시각(상태 변경·답 확정·확인 표시 포함)이 그 값보다 뒤인 결과만 뜻한다(3.4.4).
- 접근 기록: 결과 읽기·확인 표시마다 아래 접근 기록(계정 ID 포함)을 남기고 보존 365일(감사 기록).
역할 `result-reader` 토큰(상류·기계용). 이 역할은 `GET /v1/results*` 와 `POST /v1/results/{session_id}/ack` 를 부를 수 있다: ack 는 결과 값을 바꾸지 않고 확인 표시(`acknowledged_by`·`acknowledged_at`)만 더하는 쓰기라서 읽기 역할에 함께 둔 예외다(HTTP.md 공통 읽기/쓰기 구분의 예외, 3.4.4 검토 B-17). 호출마다 접근 기록(시각, 역할 이름, 게이트웨이가 인증한 행위자 `X-Openit-User`가 있으면 그 계정 ID, session_id 또는 조회 조건, 결과; 토큰·발화 제외)을 남기고, 기록을 못 남기면 데이터를 주지 않는다(503).
- `GET /v1/results/{session_id}` → `SessionResult`: `{"session_id", "subject_ref": str|null, "status": "IN_PROGRESS|PAUSED_RISK|ENDED_COMPLETE|ENDED_STAFF|ENDED_LEFT|ENDED_USER_STOP", "started_at": ISO|null, "ended_at": ISO|null, "release_id": str|null, "question_set_id": str|null, "question_set_title": str|null, "question_bank_version": str|null, "answers": [{"key","value","status","precision"}], "skipped_details": [{"item", "slot"?, "reason": "UNKNOWN|REJECTED|UNCLEAR|REASK_LIMIT|..."}]}`. 끝나지 않은 세션과 직원·이탈로 끝난 세션의 **부분 결과도 상태와 함께** 돌려준다. 환자 발화 원문과 대화 로그는 포함하지 않는다(직원 세션 조회에만 있다).
- **`status`의 뜻** (survey-service CR-014 반영): `ENDED_COMPLETE` 문진을 끝까지 마침(**완료는 이것뿐**). `ENDED_LEFT` 환자가 끝나기 전에 떠남(키오스크 종료 요청 또는 유휴 만료). `ENDED_STAFF` 직원이 종료. `ENDED_USER_STOP` 예약된 값으로 지금 만들어지지 않는다. `IN_PROGRESS`·`PAUSED_RISK` 아직 끝나지 않음. 완료가 아닌 상태의 `answers`는 그때까지 저장된 부분 결과이고, `skipped`는 건너뛴 문항 ID일 뿐 미응답 문항 목록이 아니다. 완료 여부는 `status == "ENDED_COMPLETE"`로만 판단한다.
- `GET /v1/results?subject_ref=&status=&updated_after=&limit=&cursor=` → `{"items": [SessionResult], "next_cursor": str|null}` (`limit` 기본 50 최대 200).
- 빈칸 사유(3.2.0, U36·G12·U35): 같은 문항을 3번 되물어도 답을 얻지 못하면 직원을 부르지 않고 그 칸을 빈칸으로 두고 다음 문항으로 간다. 사유는 `skipped_details[].reason`(UNKNOWN 모름, REJECTED 거부, UNCLEAR 모호, REASK_LIMIT 되묻기 한도 뒤 빈칸)에 남는다. 문진 스키마 SessionResult 가 정본.
- 오류: 401/403(`PERMISSION_DENIED`), 404(`NOT_FOUND`), 400(`INVALID_RECORD`), 503(`UNAVAILABLE`).
- 결과를 EMR 로 **밀어 넣는** 전달기(FHIR QuestionnaireResponse push)는 연동 옵션이며 수신처가 정해지면 붙인다(다음 판). `/readyz`의 `result_dispatcher`는 그때까지 `attached:false, status:NO_TARGET`.

## C. 직원 세션 조회 (CR-013 반영)
`GET /v1/staff/sessions/{session_id}` (역할 staff) → `StaffSessionView`. 모양의 정본은 문진 스키마 `StaffSessionView`(헤드 목록 EXTERNAL_SCHEMAS.json, 3.4.4 검토 B-20; 다른 리포의 변경 요청 문서를 정본으로 삼지 않는다)이고, 아래 두 가지를 더한다: 응답 최상위에 `"subject_ref": str|null`, `alerts[]`에 `"resolved_by": str|null`(해결한 직원 ID). 시각·turn_id가 null일 수 있고 `values[].status`는 `ANSWERED|CORRECTION`이라는 CR-013의 제안을 채택한다.

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
- 인증 방식은 OIDC(SSO)이고 platform 의 계정 관리(Keycloak)가 끝낸다(CONVENTIONS 6절, 3.4.0). 로그인·로그아웃·계정 관리 경로는 `HumanAuthEndpoints`, 로그인 사용자 정보는 `HumanUserInfo` 다.

## F. 키오스크 기기 인증
- **기기 인증은 게이트웨이의 클라이언트 인증서 검증(mTLS) 하나다(ADR 0012, D113; 4.0.0 D136 에서 기기 토큰 F-1 을 없앴다).** 공개 입구는 신뢰할 기기 CA(PublicIngressEnv.INGRESS_DEVICE_CA_FILE)로 TLS 에서 인증서를 검증하고, 키오스크 경로(Exposure auth `device`, `/v1/sessions*`·`/v1/question-sets`)의 요청마다 인증서의 주체 CN(=기기 ID)과 일련번호를 허용 목록(계약 `DeviceAllowlist`, INGRESS_DEVICE_ALLOWLIST_FILE)과 대조한다.
- 인증서의 발급·갱신과 기기에 넣는 일은 조직의 PKI/기기 관리(MDM) 몫이다(이 프로젝트는 시험·데모용 일회용 CA 도구만 둔다). **등록·회전·폐기는 허용 목록을 바꾸는 것이다:** 등록 = 항목 추가, 회전 = 같은 기기 ID 에 새 일련번호를 더한 뒤 옛 것을 뺀다, 폐기 = 항목이나 일련번호를 뺀다. 인증서 파일을 지우는 것만으로는 이미 발급된 인증서가 무효가 되지 않는다. 대조는 요청마다 하므로 목록에서 빠진 인증서는 이미 열린 TLS 연결에서도 다음 요청부터 거부된다.
- 출력: (1) 신뢰 CA 가 아니거나 만료·아직 유효 전·서명이 틀린 인증서는 TLS 핸드셰이크에서 거부된다(HTTP 응답 없음, RUNTIME R3.13). (2) 인증서 없이, 또는 허용 목록에 없는 인증서로 키오스크 경로를 부르면 공개 입구가 `403 PERMISSION_DENIED`(BoundaryError 본문)를 낸다 — 401 이 아니다: TLS 인증서는 HTTP 인증 challenge(RFC 9110 11.6.1 WWW-Authenticate)로 다시 낼 수 있는 자격이 아니기 때문이다.
- 게이트웨이는 클라이언트가 보낸 `X-Openit-Device`를 지우고, 통과한 요청에만 CN 을 `X-Openit-Device: <device_id>`(`^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$`)로 붙여 서비스에 넘긴다. 서비스(survey-service)는 이 값을 믿고(서비스는 게이트웨이 뒤 내부망에만 있다, ADR 0005) 세션을 만든 기기 ID만 그 세션에 접근시킨다(다른 기기는 404). 서비스에는 기기 자격 표가 없다.
- 키오스크 앱은 기기 자격을 보내지 않는다(브라우저가 TLS 에서 인증서를 낸다). `boundary_contracts.clients.HttpPublicApi`는 게이트웨이를 거칠 때 자격 없이 부른다. `device_id` 인자는 게이트웨이 토큰(CONVENTIONS 6절)과 함께일 때만 효과가 있다(서비스는 그 밖의 토큰의 `X-Openit-Device` 를 무시한다, CONVENTIONS 6절, 검토 A-25).
- 게이트웨이→서비스의 서비스 토큰(기계 대 기계)과 직원 계정 인증(OIDC)은 이 절의 범위가 아니며 그대로다.

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
- 값: `RISK`(위험 신호로 정지), `REASK_LIMIT`(되묻기 한도 N 초과로 정지, D95; 3.2.0 부터 새로 내지 않음 — 되묻기 한도 뒤에는 빈칸으로 두고 넘어간다(B절). 옛 기록·호환용), `OTHER`(그 밖). **읽는 쪽은 모르는 값과 값이 없는 경우를 `OTHER`/미상으로 취급한다**(열거 확장 대비).
- 붙는 곳(모두 optional): `SessionState`(`GET /v1/sessions/{id}/state`, `state=PAUSED_RISK`일 때만 의미가 있고 그 밖의 상태에서는 null/생략), `StaffAlert`, 직원 세션 조회 `StaffSessionView`, 그리고 `TurnFailureSignal`.
- `TurnFailureSignal`과 `StaffSessionView`는 문진 스키마(`../survey-service/schema`, survey-service 소유)에 있으므로 **이 리포가 고치지 않는다.** 이 문서가 정한 필드 이름·열거 값(`pause_reason`: `RISK|REASK_LIMIT|OTHER`, optional)을 survey-service가 자기 스키마에 반영한다(D21). `SessionState`·`StaffAlert`는 이 리포 스키마다.
- 상태 이름 `PAUSED_RISK`는 바꾸지 않는다(MAJOR가 되고 `SessionResult.status` 소비자가 깨진다). `SessionResult.status` 규약도 그대로다.
- 새 클라이언트 + 옛 서버는 필드가 없으므로 미상으로 폴백한다.

## I. 문진표 선택 (3.3.0, 사용자 결정 2026-11-03)
배포는 문진표(문항 세트)를 여러 개 함께 운영한다(`ReleaseManifest.question_sets`). 어느 문진표로 문진할지는 **배치된 값이 정한다**(접수·기기 배치; 배치가 없을 때만 키오스크 선택 화면에서 현장 사람(환자 또는 접수 직원)이 고른다, 검토 A-20).
- 기기에 배치된 문진표가 기본이다: `DeviceConfig.question_set_id`(deploy 기기 설정) 또는 시작 URL 조각 `#...&question_set_id=`(`KioskStartFragment`, 조각이 먼저).
- 키오스크는 시작 전에 `GET /v1/question-sets`로 활성 목록을 받는다. 정한 값이 목록에 있으면 그대로 `SESSION_START.question_set_id`로 보낸다. 정한 값이 없고 목록이 하나면 그것으로 시작하고(생략 가능), 둘 이상이면 선택 화면(제목 목록)을 보이고 고른 값을 보낸다. 정한 값이 있으나 목록에 없으면 그 값을 보내지 않고 정한 값이 없는 경우와 같이 한다(하나면 그것, 둘 이상이면 선택 화면). 그 값으로 이미 보내 400 `UNKNOWN_QUESTION_SET` 을 받았으면 목록을 다시 받아 같은 처리를 한 번 하고 같은 값으로 재시도하지 않는다. 목록 요청이 503 `NO_ACTIVE_RELEASE` 면 시작할 수 없다는 안내를 보이고 `Retry-After` 뒤 다시 받는다(3.4.4, 검토 B-01·B-02).
- 서비스는 그 문진표의 문항 `order`·`prerequisite`로 첫 문항·다음 문항·끝을 정한다(고정 흐름 파일은 없다, 계약 `QuestionFlowTable` 설명). 결과(`SessionResult`)와 직원 세션 조회에는 `question_set_id`·`question_set_title`·`question_bank_version`이 있어 의사 화면이 어느 문진표인지 보인다.
- 문항·칸 **구조**가 다른 문진표는 게이트가 거절한다(U81: 모델은 학습한 구조만 다룬다). 질문 문장·순서·건너뛰기만 다른 문진표는 재학습 없이 운영한다.
