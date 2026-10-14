# boundary-contracts

영역 사이에 오가는 데이터의 계약이다. 소유자는 헤드다. 문진 서비스 내부의 컴포넌트 계약은 여기에 없고 `../contracts`(HealthCheckSchema)에 있다. 이 리포지토리의 스키마는 그것을 수정하지 않고 필요하면 참조만 한다.

- `schemas/`: JSON Schema Draft 2020-12. 공통 타입은 `_common.schema.json`.
- `examples/`: 통과해야 하는 예시.
- `verify.py`: 스키마 유효성, 예시 통과, 위반 예시 거부를 검사한다. 변경 때마다 통과시킨다.

## 버전(D14, D19)

각 레코드는 `pipeline_schema_version`(`MAJOR.MINOR`)을 적는다. MAJOR는 깨지는 변경, MINOR는 읽는 쪽이 무시해도 되는 추가(선택 필드, 열거값 추가는 소비자가 모르는 값을 처리할 수 있을 때만)다. 읽는 쪽은 같은 MAJOR이고 MINOR가 자기가 아는 것 이하이거나 같을 때 읽고, 더 높은 MINOR는 모르는 필드를 무시하는 조건에서 읽는다. 런타임 계약의 정수 버전은 문진 스키마(`../contracts`)의 것이며 여기서는 `runtime_contract_version`으로 기록만 한다.

## 현재 계약 (초안, 사용자와 논의 중)

`../head/docs/STRUCTURE.md` 7절의 11개 모두: ReleaseManifest, GateDecision, TraceEnvelope, ReviewRecord, ChangeClassification, ParserSample, GeneratorSample, DatasetManifest, ModelPackageManifest, FailureCase, RollbackRequest. 모두 불변 레코드다(D25). 여기에 BoundaryError, IngestResult, GateSubmission, ActivePointer, RollbackReceipt가 더해진다.

## 코드

- `boundary_contracts/canonical.py`: JCS 정규화와 해시의 기준 구현. 시험: `python3 -m unittest discover -s tests`.

## 문서

- `CONVENTIONS.md`: 공통 규약(진화 규칙, ID·시각·해시, 오류, 멱등성, 인증, SDK 형태).
- `INTERFACES.md`: 영역 경계 명세 I1~I10(시그니처, 받는 것/내는 것).

## 규칙

- 불변 산출물은 `ArtifactRef`(id, version, content_hash)로 가리킨다.
- 해시는 정규화 JSON(RFC 8785)의 SHA-256이다.
- 시각은 UTC `Z` 표기다.
