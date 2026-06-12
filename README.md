# Oracle Self-Healing DB Agent

This project is a safe-by-default Oracle Database healing agent built around a harness engineering approach:

1. Observe database health with focused probes.
2. Let the performance expert engineer translate workload symptoms into tuning findings.
3. Convert safe operational symptoms into explicit runbook actions.
4. Gate every action with risk, approval, and capability checks.
5. Execute only when dry-run and approval settings allow it.
6. Verify outcomes and emit a structured report.
7. Prove behavior first in a deterministic local harness before live Oracle use.

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

### DPY-3015 / 10G Password Verifier

If live mode fails with `DPY-3015: password verifier type 0x939 is not supported by python-oracledb in thin mode`, use one of these fixes:

1. Ask a DBA to reset the database user's password so Oracle stores an 11G-or-newer password verifier.
2. Enable python-oracledb thick mode with Oracle Instant Client 19 or later.

For thick mode on macOS:

```bash
export ORACLE_THICK_MODE=true
export ORACLE_CLIENT_LIB_DIR="$HOME/Downloads/instantclient_23_3"

PYTHONPATH=src python3 -m oracle_self_healing_agent live \
  --config configs/agent.example.json
```

`ORACLE_CLIENT_LIB_DIR` should point to the directory containing the Instant Client libraries, such as `libclntsh.dylib` on macOS.

## Current Runbooks

| Probe | Symptom | Default healing behavior |
| --- | --- | --- |
| Tablespace pressure | Tablespace usage exceeds threshold | Plans an autoextend action only when storage changes are allowed and a datafile is available |
| Blocking sessions | A session blocks others beyond the threshold | Plans a kill-session action only when session killing is allowed |
| Invalid objects | Invalid schema objects exist | Plans `DBMS_UTILITY.COMPILE_SCHEMA` |
| Stale optimizer stats | Stale table stats are detected | Plans `DBMS_STATS.GATHER_SCHEMA_STATS` |
| FRA pressure | Recovery area usage exceeds threshold | Emits a manual RMAN cleanup advisory |
| Expensive SQL | SQL exceeds elapsed-time threshold | Adds performance expert SQL tuning findings |
| Wait-class pressure | One wait class dominates non-idle wait time | Adds performance expert wait-analysis findings |

## Performance Expert Engineer

The performance expert engineer is intentionally advisory. It does not auto-apply SQL tuning changes, create indexes, or force plans by default because those actions need workload context and DBA review.

It currently analyzes:

- high elapsed-time SQL from `v$sql`
- dominant non-idle wait classes from `v$system_wait_class`
- stale optimizer statistics discovered by the health probes

Findings appear in the report under `performance_findings`, with severity, area, evidence, and a recommended next step.

## Harness Engineering Approach

The harness is the contract between engineering intent and operational safety. Each scenario fixture supplies probe results as if they came from Oracle views. The agent then follows the same diagnosis, planning, gating, and reporting path it would use in production.

Use the harness to add scenario coverage before enabling a new remediation. Good scenarios include:

- pressure below threshold, no action
- pressure above threshold, action planned but gated
- pressure above threshold, action permitted and executed in simulated mode
- failed probes or failed executions
- noisy multi-incident runs capped by `max_actions_per_run`

See [docs/architecture.md](docs/architecture.md) for the control-loop and rollout model.
