# 영역 경계 명세

각 영역이 **무엇을 내놓고 무엇을 받는지**를 정한다. 상대 영역은 블랙박스이며, 아래 명세만 믿고 개발한다. 오류·멱등성·버전·인증은 `CONVENTIONS.md`를 따른다. 타입 이름 중 `ReleaseManifest` 같은 것은 이 리포지토리의 스키마이고, `QuestionBank`·`TurnTrace` 같은 것은 문진 스키마(`survey-service/schema`)의 계약이다. 모델 입출력(`ActionExtractionInput`, `ActionExtraction`, `ResponseRequest`, `ResponseText`)은 2.0.0부터 이 리포지토리의 스키마다. 시그니처는 `typing.Protocol`로 옮길 수 있는 형태로 적었다.

```
Ref        = ArtifactRef
Page[T]    = (items: list[T], next_cursor: str | None)
모든 함수는 실패 시 BoundaryError(code, retryable)를 던진다.
```

## 한눈에: 누가 무엇을 내고 누가 읽는가

| 인터페이스 | 제공(소유) | 쓰는 쪽 | 읽는 쪽 |
| --- | --- | --- | --- |
| I1 QuestionReader | question-authoring | 저작 API(내부) | synthetic-data, model-lab, release-gate |
| I2 DatasetStore | synthetic-data | synthetic-data | model-lab |
| I3 ModelRegistry | model-lab | model-lab | release-gate |
| I4 ReleaseReader | release-gate | release-gate | survey-service, ops-feedback, question-authoring, model-lab, admin-console |
| I5 GateService | release-gate | operator, ops-feedback, release-approver(admin-console 경유, 게이트웨이가 사람 인증 뒤 `X-Openit-User`를 붙임) | — |
| I6 TraceIngest | ops-feedback | survey-service | — |
| I7 FailureStore | ops-feedback | ops-feedback | synthetic-data, model-lab, question-authoring, admin-console(사례 검토) |
| I8 turn-engine (3.0.0 폐기: 출력 규칙은 계약 `action_rules`, 서버가 보증, D109·ADR 0010) | — | — | — |
| I9 model-runtime | model-runtime | — | survey-service, model-lab, release-gate |
| I10 공개 API | survey-service | — | kiosk-frontend(환자 화면, 직원 콘솔). 운영 화면(admin-console)은 I5·I4·I7만 쓴다 |

## I1. QuestionReader (question-authoring)

문항 세트는 불변 버전이다. `ArtifactRef.content_hash`는 `QuestionBank` JSON의 해시다. 문항 저장소에 쓰는 것은 저작 API뿐이며 이 SDK로는 읽기만 한다.

```
get_question_bank(ref: Ref) -> QuestionBank            # 문진 스키마 JSON. 해시 검증. NOT_FOUND, INTEGRITY_ERROR
latest(question_set_id: str, *, reviewed_only: bool = False) -> Ref   # reviewed_only면 APPROVED 검수가 있고 clinical_basis_approved가 true인 최신. 없으면 NOT_FOUND
list_ids(*, cursor=None, limit=100) -> Page[str]       # 문항 세트 ID 목록
list_versions(question_set_id: str, *, cursor=None, limit=100) -> Page[Ref]   # 오래된 것부터
get_reviews(ref: Ref) -> list[ReviewRecord]            # 시각순
get_change(ref: Ref) -> ChangeClassification | None    # 첫 버전이면 None
```

`ArtifactRef.version`은 문항 세트 버전 번호 n(1부터)의 문자열이고, 같은 번호가 `QuestionBank.version`(정수)이다. 즉 `ref.version == str(question_bank.version)`이 항상 성립한다. `reviewed_only`는 가장 최근 `ReviewRecord`가 승인(APPROVED이면서 `clinical_basis_approved`가 true)인 버전만 낸다. 승인 뒤에 반려가 덧붙으면 그 버전은 나오지 않는다(승인 철회). `ChangeClassification.affected_slots`의 각 문자열은 `<question_id>.<slot_id>`이다(반복 키는 쓰지 않는다). 문항 자료를 올린 출처는 `ReviewRecord.ext["question-authoring"].source`에 있다.

