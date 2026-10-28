"""METRICS.md의 지표 표를 boundary_contracts/metrics.json에서 생성한다(정본은 JSON, 마크다운은 생성물).

사용: python3 tools/gen_metrics_md.py          # METRICS.md의 표식 구역을 다시 쓴다
      python3 tools/gen_metrics_md.py --check  # 커밋된 파일과 다르면 종료 코드 1
왜 이렇게: 사람이 읽는 글에서 값을 파싱하지 않고 데이터에서 글을 만든다(워크스페이스 원칙).
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SECTIONS = ("A", "B", "COMMON")


def table(reg, section):
    items = []
    for m in reg["metrics"]:
        for d in m["doc"]:
            if d["section"] == section and "row_names" in d:
                items.append((d["order"], m, d))
    lines = ["| name | group | 상태 | 뜻 |", "| --- | --- | --- | --- |"]
    for _, m, d in sorted(items, key=lambda t: t[0]):
        names = ", ".join(f"`{n}`" for n in d["row_names"])
        lines.append(f"| {names} | {m['group']} | {d['change']} | {d['meaning']} |")
    return "\n".join(lines)


def render(md, reg):
    for s in SECTIONS:
        pat = re.compile(r"(<!-- BEGIN GENERATED metrics:%s -->\n).*?(\n<!-- END GENERATED metrics:%s -->)" % (s, s), re.S)
        if not pat.search(md):
            raise SystemExit(f"METRICS.md에 표식 metrics:{s}가 없다")
        md = pat.sub(lambda m: m.group(1) + table(reg, s) + m.group(2), md)
    return md


def main(argv):
    with open(os.path.join(ROOT, "boundary_contracts", "metrics.json"), encoding="utf-8") as f:
        reg = json.load(f)
    path = os.path.join(ROOT, "METRICS.md")
    with open(path, encoding="utf-8") as f:
        old = f.read()
    new = render(old, reg)
    if "--check" in argv:
        return 0 if new == old else 1
    with open(path, "w", encoding="utf-8") as f:
        f.write(new)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
