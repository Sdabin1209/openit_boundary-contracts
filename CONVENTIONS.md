# 공통 규약

영역 사이 호출(SDK와 서비스 API)이 모두 따르는 규칙이다. 영역 에이전트는 상대 영역을 블랙박스로 보고 이 규약과 `INTERFACES.md`만 믿고 개발한다. 이 규약은 소유자인 헤드만 바꾼다.

## 1. 계약이 다시 뜯기지 않게 하는 규칙

1. **확장 필드.** 모든 레코드에는 선택 필드 `ext`가 있다. 영역은 자기가 쓰는(주인인) 레코드에 한해 새 정보를 `ext.<영역 이름>`에 계약 변경 없이 덧붙인다. 남의 레코드에는 `ext` 키를 더하지 않는다(쓰는 영역은 하나, 6절·DATA_OWNERSHIP.md; 3.4.6). 읽는 영역은 `ext`를 이해하지 못해도 **보존하고 전달**해야 하며(복사·재게시 때 지우지 않는다), 판단에 쓰지 않는다. 여러 영역이 판단에 필요로 하게 되면 정식 필드로 올린다(MINOR).
2. **MINOR는 추가만 한다.** 선택 필드 추가, 열거값 추가, 허용 범위 확대만 MINOR다. 필수 필드 추가, 필드 삭제·이름·의미 변경, 허용 범위 축소는 MAJOR다. 의미를 바꾸려면 새 필드를 만들고 옛 필드는 유지한다.
3. **쓸 때는 엄격하게, 읽을 때는 관대하게.** 레코드를 만드는 쪽은 자기가 아는 버전의 스키마(`additionalProperties: false`)로 검증한 뒤 쓴다. 읽는 쪽은 같은 MAJOR이면 모르는 필드를 무시하고, **모르는 열거값은 오류로 죽지 않고 '알 수 없음'으로 처리**한다. 읽는 쪽의 SDK는 이 관대한 읽기를 기본으로 제공한다.
4. **MAJOR는 병행 기간을 둔다.** MAJOR를 올릴 때 소유자는 이전 MAJOR를 읽는 경로를 한 릴리스 주기 동안 유지한다. **예외: 2.0.0(D74)은 병행 없이 v1 형식을 폐기했다.** v1 계약이 기술하던 단계(파서·정규화기·판정기·Plan)가 없어졌고 학습된 모델은 v2 형식만 말하며 운영 데이터가 아직 없는 데모 단계이기 때문이다. v1.3.3은 Git 태그로 남는다. 클라이언트는 MAJOR 1의 레코드를 `UNSUPPORTED_VERSION`으로 거부한다. **3.3.0 도 같은 예외다(3.4.4 에 기록, 검토 B-13):** 필수 필드 추가(`ReleaseManifest.question_sets`)와 필드 삭제(`question_set`·`QuestionFlow`)를 포함해 이 절 2항으로는 MAJOR 였으나, 데모 단계(운영 데이터 없음)라 MINOR 로 냈고 병행 기간 없이 3.2.x 레코드를 읽지 않는다. 다음부터는 이 예외를 쓰지 않는다.
5. **모든 레코드는 불변이다(D25).** 고치지 않고 새 ID나 새 버전을 만든다.

## 2. 식별자·시각·해시

- ID는 `[A-Za-z0-9][A-Za-z0-9._:-]*`, 최대 128자. 의미를 담지 않는다.
- 시각은 UTC `Z` 표기의 RFC 3339 문자열이다.
- 해시는 `sha256:` + 소문자 16진 64자이며, 대상 JSON을 RFC 8785(JCS)로 정규화한 바이트의 SHA-256이다. 파일은 바이트 그대로 해시한다. `content_hash` 필드가 있는 레코드는 자기 자신의 `content_hash`를 뺀 객체를 해시한다.
- **해시는 기준 구현 `boundary_contracts.canonical`(`sha256_hash`, `content_hash`, `file_hash`, `directory_hash`)로만 계산한다.** SDK와 서비스는 자기 구현을 두지 않는다. 숫자 직렬화와 키 정렬을 구현마다 다르게 하면 해시가 어긋난다. 정수는 절댓값 2**53 이하만 허용한다. 디렉터리 해시는 파일마다 {경로, 파일 해시}를 모아 경로 순으로 정렬한 목록의 JCS 해시다. 개발 중에는 `PYTHONPATH=../boundary-contracts`로 가져온다.
- `ArtifactRef`(id, version, content_hash)로 가리킨 것을 읽을 때, 읽는 쪽 SDK는 내용의 해시를 다시 계산해 다르면 `INTEGRITY_ERROR`를 낸다.

## 3. 오류 (`BoundaryError`)

모든 경계 호출의 실패는 `BoundaryError`다. 호출자는 `code`와 `retryable`로만 행동한다.

| code | 뜻 | retryable |
| --- | --- | --- |
| NOT_FOUND | 대상이 없다 | false |
| INVALID_RECORD | 보낸 레코드가 스키마를 위반한다 | false |
| UNSUPPORTED_VERSION | 계약 버전을 지원하지 않는다(MAJOR 불일치, 문진 스키마 정수 불일치) | false |
| CONFLICT | 같은 ID에 다른 내용을 쓰려 했거나, 요청이 대상의 현재 순서·상태와 어긋난다(PUBLIC_API 409, HTTP.md I5) | false |
| INTEGRITY_ERROR | 해시가 맞지 않는다 | false |
| FAILED_PRECONDITION | 지금 상태에서는 할 수 없다(예: 통과하지 않은 릴리스 활성화) | false |
| PERMISSION_DENIED | 권한이 없다 | false |
| UNAVAILABLE | 일시적으로 처리할 수 없다 | true |

