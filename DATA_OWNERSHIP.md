# 데이터의 주인 (영역 사이, 소유: 헤드) — 2026-11-04

규칙(CONVENTIONS 6절 경계 규칙 1, 13절): **데이터마다 쓰는 영역(주인)은 하나다.** 다른 영역·사람은 주인의 인터페이스로 변경을 요청하고 주인이 쓴다. 읽기도 주인의 인터페이스로만 한다(공유 DB 통합 금지, Database per Service). 같은 데이터에 동시에 다른 변경이 오면 주인이 CONVENTIONS 4절(같은 내용 200·다른 내용 409·순서 어긋남 409)로 판정한다.
아래 표에 없는 영역 사이 데이터는 없다(2026-11-04 전수 확인: schemas/ 의 x-producers, INTERFACES 한눈에 표, PUBLIC_API, EXTERNAL_SCHEMAS.json). 영역 안에서만 쓰는 데이터(로그 저장소 내부 표, 캐시 등)는 그 영역이 정한다.

| 데이터 | 주인(쓰는 영역) | 바꾸려는 쪽 → 경로 | 읽는 쪽 → 경로 |
|---|---|---|---|
| 문진표(QuestionBank 버전), 검수 기록(ReviewRecord), 변경 분류(ChangeClassification) | question-authoring | 저자·검수자(사람) → platform 공개 입구 → 저작 API(AuthoringRequests) | release-gate·synthetic-data·model-lab → I1(admin-console 은 읽지 않는다) |
| 개선 신호(SignalsResponse) | question-authoring(계산·표시, 저장 데이터 아님) | — | 저자 → 저작 API |
| 데이터셋(DatasetManifest·파일) | synthetic-data(dataset-store) | synthetic-data 잡만 게시(I2) | model-lab → I2 |
| 모델 패키지(ModelPackageManifest·어댑터·평가 보고서) | model-lab(model-registry) | model-lab 파이프라인만 게시(I3) | release-gate → I3; model-runtime → I4 번들(release-gate 가 담아 줌) |
| 제출·판정·승인·릴리스·활성 포인터·롤백 영수증(GateSubmission·GateDecision·GateApproval·ReleaseManifest·ActivePointer·RollbackReceipt·ReviewReport) | release-gate | 제출: 운영자(사람) → I5(release-gate 수집 잡은 영역 안); 승인·활성화: 사람 → platform 공개 입구 → I5; 롤백: ops-feedback 잡·사람 → I5 | survey-service·ops-feedback·admin-console → I4·I5; question-authoring·model-lab → I4 판정 조회(GateDecision)만; model-runtime → I4 번들 |
| 세션·턴·문진 결과(SessionResult)·확인 표시(ack) | survey-service | 키오스크(기기) → 공개 API; 의사(사람) → 공개 API ack | admin-console → 공개 API B절; ops-feedback → I6(턴 기록 봉투로 보내 줌) |
| 직원 알림(StaffAlert)·개입 기록·직원 호출 재알림 기록 | survey-service | 직원(사람)·키오스크 → 공개 API; 위험 감지기(설치처) → risk-signals | kiosk-frontend·admin-console → 공개 API·SSE·푸시 |
| 웹 푸시 구독 | survey-service | kiosk-frontend·admin-console → 공개 API(PushSubscriptionRequest) | survey-service 만(발송) |
| 턴 기록(Trace)·실패 사례(FailureCase)·검토 결과 | ops-feedback | survey-service → I6(기록 봉투); 검토자(사람) → platform 공개 입구 → I7 검토 API; ops-feedback 잡(사례 생성) | synthetic-data·model-lab·question-authoring·admin-console → I7 |
| 사람 계정·역할(가입 승인) | platform(계정 관리) | 사람(가입), 관리자(승인) → platform 계정 관리 화면(HumanAuthEndpoints) | 영역 서비스 → 게이트웨이가 붙인 X-Openit-User·X-Openit-Roles(CONVENTIONS 6절) |
| 서비스 인증서·루트 | platform(인증서 발급) | — (platform 이 발급·갱신) | 모든 영역 → IN-ROOT(SSL_CERT_FILE), compose 밖 → OUT-FILE(deploy 가 내보냄) |
| 감시 지표 시계열·경보 | platform(감시) | 영역 → `/metrics`(platform 이 수집) | 운영자 → platform |
| 백업 저장소의 백업 묶음 | 저장 공간은 platform, **묶음의 내용·암호·보존·복구는 그 데이터의 주인 영역** | 영역의 백업 잡 → 출구 → 백업 저장소(R10.1, CommonEnv OPENIT_BACKUP_*) | 그 영역의 복구 잡만(저장소 암호는 영역마다 다르다) |
| 배포 설정(Env 값·비밀 파일·게이트 정책 파일·위험 규칙 파일·기기 설정·잡 주기) | deploy(배포 때) — 위험 규칙 내용은 설치처가 정한다 | 운영(설치처) → deploy 설정 | 해당 영역 → IN-ENV·IN-SECRET·설정 파일 |

## 확장 필드(`ext`)
레코드의 `ext.<영역 이름>` 은 **그 레코드를 쓰는 주인 영역만** 쓴다. 다른 영역은 남의 레코드에 `ext` 키를 더하지 않고, 받은 `ext` 는 보존해 전달만 한다(CONVENTIONS 1절 1항). 다른 영역이 덧붙일 정보가 있으면 자기 레코드에 두거나 주인에게 정식 필드를 요청한다.
