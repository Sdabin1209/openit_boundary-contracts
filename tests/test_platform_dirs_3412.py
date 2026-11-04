"""3.4.12: deploy 가 platform 컴포넌트에 마운트하는 폴더는 받는 쪽 Env 스키마에 경로로 있다(헤드 경계 전수 점검이 찾은 빈칸)."""
from boundary_contracts import load_schema


def _defaults(name):
    return {k: v.get("default") for k, v in load_schema(name)["properties"].items()}


def test_step_ca_declares_cert_token_and_state_dirs():
    d = _defaults("StepCaEnv")
    assert d.get("STEP_CERTS_DIR") == "/certs" and d.get("STEP_TOKENS_DIR") == "/tokens" and d.get("STEP_CA_HOME") == "/home/step"


def test_monitoring_declares_node_role_dirs():
    d = _defaults("MonitoringEnv")
    assert d.get("MONITORING_NODE_HOST_ROOT") == "/host" and d.get("MONITORING_NODE_TEXTFILE_DIR") == "/textfile"


def test_property_names_accept_the_new_names():
    from boundary_contracts import validator
    for name, ex in (("StepCaEnv", {"STEP_CERTS_DIR": "/certs", "STEP_TOKENS_DIR": "/tokens", "STEP_CA_HOME": "/home/step"}),
                     ("MonitoringEnv", {"MONITORING_NODE_HOST_ROOT": "/host", "MONITORING_NODE_TEXTFILE_DIR": "/textfile"})):
        errs = [e.message for e in validator(name).iter_errors(ex)]
        assert not errs, (name, errs)