SDK는 `BoundaryError`를 예외로 던진다. 메모리 구현도 같은 예외를 같은 조건에서 던져야 한다.

**생산자 출력 검증(ADR 0010 R7 — RUNTIME 의 R7.x 와 다른 번호다; 2026-10-31 문서 보충, 스키마 변경 없음)**: 값을 만드는 쪽은 내보내기 전에 계약 스키마로 검증하고, 어기면 그 값을 내보내지 않는다. HTTP 응답은 503 `UNAVAILABLE`(서버 결함), 잡·CLI 출력은 표준 출력을 비우고 0이 아닌 종료 코드로 끝낸다. 잡 출력 스키마가 종료 코드를 열거하는 경우(예: `SurveyPurgeOutput`의 0·2·3) 이 '계약 출력 위반'은 그 목록 밖의 값(survey-service는 4)이며, 읽는 쪽은 0이 아닌 모든 값을 실패로 다룬다. 받는 쪽은 다시 검증하지 않는다.

## 4. 쓰기의 멱등성

- 같은 ID(또는 ID+버전)와 같은 내용(같은 `content_hash`)으로 다시 쓰면 성공이고 기존 것을 돌려준다.
- 같은 ID에 다른 내용이면 `CONFLICT`다.
- 쓰는 쪽은 쓰기 전에 스키마로 검증한다. 받는 쪽도 검증하며, 위반이면 `INVALID_RECORD`다.
- 호출자는 `UNAVAILABLE`일 때만 재시도한다. 재시도해도 결과가 같다는 것이 위 규칙으로 보장된다.
- **POST 의 멱등은 이 절의 규칙이다(3.4.4, 검토 A-29).** RFC 9110 9.2.2 의 멱등 메서드는 PUT·DELETE·안전 메서드이고 POST 는 포함되지 않는다. 게시·제출·등록(POST)이 재전송에 안전한 근거는 위 내용 해시 비교 규칙이다.
- **동시 도착(3.4.4).** 같은 ID(+버전)에 대한 쓰기 둘이 동시에 도착해도 결과는 둘을 어떤 순서로든 하나씩 처리한 것과 같다: 하나가 만들고 나머지는 같은 내용이면 200, 다르면 409 `CONFLICT`. 저장소의 유일 제약 경합을 503 으로 내지 않는다(직렬화 가능성: 결과가 어떤 순차 실행과 같다).
- **예외: 턴 기록 수집(I6).** 같은 (session_id, turn_id)의 `TraceEnvelope` 가 다시 오면 내용이 달라도 200 `IngestResult{status:"DUPLICATE"}` 이고 먼저 받은 것을 유지한다(409 아님). 수집은 최소 한 번 전달이라 보내는 쪽이 재전송에 안전해야 한다.

## 5. 목록과 페이지

목록 호출은 `(items, next_cursor)`를 돌려준다. `next_cursor`가 `None`이면 끝이다. 정렬은 호출마다 명세에 적힌 기준이며, 새 항목은 뒤에 붙는다(과거 항목의 순서는 바뀌지 않는다).

## 6. 인증과 권한 (단일 서버 기준)

- 서비스 사이 호출은 `Authorization: Bearer <서비스 토큰>`이고 토큰은 파일로 받는다(D84: `NAME_FILE`에 경로를 주고 `boundary_contracts.secrets.read_secret(NAME)`으로 읽는다. 환경 변수 `NAME`은 개발·시험용 호환일 뿐이며 운영에서는 쓰지 않는다). 읽기 SDK는 읽기 전용 토큰, 쓰기는 소유 영역의 토큰만 쓴다.
- 저장소의 쓰기 권한은 소유 영역 하나에만 있다(경계 규칙 1). 데이터마다 주인과 쓰기·읽기 경로는 DATA_OWNERSHIP.md 가 정본이다. 다른 영역의 DB 계정은 없다(13절, 3.4.4 검토 A-31).
- 공개 API 의 인증은 PUBLIC_API.md F절(기기)·E절(사람)과 이 문서 6절·9절이 정한다(3.4.4 검토 A-32).
- **사람 신원과 역할(3.4.0, U82, head ADR 0014).** 사람 인증은 게이트웨이가 표준 IdP(Keycloak, OIDC)로 끝낸다. 게이트웨이는 인증을 마친 요청에 `X-Openit-User: <사용자 ID>`와 `X-Openit-Roles: <역할 쉼표 목록>`을 붙이고, 클라이언트가 보낸 같은 이름의 헤더는 지운다. 역할 이름은 고정 목록 `staff`, `operator`, `release-approver`, `reviewer`, `author`, `clinical-reviewer`, `clinician`, `admin`이다(IdP 그룹 이름과 같다). 사용자별 역할이 필요한 서비스는 자체 설정(사용자→역할 표)을 두지 않고 `X-Openit-Roles`를 읽는다. 역할이 하나도 없는 인증 사용자(가입 승인 대기)는 `Exposure.auth.kind=authenticated` 경로와 계정 관리 화면을 뺀 모든 경로에서 게이트웨이가 403 으로 막는다. 본문은 `BoundaryError` 전체 필드(`pipeline_schema_version`·`code`=`PERMISSION_DENIED`·`message`·`retryable`=false)이고 `details.reason`=`ACCOUNT_PENDING_APPROVAL` 이다(RUNTIME R3.24). 게이트웨이는 모든 경로에서(인증 여부·`Exposure.auth.kind` 와 무관하게) 클라이언트가 보낸 `X-Openit-User`·`X-Openit-Roles`·`X-Openit-Device` 를 지운다. 사람 경로만 인증 뒤에 `X-Openit-User`·`X-Openit-Roles` 를, 기기 경로만 `X-Openit-Device` 를 붙인다(OWASP ASVS 4.1.3 신뢰 경계, 검토 B-19). 서비스는 `X-Openit-User`·`X-Openit-Roles`·`X-Openit-Device` 를 **게이트웨이 토큰**(platform 공개 입구가 그 서비스로 넘길 때 붙이는 토큰 = 그 서비스의 `Exposure.routes[].upstream_token` 으로 선언된 토큰 전부; 서비스는 자기 설정에서 어느 토큰이 그것인지 안다, 새 환경 변수는 없다; 3.4.5 정정 — 3.4.4 의 '역할 이름 gateway' 는 서비스마다 토큰 파일 구성이 달라 맞지 않았다, survey-service 담당이 찾음)이 붙은 요청에서만 쓰고, 그 밖의 토큰으로 온 요청의 같은 이름 헤더는 무시한다. 사람 요청의 권한은 `X-Openit-Roles` 가 정하고, 본문의 `requested_by_role` 은 기록용이며 헤더 역할과 다르면 `PERMISSION_DENIED` 다. 기계 호출(서비스 역할 토큰)의 권한은 토큰 역할이 정한다(검토 A-6·A-25). 계약 클라이언트의 `user=`·`device_id=` 인자는 이 `gateway` 역할 토큰과 함께일 때만 효과가 있다.

