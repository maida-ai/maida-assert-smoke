import json
from hashlib import sha256

from scripts.smoke import ROOT, matrix


def test_real_gate_matrix_and_local_acceptance(tmp_path):
    baseline_path = ROOT / ".maida/baselines/sales.json"
    original = baseline_path.read_bytes()
    assert matrix(tmp_path) == 0
    summaries = {
        item["scenario"]: item
        for item in json.loads((tmp_path / "summary.json").read_text())
    }
    expected_failures = {
        "retry_loop": "no_loops",
        "missing_followup": "required_tools",
        "unreviewed_send": "forbidden_tools",
        "tool_error": "agent_process",
        "token_spike": "cost_tokens",
        "extra_research": "tool_call_count",
    }
    for scenario, check in expected_failures.items():
        assert summaries[scenario]["checks"][check] == "fail"
    assert summaries["harmless_copy_edit"]["verdict"] == "pass"
    assert summaries["inconclusive"]["verdict"] == "inconclusive"
    accepted = json.loads((tmp_path / "accepted-baseline.json").read_text())
    assert (
        accepted["acceptance"]["previous_baseline"]["sha256"]
        == sha256(original).hexdigest()
    )
    assert (
        accepted["acceptance"]["reason"] == "Synthetic smoke: reviewed comparison step"
    )
    assert summaries["accepted_extra_research"]["verdict"] == "pass"
    assert baseline_path.read_bytes() == original
