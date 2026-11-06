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
