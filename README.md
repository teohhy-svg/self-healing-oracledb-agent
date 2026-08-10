# Oracle Self-Healing DB Agent

This project is a safe-by-default Oracle Database healing system built as a governed agentic control plane:

1. The observation agent collects focused database evidence.
2. The performance-analysis agent translates symptoms into advisory findings.
3. The planning agent converts supported symptoms into bounded runbook actions.
4. The safety-governor agent applies risk, approval, capability, and action-count policy.
5. The bounded-executor agent acts only when those hard gates allow it.
6. The verification agent assesses action outcomes and verification queries.
7. Every hand-off is recorded in `agent_trace` and connected in the incident graph.
8. The deterministic harness proves the complete path before live Oracle use.

The default mode is dry-run. It will tell you what it would do without changing the database.

## Agentic Control Plane

`SelfHealingAgent` is the stable façade; `AgenticControlPlane` coordinates six
specialized agents with typed artifacts (`CheckResult`, `PerformanceFinding`,
`ActionPlan`, and `ActionResult`). Analysis and planning never receive direct
execution authority. Only the bounded executor can call the database, and it
must pass the existing deterministic safety gates.

The current agents are deterministic so their behavior can be reproduced in
the harness. A future LLM may propose analysis or planning advice through a
strict schema, but it must not own credentials, create arbitrary SQL, relax
policy, or call Oracle/Zabbix write operations directly.

## Quick Start

Run the sample harness scenario:

```bash
PYTHONPATH=src python3 -m oracle_self_healing_agent harness \
  --scenario fixtures/scenarios/high_tablespace_invalid_objects.json \
  --config configs/agent.example.json
```

Generate a human-readable Markdown report:

```bash
PYTHONPATH=src python3 -m oracle_self_healing_agent harness \
  --scenario fixtures/scenarios/high_tablespace_invalid_objects.json \
  --config configs/agent.example.json \
  --output-format markdown \
  --report-file reports/harness-report.md
```

Run the tests:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
```

Validate a scenario's regression contract and render its incident graph:

```bash
PYTHONPATH=src python3 -m oracle_self_healing_agent harness \
  --scenario fixtures/scenarios/high_tablespace_invalid_objects.json \
  --config configs/agent.example.json \
  --assert-expectations \
  --output-format mermaid
```

The JSON report includes `agent_trace` and `incident_graph`. The trace records
each agent hand-off; the graph connects those agents to evidence, plans, and
gated, dry-run, manual, or executed outcomes. It records control-flow evidence,
not a claimed database root cause. See [the loop brief](docs/loop-brief.md) for
the evaluation set, mutation levers, and stop rule used for changes to this
agent.

## Zabbix Problem and Resolution Automation

The optional Zabbix bridge polls tagged open problems with `problem.get`, runs
the same Oracle control loop, and can add an acknowledgement/comment containing
the outcome. It does **not** close problems: a SQL statement completing and a
verification query returning rows do not prove that the Zabbix trigger has
recovered. Let the trigger recover naturally, or require a separately approved
human close workflow.

Set the Zabbix URL and API token only in the environment, then enable the
integration in a private configuration file:

```bash
export ZABBIX_URL='https://zabbix.example/zabbix'
export ZABBIX_API_TOKEN='...'

PYTHONPATH=src python3 -m oracle_self_healing_agent zabbix \
  --config private-agent.json
```

Use a dedicated least-privilege token. `allow_status_updates` is `false` by
default; when enabled, the required Zabbix permission is limited to reading
problems and adding an acknowledgement/message. Keep the Oracle agent's
`dry_run` and approval gates enabled until its harness scenarios mirror the
database incidents you intend to automate.

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

Save a live dry-run report:

```bash
PYTHONPATH=src python3 -m oracle_self_healing_agent live \
  --config configs/agent.example.json \
  --output-format markdown \
  --report-file reports/live-dry-run.md
```

Review the dry-run safety switch before any live run:

```json
"safety": {
  "dry_run": true,
  "require_approval": true,
  "allow_storage_changes": false,
  "allow_session_kill": false,
  "allow_stats_jobs": true,
  "max_actions_per_run": 5
}
```

This setting is in `configs/agent.example.json`. Keep `safety.dry_run` set to `true` while testing so the agent diagnoses and reports what it would do without changing the database.

You can override it from the terminal for one session:

```bash
export AGENT_DRY_RUN=false
```

Only set dry-run to `false` after the harness results, privileges, runbooks, and operational approvals are all reviewed.

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
