# 공통 규약

영역 사이 호출(SDK와 서비스 API)이 모두 따르는 규칙이다. 영역 에이전트는 상대 영역을 블랙박스로 보고 이 규약과 `INTERFACES.md`만 믿고 개발한다. 이 규약은 소유자인 헤드만 바꾼다.

## 1. 계약이 다시 뜯기지 않게 하는 규칙

1. **확장 필드.** 모든 레코드에는 선택 필드 `ext`가 있다. 영역은 새 정보를 `ext.<영역 이름>`에 계약 변경 없이 덧붙인다. 읽는 영역은 `ext`를 이해하지 못해도 **보존하고 전달**해야 하며(복사·재게시 때 지우지 않는다), 판단에 쓰지 않는다. 여러 영역이 판단에 필요로 하게 되면 정식 필드로 올린다(MINOR).
2. **MINOR는 추가만 한다.** 선택 필드 추가, 열거값 추가, 허용 범위 확대만 MINOR다. 필수 필드 추가, 필드 삭제·이름·의미 변경, 허용 범위 축소는 MAJOR다. 의미를 바꾸려면 새 필드를 만들고 옛 필드는 유지한다.
3. **쓸 때는 엄격하게, 읽을 때는 관대하게.** 레코드를 만드는 쪽은 자기가 아는 버전의 스키마(`additionalProperties: false`)로 검증한 뒤 쓴다. 읽는 쪽은 같은 MAJOR이면 모르는 필드를 무시하고, **모르는 열거값은 오류로 죽지 않고 '알 수 없음'으로 처리**한다. 읽는 쪽의 SDK는 이 관대한 읽기를 기본으로 제공한다.
4. **MAJOR는 병행 기간을 둔다.** MAJOR를 올릴 때 소유자는 이전 MAJOR를 읽는 경로를 한 릴리스 주기 동안 유지한다. **예외: 2.0.0(D74)은 병행 없이 v1 형식을 폐기했다.** v1 계약이 기술하던 단계(파서·정규화기·판정기·Plan)가 없어졌고 학습된 모델은 v2 형식만 말하며 운영 데이터가 아직 없는 데모 단계이기 때문이다. v1.3.3은 Git 태그로 남는다. 클라이언트는 MAJOR 1의 레코드를 `UNSUPPORTED_VERSION`으로 거부한다.
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
| CONFLICT | 같은 ID에 다른 내용을 쓰려 했다 | false |
| INTEGRITY_ERROR | 해시가 맞지 않는다 | false |
| FAILED_PRECONDITION | 지금 상태에서는 할 수 없다(예: 통과하지 않은 릴리스 활성화) | false |
| PERMISSION_DENIED | 권한이 없다 | false |
| UNAVAILABLE | 일시적으로 처리할 수 없다 | true |

SDK는 `BoundaryError`를 예외로 던진다. 메모리 구현도 같은 예외를 같은 조건에서 던져야 한다.

## 4. 쓰기의 멱등성

- 같은 ID(또는 ID+버전)와 같은 내용(같은 `content_hash`)으로 다시 쓰면 성공이고 기존 것을 돌려준다.
- 같은 ID에 다른 내용이면 `CONFLICT`다.
- 쓰는 쪽은 쓰기 전에 스키마로 검증한다. 받는 쪽도 검증하며, 위반이면 `INVALID_RECORD`다.
- 호출자는 `UNAVAILABLE`일 때만 재시도한다. 재시도해도 결과가 같다는 것이 위 규칙으로 보장된다.

## 5. 목록과 페이지

목록 호출은 `(items, next_cursor)`를 돌려준다. `next_cursor`가 `None`이면 끝이다. 정렬은 호출마다 명세에 적힌 기준이며, 새 항목은 뒤에 붙는다(과거 항목의 순서는 바뀌지 않는다).

## 6. 인증과 권한 (단일 서버 기준)

- 서비스 사이 호출은 `Authorization: Bearer <서비스 토큰>`이고 토큰은 파일로 받는다(D84: `NAME_FILE`에 경로를 주고 `boundary_contracts.secrets.read_secret(NAME)`으로 읽는다. 환경 변수 `NAME`은 개발·시험용 호환일 뿐이며 운영에서는 쓰지 않는다). 읽기 SDK는 읽기 전용 토큰, 쓰기는 소유 영역의 토큰만 쓴다.
- 저장소의 쓰기 권한은 소유 영역 하나에만 있다(경계 규칙 1). 다른 영역에는 읽기 전용 DB 계정만 준다.
- 문진 대상 인증과 공개 API 인증은 이 규약의 대상이 아니다(O06, Frontend 팀과 협의).

## 7. SDK의 형태

- 언어는 Python 3.10 이상, 배포는 Git 태그(D18).
- 각 SDK는 (1) `typing.Protocol`로 쓴 인터페이스, (2) 실제 구현, (3) 같은 인터페이스를 지키는 **메모리 구현**을 함께 낸다. 메모리 구현은 오류·멱등성·해시 검증까지 실제 구현과 같게 동작해야 한다.
- 이웃 영역은 메모리 구현으로 혼자 시험한다. 실제 구현과 메모리 구현은 같은 적합성 테스트를 통과해야 한다.
- 생성자는 설정을 인자로만 받고 환경 변수는 읽지 않는다. 읽는 곳은 서비스의 진입점이다.