## 7. SDK의 형태

- 언어는 Python 3.10 이상, 배포는 Git 태그(D18).
- 각 SDK는 (1) `typing.Protocol`로 쓴 인터페이스, (2) 실제 구현, (3) 같은 인터페이스를 지키는 **메모리 구현**을 함께 낸다. 메모리 구현은 오류·멱등성·해시 검증까지 실제 구현과 같게 동작해야 한다.
- 이웃 영역은 메모리 구현으로 혼자 시험한다. 실제 구현과 메모리 구현은 같은 적합성 테스트를 통과해야 한다.
- 생성자는 설정을 인자로만 받고 환경 변수는 읽지 않는다. 읽는 곳은 서비스의 진입점이다.

## 8. 파일 형식

- 데이터셋 파일은 JSON Lines(UTF-8, 한 줄에 샘플 하나)다.
- 문항 세트(`QuestionBank`)와 FailureCase의 비식별 Trace는 JSON이다.
- 어댑터는 디렉터리이며 `adapter_hash`는 `directory_hash`다. **심볼릭 링크는 허용하지 않는다**(2.2.0, release-gate 점검 RG: 해시 계산은 링크가 가리키는 파일을 포함하고 번들 tar는 링크를 뺐기 때문에 받는 쪽 해시가 어긋날 수 있었다). 해시를 계산하는 쪽도 tar를 만드는 쪽도 파일이든 디렉터리든 링크를 만나면 `INTEGRITY_ERROR`로 거부한다. `boundary_contracts.canonical.directory_hash`의 코드 반영은 2.2.0 릴리스에 묶는다.

## 9. HTTP 전송 규약 (서비스 API)

SDK의 원격 구현과 서비스 API가 같은 규칙을 쓴다.
- 본문은 JSON, 인증은 `Authorization: Bearer <서비스 토큰>`이다. 토큰은 파일로 받고(D84, 위 6절), 서버가 토큰에 **역할을 묶어** 둔다. 호출자가 역할을 주장하지 못한다. 토큰 발급·회전은 단일 서버에서는 정적 토큰으로 시작하고 deploy가 비밀 값으로 관리한다.
- 모든 서비스는 `GET /healthz`, `GET /readyz`를 둔다. `/healthz`·`/readyz`·`/metrics` 는 인증이 없다(접근 통제는 망: 영역 게이트웨이로만 닿고 platform 공개 입구에 열지 않는다; RUNTIME R5.1·R10.11, 검토 A-33).
- 실패는 `BoundaryError` 레코드를 본문으로 낸다. 상태 코드는 다음으로 고정한다.

| BoundaryError.code | HTTP |
| --- | --- |
| INVALID_RECORD | 400 |
| PERMISSION_DENIED | 403 |
| NOT_FOUND | 404 |
| CONFLICT | 409 |
| FAILED_PRECONDITION | 412 |
| UNSUPPORTED_VERSION, INTEGRITY_ERROR | 422 |
| UNAVAILABLE | 503 |