저작 영역이 지키는 것: 문항 세트 버전은 저자(의료인)가 미리보기로 확인해야 만들어지고, 그 확인이 `ReviewRecord`(`clinical_basis_approved`)로 남는다(D30, D31). 검수가 끝나지 않은 버전도 `get_question_bank`로는 읽히지만 `reviewed_only` 조회에는 나오지 않는다. 같은 `(question_set_id, version)`의 내용은 바뀌지 않는다.

## I2. DatasetStore (synthetic-data)

파일은 JSON Lines이고 `role`이 LORA_A면 한 줄이 `ActionExtractionSample`, LORA_B면 `ResponseSample`이다(2.0.0. v1의 PARSER/GENERATOR와 두 샘플 스키마는 없어졌다).

```
publish(manifest: DatasetManifest, files: Mapping[str, Path]) -> DatasetManifest
    # files의 키는 manifest.files[].path. 파일 해시·줄 수(sample_count)·분할 일치를 검증한다.
    # 평가(EVAL) 샘플의 scenario_id가 TRAIN·VALIDATION과 겹치면 INVALID_RECORD.
    # files[].question_sets로 평가 파일이 학습에 쓰지 않은 문항 세트를 쓰는지 알 수 있다(보지 못한 문항 평가, D32).
    # 멱등: 같은 (dataset_id, version)에 같은 content_hash면 기존 것을 돌려준다. 다르면 CONFLICT.
get_manifest(dataset_id: str, version: str) -> DatasetManifest
list_versions(dataset_id: str) -> list[str]            # 오래된 것부터
open_file(dataset_id: str, version: str, path: str) -> BinaryIO   # 해시 검증은 manifest의 content_hash로
```

2.1.0부터 HTTP 면이 있다: `HTTP.md` `## I2`(D100). 원격 클라이언트는 `HttpDatasetStore`이고, `download(dataset_id, version, dest)`로 파일 묶음을 한 번에 받는다(Protocol 밖).

## I3. ModelRegistry (model-lab)

```
publish(manifest: ModelPackageManifest, adapter_dir: Path, eval_report: bytes) -> ModelPackageManifest
    # adapter_dir의 해시가 manifest.adapter_hash와 같아야 한다. adapter_dir 안에 manifest.system_prompt.path의 시스템 프롬프트 파일이 있고 그 파일 해시가 manifest.system_prompt.sha256과 같아야 한다(D75, 아니면 INTEGRITY_ERROR). eval_report는 manifest.eval_report_ref로 저장된다.
    # 멱등 규칙은 I2와 같다. 같은 (package_id, version)은 불변.
get_manifest(package_id: str, version: str) -> ModelPackageManifest
list_ids(*, cursor=None, limit=100) -> Page[str]       # 패키지 ID 목록
list_versions(package_id: str) -> list[str]            # 오래된 것부터(I2와 같다)
open_adapter(package_id: str, version: str, *, dest: Path) -> Path   # dest 아래에 어댑터를 풀고 해시를 검증한다
get_eval_report(ref: str) -> bytes                     # EvaluationReport(JSON). 사람이 읽는 첨부이기도 하다. 게이트는 스키마·해시·대상(어느 패키지의 보고서인가)만 확인하고 합격 임계치로 해석하지 않는다(D53)
```

## I4. ReleaseReader (release-gate)

게이트는 릴리스를 만들 때 문항 세트와 어댑터 내용을 릴리스 안에 **복사해 묶는다**. 그래서 서비스는 I1·I3 없이 이 SDK 하나로 필요한 것을 모두 얻는다.

```
get_active_pointer() -> ActivePointer | None           # 값싼 호출. 읽는 쪽이 주기적으로 불러 pointer_version이 달라졌는지 본다
get_release(release_id: str) -> ReleaseManifest
load_bundle(release_id: str, *, dest: Path) -> ReleaseBundle
    # ReleaseBundle(manifest: ReleaseManifest, question_bank: QuestionBank,
    #               adapters: dict["LORA_A"|"LORA_B", Path])
    # 서비스가 I9 load에 넘기는 serving_config와 해시는 manifest.adapters[role]에 있다(I3를 읽지 않는다).
    # 모든 해시를 검증한다(어댑터 디렉터리, 그 안의 시스템 프롬프트 파일 manifest.adapters[role].system_prompt 포함). 통과(PASS)하지 않은 릴리스는 FAILED_PRECONDITION.
get_decision(decision_id: str) -> GateDecision
find_decisions(*, question_set: Ref | None = None, lora_a: Ref | None = None, lora_b: Ref | None = None,
               submission_id: str | None = None, cursor=None, limit=100) -> Page[GateDecision]   # 최신부터. 같은 조합의 첫 항목이 그 조합의 현재 판정이다
list_releases(*, cursor=None, limit=100) -> Page[ReleaseManifest]   # 최신부터
```

