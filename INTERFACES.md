# 영역 경계 명세

각 영역이 **무엇을 내놓고 무엇을 받는지**를 정한다. 상대 영역은 블랙박스이며, 아래 명세만 믿고 개발한다. 오류·멱등성·버전·인증은 `CONVENTIONS.md`를 따른다. 타입 이름 중 `ReleaseManifest` 같은 것은 이 리포지토리의 스키마이고, `QuestionBank`·`TurnTrace`·`UtteranceParserInput` 같은 것은 문진 스키마(`survey-service/schema`)의 계약이다. 시그니처는 `typing.Protocol`로 옮길 수 있는 형태로 적었다.

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
| I4 ReleaseReader | release-gate | release-gate | survey-service, ops-feedback, question-authoring, model-lab |
| I5 GateService | release-gate | operator, ops-feedback | — |
| I6 TraceIngest | ops-feedback | survey-service | — |
| I7 FailureStore | ops-feedback | ops-feedback | synthetic-data, model-lab, question-authoring |
| I8 turn-engine | turn-engine | — | survey-service, synthetic-data, model-lab, release-gate, question-authoring |
| I9 model-runtime | model-runtime | — | survey-service, model-lab, release-gate |
| I10 공개 API | survey-service | — | Frontend (미정, O06) |

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

파일은 JSON Lines이고 `role`이 PARSER면 한 줄이 `ParserSample`, GENERATOR면 `GeneratorSample`이다.

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

## I3. ModelRegistry (model-lab)

```
publish(manifest: ModelPackageManifest, adapter_dir: Path, eval_report: bytes) -> ModelPackageManifest
    # adapter_dir의 해시가 manifest.adapter_hash와 같아야 한다. eval_report는 manifest.eval_report_ref로 저장된다.
    # 멱등 규칙은 I2와 같다. 같은 (package_id, version)은 불변.
get_manifest(package_id: str, version: str) -> ModelPackageManifest
list_ids(*, cursor=None, limit=100) -> Page[str]       # 패키지 ID 목록
list_versions(package_id: str) -> list[str]            # 오래된 것부터(I2와 같다)
open_adapter(package_id: str, version: str, *, dest: Path) -> Path   # dest 아래에 어댑터를 풀고 해시를 검증한다
get_eval_report(ref: str) -> bytes                     # 사람이 읽는 첨부. 게이트는 내용을 해석하지 않는다
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
    # 모든 해시를 검증한다. 통과(PASS)하지 않은 릴리스는 FAILED_PRECONDITION.
get_decision(decision_id: str) -> GateDecision
find_decisions(*, question_set: Ref | None = None, lora_a: Ref | None = None, lora_b: Ref | None = None,
               submission_id: str | None = None, cursor=None, limit=100) -> Page[GateDecision]   # 최신부터. 같은 조합의 첫 항목이 그 조합의 현재 판정이다
list_releases(*, cursor=None, limit=100) -> Page[ReleaseManifest]   # 최신부터
```

서비스가 지키는 것: 포인터가 바뀌면 **새 세션부터** 새 릴리스를 쓴다(O13). 적재를 거부하는 경우는 둘이다: (1) `runtime_contract_version`이 지원 버전이 아님, (2) 릴리스의 `turn_engine_version` 또는 `model_runtime_version`의 MAJOR.MINOR가 이미지에 설치된 것과 다름(게이트가 승인한 동작과 달라질 수 있기 때문이다. PATCH 차이는 경고만 하고 적재한다). 거부하면 이전 릴리스를 유지하고 이유를 `/readyz`에 낸다. `runtime_contract_version`을 지원하지 않는 릴리스는 `load_bundle` 결과를 적재하지 않고 이전 릴리스를 유지한다.

## I5. GateService (release-gate)

역할(`requested_by_role`)은 **토큰에 묶여 있다**. 호출자가 말한 역할이 토큰의 역할과 다르면 `PERMISSION_DENIED`이고, 인자는 기록용이다. 허용 역할: 접수 `operator`·`release-gate-collector`·`question-authoring`·`model-lab`, 활성화 `operator`, 롤백 `ops-feedback`·`operator`(설정으로 바꾼다). 같은 조합에 판정이 여러 개일 수 있다. 정책 버전이 바뀐 뒤의 재판정은 같은 `submission_id`에 새 `GateDecision`을 더하고 가장 최근 것이 현재 판정이다. `reject_codes`가 `POLICY_INCOMPLETE`이면 조합이 나쁘다는 뜻이 아니다.

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