HTTP 층의 보충 규칙(PUBLIC_API.md의 표가 공개 API의 정본이다):
- **전송 계층 한도(2.2.2):** 본문이 상한을 넘으면 413, 요청 줄이 너무 길면 414, 헤더가 너무 크면 431이다(RFC 9110 15.5.14·15.5.15, RFC 6585 5). 이 응답은 HTTP 서버(예: waitress)가 앱을 부르기 전에 낼 수 있어 본문이 `BoundaryError`가 아닐 수 있다. 클라이언트는 본문과 무관하게 `INVALID_RECORD`(재시도 안 함)로 읽는다(`details.http_status`). 서비스는 상한 값을 자기 ADR에 적는다. 서버가 본문을 읽지 않고 413을 보낸 뒤 닫아 클라이언트의 본문 쓰기가 끊겨도, 클라이언트는 응답을 읽어 같은 규칙을 지킨다(2.4.2, RFC 9112 9.5).
- **원래 상태 코드(2.4.2):** HTTP 오류 응답에서 만든 `BoundaryError`는 `details.http_status`에 원래 상태를 담는다(예: 같은 `PERMISSION_DENIED`의 401과 403 구분).
- **401과 403(두 종류의 API 모두 같은 규칙이다).** (1) **공개 API**(`PUBLIC_API.md`: 키오스크·직원 콘솔이 부르는 문진 서비스): 토큰이 없거나 틀리면 401, 토큰은 맞지만 그 호출 권한이 없으면 403이다. (2) **영역 사이 서비스 API**(`HTTP.md`의 I1~I9: 출고 게이트, 모델 등록소, 모델 서버, 운영 기록, 문항 저작): 공개 API와 같다. **토큰이 없거나 틀리면 401**이고 응답에 `WWW-Authenticate: Bearer`를 싣는다. 토큰은 맞지만 그 호출 권한이 없으면 403이다(RFC 9110 15.5.2·11.6.1, RFC 6750 3절; 2026-10-29에 D106로 정함. 이전에는 토큰이 없거나 틀린 경우도 403이었다). 사람 행위자가 필요한 `POST /v1/approvals`·`activate`·`rollback`·`cases/{id}/review`는 사람 요청에 `X-Openit-User`가 없으면 401이다. 단 서비스 역할 토큰(release-gate `GATE_SERVICE_ROLES`, 기본 `ops-feedback`)으로 오는 기계 호출의 `activate`·`rollback`은 이 헤더 없이 받고 행위자를 `service:<역할>`로 기록한다(RUNTIME R10.9). `POST /v1/approvals`와 `cases/{id}/review`는 어느 토큰이든 헤더가 필요하다. 어느 쪽이든 `BoundaryError.code`는 `PERMISSION_DENIED`이고 재시도하지 않는다. `boundary_contracts.clients`는 401과 403을 모두 `PERMISSION_DENIED`로 읽으므로 클라이언트는 바뀌지 않는다.
- **과다 요청.** 공개 API는 429와 `UNAVAILABLE`을 내고 `Retry-After`(초, 정수)를 따라 재시도한다. 영역 사이 서비스 API는 과다 요청에 **503 `UNAVAILABLE`** 을 내며(429 는 클라이언트별 속도 제한(RFC 6585 4)인데 영역 사이 호출자는 정해진 몇 서비스뿐이라 호출자별 제한을 두지 않고 서버 과부하로 답한다, 검토 B-28-2) `Retry-After`는 서비스마다 다르다(없을 수 있다). 호출자는 둘 다 일시 장애로 취급해 백오프 재시도한다.
- **재시도 의미는 `code`의 기본값에 사유가 덧붙는다.** `retryable`은 `code`별 기본값이다. 같은 `code` 안에서 재시도해도 되는 사유는 `details.reason`으로 구분한다. 예: 409 `CONFLICT`는 기본 재시도하지 않지만 `details.reason`이 `TURN_IN_PROGRESS`이면 `Retry-After` 뒤 같은 `turn_id`로 다시 보낸다. 새 사유는 `PUBLIC_API.md`나 `HTTP.md`에 적힌 것만 쓴다.
- **중계를 거쳐도 의미는 같다(RUNTIME.md).** TLS 종단·서버 분리·재시작이 끼어도 아래 상태 코드의 의미는 바뀌지 않는다. 실패 경우별 응답은 RUNTIME.md R3 표가 정본이다.
- **gateway(역방향 프록시)의 상류 장애 응답은 `BoundaryError`가 아니다.** 상류 연결 거부·재시작은 503, 상류 시간 초과는 504이고 본문은 `{"code": "UPSTREAM_UNAVAILABLE"}`, `Retry-After`가 붙는다. 이 `code`는 `BoundaryError` 열거에 없다. 클라이언트는 502·503·504를 모두 재시도 가능한 일시 장애로 취급한다(`Retry-After`가 있으면 따른다). 서비스가 직접 502·504를 내는 일은 없다.
- **SDK 클라이언트의 `Retry-After`(3.1.2 부터, 3.4.4 문장 정정).** 클라이언트는 본문이 `BoundaryError` 인 409·429·503 응답의 `Retry-After`(0~3600 정수 초)를 `details.retry_after_s` 로 호출자에게 넘긴다. 본문이 `BoundaryError` 가 아닌 502·503·504(게이트웨이 `UPSTREAM_UNAVAILABLE` 포함)는 `UNAVAILABLE` 만 내고 `retry_after_s` 는 없다. 대기와 재시도는 호출자가 정한다.

- 수집(I6): `POST /v1/traces`, 본문 `TraceEnvelope`, 성공은 200과 `IngestResult`.
- 쓰기 요청의 멱등성은 4절을 따른다(같은 ID와 내용이면 같은 응답).

## 10. 직렬화 규칙

