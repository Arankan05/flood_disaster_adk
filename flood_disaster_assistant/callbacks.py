"""Agent callbacks that gate workflow stages on the recorded intake result.

A SequentialAgent always runs every child, so later stages check the state
written by ``record_request_details`` and skip themselves when intake is not
COMPLETE (the intake agent has already asked its one focused question or
reported the not-found result). Parallel branches also skip when the user
did not ask for that kind of information.
"""

from __future__ import annotations

from typing import Optional

from google.adk.agents.callback_context import CallbackContext
from google.genai import types

from .tools import INCIDENT_REQUESTS, RELIEF_REQUESTS

# Branch agent -> state key its output is stored under.
_BRANCH_OUTPUT_KEYS = {
    "incident_lookup_agent": "incident_result",
    "safety_guidance_agent": "guidance_result",
    "relief_lookup_agent": "relief_result",
}


def _skip(callback_context: CallbackContext, reason: str) -> types.Content:
  output_key = _BRANCH_OUTPUT_KEYS.get(callback_context.agent_name)
  if output_key:
    callback_context.state[output_key] = f"SKIPPED: {reason}"
  # An empty model turn ends this agent without calling the model and is
  # ignored when later agents build their LLM history.
  return types.Content(role="model", parts=[])


def workflow_gate(callback_context: CallbackContext) -> Optional[types.Content]:
  """Skips a workflow stage when its inputs are not available."""
  state = callback_context.state
  if state.get("intake_status") != "COMPLETE":
    return _skip(callback_context, "intake is not complete")

  name = callback_context.agent_name
  request_type = state.get("request_type", "")
  danger = bool(state.get("immediate_danger"))
  area = state.get("area", "")

  if name == "incident_lookup_agent":
    if not area or not state.get("incident_type"):
      return _skip(callback_context, "no area and incident type to look up")
    if request_type not in INCIDENT_REQUESTS and not danger:
      return _skip(callback_context, "incident status was not requested")
  if name == "relief_lookup_agent":
    if not area:
      return _skip(callback_context, "no area to look up")
    if request_type not in RELIEF_REQUESTS:
      return _skip(callback_context, "relief information was not requested")
  return None
