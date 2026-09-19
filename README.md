# Maida Action smoke fixture

A synthetic, multi-step sales assistant for testing the Maida GitHub Action.
This repository is a permanent test environment, safe to use for test branches,
PRs and baseline changes. It has no production role.

All contacts, plans, drafts, tool results and model responses are invented fixture
data. No external sales system, email service or model provider is connected.
Tool effects are in memory; even the forbidden `send_email` scenario cannot send
a message. A normal run makes seven recorded tool calls and one recorded model
call. The model response and token counts are simulated: actual API spend is $0.

## The workflow

1. Look up a fictional lead in an in-memory CRM.
2. Check consent; stop if absent.
3. Qualify the request against seats, needs and budget; stop if unsuitable.
4. Look up a matching plan and calculate a quote.
5. Draft a response with the simulated model.
6. Save the draft for human review.
7. Create a follow-up task. No message is delivered.

The fixture offers realistic control flow, tool boundaries, state changes and
failure handling. It does not evaluate whether a real model can sell, reason,
use tools correctly or write an accurate response.

## Run locally

Python 3.12, `uv`, Git and Bash are required. From this repository:

```bash
uv sync --frozen
uv run python scripts/smoke.py
```

The smoke command creates an isolated Git workspace and trace store, runs the
real released Maida CLI through all scenarios, and checks expected verdicts and
exit codes. Reports, diagnostics, an acceptance artifact and `summary.json` are
saved under `artifacts/smoke/`. It exits zero only when every expected outcome
matches. FAIL is an expected result for the deliberately broken scenarios;
INCONCLUSIVE remains a distinct verdict despite its CLI exit code of zero.
The checked-in baseline is never modified by this command.

To inspect one run in this checkout:

```bash
MAIDA_DATA_DIR=artifacts/runs uv run python agent.py --scenario good
MAIDA_DATA_DIR=artifacts/runs uv run maida view
```

To reproduce a failure directly:

```bash
SALES_SCENARIO=retry_loop MAIDA_DATA_DIR=artifacts/runs uv run maida run agent.py --baseline .maida/baselines/sales.json --policy .maida/policy.yaml
```

That command exits 1 and reports a loop and excess tool calls. The tool loop is
bounded to eight additional lookups. Every scenario is finite and offline.

## Scenarios

- `good`: PASS; seven tools, a draft and a follow-up.
- `harmless_copy_edit`: PASS; different wording with the same structural behavior.
- `extra_research`: FAIL; adds a comparison step. The smoke command also reviews
  and accepts this change in its temporary workspace, then verifies a PASS.
- `retry_loop`: FAIL; repeats the contact lookup eight times.
- `missing_followup`: FAIL; omits a required tool despite producing a draft.
- `unreviewed_send`: FAIL; invokes a forbidden simulated delivery tool.
- `tool_error`: FAIL; the catalog tool raises a simulated outage.
- `token_spike`: FAIL; simulated token usage exceeds the policy limit.
- `inconclusive`: INCONCLUSIVE; two normal executions under the separate
  distributional policy. This is a test of the third verdict, not certification
  of a population-level quality claim.

The entry point reads `scenario.json` by default. `--scenario` takes precedence
over `SALES_SCENARIO`, which takes precedence over the file. The inconclusive
case runs the good agent under `.maida/inconclusive.yaml`; it is a gate scenario,
not an agent behavior.

## Baseline and policy

`.maida/baselines/sales.json` was captured from one real execution of the synthetic
good fixture using `maida baseline --from-report`. It records the agent role
version (`sales-assistant-v1`), model fixture version (`simulated-drafter-v1`), tool
structure and observed metrics. It contains no imported production traces.

The normal policy checks required/forbidden tools, completed execution, loops,
tool count relative to that baseline, and a simulated token limit. Timing varies
with the machine and is deliberately outside the gate. Required-tool checks
establish presence, not ordering; unit tests additionally check the expected
sequence, consent handling and quote arithmetic. The policy is specific to this
synthetic qualified lead, not a policy for every possible sales conversation.
One observed baseline is not evidence of reliability beyond these fixtures.

For an intentional structural change, inspect the trace and use explicit local
acceptance. The following changes the checked-in baseline, so review its diff:

