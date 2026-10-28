"""평가 지표 이름의 정본(metrics.json)을 읽는다. 값은 데이터 한 곳에만 있고 METRICS.md의 표는 거기서 생성된다."""
import json
from importlib import resources
from types import MappingProxyType

_cache = None


def _freeze(v):
    if isinstance(v, dict):
        return MappingProxyType({k: _freeze(x) for k, x in v.items()})
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


def metrics():
    """{지표 이름: 읽기 전용 항목}을 돌려준다. 항목 키: name, group, unit, higher_is_better(null 가능),
    status(ACTIVE|DEPRECATED), replaced_by(이름 튜플 또는 None), applies_to(A|B|both), doc."""
    global _cache
    if _cache is None:
        raw = json.loads(resources.files("boundary_contracts").joinpath("metrics.json").read_text(encoding="utf-8"))
        _cache = MappingProxyType({m["name"]: _freeze(m) for m in raw["metrics"]})
    return _cache


def metric_name_problems(report):
    """EvaluationReport(metrics[].name) 또는 ReviewReport(comparisons[].name)의 지표 이름 중
    레지스트리에 없거나 DEPRECATED인 것을 (이름, 사유) 목록으로 돌려준다. 비어 있으면 통과."""
    reg = metrics()
    names = [m.get("name") for m in report.get("metrics", [])] + [c.get("name") for c in report.get("comparisons", [])]
    out = []
    for n in names:
        if n not in reg:
            out.append((n, "UNKNOWN"))
        elif reg[n]["status"] != "ACTIVE":
            out.append((n, "DEPRECATED"))
    return out
