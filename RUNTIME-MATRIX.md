# 호출 × 실패 동작 표 (실행 시 동작 계약의 근거, 소유: 헤드)

왜: 계약을 결함에서 거꾸로 쓰지 않고, 흐름의 **모든 호출**에 **모든 실패 종류**를 대어 칸마다 "호출자가 무엇을 받는가"를 표준으로 정한다.
RUNTIME.md 의 조항은 이 표의 칸을 묶은 것이다. 칸이 비면 계약에 빈칸이 있는 것이다.
작성 순서: (A) 호출 목록 → (B) 실패 종류 목록 → (C) 칸 채우기 → (D) 기존 계약 문서와 상호 대조 → (E) 독립 검토 둘.

## A. 호출 목록 (영역 사이만, FLOW.md 단계 1~7 + 영역과 배포 사이)

영역 안 컴포넌트 사이의 호출은 이 표에 두지 않는다(구조 규칙 5·6). 모든 행의 호출은 호출 영역 게이트웨이(나가는 쪽 CONNECT, R1.8) → 받는 영역 게이트웨이를 지난다(CONVENTIONS 13절, 사람·기기는 platform 공개 입구). C23(웹 푸시)은 받는 영역 게이트웨이가 없는 바깥 인터넷이라 호출 영역 게이트웨이의 출구만 지난다(R3.18). C33·C34 는 deploy 의 배포 설정(컨테이너를 띄움)이라 게이트웨이를 지나지 않는다(CONVENTIONS 13절 예외). 2026-11-04 에 deploy 내부 호출 6개를 뺐다: C25 인증서 컨테이너→인증기관, C26 게이트웨이→oauth2-proxy, C28 oauth2-proxy→계정 관리, C31 경보 전달, C32 백업, C35 배치 지휘 기계→서버. C24(영역 서비스 → 데이터베이스)도 2026-11-04 검토 B-25 결정(데이터베이스는 영역의 컴포넌트, CONVENTIONS 13절)으로 영역 내부가 되어 뺐다; 그 결과는 받는 서비스의 출력 R3.10 이다. C37~C42 는 INTERFACES 한눈에 표에 있는데 이 표에 빠져 있던 호출이다(검토 A-13·B-22). 번호는 재사용하지 않는다. 그 호출들이 영역 사이 호출에 미치는 결과(예: 인증 확인 실패 → C15·C16 의 503)는 해당 영역 사이 호출의 칸에 있다.