## 8. 파일 형식

- 데이터셋 파일은 JSON Lines(UTF-8, 한 줄에 샘플 하나)다.
- 문항 세트(`QuestionBank`)와 FailureCase의 비식별 Trace는 JSON이다.
- 어댑터는 디렉터리이며 `adapter_hash`는 `directory_hash`다.

## 9. HTTP 전송 규약 (서비스 API)

SDK의 원격 구현과 서비스 API가 같은 규칙을 쓴다.
- 본문은 JSON, 인증은 `Authorization: Bearer <서비스 토큰>`이다. 토큰은 파일로 받고(D84, 위 6절), 서버가 토큰에 **역할을 묶어** 둔다. 호출자가 역할을 주장하지 못한다. 토큰 발급·회전은 단일 서버에서는 정적 토큰으로 시작하고 deploy가 비밀 값으로 관리한다.
- 모든 서비스는 `GET /healthz`, `GET /readyz`를 둔다.
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
- **401과 403은 두 종류의 API에서 다르다.** (1) **공개 API**(`PUBLIC_API.md`: 키오스크·직원 콘솔이 부르는 문진 서비스): 토큰이 없거나 틀리면 401, 토큰은 맞지만 그 호출 권한이 없으면 403이다. (2) **영역 사이 서비스 API**(`HTTP.md`의 I1~I9: 출고 게이트, 모델 등록소, 모델 서버, 운영 기록, 문항 저작): 위 표대로 `PERMISSION_DENIED`는 403이고 토큰이 없거나 틀린 경우도 403이다. 예외는 엔드포인트별로 명시한 것뿐이다(예: 사람 행위자가 필요한 `POST /v1/approvals`·`activate`·`rollback`은 `X-Openit-User`가 없으면 401). 어느 쪽이든 `BoundaryError.code`는 `PERMISSION_DENIED`이고 재시도하지 않는다.
- **과다 요청.** 공개 API는 429와 `UNAVAILABLE`을 내고 `Retry-After`(초, 정수)를 따라 재시도한다. 영역 사이 서비스 API는 과다 요청에 **503 `UNAVAILABLE`** 을 내며 `Retry-After`는 서비스마다 다르다(없을 수 있다). 호출자는 둘 다 일시 장애로 취급해 백오프 재시도한다.
- **재시도 의미는 `code`의 기본값에 사유가 덧붙는다.** `retryable`은 `code`별 기본값이다. 같은 `code` 안에서 재시도해도 되는 사유는 `details.reason`으로 구분한다. 예: 409 `CONFLICT`는 기본 재시도하지 않지만 `details.reason`이 `TURN_IN_PROGRESS`이면 `Retry-After` 뒤 같은 `turn_id`로 다시 보낸다. 새 사유는 `PUBLIC_API.md`나 `HTTP.md`에 적힌 것만 쓴다.
- **gateway(역방향 프록시)의 상류 장애 응답은 `BoundaryError`가 아니다.** 상류 연결 거부·재시작은 503, 상류 시간 초과는 504이고 본문은 `{"code": "UPSTREAM_UNAVAILABLE"}`, `Retry-After`가 붙는다. 이 `code`는 `BoundaryError` 열거에 없다. 클라이언트는 502·503·504를 모두 재시도 가능한 일시 장애로 취급한다(`Retry-After`가 있으면 따른다). 서비스가 직접 502·504를 내는 일은 없다.
- **SDK 클라이언트의 `Retry-After`.** 지금 `boundary_contracts.clients`의 원격 구현은 `Retry-After`를 읽지 않고 호출자가 정한다(서비스 영역이 `UNAVAILABLE` 처리를 직접 한다). 읽도록 바꾸는 것은 후속 MINOR 후보다.

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
- **`BoundaryError.details.reason`**: 같은 `code` 안에서 사유를 기계가 구분할 때 쓰는 대문자 코드다. 정의된 값: `STALE_REPORT`, `ALREADY_DECIDED`(409, HTTP.md I5), `OUTPUT_INVALID`(503 UNAVAILABLE, HTTP.md I9 `extract`, D75). 호출자는 `code`와 `retryable`로 행동하고 `reason`은 그 안의 세부 분기에만 쓴다.
- `serving_config_hash`는 `canonical.sha256_hash(serving_config)`이다(기본값을 채우지 않은 그대로).
- **외부 식별자를 봉투에 넣을 때:** 세션 ID·턴 ID처럼 바깥(Frontend)이 정한 식별자가 `Id` 형식(`[A-Za-z0-9][A-Za-z0-9._:-]*`, 128자)에 맞으면 그대로 쓰고, 맞지 않으면 `x-` + 원본 UTF-8의 SHA-256 앞 32자(소문자 16진)로 바꿔 쓴다. 결정적이므로 같은 원본은 같은 값이 되어 멱등성이 유지된다. 원본은 `trace` 본문에 남아 있다. 공개 API(O06)가 `Id` 형식으로 발급하기로 정해지면 이 변환은 쓰이지 않는다.
