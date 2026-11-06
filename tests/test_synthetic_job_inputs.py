"""Synthetic job environment and configuration-path binding contracts."""
import json
from pathlib import Path
import pytest
from boundary_contracts import validator

ROOT = Path(__file__).resolve().parents[1]


def test_job_environment_accepts_file_secret_paths():
    validator("SyntheticJobEnv").validate(json.loads((ROOT / "examples/SyntheticJobEnv.json").read_text()))


@pytest.mark.parametrize("name,value", [("DATASET_STORE_WRITE_TOKEN", "secret"), ("DATASET_STORE_ROOT", "/data"), ("QUESTION_READER_TOKEN_FILE", "relative"), ("FAILURE_STORE_TOKEN_FILE", "/bad\0path"), ("DATASET_STORE_WRITE_TOKEN_FILE", "/bad\npath")])
def test_job_environment_rejects_invalid_input(name, value):
    assert list(validator("SyntheticJobEnv").iter_errors({name: value}))


@pytest.mark.parametrize("pointer", ["/output/work_dir", "/output/store/root", "/input_dir", "/a~1b/~0"])
def test_job_config_path_binding(pointer):
    doc = json.loads((ROOT / "examples/ContainerInputs.json").read_text())
    doc["jobs"]["synthetic-import"] = dict(doc["roles"]["default"], config_paths={pointer: {"access": "read", "required": True}})
    validator("ContainerInputs").validate(doc)


@pytest.mark.parametrize("binding", [{"pointer": "input_dir", "access": "read", "required": True}, {"pointer": "/a~2", "access": "read", "required": True}, {"pointer": "/input_dir", "access": "execute", "required": True}, {"pointer": "/input_dir", "access": "read"}])
def test_job_config_path_binding_rejects_invalid_definition(binding):
    doc = json.loads((ROOT / "examples/ContainerInputs.json").read_text())
    pointer = binding.pop("pointer")
    doc["jobs"]["synthetic-import"] = dict(doc["roles"]["default"], config_paths={pointer: binding})
    assert list(validator("ContainerInputs").iter_errors(doc))
