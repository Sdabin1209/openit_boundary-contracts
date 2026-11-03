"""경계 인터페이스 I1·I2·I3·I4·I5·I6·I7·I9의 HTTP 클라이언트(HTTP.md). 표준 라이브러리만 쓴다."""
from ._http import require_tls_url, require_egress_proxy, egress_proxy_from   # 3.4.4 영역 게이트웨이 출구(CONVENTIONS 13절). 3.4.1(U99): 클라이언트를 거치지 않는 직접 호출(도달성 확인 등)도 같은 TLS 규칙을 쓴다
from .datasets import HttpDatasetStore
from .models import HttpModelRegistry
from .publicapi import HttpPublicApi
from .staffcall import HttpStaffCall
from .ops import HttpFailureStore, HttpTraceIngest
from .questions import HttpQuestionReader
from .runtime import HttpModelRuntime, RuntimeResult, is_output_invalid
from .releases import HttpGateService, HttpReleaseReader

__all__ = ["require_tls_url", "require_egress_proxy", "egress_proxy_from", "HttpQuestionReader", "HttpModelRegistry", "HttpReleaseReader", "HttpGateService", "HttpTraceIngest",
           "HttpFailureStore", "HttpDatasetStore", "HttpStaffCall", "HttpPublicApi", "HttpModelRuntime", "RuntimeResult", "is_output_invalid"]
