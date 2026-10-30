"""3.1.0: 계약 클라이언트의 쓰기 메서드(POST·PUT·PATCH 본문이 있는 것)는 보내기 전에 계약 스키마로 검사한다(CONVENTIONS 4절).
왜: 3.0.3까지 decide()가 ApprovalRequest를 어겼는데 시험이 못 잡았다. 메서드를 새로 더해도 검사를 빠뜨리지 못하게 정적으로 강제한다.
스키마가 이 패키지에 없는 본문은 아래 EXEMPT에 이유와 함께 적는다(이유 없는 예외 금지)."""
import ast
import pathlib
import re
import unittest

from boundary_contracts import validator

CLIENTS = pathlib.Path(__file__).resolve().parents[1] / "boundary_contracts" / "clients"
EXEMPT = {
    "HttpPublicApi.start_session": "본문(FrontendMessage)은 문진 스키마(survey-service 소유)라 이 패키지에 없다. PUBLIC_API.md 모양을 메서드가 직접 확인한다",
    "HttpPublicApi.send_utterance": "위와 같다(FrontendMessage, 문진 스키마)",
    "HttpPublicApi.end_session": "위와 같다(FrontendMessage, 문진 스키마)",
    "HttpPublicApi.intervene": "본문(InterventionRequest)은 문진 스키마 소유",
    "HttpModelRuntime.load_release": "본문 없는 PUT(HTTP.md I9)",
}


def write_methods():
    for f in sorted(CLIENTS.glob("*.py")):
        if f.name.startswith("_"):
            continue
        src = f.read_text(encoding="utf-8")
        for c in [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef)]:
            for fn in [n for n in c.body if isinstance(n, ast.FunctionDef) and not n.name.startswith("_")]:
                seg = ast.get_source_segment(src, fn)
                if re.search(r'"(POST|PUT|PATCH)"', seg):
                    yield f"{c.name}.{fn.name}", seg


class ClientOutgoing(unittest.TestCase):
    def test_쓰기_메서드는_계약_스키마로_검사하거나_이유가_있다(self):
        missing = []
        for name, seg in write_methods():
            names = re.findall(r'check_outgoing\(\s*"([A-Za-z]+)"', seg)
            if not names and name not in EXEMPT:
                missing.append(name)
            for n in names:
                validator(n)   # 스키마가 실제로 있다(이름 오타 금지)
        self.assertEqual(missing, [], "본문을 계약 스키마로 검사하지 않는 쓰기 메서드")

    def test_예외_목록에_없는_메서드가_없다(self):
        names = {n for n, _ in write_methods()}
        self.assertEqual(sorted(set(EXEMPT) - names), [], "EXEMPT에 지금 없는 메서드가 남았다")


if __name__ == "__main__":
    unittest.main()
