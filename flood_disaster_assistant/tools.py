"""Function tools for the Flood, Landslide and Disaster Recovery Assistant.

Every tool reads only the supplied data pack in ``data_pack/``. Tools never
invent values: when a record is missing they return a NOT_FOUND result, and
when a request cannot be resolved from the supplied values they return a
NEEDS_CLARIFICATION / NEEDS_INPUT result naming exactly one missing field.

Each returned record keeps its original ``source_id``, ``effective_date`` and
``data_status`` values so the response agent can cite them.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Optional

from google.adk.tools.tool_context import ToolContext

DATA_DIR = Path(__file__).resolve().parent / "data_pack"

SUPPORTED_AREAS = ("Colombo", "Ratnapura", "Kegalle")
INCIDENT_TYPES = ("flood", "landslide", "blocked_route")
REQUEST_TYPES = (
    "incident_status",
    "safety_guidance",
    "relief_point",
    "incident_and_relief",
    "problem_report",
)
INCIDENT_REQUESTS = (
    "incident_status",
    "safety_guidance",
    "incident_and_relief",
    "problem_report",
)
RELIEF_REQUESTS = ("relief_point", "incident_and_relief")
MAX_INTAKE_ATTEMPTS = 2

# User wording that names an assistance type directly. Anything else is
# matched against the ``services`` column of relief_points.csv.
ASSISTANCE_SYNONYMS = {
    "temporary_shelter": ("shelter", "temporary shelter", "relief centre", "relief center"),
    "information_point": ("information point", "information", "assistance point", "info point"),
    "relief_supplies": ("relief supplies", "supplies"),
    "first_aid_information": ("first aid", "first-aid", "first aid information"),
}


# --------------------------------------------------------------------------
# Data-pack helpers
# --------------------------------------------------------------------------


def _read_csv(name: str) -> list[dict]:
  with open(DATA_DIR / name, newline="", encoding="utf-8") as f:
    return [dict(row) for row in csv.DictReader(f)]


def _norm(value: Optional[str]) -> str:
  """Lower-cases and collapses separators so comparisons are case-insensitive."""
  return re.sub(r"[\s_\-]+", " ", (value or "").strip().lower())


def _match_area(area: Optional[str]) -> Optional[str]:
  """Returns the supplied spelling of a supported area, or None."""
  wanted = _norm(area)
  for supported in SUPPORTED_AREAS:
    if _norm(supported) == wanted:
      return supported
  return None


def _split_pipe(value: str) -> list[str]:
  return [part.strip() for part in value.split("|") if part.strip()]


def _match_rules(text: str) -> list[dict]:
  """Returns every issue rule whose keywords appear in ``text`` (file order)."""
  lowered = _norm(text)
  matches = []
  for rule in _read_csv("issue_rules.csv"):
    hits = [kw for kw in _split_pipe(rule["keywords"]) if _norm(kw) in lowered]
    if hits:
      matches.append({**rule, "matched_keywords": hits})
  return matches


def _normalise_incident_type(value: Optional[str]) -> Optional[str]:
  """Maps user wording to a supplied incident type, or None."""
  wanted = _norm(value)
  if not wanted:
    return None
  for incident_type in INCIDENT_TYPES:
    if _norm(incident_type) == wanted:
      return incident_type
  for rule in _match_rules(wanted):
    if rule["category"] in INCIDENT_TYPES:
      return rule["category"]
  return None


def _match_assistance(area: str, assistance_type: Optional[str]) -> list[dict]:
  """Relief rows in ``area`` that match the user's assistance wording."""
  wanted = _norm(assistance_type)
  rows = [r for r in _read_csv("relief_points.csv") if r["area"] == area]
  if not wanted:
    return rows
  exact = [r for r in rows if _norm(r["assistance_type"]) == wanted]
  if exact:
    return exact
  for canonical, words in ASSISTANCE_SYNONYMS.items():
    if wanted in (_norm(w) for w in words):
      return [r for r in rows if r["assistance_type"] == canonical]
  return [
      r for r in rows
      if any(wanted in _norm(s) or _norm(s) in wanted for s in _split_pipe(r["services"]))
  ]


def _source_fields(row: dict) -> dict:
  return {
      "source_id": row["source_id"],
      "effective_date": row["effective_date"],
      "data_status": row["data_status"],
  }


