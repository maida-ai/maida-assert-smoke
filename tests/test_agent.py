import json
from pathlib import Path

import pytest

from sales_agent import run_sales_agent

LEAD = json.loads((Path(__file__).parents[1] / "fixtures" / "lead.json").read_text())


def test_good_flow_creates_reviewable_draft_and_followup():
    result = run_sales_agent(LEAD)
    assert result.status == "ready_for_review"
    assert result.quote_usd == 100
    assert result.draft.startswith("Hello Example Workshop")
    assert result.followup == "review-draft"
    assert result.delivered is False
    assert result.tools == [
        "lookup_contact",
        "check_consent",
        "qualify_lead",
        "list_plans",
        "calculate_quote",
        "save_draft",
        "create_followup",
    ]


def test_copy_change_changes_answer_but_preserves_tool_path():
    good = run_sales_agent(LEAD)
    changed = run_sales_agent(LEAD, "harmless_copy_edit")
    assert changed.draft != good.draft
    assert changed.tools == good.tools
    assert changed.quote_usd == good.quote_usd


@pytest.mark.parametrize(
    "scenario,tool,count",
    [
        ("retry_loop", "lookup_contact", 9),
        ("extra_research", "compare_plans", 1),
        ("unreviewed_send", "send_email", 1),
        ("missing_followup", "create_followup", 0),
    ],
)
def test_regressions_are_real_changes_to_execution(scenario, tool, count):
    result = run_sales_agent(LEAD, scenario)
    assert result.tools.count(tool) == count
    assert result.delivered is False


def test_no_consent_stops_before_qualification_or_drafting():
    result = run_sales_agent({**LEAD, "consent": False})
    assert result.status == "no_consent"
    assert result.tools == ["lookup_contact", "check_consent"]
    assert result.draft is None
    assert result.followup is None


def test_unqualified_lead_does_not_get_a_quote():
    result = run_sales_agent({**LEAD, "monthly_budget_usd": 1})
    assert result.status == "not_qualified"
    assert result.quote_usd is None
    assert result.draft is None


def test_tool_failure_is_an_error_not_a_successful_empty_result():
    with pytest.raises(RuntimeError, match="Simulated catalog outage"):
        run_sales_agent(LEAD, "tool_error")


def test_unknown_scenario_fails_before_any_tool_call():
    with pytest.raises(ValueError, match="Unknown scenario"):
        run_sales_agent(LEAD, "typo")


@pytest.mark.parametrize(
    "change",
    [
        {"seats": 0},
        {"seats": True},
        {"monthly_budget_usd": -1},
        {"email": "real@example.com"},
        {"consent": "yes"},
        {"need": "unsupported"},
        {"id": ""},
    ],
)
def test_invalid_or_nonfixture_input_is_rejected(change):
    with pytest.raises(ValueError):
        run_sales_agent({**LEAD, **change})
