"""WRA organisational units (branches) as the stakeholder model names them (FCC stakeholder–system model, 5 Oct 2026).

Names come from WRA's own Departments page, not from the bid's earlier
placeholder names. Each unit records whether it is an *operating* branch (owns
data and approves in the workflow) and which modules it primarily uses; every
unit except HR / Office Services has one Super User (Work Plan A12).
"""
from __future__ import annotations

#: code, name, division, is_operating, primary modules, has_super_user, owns (plain text)
WRA_UNITS = [
    ("RMU", "Resource Monitoring Unit", "Technical Services Division", True, ["submissions"], True,
     "Wells, stations, water levels, water quality, streamflow, pump tests"),
    ("PLU", "Permits & Licences Unit", "Technical Services Division", True, ["licensing"], True,
     "Licence applications, licences, abstraction returns, well-drilling permits"),
    ("PIU", "Planning & Investigation Unit", "Technical Services Division", True, ["dashboards"], True,
     "Basins, WMUs, aquifers; Water Resources Master Plan; project impact assessment; primary BI consumer"),
    ("CGU", "Computer & GIS Unit", "Technical Services Division", False, ["admin"], True,
     "Hosts and operates the system after handover; networks, databases, GIS, ArcGIS Enterprise, DR/backup. Super User = system administrator"),
    ("FAD", "Finance & Accounts Division", "Finance & Accounts Division", False, ["exports"], True,
     "Volume-based fee calculation (out of scope); consumes the licence/abstraction export via API/CSV"),
    ("IDU", "Information & Documentation Unit", "Administration & Human Resources Division", False, ["public"], True,
     "Public awareness, research support, DSpace document custodian, public repository content"),
    ("HRU", "Human Resources", "Administration & Human Resources Division", False, [], False, "Training logistics and staff availability; no system role"),
    ("OSU", "Office Services", "Administration & Human Resources Division", False, [], False, "Facilities; no system role"),
    ("MDO", "Managing Director's Office", "Executive", False, ["dashboards"], False,
     "Executive sponsor; chairs the Steering Committee; accepts milestones on the ICT Manager's advice"),
]