서비스가 지키는 것: 포인터가 바뀌면 **새 세션부터** 새 릴리스를 쓴다(O13). 적재를 거부하는 경우는 둘이다: (1) `runtime_contract_version`이 지원 버전이 아님, (2) 릴리스의 `action_rules_version`(3.0.0, 이전 `turn_engine_version`)이 다르거나 `model_runtime_version`의 MAJOR.MINOR가 이미지에 설치된 것과 다름(게이트가 승인한 동작과 달라질 수 있기 때문이다. PATCH 차이는 경고만 하고 적재한다). 거부하면 이전 릴리스를 유지하고 이유를 `/readyz`에 낸다. `runtime_contract_version`을 지원하지 않는 릴리스는 `load_bundle` 결과를 적재하지 않고 이전 릴리스를 유지한다.

## I5. GateService (release-gate)

역할(`requested_by_role`)은 **토큰에 묶여 있다**. 호출자가 말한 역할이 토큰의 역할과 다르면 `PERMISSION_DENIED`이고, 인자는 기록용이다. 허용 역할: 접수 `operator`·`release-gate-collector`·`question-authoring`·`model-lab`, 활성화 `operator`, 롤백 `ops-feedback`·`operator`(설정으로 바꾼다), 승인 `release-approver`(D53, HTTP.md `decide`와 `X-Openit-User`). 같은 조합에 판정이 여러 개일 수 있다. 정책 버전이 바뀐 뒤의 재판정은 같은 `submission_id`에 새 `GateDecision`을 더하고 가장 최근 것이 현재 판정이다. `reject_codes`가 `POLICY_INCOMPLETE`이면 조합이 나쁘다는 뜻이 아니다.

서비스 API다. 쓰기 권한은 게이트에만 있다.

```
submit_candidate(subject: GateSubject, *, requested_by_role: str) -> GateSubmission
    # GateSubject = {question_set: Ref, lora_a: Ref, lora_b: Ref}. 즉시 접수만 하고 판정은 비동기.
    # 판정이 끝나면 GateDecision(submission_id로 연결)이 생긴다. 같은 subject의 중복 요청은 기존 접수를 돌려준다.
activate(release_id: str, *, requested_by_role: str) -> ActivePointer
    # PASS로 만든 릴리스만 가능. 아니면 FAILED_PRECONDITION. 포인터 변경은 원자적이다.
request_rollback(request: RollbackRequest) -> RollbackReceipt
    # to_release_id가 PASS 릴리스이고 from_release_id가 현재 활성이면 APPLIED. 아니면 REJECTED와 사유.
    # 같은 request_id는 같은 결과를 돌려준다(멱등).
```

게이트가 지키는 것: 판정은 통과·반려 모두 `GateDecision`으로 남긴다. 통과일 때만 `ReleaseManifest`를 만들고 릴리스 안에 내용을 묶는다. 어떤 검사가 필수인지는 `gate_policy_version`이 정한다.

## I6. TraceIngest (ops-feedback)

```
send(envelope: TraceEnvelope) -> IngestResult
    # 키는 (session_id, turn_id). 처음이면 ACCEPTED, 이미 있으면 DUPLICATE(먼저 받은 것을 유지한다).
    # trace는 envelope.runtime_contract_version의 문진 스키마 TurnTrace로 검증한다. 위반이면 INVALID_RECORD.
```

HTTP 규약은 `CONVENTIONS.md` 9절이다: `POST /v1/traces`.

서비스가 지키는 것: 전송은 턴 처리와 분리한다. 실패하면 서비스 쪽 영속 버퍼에 두고 `UNAVAILABLE`일 때만 재시도한다(최소 1회 전달, D16). 전송 때문에 턴 응답이 늦어지거나 실패하면 안 된다.
수집이 지키는 것: 원본은 비식별 처리기만 읽는다(D15).

## I7. FailureStore (ops-feedback)

