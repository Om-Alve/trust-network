---
id: "30"
title: Install outside the checkout
status: done
priority: P1
owner: agent
depends_on: ["29"]
plan_refs: ["§5 Components", "§11 Risks (judges reproduce it)"]
target: Nov 6
---

# 30 · Install outside the checkout (TN-03)

`pyproject.toml` packaged Python modules, while `brief.py` read the share-card
template from the repository's `templates/` directory and `wake.py` read the
skill and watcher prompt from the repository too. `identity.py` ran an exporter
from `scripts/`. A wheel installed elsewhere had none of those files.

This phase makes the package self-contained: one canonical source for each
runtime file lives in `trustnet/resources/` and is loaded with
`importlib.resources`. Repository copies are removed rather than mirrored, so
the two cannot drift.

## Tasks
- [x] Write the installed-wheel E2E first (`scripts/e2e_install.py`) and record
      its pre-fix failures.
- [x] Move the share-card template, agent skill, watcher prompt and identity
      exporter into `trustnet/resources/` and load them through
      `importlib.resources`.
- [x] Migrate runtime callers: `gate/brief.py`, `tn/wake.py`, `gate/identity.py`,
      the two live scenario runners and the Hermes scene reset.
- [x] Read the wake persona (`agent.md`) from the person's data directory, so a
      wheel install uses `TN_DATA_DIR` instead of `examples/`.
- [x] When an installed copy has no checkout and no `TN_DATA_DIR`, fail with a
      message that names `TN_DATA_DIR`.
- [x] Update living references: README, PROTOCOL.md, the home template, PLAN.md
      and `docs/practical-next-steps.md`.

## Done when
- [x] The E2E builds a wheel, installs it in a clean virtualenv outside the
      checkout with no `PYTHONPATH`, changes outside the checkout, renders both
      demo share cards from copied fixtures, runs `tn wake` as a real process
      through stdin with the packaged skill and watcher prompt, and materializes
      the packaged identity exporter.
- [x] `make check` passes.
- [x] No repository copy of a packaged runtime file remains.

## Commit
`phase 30: install outside the checkout`

## Log
Test first. `uv run python scripts/e2e_install.py` failed before the change at
`data/install-20261106T235025/report.md`: the share card could not find
`site-packages/templates/envoy-brief.md.j2`, `wake` could not find
`site-packages/skills/trust-network/SKILL.md`, the identity exporter module was
absent, and a command with no `TN_DATA_DIR` pointed at
`site-packages/examples/om/facts.yaml` instead of naming the variable.

After the change the same run passes every check at
`data/install-20261106T235439/report.md`: wheel `trust_network-0.1.0-py3-none-any.whl`
built from the checkout, installed into a temporary venv outside it, then run
from a temporary working directory with no `PYTHONPATH`. The report records the
installed `trustnet` location, both share cards, the real `tn wake` prompt and
reply, the watcher prompt delivered through `Runner.poll`, the materialized
identity exporter, and the no-data error. The wheel listing confirms
`trustnet/resources/{SKILL.md, envoy-brief.md.j2, tn-watch-prompt.md,
gate_identity_export.py}` are inside it. Reports are local-only under `data/`.

Checks: `make check` passed with 509 tests. The offline scenario runners still
pass: planning 8/8, facts 10/10, agent facts PASS. Fixtures were copied to
temporary directories; `examples/` has no new files.

Deviations from `PLAN.md`, now reflected there: the runtime files live under
`trustnet/resources/` instead of `skills/`, `templates/` (for the template only;
`home.template.yaml` stays) and `scripts/`. The wake persona default moved from
the repository's `examples/<person>/agent.md` to `agent.md` in the person's data
directory; inside a checkout both resolve to the same file. Identity export now
writes the packaged exporter to a temporary directory before running it with
Switch core's Python.