- **모델 입출력(`ActionExtractionInput`, `ActionExtraction`, `ResponseRequest`, `ResponseText`)은 레코드가 아니다.** 모델이 말하는 형식 그대로여서 `pipeline_schema_version`과 `ext`가 없고(`additionalProperties: false`), 읽는 쪽도 완화 없이 엄격하게 검증한다. 데이터셋 줄(`ActionExtractionSample`, `ResponseSample`)이 레코드이고 `ext`를 가진다.
- **키 문법이 둘이다.** (1) `SlotRef` 문자열(`ChangeClassification.affected_slots` 등 문항 저작의 구조 참조): 아래 첫 항목. (2) **모델 키**(`ActionExtraction.values[].key`, `targets[]`): `<문항>.<칸>` 또는 술 칸의 `<문항>[<종류>].<칸>`(종류는 soju, beer, spirits, makgeolli, wine). 종류를 모르는 술 칸은 괄호 없는 `Q7_1.amount`다. 모델 키를 `SlotRef`로 바꿀 때는 `[종류]`를 떼고, 반대로는 종류를 알 수 없으므로 바꾸지 않는다(서비스가 문항 은행과 대조해 쓴다).
- `SlotRef`를 문자열로 쓸 때는 `<question_id>.<slot_id>`이다(반복 키는 쓰지 않는다). 읽을 때는 **마지막 `.`**에서 나눈다. 문항 ID에는 `.`이 있을 수 있고 슬롯 ID에는 없다.
- `version`(데이터셋, 모델 패키지, 문항 세트 등 모든 산출물)은 Id 규칙(`[A-Za-z0-9][A-Za-z0-9._:-]*`, 128자)을 따른다. 파일 경로에 쓸 수 있어야 하기 때문이다. SDK 구현은 어기면 `INVALID_RECORD`로 거부한다.
- 재현성: 같은 입력과 시드는 같은 **내용**을 낸다. 내용 비교는 시각과 버전을 뺀 해시(예: 데이터셋의 `ext."synthetic-data".dataset_digest`)로 하고, `content_hash` 자체는 `created_at`을 포함하므로 시각이 다르면 달라진다. 같은 내용 해시의 산출물이 이미 있으면 새로 게시하지 않는다.
- `ArtifactRef.version`은 문자열이다. 문항 세트는 버전 번호 n의 문자열이며 `QuestionBank.version`(정수)과 같은 번호다.
- 같은 조합에 판정이 여러 개이면 가장 최근(`decided_at`, 같으면 `decision_id`가 큰 것)이 현재 판정이다.
- **`runtime_contract_version`**(D75): 모델 패키지가 학습된 문진 스키마(문항 은행·칸 키)의 정수 버전이다. 소유는 survey-service(D19, D21)이고 필드는 그대로 둔다. 서비스와 게이트는 값이 다르면 적재를 거부한다. 모델 입출력 스키마(`ActionExtraction` 등)의 버전은 `pipeline_schema_version`(이 리포지토리의 MAJOR.MINOR)이며 이 정수와 별개다.
- **`BoundaryError.details.reason`**: 같은 `code` 안에서 사유를 기계가 구분할 때 쓰는 대문자 코드다. 정의된 값(3.4.4 검토 A-28·B-28-4 로 전부 모음, 이 목록이 정본): `STALE_REPORT`·`ALREADY_DECIDED`(409, HTTP.md I5), `OUTPUT_INVALID`(503, HTTP.md I9), `TURN_IN_PROGRESS`·`QUESTION_SET_REQUIRED`·`UNKNOWN_QUESTION_SET`·`NO_OPEN_ALERT`·`INTERVAL`·`RETRY_LIMIT`(PUBLIC_API), `ACCOUNT_PENDING_APPROVAL`(403, 6절·RUNTIME R3.24), `NO_ACTIVE_RELEASE`(503, PUBLIC_API), `EGRESS_DENIED`(403 `PERMISSION_DENIED`, RUNTIME R1.8). 계약 클라이언트가 연결 오류에 붙이는 `details.reason`(예외 클래스 이름, RUNTIME R3.25·R3.27)은 로그용이고 기계 분기에 쓰지 않는다. 호출자는 `code`와 `retryable`로 행동하고 `reason`은 그 안의 세부 분기에만 쓴다.
- `serving_config_hash`는 `canonical.sha256_hash(serving_config)`이다(기본값을 채우지 않은 그대로).
- **외부 식별자를 봉투에 넣을 때:** 세션 ID·턴 ID처럼 바깥(Frontend)이 정한 식별자가 `Id` 형식(`[A-Za-z0-9][A-Za-z0-9._:-]*`, 128자)에 맞으면 그대로 쓰고, 맞지 않으면 `x-` + 원본 UTF-8의 SHA-256 앞 32자(소문자 16진)로 바꿔 쓴다. 결정적이므로 같은 원본은 같은 값이 되어 멱등성이 유지된다. 원본은 `trace` 본문에 남아 있다. 공개 API(O06)가 `Id` 형식으로 발급하기로 정해지면 이 변환은 쓰이지 않는다.

## 11. 모델 입력 `state` 의 키 순서 (3.2.0, U80)
`ActionExtractionInput.state` 는 JSON 객체이지만 **키 순서가 모델 입력의 일부**다(학습 데이터 규칙, D77 글자 일치). 순서는 (1) 지금 문항에 이미 저장된 값 → (2) 직전 문항(건너뛴 문항 제외)과 참조 원천 문항의 저장 값 → (3) 지금 문항의 비어 있는 칸(MISSING·UNCLEAR, value null). 같은 묶음 안에서는 문진 스키마 slot_order. 직렬화는 삽입 순서를 보존하는 JSON 으로만 하고, 키를 정렬하는 직렬화(sort_keys)는 금지한다. 서비스는 이 순서를 시험으로 고정한다. 알려진 한계: 학습 데이터 val 549행 중 13행(2.4%)이 이 규칙과 다르다(G13, 데이터셋 담당 확인 대기).

