#!/usr/bin/env python3
"""영역이 wo6 브랜치에 준비한 docs/change-requests/contract-ready/ 를 계약 패키지로 옮긴다(D107).
스키마 -> boundary_contracts/schemas/, 통과 예시 -> conformance/examples/, 거부 예시 -> conformance/examples_invalid/.
이름이 겹치면 중단한다. 사용: promote_contract_ready.py <워크스페이스 루트> [영역[=브랜치] ...] [--replace]"""
import io, json, shutil, subprocess, sys, tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AREAS = ["admin-console", "deploy", "kiosk-frontend", "model-lab", "model-runtime", "ops-feedback", "question-authoring", "release-gate", "survey-service", "synthetic-data"]


def main(ws, areas, replace=False):
    sch, exv, exi = ROOT / "boundary_contracts/schemas", ROOT / "conformance/examples", ROOT / "conformance/examples_invalid"
    exi.mkdir(exist_ok=True)
    seen = {}
    for a in areas:
        a, _, branch = a.partition("=")   # 영역=브랜치 (기본 wo6)
        branch = branch or "wo6"
        data = subprocess.run(["git", "-C", f"{ws}/{a}", "archive", branch, "docs/change-requests/contract-ready"], capture_output=True, check=True).stdout
        with tarfile.open(fileobj=io.BytesIO(data)) as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                rel = m.name.split("contract-ready/", 1)[1]
                body = tf.extractfile(m).read()
                if rel.startswith("schemas/") and rel.endswith(".schema.json"):
                    dest = sch / Path(rel).name
                elif rel.startswith("examples/valid/") and rel.endswith(".json"):
                    dest = exv / Path(rel).name
                elif rel.startswith("examples/invalid/") and rel.endswith(".json"):
                    dest = exi / Path(rel).name
                elif rel == "MANIFEST.json":
                    dest = ROOT / "conformance/promoted" / f"{a}.MANIFEST.json"
                else:
                    continue
                if dest in seen:
                    sys.exit(f"이름 충돌: {dest.name} ({seen[dest]} / {a})")
                if dest.exists() and not replace and dest.parent != ROOT / "conformance/promoted":
                    sys.exit(f"이미 있음: {dest}")
                seen[dest] = a
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(body)
    print(f"옮긴 파일 {len(seen)}개")


if __name__ == "__main__":
    args = [x for x in sys.argv[2:] if x != "--replace"]
    main(sys.argv[1], args or AREAS, "--replace" in sys.argv)