```
publish_case(case: FailureCase) -> FailureCase        # 멱등: (case_id, version). 같은 키에 다른 내용이면 CONFLICT
get_case(case_id: str, *, version: int | None = None) -> FailureCase   # 기본은 최신 version
list_cases(*, review_status=None, failure_type=None, source_release_id=None,
           updated_since: datetime | None = None, latest_only: bool = True,
           cursor=None, limit=100) -> Page[FailureCase]
get_trace(deidentified_trace_ref: str) -> dict         # 비식별 TurnTrace(DeidentifiedTurnTrace). FailureCase에 비식별 전 데이터는 없다
```

`get_trace`가 돌려주는 것은 TurnTrace의 **형태를 따르지만 TurnTrace 스키마 통과를 보장하지 않는다.** 자유 문자열은 마스킹 토큰으로 바뀌고, 스키마에 없는 키와 구조 없는 객체는 제거되며, 정책이 지목한 값은 통째로 마스킹된다. 소비자는 이것을 `TurnTrace`로 검증하지 말고 **구조 정보**(열거값, 식별자, 개수, 순서)만 쓴다. 비식별 뒤에 발화 문장 자체를 어디까지 남길지는 비식별 기준이며 사용자가 정한다(O19). `RollbackRequest.evidence_refs`는 ops-feedback이 해석하는 불투명한 Id이고 게이트는 기록만 한다.

소비자가 지키는 것: `review_status`가 CONFIRMED이고 `expected`가 있는 것만 정답 있는 회귀 케이스로 쓴다.

## I8. turn-engine — 3.0.0 폐기 (D109)

> 3.0.0: turn-engine은 쓰지 않는다. LoRA-A 출력 규칙은 계약 `boundary_contracts.action_rules`와 규칙 데이터가 정본이고 model-runtime 서버가 보증한다(ADR 0010, R7). 계보 표지는 `action_rules_version`. 아래는 2.x 기록이다.

### (2.x 기록) 출력 검증 라이브러리 (2.0.0, D74·D75)

`normalize`, `judge`, `write_record`, `plan`은 이 계약에서 없어졌다. 이 함수들은 파서 출력을 정규화·판정하고 다음 문항을 계획하는 단계였는데, 학습 데이터셋 v2에서는 LoRA-A가 값 정규화·절차(`action`)·다음 문항(`next_item`)을 한 번에 낸다(`ActionExtraction`). 서비스에는 정규화기·판정기·Plan 코드가 없다. v1.3.3은 태그로 남는다.

> 3.0.0 갱신: 아래 '의미 검증'은 turn-engine이 아니라 계약 `boundary_contracts.action_rules`의 규칙 데이터로 model-runtime 서버가 보증한다(ADR 0010, R7, D109). survey-service는 다시 검증하지 않는다. 아래는 D75 당시의 서술로 남긴다.

turn-engine은 폐기하지 않고 **A 출력의 의미 검증 안전망**으로 남는다(D75). 의료 문진 기록에 틀린 값이 들어가는 것보다 다시 묻는 편이 안전하기 때문이다. 검증은 둘로 나뉜다.
- **형식(스키마)**: model-runtime이 `ActionExtraction` 스키마로 검증한다(I9). 어기면 재시도하고 끝내 못 지키면 503 `OUTPUT_INVALID`.
- **의미**: turn-engine의 순수 함수가 검증하고 survey-service가 호출한다. 스키마로 표현할 수 없는 규칙이다: (a) `targets`가 같은 출력 `values`의 `key` 부분집합, (b) `next_item` 규칙(REASK·REDIRECT는 입력 `question_id`와 같다. CONFIRM은 `targets` 칸의 문항이다. NEXT·CORRECT·HOLD·SKIP은 문항 순서와 건너뛰기 규칙의 다음 문항이다. 한 말에 여러 문항의 값이 나오면 가장 뒤 문항이 기준이다), (c) 건너뛰기 순서, (d) `save` 규칙(`save`는 status가 ANSWERED 또는 CORRECTION일 때만 true이고, 나머지 status의 `value`는 null).

함수 시그니처 **초안**(문서일 뿐이며 코드는 turn-engine 영역이 만든다. 시그니처는 그 영역이 바꿀 수 있고 바꾸면 이 절을 고친다):

