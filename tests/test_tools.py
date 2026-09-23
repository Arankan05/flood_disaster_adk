"""Deterministic tests for the Function tools (no model or API key needed)."""

from types import SimpleNamespace

from flood_disaster_assistant import tools


class FakeToolContext:
  def __init__(self, state=None):
    self.state = dict(state or {})
    self.actions = SimpleNamespace(escalate=False)


def intake(**kwargs):
  ctx = FakeToolContext()
  return tools.record_request_details(tool_context=ctx, **kwargs), ctx


def test_intake_asks_for_missing_area():
  result, ctx = intake(request_type="incident_status")
  assert result["intake_status"] == "NEEDS_INPUT"
  assert result["missing_field"] == "area"
  assert ctx.actions.escalate


def test_intake_asks_one_question_for_incident_type():
  result, _ = intake(request_type="incident_status", area="colombo")
  assert result["missing_field"] == "incident_type"
  assert "blocked_route or flood" in result["question"]
  assert result["area"] == "Colombo"


def test_intake_derives_incident_type_from_description():
  result, ctx = intake(request_type="problem_report", area="Ratnapura",
                       problem_description="The river rising near our road")
  assert result["intake_status"] == "COMPLETE"
  assert ctx.state["incident_type"] == "flood"


def test_intake_immediate_danger_skips_questions():
  result, _ = intake(request_type="problem_report",
                     problem_description="My neighbour is trapped after a collapsed structure")
  assert result["intake_status"] == "COMPLETE"
  assert result["immediate_danger"] is True


def test_intake_unsupported_area_not_found():
  result, _ = intake(request_type="relief_point", area="Galle")
  assert result["intake_status"] == "NOT_FOUND"


def test_intake_retry_is_bounded():
  ctx = FakeToolContext()
  first = tools.record_request_details(request_type="weather", tool_context=ctx)
  assert first["intake_status"] == "RETRY" and not ctx.actions.escalate
  second = tools.record_request_details(request_type="weather", tool_context=ctx)
  assert second["intake_status"] == "NEEDS_INPUT" and ctx.actions.escalate


def test_intake_asks_for_assistance_type():
  result, _ = intake(request_type="relief_point", area="Kegalle")
  assert result["missing_field"] == "assistance_type"


def test_classify_precedence_immediate_danger():
  result = tools.classify_issue("active landslide and a person trapped")
  assert result["category"] == "immediate_danger"
  assert result["priority"] == "critical"
  assert result["source_id"] == "DR-005"


def test_classify_from_incident_type():
  result = tools.classify_issue("", "blocked_route")
  assert result["rule_id"] == "DR-R004"


def test_classify_not_found():
  assert tools.classify_issue("power cut")["status"] == "NOT_FOUND"


def test_lookup_incident():
  result = tools.lookup_incident_status("KEGALLE", "landslide")
  assert result["incident"]["incident_id"] == "INC-005"
  assert result["incident"]["data_status"] == "SUPPLIED-RECORD"


def test_lookup_incident_needs_clarification_and_not_found():
  assert tools.lookup_incident_status("Colombo")["status"] == "NEEDS_CLARIFICATION"
  assert tools.lookup_incident_status("Colombo", "landslide")["status"] == "NOT_FOUND"
  assert tools.lookup_incident_status("Galle", "flood")["status"] == "NOT_FOUND"


def test_safety_guidance():
  assert tools.get_safety_guidance("flood", "critical")["guidance"][0]["guidance_id"] == "SG-002"
  assert tools.get_safety_guidance("immediate_danger", "critical")["guidance"][0]["guidance_id"] == "SG-005"
  assert tools.get_safety_guidance("earthquake")["status"] == "NOT_FOUND"


def test_relief_points():
  assert tools.find_relief_point("Ratnapura", "food")["relief_point"]["relief_id"] == "RP-004"
  assert tools.find_relief_point("colombo", "shelter")["relief_point"]["relief_id"] == "RP-001"
  assert tools.find_relief_point("Ratnapura", "drinking water")["status"] == "NEEDS_CLARIFICATION"
  assert tools.find_relief_point("Colombo", "first aid")["status"] == "NOT_FOUND"


def test_source_details():
  result = tools.get_source_details("DR-001, DR-005, DR-004")
  assert [s["source_id"] for s in result["sources"]] == ["DR-001", "DR-005"]
  assert result["not_found"] == ["DR-004"]
