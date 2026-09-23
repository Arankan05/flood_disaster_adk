# Flood, Landslide and Disaster Recovery Data Pack

This data pack contains supplied records for the Flood, Landslide and Disaster Recovery Assistant assignment. The records cover Colombo, Ratnapura, and Kegalle.

The records are not a live feed and do not represent current government, emergency-service, shelter, road, hospital, police, or weather information. An agent must report only the values returned from these files and must preserve the returned `source_id`, `effective_date`, and `data_status` fields.

## Included records

- `incident_status.csv` contains recorded flood, landslide, and blocked-route incidents.
- `issue_rules.csv` contains deterministic classification and priority rules.
- `safety_guidance.csv` contains recorded guidance associated with supported incident types and priorities.
- `relief_points.csv` contains listed shelters, relief centres, and assistance points.
- `source_register.md` explains the source identifiers used by the supplied records.

## Supported areas

- Colombo
- Ratnapura
- Kegalle

Area and alias comparisons may be case-insensitive, but the original supplied value should be preserved in user-visible results. A missing record must return a clear not-found result. The assistant must not invent a replacement area, incident, shelter, guidance item, source value, or case identifier.

## Immediate-danger boundary

Descriptions involving a trapped person, serious injury, a collapsed structure, rising water inside an occupied building, or an active landslide require an immediate safety warning. The records do not provide emergency dispatch. The assistant must advise the user to move away from immediate danger when possible and contact the relevant local emergency service or authority.