# --------------------------------------------------------------------------
# Tool 1 - intake validation (owned by intake_agent inside the Loop agent)
# --------------------------------------------------------------------------


def record_request_details(
    request_type: str,
    area: str = "",
    incident_type: str = "",
    assistance_type: str = "",
    problem_description: str = "",
    tool_context: ToolContext = None,
) -> dict:
  """Validates the user's request details and records them in session state.

  Args:
    request_type: One of incident_status, safety_guidance, relief_point,
      incident_and_relief, problem_report.
    area: The area named by the user (Colombo, Ratnapura or Kegalle).
    incident_type: flood, landslide or blocked_route when the user named one.
    assistance_type: The kind of help wanted (for example shelter, relief
      supplies, information point, first aid) when the user named one.
    problem_description: The user's own short description of the problem.

  Returns:
    A dict with intake_status COMPLETE, NEEDS_INPUT, NOT_FOUND or RETRY. For
    NEEDS_INPUT it names exactly one missing_field and one focused question.
  """
  state = tool_context.state if tool_context else {}
  attempts = int(state.get("intake_attempts", 0)) + 1
  state["intake_attempts"] = attempts

  def finish(result: dict) -> dict:
    """Stores the result and stops the Loop agent unless a retry is allowed."""
    status = result["intake_status"]
    if status == "RETRY" and attempts >= MAX_INTAKE_ATTEMPTS:
      result = {
          "intake_status": "NEEDS_INPUT",
          "missing_field": "request_type",
          "question": (
              "Do you want incident status, safety guidance, a relief point, "
              "or incident and relief information together?"
          ),
      }
      status = "NEEDS_INPUT"
    for key, value in result.items():
      state[key] = value
    if tool_context and status != "RETRY":
      tool_context.actions.escalate = True  # exits intake_loop
      state["intake_attempts"] = 0
    return result

  # Fresh request: clear values left over from a previous turn.
  for key in ("missing_field", "question", "not_found_reason"):
    state[key] = ""
  state["immediate_danger"] = False

  request_type = _norm(request_type).replace(" ", "_")
  if request_type not in REQUEST_TYPES:
    return finish({
        "intake_status": "RETRY",
        "reason": f"request_type must be one of {', '.join(REQUEST_TYPES)}.",
    })

  base = {
      "request_type": request_type,
      "area": "",
      "incident_type": "",
      "assistance_type": "",
      "problem_description": problem_description.strip(),
  }

  # Immediate danger is answered first, without asking for more details.
  danger = [r for r in _match_rules(problem_description) if r["category"] == "immediate_danger"]
  matched_area = _match_area(area)
  if danger:
    return finish({
        **base,
        "intake_status": "COMPLETE",
        "immediate_danger": True,
        "area": matched_area or "",
        "incident_type": _normalise_incident_type(incident_type)
        or _normalise_incident_type(problem_description) or "",
    })

  needs_incident = request_type in INCIDENT_REQUESTS
  needs_relief = request_type in RELIEF_REQUESTS
  area_required = request_type != "safety_guidance"

  if area.strip() and not matched_area:
    return finish({
        **base,
        "intake_status": "NOT_FOUND",
        "area": area.strip(),
        "not_found_reason": (
            f"No supplied records exist for area '{area.strip()}'. Supported "
            f"areas are {', '.join(SUPPORTED_AREAS)}."
        ),
    })
  if area_required and not matched_area:
    return finish({
        **base,
        "intake_status": "NEEDS_INPUT",
        "missing_field": "area",
        "question": "Which area are you asking about: Colombo, Ratnapura, or Kegalle?",
    })
  base["area"] = matched_area or ""

  if needs_incident:
    resolved = _normalise_incident_type(incident_type) or _normalise_incident_type(
        problem_description
    )
    if incident_type.strip() and not resolved:
      return finish({
          **base,
          "intake_status": "NOT_FOUND",
          "incident_type": incident_type.strip(),
          "not_found_reason": (
              f"'{incident_type.strip()}' is not a supported incident type. "
              f"Supported types are {', '.join(INCIDENT_TYPES)}."
          ),
      })
    if not resolved:
      if matched_area:
        options = sorted({r["incident_type"] for r in _read_csv("incident_status.csv")
                          if r["area"] == matched_area})
      else:
        options = list(INCIDENT_TYPES)
      if len(options) == 1:
        resolved = options[0]
      else:
        where = f" in {matched_area}" if matched_area else ""
        return finish({
            **base,
            "intake_status": "NEEDS_INPUT",
            "missing_field": "incident_type",
            "question": (
                f"Which incident type are you asking about{where}: "
                f"{' or '.join(options)}?"
            ),
        })
    base["incident_type"] = resolved

  if needs_relief:
    rows = _match_assistance(matched_area, assistance_type)
    if assistance_type.strip() and not rows:
      return finish({
          **base,
          "intake_status": "COMPLETE",
          "assistance_type": assistance_type.strip(),
      })  # find_relief_point will report the not-found result.
    if len({r["assistance_type"] for r in rows}) > 1:
      options = sorted({r["assistance_type"] for r in rows})
      return finish({
          **base,
          "intake_status": "NEEDS_INPUT",
          "missing_field": "assistance_type",
          "question": (
              f"Which type of assistance do you need in {matched_area}: "
              f"{' or '.join(o.replace('_', ' ') for o in options)}?"
          ),
      })
    base["assistance_type"] = rows[0]["assistance_type"]

  return finish({**base, "intake_status": "COMPLETE"})


