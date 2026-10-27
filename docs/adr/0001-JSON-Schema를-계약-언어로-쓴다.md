# 0001. 영역 사이 계약의 언어로 JSON Schema(Draft 2020-12)를 쓴다

- 상태: 수용(2026-10-28 소급 기록)
- 관련: `head/docs/DECISIONS.md` D19, D26, D48, D83 / `head/docs/HANDOFF.md`(계약 세트를 JSON Schema로 쓴다) / `CONVENTIONS.md` 10절

## 맥락

영역 사이에 오가는 레코드(릴리스 매니페스트, 게이트 판정, 모델 입출력 등)의 형식을 한 곳에서 정하고 모든 영역이 같은 검증을 해야 한다. 계약을 표현할 언어를 골라야 했다.

## 결정

레코드와 모델 입출력의 형식을 JSON Schema(Draft 2020-12) 28개 + 공통 정의(`_common.schema.json`)로 쓰고, `verify.py`와 `jsonschema` 라이브러리로 검증한다. 호출 경로는 문서(`HTTP.md`)로 쓴다.

## 왜

- 문진 스키마(`survey-service/schema`)가 이미 JSON Schema이고 학습 데이터·모델 입출력도 JSON이다. 같은 언어이면 도구와 사람이 하나만 배우면 된다. (프로젝트가 JSON Schema로 시작한 맥락은 `HANDOFF.md`에서 확인했다. 언어를 비교해 고른 기록은 아래 참고.)
- 모델 출력을 구조화 출력(vLLM의 제약 디코딩, xgrammar)으로 강제하려면 JSON Schema가 그대로 입력이 된다(D48, D82, D83, 2.0.1 변경 이력: xgrammar가 `properties` 순서대로 키를 낸다). protobuf는 이 경로에 쓸 수 없다.
- 데이터가 JSON(데이터셋은 JSON Lines, 해시는 RFC 8785 JCS 정규화 JSON의 SHA-256, `CONVENTIONS.md` 2·8절)이므로 스키마 언어가 JSON이면 변환 단계가 없다.
- `additionalProperties: false`, `pattern`, `enum`, 조건(`if/then`) 등 검증 표현력이 있고 예시 파일로 통과·거부 시험을 쓰기 쉽다(`verify.py`, `tools/negatives_v2.py`).

## 검토한 대안과 버리는 이유

| 대안 | 버리는 이유 |
|---|---|
| protobuf | 근거 기록 없음(대안을 직접 비교한 문서를 찾지 못했다). 위 "왜"에서 읽을 수 있는 이유: 모델 출력의 제약 디코딩에 쓸 수 없고, 모든 입출력이 JSON/JSONL이라 이진 직렬화의 이점이 없다. 해시도 JSON 정규화로 정했다. 추론이며 측정한 비교는 없다 |
| OpenAPI | 근거 기록 없음. 읽을 수 있는 이유: OpenAPI는 경로 정의 위에 JSON Schema를 얹은 것이라 스키마 부분은 같다. 이 프로젝트는 경로 규약을 사람이 읽는 문서(`HTTP.md`, `PUBLIC_API.md`)로 두고 클라이언트·참조 서버·적합성 시험 코드로 강제한다. OpenAPI 문서에서 코드를 생성하는 방식은 채택·검토한 기록이 없다(미정) |
| 언어별 타입 정의(Python dataclass만) | 영역이 모두 Python이지만 프론트(다른 팀)가 공개 API를 읽는다(D12, D55). 언어 중립 형식이 필요하다 |

## 결과

- 얻는 것: 모델 서버·데이터 검증·시험이 같은 스키마를 쓴다. 문서와 데이터의 차이를 `tools/validate_dataset_v2.py`가 잡았다(V2_DRAFT).
- 감수하는 것: JSON Schema는 구조화 출력 엔진이 모든 키워드를 지키지 않는다(`allOf`·`if/then`·`not` 무시, D48). 그래서 모델 서버가 완화한 스키마를 쓰고 사후 검증이 필요하다. `jsonschema`의 `RefResolver` 폐기 예고도 기술 부채다(STATUS 2026-10-15).

## 되돌리는 조건

구조화 출력 엔진이 JSON Schema 외 형식을 요구하거나, 경로 정의에서 코드를 생성하는 방식이 필요해지면(OpenAPI 도입) 경로 부분만 별도 ADR로 바꾼다. 스키마 언어를 바꾸는 것은 모든 영역에 영향이 가는 MAJOR 변경이다.
