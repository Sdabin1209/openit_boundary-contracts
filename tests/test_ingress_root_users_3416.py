"""3.4.16: 공개 입구 루트 인증서 출력 폴더(PublicIngressEnv.INGRESS_ROOT_EXPORT_DIR)와 identity 사용자 등록 잡 설정(IdentityUsersConfig)."""
import json
from boundary_contracts import validator

def test_users_config():
    v = validator("IdentityUsersConfig")
    v.validate(json.load(open("examples/IdentityUsersConfig.json")))
    assert list(v.iter_errors({"users": [{"username": "a1", "groups": ["superuser"], "password_file": "/p"}]}))   # 고정 목록 밖 역할
    assert list(v.iter_errors({"users": [{"username": "a1", "groups": ["staff"], "password": "x"}]}))   # 암호를 값으로 받지 않는다(D84)

def test_ingress_root_export_dir():
    s = json.load(open("schemas/PublicIngressEnv.schema.json"))
    assert s["properties"]["INGRESS_ROOT_EXPORT_DIR"]["default"] == "/etc/openit/root-out"