# --------------------------------------------------------------------------
# Tool 2 - classification (owned by issue_classifier_agent)
# --------------------------------------------------------------------------


def classify_issue(
    problem_description: str = "",
    incident_type: str = "",
    request_type: str = "",
    tool_context: ToolContext = None,
) -> dict:
  """Classifies the reported problem with the supplied issue_rules.csv.

  Args:
    problem_description: The user's description of the problem, if any.
    incident_type: The recorded incident type from intake, if any.
    request_type: The request type recorded by intake.

  Returns:
    The matched rule (rule_id, category, priority, recommended_action and
    source fields) or status NOT_FOUND when no rule matches.
  """
  matches = _match_rules(problem_description)
  basis = "problem_description keywords"
  if not matches and incident_type:
    matches = [
        {**r, "matched_keywords": []}
        for r in _read_csv("issue_rules.csv")
        if r["category"] == _normalise_incident_type(incident_type)
    ]
    basis = "incident_type recorded at intake"
  if not matches and _norm(request_type).replace(" ", "_") in RELIEF_REQUESTS:
    matches = [
        {**r, "matched_keywords": []}
        for r in _read_csv("issue_rules.csv")
        if r["category"] == "relief_request"
    ]
    basis = "relief request type recorded at intake"

  if not matches:
    result = {
        "status": "NOT_FOUND",
        "message": "No supplied classification rule matches this description.",
    }
  else:
    rule = matches[0]  # issue_rules.csv is ordered by precedence
    result = {
        "status": "FOUND",
        "rule_id": rule["rule_id"],
        "category": rule["category"],
        "priority": rule["priority"],
        "recommended_action": rule["recommended_action"],
        "matched_keywords": rule["matched_keywords"],
        "match_basis": basis,
        "other_matched_categories": [m["category"] for m in matches[1:]],
        **_source_fields(rule),
    }
  if tool_context:
    tool_context.state["classification"] = result
  return result


# --------------------------------------------------------------------------
# Tool 3 - incident status (owned by incident_lookup_agent)
# --------------------------------------------------------------------------


def lookup_incident_status(area: str, incident_type: str = "") -> dict:
  """Returns the recorded incident for an area and incident type.

  Args:
    area: Colombo, Ratnapura or Kegalle (case-insensitive).
    incident_type: flood, landslide or blocked_route.

  Returns:
    FOUND with the incident record, NEEDS_CLARIFICATION with the recorded
    incident types when the area has several, or NOT_FOUND.
  """
  matched_area = _match_area(area)
  if not matched_area:
    return {
        "status": "NOT_FOUND",
        "message": f"No supplied incident records exist for area '{area}'.",
        "supported_areas": list(SUPPORTED_AREAS),
    }
  rows = [r for r in _read_csv("incident_status.csv") if r["area"] == matched_area]
  if not incident_type.strip():
    if len(rows) == 1:
      return {"status": "FOUND", "incident": rows[0]}
    return {
        "status": "NEEDS_CLARIFICATION",
        "missing_field": "incident_type",
        "area": matched_area,
        "recorded_incident_types": [r["incident_type"] for r in rows],
    }
  wanted = _normalise_incident_type(incident_type)
  found = [r for r in rows if r["incident_type"] == wanted]
  if not found:
    return {
        "status": "NOT_FOUND",
        "message": (
            f"No supplied {incident_type} incident record exists for {matched_area}."
        ),
        "recorded_incident_types": [r["incident_type"] for r in rows],
    }
  return {"status": "FOUND", "incident": found[0]}


