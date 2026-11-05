"""Authorize a release only after full CI succeeds on the exact current main SHA."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY = 'RaghhavMalani/logistics-route-optimization'
REQUIRED_JOBS = {
    'Operations OS (agents, MCP, learning, twin, advisories)',
    'Intelligence, pipeline and API tests',
    'Terminal typecheck and build',
    'Browser Research (isolated renderer)',
    *(f'Browser regression (production build, shard {number})' for number in range(1, 5)),
}


def validate(sha: str, main_sha: str, run: dict) -> None:
    if not re.fullmatch(r'[a-f0-9]{40}', sha) or main_sha != sha:
        raise ValueError('Release SHA must be the exact current main commit')
    if run.get('headSha') != sha or run.get('headBranch') != 'main':
        raise ValueError('CI must belong to the exact main SHA')
    if run.get('status') != 'completed' or run.get('conclusion') != 'success':
        raise ValueError('CI on the exact main SHA must finish green before deployment')
    jobs = run.get('jobs', [])
    if not REQUIRED_JOBS.issubset({job['name'] for job in jobs}):
        raise ValueError('Full CI must include all backend, build and browser jobs')
    if any(job.get('status') != 'completed' or job.get('conclusion') != 'success' for job in jobs):
        raise ValueError('Every CI job must finish green before deployment')


def github(*arguments: str):
    return json.loads(subprocess.check_output(['gh', *arguments], text=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    runs = github('run', 'list', '--repo', REPOSITORY, '--workflow', 'award-ci.yml', '--branch', 'main',
                  '--event', 'push', '--commit', args.sha, '--limit', '10',
                  '--json', 'databaseId,headSha,status,conclusion,createdAt')
    if not runs:
        raise ValueError('No push CI run exists for the exact main SHA')
    latest = max(runs, key=lambda run: run['databaseId'])
    run = github('run', 'view', str(latest['databaseId']), '--repo', REPOSITORY,
                 '--json', 'headSha,headBranch,status,conclusion,jobs,url')
    main_ref = github('api', f'repos/{REPOSITORY}/git/ref/heads/main')
    validate(args.sha, main_ref['object']['sha'], run)
    receipt = {'sha': args.sha, 'mainSha': main_ref['object']['sha'], 'runId': latest['databaseId'],
               'url': run['url'], 'verifiedAt': datetime.now(timezone.utc).isoformat(),
               'jobs': [{'name': job['name'], 'conclusion': job['conclusion']} for job in run['jobs']]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(f'RELEASE GATE PASSED {args.sha} {run["url"]}')


if __name__ == '__main__':
    main()