## I8. turn-engine (라이브러리)

모두 순수 함수다. 같은 입력은 같은 출력을 낸다. I/O·시간·난수는 인자로 주입한다. 입력과 출력은 문진 스키마의 계약이다.

```
normalize(input: AnswerNormalizerInput) -> NormalizerOutput
judge(input: AnswerJudgeInput) -> JudgeOutput
write_record(input: RecordWriterInput) -> StoreResult
plan(input: DialoguePlannerInput) -> PlannerOutput
ENGINE_VERSION: str                 # 매니페스트에 기록되는 값
SUPPORTED_RUNTIME_CONTRACT_VERSION: int
```

입력이 문진 스키마를 위반하면 `ContractViolation`을 던진다(경계 호출이 아니라 라이브러리이므로 `BoundaryError`가 아님).

## I9. model-runtime (라이브러리)

```
load(adapters: Mapping["LORA_A"|"LORA_B", Path], serving_configs: Mapping["LORA_A"|"LORA_B", Mapping], *,
     schema_dir: Path, expected_serving_config_hashes: Mapping["LORA_A"|"LORA_B", str], backend=None) -> ModelSession
    # 설정과 해시는 역할마다 받는다(D45). ReleaseManifest.adapters[role]과 모델 패키지가 역할별이기 때문이다.
    # 어댑터, 설정, 기대 해시의 역할 집합이 서로 다르면 ContractViolation.
    # schema_dir: 문진 스키마의 배포 스키마 디렉터리(`<...>/schema/schemas`, <계약명>.json이 있는 곳). 상위의 CONTRACT_VERSION을 읽어
    #   SUPPORTED_RUNTIME_CONTRACT_VERSION과 다르면 ContractVersionMismatch.
    # 역할마다 serving_config_hash(serving_configs[role]) != expected_serving_config_hashes[role] 이면 ServingConfigMismatch.
    # 지원하지 않는 프롬프트 템플릿·디코딩 버전이면 UnsupportedServingConfig.
ModelSession.parse(input: UtteranceParserInput) -> ParserOutput          # 항상 스키마를 통과하는 값. 아래 '출력 보호'
ModelSession.generate(input: ResponseGeneratorInput) -> GeneratorOutput  # 항상 스키마를 통과하는 값. 아래 '출력 보호'
ModelSession.parse_raw(input) -> RawResult    # 평가용: 보호 전 모델 출력과 유효 여부. RawResult(output: dict | None, valid: bool, errors: list[str])
ModelSession.generate_raw(input) -> RawResult
ModelSession.last_call_info                   # 시도 횟수, 보호(repaired|fallback) 여부와 종류 등. 입력 원문은 담지 않는다
render_prompt(role: "LORA_A"|"LORA_B", input: Mapping, *, serving_config: Mapping, schema_dir: Path) -> str
serving_config_hash(serving_config: Mapping) -> str     # boundary_contracts.canonical 기준
validate_serving_config(serving_config: Mapping) -> None  # 형식 위반이면 ContractViolation. model-lab이 매니페스트를 쓰기 전에 호출한다
FakeModelSession                    # 모델 없이 호출 경로를 시험하는 구현. 실제와 같은 검증·재시도·보호 경로를 거친다
RUNTIME_VERSION: str
SUPPORTED_RUNTIME_CONTRACT_VERSION: int
```

전역 설정 함수(`configure`)는 두지 않는다. 필요한 값은 모두 인자로 받는다.

`serving_config`의 형식은 model-runtime이 정하고 라이브러리로 내놓는다(`ServingConfig`). 프롬프트 템플릿 버전, 디코딩 방식과 설정(제약 모드, 온도, 기본 시드), `max_attempts`를 반드시 포함한다. 어댑터에는 버전 정보를 따로 넣지 않는다. 어댑터는 `adapter_hash`(`directory_hash`)로, 설정은 `serving_config_hash`로 고정된다.

