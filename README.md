# Flood, Landslide and Disaster Recovery Assistant (Google ADK)

INTE 22303 Assignment 2. An ADK Web Builder (Agent Config YAML) project that
answers questions about the supplied disaster-recovery records for Colombo,
Ratnapura and Kegalle. The supplied data pack is the only source of truth.

## Agent tree

```
disaster_recovery_coordinator      LlmAgent (root)
└── assistance_pipeline            SequentialAgent
    ├── intake_loop                LoopAgent (max_iterations: 2)
    │   └── intake_agent           LlmAgent  -> record_request_details
    ├── issue_classifier_agent     LlmAgent  -> classify_issue
    ├── parallel_lookup            ParallelAgent
    │   ├── incident_lookup_agent  LlmAgent  -> lookup_incident_status
    │   ├── safety_guidance_agent  LlmAgent  -> get_safety_guidance
    │   └── relief_lookup_agent    LlmAgent  -> find_relief_point
    └── response_agent             LlmAgent  -> get_source_details
```

- `flood_disaster_assistant/*.yaml` - agent configs (one per agent)
- `flood_disaster_assistant/tools.py` - the six Python Function tools
- `flood_disaster_assistant/callbacks.py` - `workflow_gate`, which skips later
  stages when intake is incomplete or a branch was not requested
- `flood_disaster_assistant/data_pack/` - the supplied records

## Run

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example flood_disaster_assistant/.env   # then add your own API key
adk web          # run from this folder, then pick flood_disaster_assistant
```

Tool tests (no API key needed): `pip install pytest && python -m pytest -q tests`

Do not submit `.env`, the virtual environment, or any API key.
