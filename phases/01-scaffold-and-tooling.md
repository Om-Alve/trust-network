---
id: "01"
title: Scaffold and dev tooling
status: done        # todo | in-progress | done | blocked | skipped
priority: P0
owner: agent
depends_on: []
plan_refs: ["§5 Components (repo tree, stack)"]
target: Nov 5 evening
---

# 01 · Scaffold and dev tooling

## Goal
An empty but runnable Python project with the repo layout from PLAN.md §5, pinned dependencies, and one command (`make check`) that every later phase uses as its quality bar.

## Tasks
- [x] `git init`, default branch `main`.
- [x] `.gitignore`: `.venv/`, `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.env`, `**/ledger.jsonl`, `**/claims.json`, `data/` (runtime state), `.DS_Store`.
- [x] `.python-version` → `3.12`.
- [x] `pyproject.toml` (managed by `uv`):
  - runtime deps: `websockets`, `httpx`, `icalendar`, `recurring-ical-events`, `dateparser`, `pyyaml`, `mcp` (FastMCP), `jinja2` (for `envoy-brief.md.j2`; not named in the plan, but the template needs it);
  - dev deps: `pytest`, `pytest-asyncio`, `ruff`;
  - console script `tn = "trustnet.tn.cli:main"`;
  - ruff config (line length 100, `I` import sorting on), pytest config (`asyncio_mode = "auto"`, `testpaths = ["tests"]`).
- [x] `uv lock` and commit `uv.lock`.
- [x] Package skeleton, each module with a one-line docstring and nothing else:
  ```
  trustnet/__init__.py
  trustnet/switch_client.py
  trustnet/gate/{__init__,__main__,policy,facts,calendar,commands,relay,surprise,ledger,envoy}.py
  trustnet/tn/{__init__,cli,mcp}.py
  skills/trust-network/.gitkeep
  templates/.gitkeep
  examples/{om,rahul,priya}/.gitkeep
  scripts/.gitkeep
  tests/test_smoke.py
  docs/.gitkeep
  ```
- [x] `trustnet/tn/cli.py` `main()` prints help (argparse) and exits 0. `trustnet/gate/__main__.py` does the same for `python -m trustnet.gate --help`.
- [x] `tests/test_smoke.py`: imports every module.
- [x] `Makefile` targets: `check` (= `uv run ruff format --check . && uv run ruff check . && uv run pytest -q`), `fmt`, `test`.
- [x] `.env.example` listing the variables later phases need, with no values: `SWITCH_URL`, `OM_GATE_KEY`, `RAHUL_GATE_KEY`, `PRIYA_GATE_KEY`, `RAHUL_HERMES_KEY`, `TN_DATA_DIR`.
- [x] `AGENTS.md` (and a `CLAUDE.md` symlink to it): three lines pointing agents at `PLAN.md` and `phases/README.md`, plus "run `make check` before every commit".

## Done when
- [x] `uv sync` succeeds from a clean clone.
- [x] `make check` passes.
- [x] `uv run tn --help` and `uv run python -m trustnet.gate --help` both exit 0.
- [x] `git status` is clean after the commit; `.env` is ignored (`git check-ignore .env` prints `.env`).

## Commit
`phase 01: scaffold, uv project, dev tooling`

## Log

Completed 2026-11-05. All phase 01 files were explicitly staged; phase 02 paths
were excluded. No `.env` was created. `CLAUDE.md` points to `AGENTS.md`.

### Deviations
- Added `jinja2` as required by this phase for the planned brief template.
- Added setuptools packaging configuration, build artifact ignores, and an explicit
  pytest async fixture loop scope. These support installation and warning-free checks.
- Per the coordination exception, phase 02 files may remain untracked or modified
  after this commit: `docs/day0.md`, `docs/setup-laptop.md`, `docs/setup-vm.md`,
  `scripts/ws_probe.py`, and `phases/02-infra-day0-checks.md`. They are not included.

### Evidence

`uv lock` resolved 56 packages. Initial `uv sync` installed 53 packages using
CPython 3.12.13. Repeated `uv sync`:

```text
Resolved 56 packages in 4ms
Checked 53 packages in 1ms
```

Fresh staged-source checkout, with no virtual environment, `uv sync`:

