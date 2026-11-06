"""3.4.17: 역할을 Env 로 고른다(StepCaEnv.STEP_ROLE, MonitoringEnv.MONITORING_ROLE)."""
from boundary_contracts import validator

def test_step_roles():
    v = validator("StepCaEnv")
    assert not list(v.iter_errors({"STEP_ROLE": "cert", "STEP_CERT_NAME": "survey-service", "STEP_CERT_GID": "10100"}))
    assert not list(v.iter_errors({"STEP_ROLE": "token", "STEP_TOKEN_NAMES": "survey-service release-gate"}))
    assert list(v.iter_errors({"STEP_ROLE": "shell"}))
    assert list(v.iter_errors({"STEP_ROLE": "cert", "STEP_CERT_NAME": "Bad Name"}))

def test_monitoring_role():
    v = validator("MonitoringEnv")
    assert not list(v.iter_errors({"MONITORING_ROLE": "node"}))
    assert list(v.iter_errors({"MONITORING_ROLE": "grafana"}))

def test_every_property_is_allowed_by_property_names():   # 3.4.11·3.4.17 교훈: properties 에 넣고 propertyNames 허용 목록에 빠뜨리지 않는다
    import json, glob
    for p in glob.glob("schemas/*.schema.json"):
        s = json.load(open(p))
        pn = s.get("propertyNames")
        if not pn or not s.get("properties"):
            continue
        v = validator(p.rsplit("/", 1)[-1][: -len(".schema.json")])
        from jsonschema import Draft202012Validator
        chk = v.evolve(schema=pn)
        for k in s["properties"]:
            assert chk.is_valid(k), (p, k)