**출력 보호(D36).** 문진 스키마의 업무 규칙은 각 컴포넌트가 "출력이 자기 계약을 지키는 것까지 책임지고, 지키지 못할 때 낼 대체 출력도 정해 둔다"고 한다. 그래서 `parse`와 `generate`는 모델 출력이 깨져도 예외를 던지지 않고 **규칙이 정한 대체 출력**을 돌려준다(턴은 실패하지 않는다). 재시도(`max_attempts`)를 다 쓴 뒤에도 유효하지 않으면 보호를 적용한다. 재시도의 프롬프트는 첫 시도와 같고(검증 오류를 덧붙이지 않는다), 시드만 `기본 시드 + 시도 번호`로 바꾼다.
- `parse`: 형식을 못 지키면 빈 목록. 항목의 의도, 대상, 값이 규칙을 어기면 규칙이 정한 대로 고친다(대체 출력 규칙은 업무 규칙 문서에 있고, 이 라이브러리가 코드로 구현한다). 대상이 문항 정의에 없는 항목은 고치지 않고 그대로 낸다.
- `generate`: 모델은 `response_text`만 낸다. `is_fallback`은 **모델이 아니라 코드가 채운다**(정상이면 false). 응답 지시를 지키지 못하면 문장 재료를 그대로 읽는 문장을 만들고 `is_fallback=true`로 낸다.
- 보호가 적용되면 `last_call_info`에 어떤 보호가 몇 건 적용됐는지 남긴다. 조용히 지나가지 않는다. model-lab은 `*_raw`로 보호 전 품질을 따로 잰다.
- 라이브러리 예외는 인프라 문제에만 쓴다(`BackendNotAvailable` 등). `BoundaryError`가 아니다.
제약 디코딩은 교체 가능한 백엔드이고 엔진 선택은 model-runtime이 정한다(O14).

**어댑터 형식과 재현성(D48).** 어댑터는 PEFT 형식의 디렉터리(`adapter_config.json`에 순위 `r`와 `base_model_name_or_path`)다. model-lab이 이 형식으로 내고, model-runtime은 엔진에 올리기 전에 `adapter_config.json`의 순위가 `serving_config`의 `max_lora_rank`를 넘으면 `UnsupportedServingConfig`로 거부한다(엔진 전체가 죽는 것을 막는다). 제약 디코딩은 엔진 버전에 따라 지원하는 스키마 키워드가 다르다. 확인된 vLLM 0.31.0 + xgrammar 0.2.7에서는 `allOf`, `if/then`, `not`을 조용히 무시하고 `uniqueItems`를 거부하므로 그런 규칙은 사후 검증과 보호가 맡는다. 엔진과 라이브러리 버전은 `serving_config.constraint.backend_version`에 고정되어 해시에 반영된다. **재현성은 같은 서버 프로세스 안에서만 약속한다.** 서버를 다시 띄우면 온도 > 0의 긴 출력은 달라질 수 있어서, 평가와 서비스의 일치를 토큰 단위로 약속하지 않는다. 평가는 온도 0에서 한다.

## I10. 공개 API (survey-service ↔ Frontend)

세션 시작, 발화 전달(세션 ID와 턴 ID, 같은 턴 ID 재전송은 같은 결과), 세션 종료, 상태 확인의 4동작만 정해져 있다. 전송 방식, 인증, 문진 대상 참조, 실패 신호의 의미와 타임아웃은 Frontend 팀과 협의 중이다(O06). 확정 전에는 이 부분을 설계하지 않는다. 메시지의 본문은 문진 스키마의 `FrontendMessage`·`FrontendInput`이다.

## 영역별 책임 요약 (받는 것 / 내는 것)

| 영역 | 받는 것 | 내는 것 |
| --- | --- | --- |
| question-authoring | 관리자 입력, I7(개선 신호), I4(판정 조회) | I1 |
| synthetic-data | I1, I7, I8 | I2 |
| model-lab | I2, I1, I7, I4, I8, I9 | I3 |
| release-gate | I1, I3, I8, I9, I5 요청 | I4, I5 |
| survey-service | I4, I8, I9 | I6, I10 |
| ops-feedback | I6, I4, (롤백 요청은 I5 호출) | I7, I6 수집 |
| turn-engine / model-runtime | 문진 스키마 | I8 / I9 |