```text
Using CPython 3.12.13
Creating virtual environment at: .venv
Resolved 56 packages in 2ms
   Building trust-network @ file:///private/tmp/trustnet-phase01-cKwShB
      Built trust-network @ file:///private/tmp/trustnet-phase01-cKwShB
Prepared 1 package in 264ms
Installed 53 packages in 61ms
 + annotated-types==0.8.0
 + anyio==4.16.0
 + attrs==26.1.0
 + certifi==2026.10.23
 + cffi==2.1.1
 + click==8.5.0
 + cryptography==50.0.2
 + dateparser==1.5.0
 + h11==0.16.0
 + httpcore==1.0.9
 + httpcore2==2.16.0
 + httpx==0.28.1
 + httpx2==2.16.0
 + icalendar==7.3.0
 + idna==3.20
 + iniconfig==2.3.1
 + jinja2==3.1.6
 + jsonschema==4.26.0
 + jsonschema-specifications==2025.9.1
 + markupsafe==3.0.4
 + mcp==2.3.0
 + mcp-types==2.3.0
 + opentelemetry-api==1.45.2
 + packaging==26.3
 + pluggy==1.7.0
 + pycparser==3.12
 + pydantic==2.14.3
 + pydantic-core==2.50.4
 + pygments==2.21.0
 + pyjwt==2.15.1
 + pytest==9.2.0
 + pytest-asyncio==1.4.1.post1
 + python-dateutil==2.9.0.post0
 + python-multipart==0.0.33
 + pytz==2026.6
 + pyyaml==6.0.3
 + recurring-ical-events==3.8.2
 + referencing==0.37.0
 + regex==2026.9.29
 + rpds-py==2026.9.1
 + ruff==0.17.3
 + six==1.17.0
 + sse-starlette==3.6.0
 + starlette==1.10.0
 + trust-network==0.1.0 (from file:///private/tmp/trustnet-phase01-cKwShB)
 + truststore==0.10.5
 + typing-extensions==4.16.0
 + typing-inspection==0.4.5
 + tzdata==2026.6
 + tzlocal==5.4.5
 + uvicorn==0.54.0
 + websockets==17.4
 + x-wr-timezone==2.0.1
```

`make check`:

```text
uv run ruff format --check . && uv run ruff check . && uv run pytest -q
   Building trust-network @ file:///Users/om/switch-hackathon/trust-network
      Built trust-network @ file:///Users/om/switch-hackathon/trust-network
Uninstalled 1 package in 0.56ms
Installed 1 package in 1ms
46 files already formatted
All checks passed!
...............                                                          [100%]
15 passed in 0.01s
```

`uv run tn --help; echo $?`:

```text
usage: tn [-h]

Manage trust network profiles and conversations.

options:
  -h, --help  show this help message and exit
0
```

`uv run python -m trustnet.gate --help; echo $?`:

```text
usage: python -m trustnet.gate [-h]

Run a trust network gate.

options:
  -h, --help  show this help message and exit
0
```

`git check-ignore .env`:

```text
.env
```


Actual clean clone verification after the phase commit, `uv sync`:

```text
Using CPython 3.12.13
Creating virtual environment at: .venv
Resolved 56 packages in 2ms
   Building trust-network @ file:///private/tmp/trustnet-phase01-clone-z9KsYy/repo
      Built trust-network @ file:///private/tmp/trustnet-phase01-clone-z9KsYy/repo
Prepared 1 package in 277ms
Installed 53 packages in 62ms
 + annotated-types==0.8.0
 + anyio==4.16.0
 + attrs==26.1.0
 + certifi==2026.10.23
 + cffi==2.1.1
 + click==8.5.0
 + cryptography==50.0.2
 + dateparser==1.5.0
 + h11==0.16.0
 + httpcore==1.0.9
 + httpcore2==2.16.0
 + httpx==0.28.1
 + httpx2==2.16.0
 + icalendar==7.3.0
 + idna==3.20
 + iniconfig==2.3.1
 + jinja2==3.1.6
 + jsonschema==4.26.0
 + jsonschema-specifications==2025.9.1
 + markupsafe==3.0.4
 + mcp==2.3.0
 + mcp-types==2.3.0
 + opentelemetry-api==1.45.2
 + packaging==26.3
 + pluggy==1.7.0
 + pycparser==3.12
 + pydantic==2.14.3
 + pydantic-core==2.50.4
 + pygments==2.21.0
 + pyjwt==2.15.1
 + pytest==9.2.0
 + pytest-asyncio==1.4.1.post1
 + python-dateutil==2.9.0.post0
 + python-multipart==0.0.33
 + pytz==2026.6
 + pyyaml==6.0.3
 + recurring-ical-events==3.8.2
 + referencing==0.37.0
 + regex==2026.9.29
 + rpds-py==2026.9.1
 + ruff==0.17.3
 + six==1.17.0
 + sse-starlette==3.6.0
 + starlette==1.10.0
 + trust-network==0.1.0 (from file:///private/tmp/trustnet-phase01-clone-z9KsYy/repo)
 + truststore==0.10.5
 + typing-extensions==4.16.0
 + typing-inspection==0.4.5
 + tzdata==2026.6
 + tzlocal==5.4.5
 + uvicorn==0.54.0
 + websockets==17.4
 + x-wr-timezone==2.0.1
```

Post-commit `git status --short` showed only the allowed phase 02 file:

```text
?? phases/02-infra-day0-checks.md
```
