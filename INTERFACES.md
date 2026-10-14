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
list_versions(question_set_id: str, *, cursor=None, limit=100) -> Page[Ref]   # 오래된 것부터
get_reviews(ref: Ref) -> list[ReviewRecord]            # 시각순
get_change(ref: Ref) -> ChangeClassification | None    # 첫 버전이면 None
```

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
list_versions(package_id: str) -> list[str]
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
    # 모든 해시를 검증한다. 통과(PASS)하지 않은 릴리스는 FAILED_PRECONDITION.
get_decision(decision_id: str) -> GateDecision
find_decisions(*, question_set: Ref | None = None, lora_a: Ref | None = None, lora_b: Ref | None = None,
               submission_id: str | None = None, cursor=None, limit=100) -> Page[GateDecision]   # 최신부터
list_releases(*, cursor=None, limit=100) -> Page[ReleaseManifest]   # 최신부터
```

서비스가 지키는 것: 포인터가 바뀌면 **새 세션부터** 새 릴리스를 쓴다(O13). `runtime_contract_version`을 지원하지 않는 릴리스는 `load_bundle` 결과를 적재하지 않고 이전 릴리스를 유지한다.

## I5. GateService (release-gate)

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

서비스가 지키는 것: 전송은 턴 처리와 분리한다. 실패하면 서비스 쪽 영속 버퍼에 두고 `UNAVAILABLE`일 때만 재시도한다(최소 1회 전달, D16). 전송 때문에 턴 응답이 늦어지거나 실패하면 안 된다.
수집이 지키는 것: 원본은 비식별 처리기만 읽는다(D15).

## I7. FailureStore (ops-feedback)

```
publish_case(case: FailureCase) -> FailureCase        # 멱등: (case_id, version). 같은 키에 다른 내용이면 CONFLICT
get_case(case_id: str, *, version: int | None = None) -> FailureCase   # 기본은 최신 version
list_cases(*, review_status=None, failure_type=None, source_release_id=None,
           updated_since: datetime | None = None, latest_only: bool = True,
           cursor=None, limit=100) -> Page[FailureCase]
get_trace(deidentified_trace_ref: str) -> dict         # 비식별 TurnTrace. FailureCase에 비식별 전 데이터는 없다
```

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
load(adapters: Mapping["LORA_A"|"LORA_B", Path], serving_config: Mapping) -> ModelSession
ModelSession.parse(input: UtteranceParserInput) -> ParserOutput
ModelSession.generate(input: ResponseGeneratorInput) -> GeneratorOutput
render_prompt(role: "LORA_A"|"LORA_B", input: Mapping) -> str     # 학습 데이터 변환과 서빙이 같은 프롬프트를 쓰게 한다
FakeModelSession                    # 모델 없이 호출 경로를 시험하는 구현
RUNTIME_VERSION: str
SUPPORTED_RUNTIME_CONTRACT_VERSION: int
```

출력이 문진 스키마를 통과하지 못하면 규정된 재시도 뒤 `ModelOutputInvalid`를 던진다. 조용히 통과시키지 않는다(O14는 이 라이브러리가 방식을 정한다).

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