## 12. 문진 스키마 정수 버전 (3.2.0 G11; 3.3.0 개정 2026-11-03)
문진 스키마(`survey-service/schema`)의 정수 `CONTRACT_VERSION`은 **모델 입출력 계약 번호**다: `ReleaseManifest.runtime_contract_version`, `ModelPackageManifest.runtime_contract_version`, `ServingConfig.output_contract`, 게이트의 `GATE_SUPPORTED_RUNTIME_CONTRACT_VERSION`, model-runtime 의 지원 값이 모두 이 하나의 정수를 든다. 따라서 이 정수는 **모델이 읽고 쓰는 모양**(TurnTrace·ActionExtractionInput 에 실리는 문진 스키마 값, 모델 출력 규칙)이 깨질 때만 올린다. 올리면 모델 패키지는 그 번호로 다시 게시되어야 하고 survey-service·ops-feedback·release-gate·model-runtime 이 같은 정수를 지원해야 한다.
문진 스키마 **패키지 버전**(`openit-survey-schema` X.Y.Z)은 그와 별개로 semver 를 따른다: 읽는 쪽이 깨지는 변경(키 삭제·이름 변경·enum 축소·필수 추가)은 MAJOR 를 올린다. 예: 4.0.0 (QuestionBank 에 `question_set_id`·`title` 필수, Prerequisite `op`) 은 모델 입출력을 바꾸지 않아 정수는 1 그대로다. 3.2.0 의 이 절은 두 번호를 섞어 "필수 추가면 정수를 올린다"고 적었고, 그대로 따르면 모델 입출력이 그대로인데 LoRA 패키지를 전부 다시 게시해야 했다(2026-11-03 survey-service 담당의 지적). 그래서 고쳤다.

## 상태 확인 응답 시간 (2.1.0, FAULT_POLICY 5)
- 서비스의 `/healthz`는 의존과 무관하게 200으로 즉시 답한다(살아 있음).
- 서비스의 `/readyz`는 의존(데이터베이스, 이웃 서비스)이 응답하지 않거나 연결할 수 없을 때도 **총 2초 안에** 503과 사유를 답한다(2초: 감시 수집 한도 10초(R10.11)와 blackbox 탐침 관행 안에서 고른 시작값, 측정 안 함, 검토 A-26). 의존이 여럿이면 확인 시간이 더해져 총합이 2초를 넘지 않게 한다(병렬 확인이나 총 마감). 사유에 접속 정보를 넣지 않는다.

## 시간 상한 사슬 (2.1.0, FAULT_POLICY 3·7; 2026-11-02 D125 개정)
환자 턴 한 번에 걸리는 시간 상한은 바깥에서 안쪽으로 **항상 더 짧아져야** 한다. 한 단계가 안쪽보다 짧으면 안쪽이 끝나기 전에 바깥이 포기해 같은 요청이 이중으로 처리된다.

**목표와 실패 판정을 나눈다(D125, 사용자 지시 2026-11-02).** "환자 턴 2초"는 **목표(SLO)** 다: 지표로 재고 넘으면 경보를 낸다. 요청을 실패시키는 값이 아니다. 아래 표의 값은 **실패 판정 상한**(이 이상이면 장애로 본다)이며, 표준 관행에서 가져왔다: HTTP 프록시·부하분산기의 기본 읽기/유휴 상한 60초(nginx `proxy_read_timeout`, AWS ALB idle timeout), 화면 응답 지침(Nielsen: 1초를 넘으면 진행 표시, 10초를 넘으면 안내 문구)과 계산된 최악값(설정 상한의 합, 실측 아님) 위의 여유. 2026-10-31까지의 값(extract 3.0·respond 5.0·턴 9·gateway 10.5·키오스크 12)은 목표를 그대로 상한으로 쓴 것이라 첫 호출의 JIT 컴파일 같은 정상 지연에도 턴을 실패시켰다(H4 실측 2026-11-02).

| 단계 | 실패 판정 상한 | 근거 |
| --- | --- | --- |
| 키오스크 요청 대기 | 60초 | 프록시·LB 표준 60초. 1초가 지나면 "생각 중" 진행 표시, 10초가 지나면 안내 문구(Nielsen). 재시도 총 예산은 120초(대기의 2배, kiosk-frontend ADR 0033, 같은 `turn_id`) |
| gateway 환자·직원 경로(연결 1초 + 응답 헤더 55초) | 56초 | 키오스크 대기보다 짧다 |
| survey-service 턴 총 마감 | 50초 | 턴 전체의 상한(호출별 합이 아님). 두 모델 호출 상한의 합 45초 + 서버 처리 여유 5초(시작값·측정 안 함) |
| survey-service → model-runtime 클라이언트 읽기 상한 | extract 21초, respond 26초 | 서버 상한보다 1초 길다(서버가 먼저 503을 내게; 1초는 시작값·측정 안 함) |
| model-runtime 요청 상한 | extract 20초, respond 25초 | 한 환자 턴이 모델을 두 번 부른다. 합 45초 < 턴 마감 50초. 20·25 자체는 근거 기록 없음·시작값·측정 안 함(2026-11-02 H4 에서 옛 값 3·5초가 첫 호출 JIT 지연에 턴을 실패시킨 뒤 프록시 표준 60초 안에서 고른 값, 검토 A-26) |

사람 화면 경로(승인·운영·검토·저작)도 같은 원칙이다(D120 개정). 서버 쪽 전체 마감 < gateway 응답 헤더 상한 < 화면 대기.

