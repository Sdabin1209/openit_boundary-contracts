# 공통 규약

영역 사이 호출(SDK와 서비스 API)이 모두 따르는 규칙이다. 영역 에이전트는 상대 영역을 블랙박스로 보고 이 규약과 `INTERFACES.md`만 믿고 개발한다. 이 규약은 소유자인 헤드만 바꾼다.

## 1. 계약이 다시 뜯기지 않게 하는 규칙

1. **확장 필드.** 모든 레코드에는 선택 필드 `ext`가 있다. 영역은 새 정보를 `ext.<영역 이름>`에 계약 변경 없이 덧붙인다. 읽는 영역은 `ext`를 이해하지 못해도 **보존하고 전달**해야 하며(복사·재게시 때 지우지 않는다), 판단에 쓰지 않는다. 여러 영역이 판단에 필요로 하게 되면 정식 필드로 올린다(MINOR).
2. **MINOR는 추가만 한다.** 선택 필드 추가, 열거값 추가, 허용 범위 확대만 MINOR다. 필수 필드 추가, 필드 삭제·이름·의미 변경, 허용 범위 축소는 MAJOR다. 의미를 바꾸려면 새 필드를 만들고 옛 필드는 유지한다.
3. **쓸 때는 엄격하게, 읽을 때는 관대하게.** 레코드를 만드는 쪽은 자기가 아는 버전의 스키마(`additionalProperties: false`)로 검증한 뒤 쓴다. 읽는 쪽은 같은 MAJOR이면 모르는 필드를 무시하고, **모르는 열거값은 오류로 죽지 않고 '알 수 없음'으로 처리**한다. 읽는 쪽의 SDK는 이 관대한 읽기를 기본으로 제공한다.
4. **MAJOR는 병행 기간을 둔다.** MAJOR를 올릴 때 소유자는 이전 MAJOR를 읽는 경로를 한 릴리스 주기 동안 유지한다.
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

- 서비스 사이 호출은 `Authorization: Bearer <서비스 토큰>`이고 토큰은 환경 변수로 받는다. 읽기 SDK는 읽기 전용 토큰, 쓰기는 소유 영역의 토큰만 쓴다.
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
- 본문은 JSON, 인증은 `Authorization: Bearer <서비스 토큰>`이다. 토큰은 환경 변수로 받고, 서버가 토큰에 **역할을 묶어** 둔다. 호출자가 역할을 주장하지 못한다. 토큰 발급·회전은 단일 서버에서는 정적 토큰으로 시작하고 deploy가 비밀 값으로 관리한다.
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

- 수집(I6): `POST /v1/traces`, 본문 `TraceEnvelope`, 성공은 200과 `IngestResult`.
- 쓰기 요청의 멱등성은 4절을 따른다(같은 ID와 내용이면 같은 응답).

## 10. 직렬화 규칙

- `SlotRef`를 문자열로 쓸 때는 `<question_id>.<slot_id>`이다(반복 키는 쓰지 않는다). 읽을 때는 **마지막 `.`**에서 나눈다. 문항 ID에는 `.`이 있을 수 있고 슬롯 ID에는 없다.
- `version`(데이터셋, 모델 패키지, 문항 세트 등 모든 산출물)은 Id 규칙(`[A-Za-z0-9][A-Za-z0-9._:-]*`, 128자)을 따른다. 파일 경로에 쓸 수 있어야 하기 때문이다. SDK 구현은 어기면 `INVALID_RECORD`로 거부한다.
- 재현성: 같은 입력과 시드는 같은 **내용**을 낸다. 내용 비교는 시각과 버전을 뺀 해시(예: 데이터셋의 `ext."synthetic-data".dataset_digest`)로 하고, `content_hash` 자체는 `created_at`을 포함하므로 시각이 다르면 달라진다. 같은 내용 해시의 산출물이 이미 있으면 새로 게시하지 않는다.
- `ArtifactRef.version`은 문자열이다. 문항 세트는 버전 번호 n의 문자열이며 `QuestionBank.version`(정수)과 같은 번호다.
- 같은 조합에 판정이 여러 개이면 가장 최근(`decided_at`, 같으면 `decision_id`가 큰 것)이 현재 판정이다.
- `serving_config_hash`는 `canonical.sha256_hash(serving_config)`이다(기본값을 채우지 않은 그대로).