# --------------------------------------------------------------------------
# Tool 4 - safety guidance (owned by safety_guidance_agent)
# --------------------------------------------------------------------------


def get_safety_guidance(incident_type: str, priority: str = "") -> dict:
  """Returns recorded safety guidance for an incident type and priority.

  Args:
    incident_type: flood, landslide, blocked_route, immediate_danger or
      relief_request (the classification category).
    priority: normal, high, urgent or critical (from classification).

  Returns:
    FOUND with the guidance row(s), or NOT_FOUND.
  """
  wanted = _norm(incident_type).replace(" ", "_")
  rows = [r for r in _read_csv("safety_guidance.csv") if r["incident_type"] == wanted]
  if not rows:
    return {
        "status": "NOT_FOUND",
        "message": f"No supplied safety guidance exists for '{incident_type}'.",
    }
  exact = [r for r in rows if r["priority"] == _norm(priority)]
  if exact:
    return {"status": "FOUND", "guidance": exact}
  return {
      "status": "FOUND",
      "guidance": rows,
      "note": (
          f"No guidance is recorded for priority '{priority}'; all recorded "
          f"guidance for {wanted} is returned."
      ),
  }


# --------------------------------------------------------------------------
# Tool 5 - relief points (owned by relief_lookup_agent)
# --------------------------------------------------------------------------


def find_relief_point(area: str, assistance_type: str = "") -> dict:
  """Returns the listed relief point for an area and assistance type.

  Args:
    area: Colombo, Ratnapura or Kegalle (case-insensitive).
    assistance_type: temporary_shelter, information_point, relief_supplies,
      first_aid_information, or wording such as shelter, food or first aid.

  Returns:
    FOUND with the relief point, NEEDS_CLARIFICATION with the listed
    assistance types when more than one matches, or NOT_FOUND.
  """
  matched_area = _match_area(area)
  if not matched_area:
    return {
        "status": "NOT_FOUND",
        "message": f"No supplied relief points are listed for area '{area}'.",
        "supported_areas": list(SUPPORTED_AREAS),
    }
  listed = sorted({r["assistance_type"] for r in _read_csv("relief_points.csv")
                   if r["area"] == matched_area})
  rows = _match_assistance(matched_area, assistance_type)
  if not rows:
    return {
        "status": "NOT_FOUND",
        "message": (
            f"No listed relief point in {matched_area} matches '{assistance_type}'."
        ),
        "listed_assistance_types": listed,
    }
  if len(rows) > 1:
    return {
        "status": "NEEDS_CLARIFICATION",
        "missing_field": "assistance_type",
        "area": matched_area,
        "listed_assistance_types": sorted({r["assistance_type"] for r in rows}),
    }
  return {"status": "FOUND", "relief_point": rows[0]}


# --------------------------------------------------------------------------
# Tool 6 - source register (owned by response_agent)
# --------------------------------------------------------------------------


def get_source_details(source_ids: str) -> dict:
  """Looks up source IDs in source_register.md.

  Args:
    source_ids: Comma-separated source IDs, for example "DR-001,DR-002".

  Returns:
    The register entry for each ID, and a list of IDs that are not found.
  """
  register = {}
  text = (DATA_DIR / "source_register.md").read_text(encoding="utf-8")
  for line in text.splitlines():
    cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
    if len(cells) == 5 and re.fullmatch(r"DR-\d+", cells[0]):
      register[cells[0]] = {
          "source_id": cells[0],
          "record_group": cells[1],
          "description": cells[2],
          "effective_date": cells[3],
          "data_status": cells[4],
      }
  wanted = [s.strip().upper() for s in re.split(r"[,\s]+", source_ids) if s.strip()]
  return {
      "sources": [register[s] for s in wanted if s in register],
      "not_found": [s for s in wanted if s not in register],
      "note": (
          "The effective date identifies the dataset version. It is not a "
          "promise that an incident, route, service, or location is currently "
          "unchanged."
      ),
  }