```bash
MAIDA_DATA_DIR=artifacts/review uv run python agent.py --scenario extra_research
MAIDA_DATA_DIR=artifacts/review uv run maida accept --baseline .maida/baselines/sales.json --reason "Reviewed synthetic comparison step"
git diff -- .maida/baselines/sales.json
```

Acceptance records the prior hash and reason. It cannot make a forbidden tool or
missing required tool acceptable under unchanged policy.

## GitHub smoke workflow

`verify.yml` runs tests, coverage and lint on every PR. `maida.yml` has two
purposes:

- **Consumer PR gate:** every PR, regardless of target branch, runs the reviewed,
  SHA-pinned Action in blocking mode against the exact candidate commit. The
  Action reads policy and baseline from the PR base. PASS succeeds; FAIL and
  INCONCLUSIVE fail the gate. Missing evidence or failed check publication also
  fails the job. The candidate's `scenario.json` selects the agent behavior.
- **Upstream Action regression smoke:** every Monday at 08:41 UTC, test current
  `maida-ai/maida-assert` main with `good`, `extra_research`, `retry_loop` and
  `inconclusive`. Manual dispatch tests any scenario listed above. Resolve main
  once, check out that exact SHA as a runtime dependency, and record it in the run summary and
  artifacts. No Action source is vendored in this repository.

Scheduled/manual tests use report-only mode because blocking mode requires a
real PR and trusted base revision. Their verifier requires the expected verdict,
a nonempty Markdown report, and a newly published neutral check on the consumer
commit with matching title and summary. An unexpected verdict, missing check or
stale check fails the smoke job even if the Action step succeeded. This tests
Action installation, CLI invocation, report handling and GitHub check publication;
it does not test PR comments, trusted-base enforcement or protected merges.
The released CLI stays pinned to keep these tests focused on Action changes.

Known incompatibility in the current PR Action pin: invariant-failure reports
(such as `retry_loop`, `missing_followup` and `unreviewed_send`) contain a decisive
FAIL but also `abort_reason=invariant_violation`. The Action currently rejects
these as aborted evidence before publishing a check or comment. The manual
`tool_error` scenario similarly stops before publication with
`abort_reason=agent_process_failure`. Local execution of the Action's shell steps
against this fixture reproduced these failures; GitHub transport was simulated.
The scheduled `retry_loop` case deliberately preserves the expected FAIL report
and publication requirement, so it will expose the upstream incompatibility
until the Action handles it. `extra_research` covers measured FAIL independently.
Do not weaken the fixture policy or accept a missing report to make CI green.

The schedule becomes active when this workflow is on the default branch. Changes
to the Action repository are picked up on the next scheduled run, not immediately.
Use manual dispatch for an earlier check. Upstream tests request only contents
read and checks write; PR jobs additionally request pull-requests write for the
comment. Fork tokens may lack write permissions, in which case the blocking job
fails closed. No privileged PR trigger is used.

To exercise the PR gate, open a test PR changing `scenario.json` from `good` to
`extra_research`. Fixture tests should stay green and `Sales agent gate` should
fail with a PR comment. Changing back to `good` should update the comment and pass.
Intentional policy/baseline changes require a maintainer-controlled
`MAIDA_CONFIGURATION_ACCEPTANCE` value bound to the base, head and configuration;
see the [Action documentation](https://github.com/maida-ai/maida-assert#readme).
Never source that variable from candidate content.

Repository settings must require both `Sales agent gate` and `Maida statistical
gate` and require review of workflow/control changes using CODEOWNERS. YAML alone
does not configure protection. Protected merge behavior remains unverified; this
fixture's scheduled checks do not establish merge enforcement. An issue-comment
acceptance workflow is not enabled.

Jobs time out after five minutes, request no model credentials and retain only
synthetic reports and check metadata for seven days. GitHub runner minutes may
still be billable. Update the PR Action pin after reviewing a new upstream
revision; scheduled testing does not automatically promote it.

## Development

```bash
uv run pytest --cov
uv run ruff check .
uv run ruff format --check .
```

Tests cover the successful path, harmless variance, deliberate regressions,
invalid input, consent and qualification exits, tool failure, real CLI verdicts,
reviewed acceptance in a temporary copy, and rejection of missing, stale or
incorrect Action check evidence. A network guard rejects socket
connections in the in-process agent tests. Do not add real contact data, provider
keys or delivery integrations to this fixture.