| # | 호출자 → (중계) → 받는 쪽 | 면(계약) | 인증 | 흐름 단계 |
|---|---|---|---|---|
| C01 | 저자(브라우저) → 게이트웨이 → question-authoring | 저작 화면·API | 사람(OIDC) | 1 |
| C02 | 임상 검수자(2인 승인을 켠 배포) → 게이트웨이 → question-authoring `/v1/reviews` | 저작 API | 사람 | 1 |
| C03 | release-gate → question-authoring | I1 읽기 | 서비스 토큰 | 2 |
| C04 | synthetic-data 잡 → question-authoring | I1 읽기 | 서비스 토큰 | 7 |
| C05 | synthetic-data 잡 → dataset-store | I2 게시 | 서비스 토큰(쓰기) | 7 |
| C06 | model-lab 파이프라인(학습 서버, compose 밖) → dataset-store | I2 읽기 | 서비스 토큰 | 7 |
| C07 | model-lab 파이프라인 → model-registry | I3 게시 | 서비스 토큰(쓰기) | 7 |
| C08 | release-gate → model-registry | I3 읽기 | 서비스 토큰 | 2 |
| C09 | 운영자(브라우저) → 게이트웨이 → release-gate | I5 제출·활성·롤백 | 사람 | 2 |
| C10 | 승인자(브라우저) → 게이트웨이 → release-gate | I5 검토 보고서·결정 | 사람 | 2 |
| C11 | ops-feedback 잡 → release-gate | I5 롤백 | 서비스 토큰(쓰기) | 7 |
| C12 | survey-service → release-gate | I4 활성 포인터·문진표 | 서비스 토큰 | 4·5 |
| C13 | 추론 서버(model-runtime 영역, 다른 서버일 수 있음) → release-gate | I4 번들 | 서비스 토큰 | 5 |
| C14 | survey-service → 추론 서버 | I9 적재·extract·respond·정보·준비 | 서비스 토큰 | 5 |
| C15 | 키오스크(기기) → 게이트웨이 → survey-service | I10 문진표 목록·세션·발화·종료 | 기기 토큰(또는 기기 인증서) | 4·5 |
| C16 | 직원(브라우저) → 게이트웨이 → survey-service | I10 직원 화면·알림 SSE·개입·호출 | 사람 | 5 |
| C17 | 의사(브라우저) → 게이트웨이 → survey-service | I10 결과·확인·결과 SSE·푸시 구독 | 사람 | 6 |
| C18 | survey-service → ops-feedback | I6 Trace 수집 | 서비스 토큰 | 5·7 |
| C19 | 검토자(브라우저) → 게이트웨이 → ops-feedback | I7 사례·검토·검토용 Trace | 사람 | 7 |
| C20 | synthetic-data 잡 → ops-feedback | I7 읽기 | 서비스 토큰 | 7 |
| C21 | question-authoring → ops-feedback | I7 개선 신호 읽기 | 서비스 토큰 | 7 |
| C22 | ops-feedback 잡 → release-gate | I4 읽기 | 서비스 토큰 | 7 |
| C23 | survey-service → 공개 푸시 서비스(바깥 인터넷) | 웹 푸시(RFC 8030) | VAPID | 6 |
| C27 | 브라우저 → 게이트웨이 → 계정 관리(Keycloak) | 로그인·가입·관리 화면 | 사람 | 1·2·5·6·7 |
| C29 | 브라우저·키오스크 → 게이트웨이 → 화면 정적 파일(kiosk-frontend·admin-console) | 정적 화면 | 사람·기기 | 4·6 |
| C30 | 감시(platform) → 영역 게이트웨이 → 영역 서비스 | `/healthz`·`/readyz`·`/metrics` | — (인증 없음, R5.1·R10.11; 접근 통제는 망) | 운영 |
| C33 | deploy(잡 주기 배포 설정) → 영역 잡 한 번 실행 | `run-once` | — | 운영 |
| C34 | 운영자 관리 명령(deploy 가 영역 이미지로 한 번 띄움, 12-Factor XII: 예 ops-feedback migrate, survey purge) → 영역 잡 | 잡 선언 `JobsDeclaration`, 출력 OUT-JOB(`*JobResult`·`SurveyPurgeOutput`) | — (deploy 배포 설정, CONVENTIONS 13절 예외) | 운영 |
| C36 | 배포 → compose 밖 호출자(C06·C07) | 루트 인증서·이름→주소 표 내보내기 | — | 운영 |
| C37 | model-lab 파이프라인(학습 서버, compose 밖) → question-authoring | I1 읽기 | 서비스 토큰 | 7 |
| C38 | model-lab 파이프라인(compose 밖) → ops-feedback | I7 읽기 | 서비스 토큰 | 7 |
| C39 | model-lab 파이프라인(compose 밖) → release-gate | I4 읽기(판정 조회) | 서비스 토큰 | 7 |
| C40 | (3.4.6 뺌: model-lab 은 I9 HTTP 를 부르지 않는다 — 평가는 model-runtime 라이브러리) | | | |
| C41 | question-authoring → release-gate | I4 읽기(판정 조회) | 서비스 토큰 | 1·7 |
| C42 | (3.4.6 뺌: release-gate 는 I9 HTTP 를 부르지 않는다 — 버전 확인은 model-runtime 라이브러리) | | | |

## B. 실패 종류 목록 (근거 표준)

