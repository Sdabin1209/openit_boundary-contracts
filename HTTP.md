# HTTP 매핑 (서비스 사이 호출)

영역 사이 호출은 서로의 코드가 아니라 **HTTP 서비스 API**로 한다(D49). 이 문서는 `INTERFACES.md`의 인터페이스마다 경로, 요청, 응답을 정한다. 서비스(소유 영역)는 서버 쪽을, `boundary_contracts.clients`는 클라이언트 쪽을 구현하고, 둘 다 같은 적합성 시험을 통과한다. 공통 규칙은 `CONVENTIONS.md` 9절(JSON, Bearer 토큰, 역할은 토큰에 묶임, `/healthz`·`/readyz`, 오류는 `BoundaryError` 본문과 고정된 상태 코드)이다.

## 공통

- 모든 경로는 `/v1` 아래다. 본문과 응답은 UTF-8 JSON(`application/json`)이고, 예외는 tar 스트림(`application/x-tar`)이다.
- **단일 레코드**는 레코드 자체를 돌려준다. 없을 수 있는 것은 `{"item": 레코드 | null}`이다.
- **목록**은 `{"items": [...], "next_cursor": 문자열 | null}`이다. 쿼리 `cursor`, `limit`(기본 100, 최대 500)을 받는다. 정렬은 인터페이스 명세를 따른다.
- 해시는 클라이언트가 받은 뒤 다시 계산해 `INTEGRITY_ERROR`로 판정한다(서버를 믿지 않는다). 서버는 `content_hash`를 계산해 담는다.
- 토큰: 서버는 환경 변수 `<이름>_TOKENS=역할=토큰,역할=토큰`으로 받는다(영역 문서가 이름을 정한다). 읽기와 쓰기 역할을 구분하고, 읽기 토큰은 쓰기 경로를 호출할 수 없다(PERMISSION_DENIED, 403).
- 클라이언트는 생성자에 `base_url`, `token`, `timeout`을 인자로 받는다(환경 변수는 서비스 진입점이 읽는다, CONVENTIONS 7절). 네트워크 오류와 5xx와 503은 `UNAVAILABLE`(재시도 가능)이다.
- tar 스트림은 경로에 `..`, 절대 경로, 심볼릭 링크를 두지 않고 클라이언트도 풀 때 거부한다.

## I1 QuestionReader — 소유: question-authoring

| 호출 | 요청 | 응답 |
| --- | --- | --- |
| `list_ids` | `GET /v1/question-sets` | 목록(ID 문자열) |
| `list_versions` | `GET /v1/question-sets/{id}/versions` | 목록(`ArtifactRef`, 오래된 것부터) |
| `latest` | `GET /v1/question-sets/{id}/latest?reviewed_only=true\|false` | `ArtifactRef`. 없으면 404 |
| `get_question_bank` | `GET /v1/question-sets/{id}/versions/{version}` | `QuestionBank` JSON. 클라이언트는 `ref.content_hash`와 대조 |
| `get_reviews` | `GET /v1/question-sets/{id}/versions/{version}/reviews` | 목록(`ReviewRecord`, 시각순) |
| `get_change` | `GET /v1/question-sets/{id}/versions/{version}/change` | `{"item": ChangeClassification \| null}` |

저작 API(`/v1/drafts`, `/v1/materials`, `/v1/reviews` 등)는 이 규약의 대상이 아니다(영역 내부).

## I3 ModelRegistry — 소유: model-lab (서비스 이름: model-registry)

| 호출 | 요청 | 응답 |
| --- | --- | --- |
| `list_ids` | `GET /v1/packages` | 목록(패키지 ID) |
| `list_versions` | `GET /v1/packages/{id}/versions` | 목록(버전 문자열, 오래된 것부터) |
| `get_manifest` | `GET /v1/packages/{id}/versions/{version}` | `ModelPackageManifest` |
| `open_adapter` | `GET /v1/packages/{id}/versions/{version}/adapter` | tar: 어댑터 디렉터리의 파일들. 클라이언트가 풀어 `directory_hash`를 `adapter_hash`와 대조 |
| `get_eval_report` | `GET /v1/eval-reports/{ref}` | `application/octet-stream` 바이트 |
| `publish` | `POST /v1/packages` (쓰기 역할 `model-lab`) | 본문 tar: `manifest.json`, `adapter/…`, `eval_report`. 새로 만들면 201, 같은 ID·버전·같은 내용이면 200, 다르면 409. 응답은 매니페스트 |

## I4 ReleaseReader — 소유: release-gate

| 호출 | 요청 | 응답 |
| --- | --- | --- |
| `get_active_pointer` | `GET /v1/active-pointer` | `{"item": ActivePointer \| null}` |
| `get_release` | `GET /v1/releases/{id}` | `ReleaseManifest` |
| `list_releases` | `GET /v1/releases` | 목록(`ReleaseManifest`, 최신부터) |
| `load_bundle` | `GET /v1/releases/{id}/bundle` | tar: `manifest.json`, `question_bank.json`, `adapters/LORA_A/…`, `adapters/LORA_B/…`. PASS가 아닌 릴리스는 412. 클라이언트가 모든 해시를 검증 |
| `get_decision` | `GET /v1/decisions/{id}` | `GateDecision` |
| `find_decisions` | `GET /v1/decisions?question_set_id=&question_set_version=&lora_a_id=&lora_a_version=&lora_b_id=&lora_b_version=&submission_id=` | 목록(`GateDecision`, 최신부터) |

## I5 GateService — 소유: release-gate (현행 경로를 그대로 따른다)

| 호출 | 요청 | 응답 |
| --- | --- | --- |
| `submit_candidate` | `POST /v1/submissions` 본문 `{subject, requested_by_role}` | `GateSubmission` (202) |
| `activate` | `POST /v1/activate` 본문 `{release_id, requested_by_role}` | `ActivePointer` |
| `request_rollback` | `POST /v1/rollback` 본문 `RollbackRequest` | `RollbackReceipt` |

## I6 TraceIngest — 소유: ops-feedback (현행)

`POST /v1/traces` 본문 `TraceEnvelope` → `IngestResult`.

## I7 FailureStore — 소유: ops-feedback

| 호출 | 요청 | 응답 |
| --- | --- | --- |
| `get_case` | `GET /v1/cases/{case_id}?version=` | `FailureCase` (version 생략 시 최신) |
| `list_cases` | `GET /v1/cases?review_status=&failure_type=&source_release_id=&updated_since=&latest_only=true\|false` | 목록(`FailureCase`) |
| `get_trace` | `GET /v1/deidentified-traces/{ref}` | 비식별 TurnTrace JSON |
| `publish_case` | (HTTP로 열지 않는다. ops-feedback 내부 잡이 로컬 저장소에 쓴다) | |

## 적합성

`boundary_contracts.clients`의 각 클라이언트는 `typing.Protocol` 인터페이스와 같은 적합성 시험(CONVENTIONS 7절, 오류, 멱등성, 해시 검증)을 통과해야 한다. 서비스는 자기 서버를 띄워 클라이언트로 같은 시험을 돌려 통과시킨다. 시험 모음은 `boundary-contracts/conformance/`에 있다.
