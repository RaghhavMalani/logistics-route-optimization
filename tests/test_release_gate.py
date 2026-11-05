"""Prevent deployment from a green PR or an incomplete/red main workflow."""
import pytest

from scripts.verify_release_gate import REQUIRED_JOBS, validate

SHA = 'a' * 40


def green_main():
    return {'headSha': SHA, 'headBranch': 'main', 'status': 'completed', 'conclusion': 'success',
            'jobs': [{'name': name, 'status': 'completed', 'conclusion': 'success'} for name in REQUIRED_JOBS]}


def test_release_gate_accepts_full_green_main():
    validate(SHA, SHA, green_main())


@pytest.mark.parametrize('change', [
    {'headSha': 'b' * 40},
    {'headBranch': 'fix/research-asof'},
    {'status': 'in_progress', 'conclusion': ''},
    {'conclusion': 'failure'},
    {'jobs': []},
])
def test_release_gate_rejects_wrong_or_incomplete_ci(change):
    run = green_main()
    run.update(change)
    with pytest.raises(ValueError):
        validate(SHA, SHA, run)


def test_release_gate_rejects_newer_main():
    with pytest.raises(ValueError):
        validate(SHA, 'b' * 40, green_main())


def test_release_gate_rejects_any_failed_job():
    run = green_main()
    run['jobs'][0]['conclusion'] = 'failure'
    with pytest.raises(ValueError):
        validate(SHA, SHA, run)


def test_release_gate_requires_research_job():
    run = green_main()
    run['jobs'] = [job for job in run['jobs'] if job['name'] != 'Browser Research (isolated renderer)']
    with pytest.raises(ValueError):
        validate(SHA, SHA, run)