| # | 실패 종류 | 근거 |
|---|---|---|
| F01 | 받는 쪽 프로세스가 죽음(컨테이너는 살아 있음) | RFC 9110 15.6.4(503), TCP RST |
| F02 | 받는 쪽 컨테이너 정지·재시작 중 | RFC 9110 15.6.4 |
| F03 | 받는 쪽이 느림(응답 헤더가 한도 안에 오지 않음) | RFC 9110 15.6.5(504) |
| F04 | 연결이 맺어지지 않음(네트워크 분단·연결 시간 초과) | RFC 9110 15.6.4·15.6.5 |
| F05 | 이름 해석 실패 | RFC 9110 15.6.3·15.6.4 |
| F06 | 중계(게이트웨이·TLS 종단) 자신이 멈춤·재시작 | RFC 9110 15.6.4 |
| F07 | 중계의 연결·대기열 포화 | RFC 9110 15.6.4 |
| F08 | 서버 인증서 만료·아직 유효 전 | RFC 5280 4.1.2.5, 6.1.3 |
| F09 | 서버 인증서 이름 불일치 | RFC 6125, RFC 9110 4.3.4 |
| F10 | 모르는 루트로 서명된 인증서 | RFC 5280 6.1 |
| F11 | 시계 어긋남(인증서·토큰·쿠키 판정) | RFC 5280 4.1.2.5, RFC 7519 4.1.4 |
| F12 | 인증 정보 없음·틀림 | RFC 9110 15.5.2(401), RFC 6750 3 |
| F13 | 권한 없음·가입 승인 대기 | RFC 9110 15.5.4(403) |
| F14 | 인증 쪽(oauth2-proxy·계정 관리) 멈춤·느림 | RFC 9110 15.6.4, OWASP Session Management |
| F15 | 요청 크기 한도(본문·요청 줄·헤더) | RFC 9110 15.5.14·15.5.15, RFC 6585 5 |
| F16 | 느린 클라이언트(요청을 한도 안에 다 보내지 않음) | RFC 9110 15.5.9(408), RFC 9112 9.5 |
| F17 | 과다 요청 | RFC 6585 4(429), RFC 9110 10.2.3(Retry-After) |
| F18 | 내용 오류(스키마 위반)·버전 불일치·해시 불일치 | CONVENTIONS 9절(400·422) |
| F19 | 상태 충돌·선행 조건 | CONVENTIONS 9절(409·412) |
| F20 | 중복·재전송(같은 요청을 다시 보냄) | CONVENTIONS 4절(POST 멱등은 내용 해시 비교 규칙; RFC 9110 9.2.2 의 멱등 메서드는 PUT·DELETE), PUBLIC_API turn_id |
| F21 | 의존 데이터베이스 멈춤·쓰기 불가(디스크 가득) | RFC 9110 15.6.4 |
| F22 | 인증기관 멈춤 | RFC 8555(ACME)·step-ca 문서 — 발급만 실패 |
| F23 | 서버 전체 재시작(전원 순단·재부팅) | 12-Factor IX(폐기 용이성) |
| F24 | 스트림 도중 끊김(SSE) | WHATWG HTML Server-sent events |
| F25 | 바깥 인터넷 호출 실패(불통·429·5xx·404·410) | RFC 8030 5·8.2 |
| F26 | 응답이 받는 쪽 상한을 넘거나 손상(해시 불일치) | HTTP.md 공통(클라이언트가 해시를 다시 계산), 계약 클라이언트 상한(`max_body_bytes` 256MiB·`max_tar_bytes` 8GiB) |
| F27 | 디스크 가득(로그·저장 쓰기 실패) | 12-Factor XI(로그는 스트림) |

## C. 칸 채우기

칸은 RUNTIME-MATRIX-CELLS.md 에 있다(호출 30 × 실패 27 = 810칸에서 C24 를 영역 내부로 빼고 C37~C42 를 더함)(2026-11-04 확정, 빈칸 0, 열린 칸은 모두 계약 행으로 닫음).

칸은 입력(호출 + 실패 종류) → 출력이다. 칸마다 "호출자가 관찰하는 것 | 근거(B 의 표준 또는 계약 절) | RUNTIME 조항"을 적는다. 해당하지 않는 칸은 "해당 없음 + 이유"를 적는다(빈칸 금지).
