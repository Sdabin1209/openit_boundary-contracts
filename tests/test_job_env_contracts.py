"""Job environments have their own requirements, independent of server startup."""
import json
from pathlib import Path

import pytest
from boundary_contracts import validator

ROOT = Path(__file__).resolve().parents[1]
NAMES = ['BackupJobEnv', 'SurveyBackupEnv', 'QuestionAuthoringBackupEnv', 'GateBackupEnv',
         'ModelRegistryBackupEnv', 'DatasetStoreBackupEnv', 'OpsFeedbackBackupEnv',
         'PublicIngressBackupEnv', 'IdentityDatabaseBackupEnv', 'StepCaBackupEnv', 'IdentityUsersEnv']


@pytest.mark.parametrize('name', NAMES)
def test_actual_job_requirements_accept_control_and_reject_invalid_input(name):
    good = json.loads((ROOT / 'examples' / f'{name}.json').read_text())
    bad = json.loads((ROOT / 'conformance/examples_invalid' / f'{name}.invalid.json').read_text())
    check = validator(name)
    assert check.is_valid(good)
    assert not check.is_valid(bad)


@pytest.mark.parametrize('name', NAMES[:-1])
def test_backup_requires_its_own_url_and_credential_paths(name):
    document = json.loads((ROOT / 'examples' / f'{name}.json').read_text())
    for required in ['OPENIT_BACKUP_URL', 'OPENIT_BACKUP_CREDENTIALS_FILE', 'OPENIT_BACKUP_REPO_PASSWORD_FILE']:
        missing = {key: value for key, value in document.items() if key != required}
        assert not validator(name).is_valid(missing), (name, required)


def test_user_registration_has_no_server_public_url_dependency():
    document = {'IDENTITY_ROOT_CA': '/etc/openit/pki/root_ca.crt',
                'IDENTITY_ADMIN_PASSWORD_FILE': '/run/secrets/admin-password'}
    assert validator('IdentityUsersEnv').is_valid(document)
    assert not validator('IdentityUsersEnv').is_valid({'IDENTITY_ADMIN_PASSWORD_FILE': '/run/secrets/admin-password'})


@pytest.mark.parametrize("name", NAMES[:-1])
@pytest.mark.parametrize("change", [
    {"OPENIT_BACKUP_UNKNOWN": "x"},
    {"OPENIT_BACKUP_URL": "https://user:password@backup.example.org/repository"},
    {"OPENIT_BACKUP_URL": "https://backup.example.org:0/repository"},
    {"OPENIT_BACKUP_URL": "https://backup.example.org:65536/repository"},
    {"OPENIT_BACKUP_CREDENTIALS_FILE": "/run/secrets/a\x00b"},
    {"OPENIT_BACKUP_REPO_PASSWORD_FILE": "/run/secrets/a\x00b"},
])
def test_backup_env_rejects_undeclared_or_unusable_inputs(name, change):
    document = json.loads((ROOT / "examples" / f"{name}.json").read_text())
    assert not validator(name).is_valid({**document, **change}), (name, tuple(change))


@pytest.mark.parametrize("name", NAMES[:-1])
@pytest.mark.parametrize("url", [
    "https://backup.example.org/repository", "https://backup.example.org:1/repository",
    "https://backup.example.org:65535/repository", "https://[::1]:8443/repository",
    "https://backup.example.org/nested/repository", "https://backup.example.org/a%20b",
    "https://backup.example.org:00080/repository", "https://backup.example.org:/repository",
    "https://backup.example.org/repository?param=value", "https://backup.example.org/repository#fragment",
])
def test_backup_env_accepts_supported_repository_urls(name, url):
    document = json.loads((ROOT / "examples" / f"{name}.json").read_text())
    assert validator(name).is_valid({**document, "OPENIT_BACKUP_URL": url})


def test_repository_port_range_is_exhaustive_and_accepts_uri_decimal_spelling():
    import re
    from boundary_contracts import load_schema
    pattern = re.compile(load_schema("BackupJobEnv")["properties"]["OPENIT_BACKUP_URL"]["allOf"][-1]["pattern"])
    for port in range(65537):
        for spelling in (str(port), "000" + str(port)):
            assert bool(pattern.fullmatch(f"https://backup.example.org:{spelling}/repository")) == (1 <= port <= 65535), spelling
    assert pattern.fullmatch("https://backup.example.org:/repository")