| 경로 | gateway(연결 1초 + 응답 헤더) | 서버 전체 마감 | 화면 대기 | 근거 |
| --- | --- | --- | --- | --- |
| release-gate 승인·활성화·롤백·조회 | 181초(180) | 170초 | 190초 | 계산된 최악 승인 128초(D120 계기: 설정 상한의 합 — DB 문장 16×3초 + 이웃 호출 8×10초; 실측 아님) 위의 여유 |
| question-authoring 저자 경로·신호 | 121초(120) | 110초 | 130초 | 계산된 최악 자료 올리기 62초(설정 상한의 합, 실측 아님) 위의 여유 |
| ops-feedback 검토 | 61초(60) | 55초 | 70초 | 프록시 표준 60초(계산된 최악 11초) |
| 표에 행이 없는 사람·기기 경로(survey-service 의사 결과 조회·확인·푸시 구독·push-config, 계정 관리 화면, 화면 정적 파일) | 56초(연결 1초 + 응답 헤더 55초) | 50초(환자 턴과 같은 값, 시작값·측정 안 함; 검토 B-11) | 60초 | 가장 짧은 사람 화면 행(환자·직원 경로)의 일반화, 프록시 표준 60초(측정 안 함). RUNTIME R3.3 |
| 표에 없는 서비스 사이 호출(이웃 호출, 계약 클라이언트) | — | — | — | 계약 클라이언트 `timeout` 10초(소켓 단위: 연결과 각 읽기 대기; 호출 전체 시간의 상한이 아니다. 호출 전체는 받는 서비스의 자기 마감 R3.19 가 막는다). 시작값·측정 안 함. 위 release-gate 행의 "이웃 호출 8×10초"는 이웃이 10초 안에 응답한다는 가정의 계산이고 실측이 아니다(RUNTIME R10.3, 검토 A-8·B-27) |

재시도는 **남은 턴 예산이 호출 상한 이상일 때만** 한다. 남은 예산이 모자라면 재시도하지 않고 실패로 처리한다. 값은 측정이 아니라 표준·여유에서 나온 상한이며, 목표(2초)의 달성 여부는 지표(`METRICS.md`)로 본다. 상태 확인(`/readyz` 2초)은 관측 임계라 이 표와 별개다.

## 13. 영역의 입구와 계약의 주인 (3.4.4, 사용자 원칙 2026-11-04, D104)