```
validate_extraction(input: ActionExtractionInput, output: ActionExtraction, flow: QuestionFlowTable) -> list[Violation]
    # 순수 함수. 같은 입력은 같은 출력이다. 위반이 없으면 빈 목록. 입력이 스키마를 어기면 ContractViolation.
QuestionFlowTable    # 문진 스키마(QuestionBank)에서 만든 읽기 전용 표: 문항 ID 순서 목록, 건너뛰기 규칙 목록(조건 칸·값 -> 건너뛸 문항)
Violation            # (code, path, message). code 예: TARGET_NOT_IN_VALUES, NEXT_ITEM_MISMATCH, SKIP_ORDER_MISMATCH, SAVE_RULE
ENGINE_VERSION: str                       # 매니페스트에 기록되는 값
SUPPORTED_RUNTIME_CONTRACT_VERSION: int
```

`validate_extraction`은 "같은 말에서 이미 일부 칸이 채워진 문항으로 넘어가는 NEXT"(계약이 허용한다, V2_DRAFT.md)를 위반으로 세지 않는다. 위반이 나오면 survey-service는 `OUTPUT_INVALID`와 같게 처리한다(I9의 "서비스가 지키는 것"). 문항 순서·건너뛰기 표는 문진 스키마가 소유하고 이 계약은 표의 형식을 정하지 않는다.

## I9. model-runtime (라이브러리)

2.0.0에서 입출력이 학습 데이터셋 v2의 형식으로 바뀌었다: `parse`/`generate`와 문진 스키마의 파서·생성기 입출력은 `extract`/`respond`와 이 리포지토리의 `ActionExtraction` 계열로 대체되었다.

**`runtime_contract_version`의 의미(D75, 유지).** 모델 패키지가 학습된 **문진 스키마(문항 은행·칸 키)의 정수 버전**이다. 소유는 survey-service이고(D19, D21) 필드는 지우지 않는다(지우면 또 MAJOR). 모델 입출력 스키마가 이 리포지토리로 옮겨 왔어도 `load`의 `schema_dir`(문진 스키마 배포 디렉터리)와 `SUPPORTED_RUNTIME_CONTRACT_VERSION` 확인은 그대로다. 서비스와 게이트는 이 값이 다르면 적재를 거부한다(UNSUPPORTED_VERSION).

```
load(adapters: Mapping["LORA_A"|"LORA_B", Path], serving_configs: Mapping["LORA_A"|"LORA_B", Mapping], *,
     schema_dir: Path, expected_serving_config_hashes: Mapping["LORA_A"|"LORA_B", str], backend=None) -> ModelSession
    # 설정과 해시는 역할마다 받는다(D45). ReleaseManifest.adapters[role]과 모델 패키지가 역할별이기 때문이다.
    # 어댑터, 설정, 기대 해시의 역할 집합이 서로 다르면 ContractViolation.
    # schema_dir: 문진 스키마의 배포 스키마 디렉터리(`<...>/schema/schemas`, <계약명>.json이 있는 곳). 상위의 CONTRACT_VERSION을 읽어
    #   SUPPORTED_RUNTIME_CONTRACT_VERSION과 다르면 ContractVersionMismatch.
    # 역할마다 serving_config_hash(serving_configs[role]) != expected_serving_config_hashes[role] 이면 ServingConfigMismatch.
    # 지원하지 않는 프롬프트 템플릿·디코딩 버전이면 UnsupportedServingConfig.
ModelSession.extract(input: ActionExtractionInput, flow: QuestionFlowTable, fields: {fields: [QuestionFieldSpec]}) -> ActionExtraction   # 3.0.0: flow·fields 필수
# (이전 서명) ModelSession.extract(input: ActionExtractionInput) -> ActionExtraction   # LoRA-A. 항상 스키마를 통과하는 값. 아래 '출력 검증'
ModelSession.respond(input: ResponseRequest) -> ResponseResult         # LoRA-B. ResponseResult(text: str, is_fallback: bool). 아래 '출력 검증'
ModelSession.extract_raw(input) -> RawResult    # 평가용: 검증 전 모델 출력과 유효 여부. RawResult(output: dict | str | None, valid: bool, errors: list[str])
ModelSession.respond_raw(input) -> RawResult
ModelSession.last_call_info                   # 시도 횟수, 보호(repaired|fallback) 여부와 종류 등. 입력 원문은 담지 않는다
render_prompt(role: "LORA_A"|"LORA_B", input: Mapping, *, serving_config: Mapping, system_prompt: str, schema_dir: Path) -> str   # system_prompt는 모델 패키지의 프롬프트 파일 내용(아래 '시스템 프롬프트')
serving_config_hash(serving_config: Mapping) -> str     # boundary_contracts.canonical 기준
validate_serving_config(serving_config: Mapping) -> None  # 형식 위반이면 ContractViolation. model-lab이 매니페스트를 쓰기 전에 호출한다
FakeModelSession                    # 모델 없이 호출 경로를 시험하는 구현. 실제와 같은 검증·재시도·보호 경로를 거친다
RUNTIME_VERSION: str
SUPPORTED_RUNTIME_CONTRACT_VERSION: int
```

