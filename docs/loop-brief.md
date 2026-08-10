# Loop Brief

## Objective

Improve the Oracle self-healing agent while preserving its safe-by-default behavior: every new remediation must be reproducible in the local harness, traceable from evidence to outcome, and blocked unless its explicit safety conditions are met.

## Success signals

- All scenario contracts pass with `--assert-expectations`.
- Default configuration never executes SQL in the harness.
- Every planned action has an evidence-to-plan-to-outcome path in the incident graph.
- Every run records the ordered observe, analyze, plan, govern, act, and verify hand-offs.
- Planning and analysis remain structurally separate from policy and execution authority.
- New automatic remediation has a verification query or is explicitly marked manual.

## Failure signals

- A fixture executes SQL with the default configuration.
- A plan has no source check or an action has no source plan.
- An advisory agent gains a direct database-write path or can relax a safety gate.
- A new scenario changes expected safety outcomes without an intentional fixture update and DBA review.

## Evaluation set

| Scenario | Purpose | Required result |
| --- | --- | --- |
| `healthy.json` | Golden path | No plans and no actions |
| `high_tablespace_invalid_objects.json` | Multi-incident safety path | Plans are visible; gated and dry-run behavior matches the contract |
| In-memory permitted simulation in `test_agent_harness.py` | Capability path | Only explicitly enabled SQL actions execute against the fake client |
| Missing probe data | Boundary path | Probe is reported as an error and no invented action is created |

## Mutation levers

Change one lever per iteration:

1. Probe threshold or evidence normalization.
2. Runbook eligibility and action metadata.
3. Safety gate or verification behavior.
4. Agent hand-off or graph relationship mapping and report presentation.

## Iteration plan

1. Add or update one deterministic fixture with an `expect` contract.
2. Run the contract and the unit suite.
3. Inspect the Mermaid graph for an evidence-to-outcome path.
4. Keep, revert, or branch the single change and record the result in the pull request or incident change record.

## Stop rule

Stop when all fixtures and unit tests pass, the new graph path is complete, and the next improvement would require production evidence, a DBA decision, or a new capability approval.