- **영역 게이트웨이.** 서비스를 가진 영역은 게이트웨이 하나를 가진다. 영역 밖에서 들어오는 입력과 영역 밖으로 나가는 출력은 모두 그 게이트웨이를 지난다(영역의 서비스가 이웃 영역을 부르는 호출, 잡이 이웃을 부르는 호출, 감시 수집, 잡 실행 요청 포함). 영역 안 컴포넌트 사이의 입출력과 그 스키마는 영역이 정한다(구조 규칙 5). 이 리포는 영역 게이트웨이 사이를 지나는 것만 정한다(구조 규칙 6).
- **영역 게이트웨이의 들어오는 쪽과 나가는 쪽(3.4.4).** 들어오는 쪽: 영역 밖의 호출은 영역 게이트웨이가 서비스 이름 인증서로 TLS 를 끝내고 영역 안 컴포넌트로 넘긴다. 나가는 쪽: 영역 안 컴포넌트(서비스·잡)의 영역 밖 호출은 자기 영역 게이트웨이의 HTTP CONNECT 터널(RFC 9110 9.3.6)로 나간다. TLS 는 호출 컴포넌트와 받는 영역 게이트웨이 사이에서 끝까지 유지된다. 자기 게이트웨이는 그 영역이 `Exposure.egress` 에 선언한 상대에게만 터널을 열고 그 밖은 403 으로 거절한다(RUNTIME R1.8·R6.2). 선언할 수 있는 상대는 INTERFACES.md "한눈에" 표에서 그 영역이 부르는 서비스, `external:backup`(platform 백업 저장소), `external:web-push`(survey-service 만, RUNTIME R6.4)뿐이다(이 목록이 정본, 검토 P6-R6-8). 터널 주소는 모든 영역 컨테이너 공통의 환경 변수 `OPENIT_EGRESS_PROXY`(스키마 `CommonEnv`, 각 영역 Env 스키마와 함께 지킨다)(형식 `http://<loopback>:<포트>`, deploy 가 준다)이고, 영역의 배선 코드가 `boundary_contracts.clients.egress_proxy_from(environ)` 으로 이 이름 하나만 꺼내 계약 클라이언트의 `egress_proxy` 인자로 넘긴다(R9.1: 환경을 통째로 넘기지 않는다; 클라이언트는 `HTTPS_PROXY` 등 다른 프록시 변수를 읽지 않는다). compose 밖(R1.5)에서 도는 영역 컴포넌트도 같은 서버에 둔 자기 영역 게이트웨이를 거친다.
- **영역 이미지는 스스로 서는 단위다(3.4.17).** 영역 이미지는 자기 실행 명령(진입점 기본값), 상태 확인(Dockerfile `HEALTHCHECK`), 실행 사용자(`USER`)를 갖는다. 한 이미지가 여러 역할을 하면 역할은 그 이미지의 Env 스키마 값으로 고른다(예: `StepCaEnv.STEP_ROLE`, `MonitoringEnv.MONITORING_ROLE`). deploy 는 영역 이미지에 compose `command`·`entrypoint`·`healthcheck`·`user`·`volumes_from` 을 쓰지 않고, 실행 중 컨테이너 안에서 명령을 실행하지 않는다(`exec`). deploy 가 하는 일은 환경 구성(Env 값·비밀 파일·마운트·망·자원·보안 설정·보조 그룹)과 잡 실행(JobsDeclaration)뿐이다. 인증서 파일을 읽는 컨테이너는 `StepCaEnv.STEP_CERT_GID` 를 보조 그룹으로 받는다.
- **유일한 예외: 배포 때의 환경 설정.** deploy 가 배포할 때 컨테이너에 주는 환경 변수(`*Env`·`CommonEnv` 스키마)·비밀 파일(`NAME_FILE`, D84)·루트 인증서(`SSL_CERT_FILE`)·compose 밖 호출자에게 내보내는 파일(루트 인증서 PEM·hosts 표·SHA-256 목록, RUNTIME R1.5; 검토 P3-D3·P4-4)·이미지 빌드와 게시 호출(`BuildImage*`·`Publish*`·`ImageLabels`·`JobsDeclaration`·`Exposure`·`SetupEnvReport`), 그리고 **어떤 이미지를 언제 어떤 명령으로 띄우는가**(서비스 기동, 잡의 주기 실행과 그 종료 코드·마지막 줄 JSON 수거 — `*JobResult`·`SurveyPurgeOutput`)는 게이트웨이를 지나지 않는다. 컨테이너를 띄우는 일은 배포(오케스트레이션) 설정이지 실행 중 요청 경로가 아니다. deploy 는 배치 도구이고 실행 중인 요청·데이터 경로에 끼지 않는다.
- **공개 입구의 경로 표(3.4.9).** platform 공개 입구는 영역 Exposure 선언으로 경로 표를 만든다. `denied`·`machine-token` 경로와 영역의 `/healthz`·`/readyz`·`/metrics` 는 내보내지 않는다. 같은 (경로, 메서드)를 두 영역이 공개로 열면 공개 입구는 시작하지 않는다(종료 65): 데이터마다 주인은 하나다(DATA_OWNERSHIP.md).
- **deploy 가 넘기는 입력은 모두 받는 쪽의 계약 Env 스키마에 있다(3.4.10).** 영역 서비스는 <영역>Env, platform 이미지는 AreaGatewayEnv·PublicIngressEnv·MonitoringEnv·BackupStoreEnv·StepCaEnv·IdentityEnv·IdentityProxyEnv, 영역 DB 이미지는 AreaDatabaseEnv. 받는 쪽 구현의 내부 설정(Keycloak·oauth2-proxy·Caddy·PostgreSQL 초기화)은 그 이미지가 이 입력에서 만들고 deploy 는 쓰지 않는다(구조 규칙 1·6). DB 계정은 DB 이미지 라벨 `io.openit.database`(DatabaseDeclaration)로 선언하고, deploy 는 계정마다 무작위 암호 파일을 만들어 DB 와 그 계정을 쓰는 컨테이너(url_env)에 같은 값으로 준다. 키오스크 기기 토큰(F-1 호환)은 기기마다 비밀 파일 하나(PublicIngressEnv.INGRESS_DEVICE_TOKENS_DIR).
- **잡 환경(3.5.1).** `ContainerInputs.jobs.*.env_schema`는 그 잡이 실제로 받는 환경 계약을 가리킨다. 서버의 기동·인증 필수 조건을 잡에 요구하지 않는다. 백업·복구는 `BackupJobEnv`와 영역별 `*BackupEnv`, 사용자 등록은 `IdentityUsersEnv`다. 서비스와 잡 모두 선언이 가리키는 Env와 CommonEnv를 기동 전에 검증한다. 파일을 마운트하는 것과 그 경로 환경 변수를 주는 것은 별개이며 둘 다 선언을 따라야 한다.
- **서비스 이름(2026-11-04 문서 보충, 태그 없음).** 영역 사이 호출의 서비스 이름(RUNTIME IN-NAME, `Exposure.egress` 의 받는 쪽, 서비스 인증서 SAN)은 그 서비스 이미지의 게시 이름(`PublishRequest.service`)과 같다. 예: ops-feedback 서버는 `ops-feedback`(compose 서비스 이름도 같다). 다른 이름(별칭)을 쓰지 않는다 — deploy 연결 시험(test-egress-edges)이 `ops-feedback` 과 `ops-feedback-ingest` 가 섞여 쓰인 것을 찾았다. 점검: head/scripts/cross-area-check.py 가 영역 이미지 라벨의 egress 이름이 모두 게시 이름인지 본다.
- **platform 영역.** 사람·기기의 공개 입구, 사람 인증(계정 관리), 인증서 발급, 감시, 백업 저장소는 platform 영역의 서비스다. 다른 영역과는 platform 게이트웨이와 이 리포의 스키마로만 만난다.
- **데이터베이스는 영역의 컴포넌트다(Database per Service, 3.4.4 검토 B-25).** 데이터를 저장하는 영역은 자기 데이터베이스(예: PostgreSQL 컨테이너)를 자기 컴포넌트로 가진다. 다른 영역의 데이터베이스에 닿는 길은 없고, 영역 사이의 데이터는 그 데이터를 가진 영역의 인터페이스(I1~I10)로만 나간다(공유 DB 통합 금지). 백업은 영역이 자기 데이터를 꺼내 자기 게이트웨이 출구로 platform 백업 저장소에 보낸다(RUNTIME R10.1). 데이터베이스 엔진·버전·접속 설정은 영역이 정한다.
- **계약의 주인.** 모든 스키마는 최상위에 `x-producers`(그 값을 출력하는 쪽)와 `x-consumers`(그 값을 입력으로 받는 쪽)를 가진다. 값은 영역 이름(`head`, `deploy`, `platform`, `model-runtime`, `model-lab`, `synthetic-data`, `survey-service`, `release-gate`, `ops-feedback`, `question-authoring`, `kiosk-frontend`, `admin-console` — 정본 head/shared/areas.json), `*`(서비스를 가진 모든 영역), `external:person`(사람이 직접), `external:install-site`(설치처 운영)이다. 출력이 스키마를 어기면 생산자의 결함이고, 받는 쪽은 다시 검증하지 않는다(R7). 시험 `tests/test_schema_owners_344.py` 가 빠짐·모르는 이름을 거부한다.