전역 설정 함수(`configure`)는 두지 않는다. 필요한 값은 모두 인자로 받는다.

`serving_config`의 형식은 model-runtime이 정하고 라이브러리로 내놓는다(`ServingConfig`). 프롬프트 템플릿 버전, 디코딩 방식과 설정(제약 모드, 온도, 기본 시드), `max_attempts`를 반드시 포함한다. 어댑터에는 버전 정보를 따로 넣지 않는다. 어댑터는 `adapter_hash`(`directory_hash`)로, 설정은 `serving_config_hash`로 고정된다.

**출력 검증과 대체 응답(D36, 2.0.0).** 서버와 라이브러리는 모델 출력을 계약 스키마로 검증하고, 어기면 재시도(`max_attempts`)한다. 재시도의 프롬프트는 첫 시도와 같고(검증 오류를 덧붙이지 않는다), 시드만 `기본 시드 + 시도 번호`로 바꾼다.
- `extract`(LoRA-A): 재시도를 다 써도 `ActionExtraction`을 지키지 못하면 **대체 출력을 만들지 않는다**(값을 지어내지 않는다). 라이브러리는 `ModelOutputInvalid`를 던지고, HTTP 서버는 503 `UNAVAILABLE`(`details.reason="OUTPUT_INVALID"`, `details.attempts`는 선택)로 낸다. **확정(D75).**
- `respond`(LoRA-B): 출력은 JSON이 아니라 **문장 그대로의 텍스트**(`ResponseText`)다. 형식(비어 있지 않은 문자열)을 지키지 못하면 입력의 재료(`known`, `ask`, `hold`, `next.text`)를 이어 붙여 읽는 문장을 대신 내고, 대체했음을 알린다. 라이브러리는 `is_fallback=true`, HTTP는 응답 헤더 `X-Openit-Outcome: fallback`이다. `is_fallback`은 모델이 아니라 코드가 채운다. 대체 문장을 만드는 규칙은 model-runtime이 정한다(계약 밖, 미정).
- 대체 응답이나 재시도가 일어나면 `last_call_info`에 몇 번 시도했고 어떤 보호가 몇 건 적용됐는지 남긴다. 조용히 지나가지 않는다. model-lab은 `*_raw`로 검증 전 품질을 따로 잰다.
- 라이브러리 예외는 인프라 문제에만 쓴다(`BackendNotAvailable` 등). `BoundaryError`가 아니다.
**서비스가 지키는 것: `OUTPUT_INVALID` 처리(D75).** survey-service는 `extract`가 503 `OUTPUT_INVALID`를 내거나 turn-engine의 `validate_extraction`이 위반을 내면 **같은 요청을 한 번 다시 보낸다.** 그래도 같으면 그 턴을 실패 신호(`TurnFailureSignal`, `write_committed`는 NOT_COMMITTED)로 처리하고 **세션 상태를 바꾸지 않는다**(기록 저장, 진행 갱신 없음). 틀린 값을 기록에 넣는 것보다 환자에게 다시 묻는 편이 안전하다. 다른 이유의 `UNAVAILABLE`은 서비스의 일반 재시도 정책을 따른다. 클라이언트는 `boundary_contracts.clients.is_output_invalid(err)`로 구분한다.

