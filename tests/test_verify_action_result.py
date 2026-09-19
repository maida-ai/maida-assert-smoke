"""A green Action step alone is not evidence that the expected check exists."""

import copy
import json

import pytest

from scripts.smoke import EXPECTED
from scripts.verify_action_result import main, verify

HEAD = "a" * 40
RUN_URL = "https://github.com/example/smoke/actions/runs/123"
NAME = "Maida behavioral report (non-blocking)"


def evidence(directory, scenario="good"):
    verdict = EXPECTED[scenario][0]
    payload = {
        "name": NAME,
        "head_sha": HEAD,
        "status": "completed",
        "conclusion": "neutral",
        "details_url": RUN_URL,
        "output": {"title": f"{NAME}: {verdict.upper()}", "summary": RUN_URL},
    }
    published = copy.deepcopy(payload)
    published.update(id=12, details_url="https://github.com/check/12")
    documents = {
        "maida-report.json": {"verdict": verdict},
        "maida-check-payload.json": payload,
        "checks-before.json": [{"check_runs": [{"id": 11}]}],
        "checks-after.json": [{"check_runs": [published]}],
    }
    for name, value in documents.items():
        (directory / name).write_text(json.dumps(value))
    (directory / "maida-report.md").write_text(f"# {verdict.upper()}\n")
    return documents


def change(directory, documents, filename, mutate):
    mutate(documents[filename])
    (directory / filename).write_text(json.dumps(documents[filename]))


@pytest.mark.parametrize("scenario", EXPECTED)
def test_expected_verdict_with_new_published_check(tmp_path, scenario):
    evidence(tmp_path, scenario)
    assert verify(tmp_path, scenario, HEAD, RUN_URL) == 12


@pytest.mark.parametrize(
    ("filename", "mutate", "message"),
    [
        ("maida-report.json", lambda d: d.update(verdict="inconclusive"), "verdict"),
        ("maida-check-payload.json", lambda d: d.update(head_sha="b" * 40), "head_sha"),
        ("maida-check-payload.json", lambda d: d.update(name="gate"), "name"),
        (
            "maida-check-payload.json",
            lambda d: d.update(conclusion="success"),
            "conclusion",
        ),
        (
            "maida-check-payload.json",
            lambda d: d.update(status="in_progress"),
            "status",
        ),
        (
            "maida-check-payload.json",
            lambda d: d.update(details_url="old"),
            "details_url",
        ),
        (
            "maida-check-payload.json",
            lambda d: d["output"].update(title="PASS"),
            "title",
        ),
        (
            "maida-check-payload.json",
            lambda d: d["output"].update(summary=""),
            "summary",
        ),
        ("checks-after.json", lambda d: d[0].update(check_runs=[]), "one new"),
        (
            "checks-before.json",
            lambda d: d[0]["check_runs"].append({"id": 12}),
            "one new",
        ),
        (
            "checks-after.json",
            lambda d: d.append({"check_runs": [dict(d[0]["check_runs"][0], id=13)]}),
            "one new",
        ),
    ],
)
def test_rejects_incorrect_or_missing_evidence(tmp_path, filename, mutate, message):
    documents = evidence(tmp_path)
    change(tmp_path, documents, filename, mutate)
    with pytest.raises(ValueError, match=message):
        verify(tmp_path, "good", HEAD, RUN_URL)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("head_sha", "old"),
        ("name", "other"),
        ("conclusion", "success"),
        ("status", "queued"),
    ],
)
def test_rejects_published_check_that_differs_from_payload(tmp_path, key, value):
    documents = evidence(tmp_path)
    change(
        tmp_path,
        documents,
        "checks-after.json",
        lambda d: d[0]["check_runs"][0].update({key: value}),
    )
    with pytest.raises(ValueError, match="one new"):
        verify(tmp_path, "good", HEAD, RUN_URL)


@pytest.mark.parametrize("key", ["title", "summary"])
def test_rejects_mismatched_published_output(tmp_path, key):
    documents = evidence(tmp_path)
    change(
        tmp_path,
        documents,
        "checks-after.json",
        lambda d: d[0]["check_runs"][0]["output"].update({key: "old"}),
    )
    with pytest.raises(ValueError, match="one new"):
        verify(tmp_path, "good", HEAD, RUN_URL)


def test_finds_check_on_later_api_page(tmp_path):
    documents = evidence(tmp_path)
    change(
        tmp_path,
        documents,
        "checks-after.json",
        lambda d: d.insert(0, {"check_runs": []}),
    )
    assert verify(tmp_path, "good", HEAD, RUN_URL) == 12


def test_rejects_empty_markdown(tmp_path):
    evidence(tmp_path)
    (tmp_path / "maida-report.md").write_text("\n")
    with pytest.raises(ValueError, match="Markdown"):
        verify(tmp_path, "good", HEAD, RUN_URL)


@pytest.mark.parametrize("contents", [None, "not json", "null", "[]"])
def test_cli_reports_missing_or_malformed_evidence(tmp_path, capsys, contents):
    if contents is not None:
        evidence(tmp_path)
        (tmp_path / "maida-report.json").write_text(contents)
    assert (
        main(
            [
                "good",
                "--head-sha",
                HEAD,
                "--run-url",
                RUN_URL,
                "--directory",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert "Action smoke verification failed" in capsys.readouterr().err


def test_cli_success(tmp_path, capsys):
    evidence(tmp_path)
    assert (
        main(
            [
                "good",
                "--head-sha",
                HEAD,
                "--run-url",
                RUN_URL,
                "--directory",
                str(tmp_path),
            ]
        )
        == 0
    )
    assert "published check 12" in capsys.readouterr().out
