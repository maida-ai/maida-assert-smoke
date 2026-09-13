"""Synthetic, in-memory sales workflow for behavioral regression testing."""

from __future__ import annotations

from dataclasses import dataclass, field

from maida import record_llm_call, record_tool_call, traced_run

SCENARIOS = (
    "good",
    "harmless_copy_edit",
    "extra_research",
    "retry_loop",
    "missing_followup",
    "unreviewed_send",
    "tool_error",
    "token_spike",
)


@dataclass
class SalesResult:
    status: str = "started"
    quote_usd: int | None = None
    draft: str | None = None
    followup: str | None = None
    tools: list[str] = field(default_factory=list)
    delivered: bool = False


class MockTools:
    """Each tool records a real Maida event; its effects stay in this object."""

    def __init__(self, lead: dict, result: SalesResult):
        self.lead = dict(lead)
        self.result = result
        self.drafts: list[str] = []
        self.tasks: list[str] = []

    def call(self, name: str, arguments: dict, operation):
        self.result.tools.append(name)
        try:
            value = operation()
        except RuntimeError as exc:
            record_tool_call(
                name=name,
                args=arguments,
                status="error",
                error=str(exc),
                meta={"simulated": True},
            )
            raise
        record_tool_call(
            name=name, args=arguments, result=value, meta={"simulated": True}
        )
        return value

    def save_draft(self, text: str) -> dict:
        self.drafts.append(text)
        return {"draft_id": "draft-001", "status": "awaiting_review"}

    def create_followup(self) -> dict:
        self.tasks.append("review-draft")
        return {"task": "review-draft", "status": "pending"}


def validate_lead(lead: dict) -> None:
    if not isinstance(lead.get("email"), str) or not lead["email"].endswith(
        "@example.invalid"
    ):
        raise ValueError("Use only synthetic @example.invalid contact addresses")
    if type(lead.get("seats")) is not int or not 1 <= lead["seats"] <= 100:
        raise ValueError("seats must be an integer between 1 and 100")
    if (
        type(lead.get("monthly_budget_usd")) is not int
        or lead["monthly_budget_usd"] < 0
    ):
        raise ValueError("monthly_budget_usd must be a non-negative integer")
    if type(lead.get("consent")) is not bool or lead.get("need") != "shared inbox":
        raise ValueError(
            "Use a boolean consent value and the shared inbox fixture need"
        )
    if not all(
        isinstance(lead.get(key), str) and lead[key] for key in ("id", "company")
    ):
        raise ValueError("id and company must be non-empty strings")


def run_sales_agent(lead: dict, scenario: str = "good") -> SalesResult:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")
    validate_lead(lead)
    result = SalesResult()
    tools = MockTools(lead, result)
    with traced_run(name="sales-assistant-v1", stop_on_loop=False, max_tool_calls=20):
        contact = tools.call(
            "lookup_contact", {"lead_id": lead["id"]}, lambda: tools.lead
        )
        consent = tools.call(
            "check_consent", {"lead_id": lead["id"]}, lambda: contact["consent"]
        )
        if not consent:
            result.status = "no_consent"
            return result
        qualified = tools.call(
            "qualify_lead",
            {"need": lead["need"], "seats": lead["seats"]},
            lambda: lead["monthly_budget_usd"] >= 20 * lead["seats"],
        )
        if not qualified:
            result.status = "not_qualified"
            return result

        if scenario == "retry_loop":
            for _ in range(8):
                tools.call(
                    "lookup_contact", {"lead_id": lead["id"]}, lambda: tools.lead
                )

        def catalog():
            if scenario == "tool_error":
                raise RuntimeError("Simulated catalog outage")
            return [{"name": "team-inbox", "usd_per_seat": 20}]

        plans = tools.call("list_plans", {"need": lead["need"]}, catalog)
        if scenario == "extra_research":
            tools.call(
                "compare_plans",
                {"plans": [p["name"] for p in plans]},
                lambda: {"recommended": "team-inbox"},
            )
        result.quote_usd = tools.call(
            "calculate_quote",
            {"plan": plans[0]["name"], "seats": lead["seats"]},
            lambda: plans[0]["usd_per_seat"] * lead["seats"],
        )

        closing = (
            "Please review this draft."
            if scenario == "harmless_copy_edit"
            else "A teammate will review this draft."
        )
        result.draft = f"Hello {lead['company']}, your {lead['seats']}-seat shared inbox quote is ${result.quote_usd}/month. {closing}"
        record_llm_call(
            model="simulated-drafter-v1",
            prompt={
                "task": "Draft an offer for human review",
                "quote_usd": result.quote_usd,
            },
            response=result.draft,
            usage={
                "prompt_tokens": 48,
                "completion_tokens": 1024 if scenario == "token_spike" else 32,
            },
            meta={"simulated": True, "usage_is_fixture_data": True},
            stop_reason="stop",
        )
        tools.call(
            "save_draft",
            {"lead_id": lead["id"], "text": result.draft},
            lambda: tools.save_draft(result.draft),
        )
        if scenario != "missing_followup":
            task = tools.call(
                "create_followup", {"lead_id": lead["id"]}, tools.create_followup
            )
            result.followup = task["task"]
        if scenario == "unreviewed_send":
            # A forbidden *simulated* call: no delivery implementation exists.
            tools.call(
                "send_email",
                {"draft_id": "draft-001"},
                lambda: {"delivered": False, "simulated": True},
            )
        result.status = "ready_for_review"
    return result
