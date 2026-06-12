# Oracle Self-Healing DB Agent

This project is a safe-by-default Oracle Database healing agent built around a harness engineering approach:

1. Observe database health with focused probes.
2. Convert symptoms into explicit runbook actions.
3. Gate every action with risk, approval, and capability checks.
4. Execute only when dry-run and approval settings allow it.
5. Verify outcomes and emit a structured report.
6. Prove behavior first in a deterministic local harness before live Oracle use.

The default mode is dry-run. It will tell you what it would do without changing the database.

## Quick Start

Run the sample harness scenario:

```bash
PYTHONPATH=src python3 -m oracle_self_healing_agent harness \
  --scenario fixtures/scenarios/high_tablespace_invalid_objects.json \
  --config configs/agent.example.json
```

Run the tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

## Live Oracle Mode

Install the Oracle driver when you are ready to connect to a database:

```bash
python3 -m pip install "oracledb>=2.0"
```

Set credentials using environment variables or edit a private config file copied from `configs/agent.example.json`:

```bash
export ORACLE_USER=system
export ORACLE_PASSWORD='...'
export ORACLE_DSN='host:1521/service'

PYTHONPATH=src python3 -m oracle_self_healing_agent live --config configs/agent.example.json
```

Keep `safety.dry_run` set to `true` until the harness results, privileges, runbooks, and operational approvals are all reviewed.

## Current Runbooks

| Probe | Symptom | Default healing behavior |
| --- | --- | --- |
| Tablespace pressure | Tablespace usage exceeds threshold | Plans an autoextend action only when storage changes are allowed and a datafile is available |
| Blocking sessions | A session blocks others beyond the threshold | Plans a kill-session action only when session killing is allowed |
| Invalid objects | Invalid schema objects exist | Plans `DBMS_UTILITY.COMPILE_SCHEMA` |
| Stale optimizer stats | Stale table stats are detected | Plans `DBMS_STATS.GATHER_SCHEMA_STATS` |
| FRA pressure | Recovery area usage exceeds threshold | Emits a manual RMAN cleanup advisory |

## Harness Engineering Approach

The harness is the contract between engineering intent and operational safety. Each scenario fixture supplies probe results as if they came from Oracle views. The agent then follows the same diagnosis, planning, gating, and reporting path it would use in production.

Use the harness to add scenario coverage before enabling a new remediation. Good scenarios include:

- pressure below threshold, no action
- pressure above threshold, action planned but gated
- pressure above threshold, action permitted and executed in simulated mode
- failed probes or failed executions
- noisy multi-incident runs capped by `max_actions_per_run`

See [docs/architecture.md](docs/architecture.md) for the control-loop and rollout model.