**시스템 프롬프트는 모델 패키지의 일부다(D75).** LoRA 어댑터와 짝이 되는 시스템 프롬프트 파일이 어댑터 디렉터리 안에 있고, `ModelPackageManifest.system_prompt`(`path`는 디렉터리 안의 상대 경로, `sha256`은 파일 바이트의 `canonical.file_hash`)가 이를 가리킨다. 게이트는 같은 값을 `ReleaseManifest.adapters[role].system_prompt`로 복사한다(서비스가 I3를 읽지 않아도 되게). model-runtime은 서빙할 때 **이 패키지의 프롬프트만 쓴다**(코드나 설정에 박은 문장을 쓰지 않는다). LoRA 교체(D72)가 프롬프트까지 함께 바뀌어야 하기 때문이다. 프롬프트 파일은 어댑터 디렉터리 안에 있으므로 `adapter_hash`에도 포함되고, 클라이언트(`open_adapter`, `load_bundle`, `publish`)는 파일이 있고 `sha256`이 맞는지 따로 확인한다(어기면 INTEGRITY_ERROR). 역할마다 하나(A, B 각 한 종)다. `serving_config`의 **프롬프트 템플릿 버전**과는 다른 것이다: 시스템 프롬프트는 *무슨 말을 시키는가*(패키지 데이터, 학습과 짝)이고, 템플릿 버전은 *입력 JSON과 시스템 프롬프트를 어떻게 채팅 형식으로 조립하는가*(model-runtime 코드의 렌더링 규칙)다. 둘 다 해시로 고정된다(`system_prompt.sha256`, `serving_config_hash`).

제약 디코딩은 교체 가능한 백엔드이고 엔진 선택은 model-runtime이 정한다(O14).

**어댑터 형식과 재현성(D48).** 어댑터는 PEFT 형식의 디렉터리(`adapter_config.json`에 순위 `r`와 `base_model_name_or_path`)다. model-lab이 이 형식으로 내고, model-runtime은 엔진에 올리기 전에 `adapter_config.json`의 순위가 `serving_config`의 `max_lora_rank`를 넘으면 `UnsupportedServingConfig`로 거부한다(엔진 전체가 죽는 것을 막는다). 제약 디코딩은 엔진 버전에 따라 지원하는 스키마 키워드가 다르다. 확인된 vLLM 0.31.0 + xgrammar 0.2.7에서는 `allOf`, `if/then`, `not`을 조용히 무시하고 `uniqueItems`를 거부하므로 그런 규칙은 사후 검증과 보호가 맡는다. 엔진과 라이브러리 버전은 `serving_config.constraint.backend_version`에 고정되어 해시에 반영된다. **재현성은 같은 서버 프로세스 안에서만 약속한다.** 서버를 다시 띄우면 온도 > 0의 긴 출력은 달라질 수 있어서, 평가와 서비스의 일치를 토큰 단위로 약속하지 않는다. 평가는 온도 0에서 한다.

## I10. 공개 API (survey-service ↔ Frontend)

전송(HTTP/JSON), 인증(Bearer 토큰, 키오스크는 기기 토큰), 오류와 재시도, 세션 시작·발화·종료·상태·개입 결정·직원 알림·직원 호출 재알림의 호출 모양은 **`PUBLIC_API.md`가 정본**이다(이 절은 복사하지 않고 가리킨다). HTTP 규약만 `HTTP.md ## I10`에 있다. 읽는 쪽은 kiosk-frontend(환자 화면, 직원 콘솔)다. 메시지의 본문은 문진 스키마의 `FrontendMessage`·`FrontendInput`이다. 클라이언트 `HttpPublicApi`·`HttpStaffCall`(Protocol `sdk.PublicApi`·`sdk.StaffCall`)과 참조 서버 `conformance.servers.PublicApiReferenceServer`가 있다.

## 영역별 책임 요약 (받는 것 / 내는 것)

| 영역 | 받는 것 | 내는 것 |
| --- | --- | --- |
| question-authoring | 관리자 입력, I7(개선 신호), I4(판정 조회) | I1 |
| synthetic-data | I1, I7 | I2 |
| model-lab | I2, I1, I7, I4, I9 | I3 |
| release-gate | I1, I3, I9, I5 요청 | I4, I5 |
| survey-service | I4, I8, I9 | I6, I10 |
| ops-feedback | I6, I4, (롤백 요청은 I5 호출) | I7, I6 수집 |
| turn-engine / model-runtime | 이 리포지토리의 모델 입출력 스키마, 문진 스키마 | I8 / I9 |
