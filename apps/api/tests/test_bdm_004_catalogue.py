"""bdm-004 -- the stage catalogues (spec §4, S2, S4; AC1, AC9). Pure: no database."""

import re

from app.bdm_stages import AGENT_STATUS, AGENT_STATUSES, FIRST_STAGE, LIVE, MANUAL, MANUAL_STAGES, PIPELINES, VOLUME

# EVID-016 Agent §E (685-741), School §D (897-951), College §D (1136-1190), in source order and wording.
SOURCE = {
    "agent": [
        "Agent Prospect", "Contacted", "Meeting Scheduled", "Meeting Completed", "Interested", "Proposal / Agreement",
        "Agreement Signed", "Agent Onboarding", "Master Login Created", "Staff Logins Created", "Active Agent", "Students",
        "Applications", "Enrollments",
    ],
    "school": [
        "School Prospect", "Contacted", "Meeting", "Presentation", "Proposal", "Negotiation", "MoU", "Signed", "School Onboarding",
        "Teachers / Parents / Students Created", "Career Guidance", "Psychometric", "Student Profile Building", "University Planning",
    ],
    "college": [
        "College Prospect", "Contacted", "Meeting", "Presentation", "Proposal", "MoU Negotiation", "MoU Signed", "College Activated",
        "Course Promotion", "Student Leads", "Training", "Internship", "Recruitment", "Placement",
    ],
}
KIND_COUNTS = {"agent": (7, 4, 3), "school": (8, 6, 0), "college": (8, 0, 6)}


def test_labels_match_the_source_in_order():
    assert set(PIPELINES) == {"agent", "school", "college"}
    for bdm_type, labels in SOURCE.items():
        assert [s.label for s in PIPELINES[bdm_type]] == labels


def test_kinds_per_type_with_manual_first_then_live_then_volume():
    order = [MANUAL, LIVE, VOLUME]
    for bdm_type, (manual, live, volume) in KIND_COUNTS.items():
        kinds = [s.kind for s in PIPELINES[bdm_type]]
        assert (kinds.count(MANUAL), kinds.count(LIVE), kinds.count(VOLUME)) == (manual, live, volume)
        assert kinds == sorted(kinds, key=order.index)


def test_keys_are_unique_snake_case_and_start_at_prospect():
    for steps in PIPELINES.values():
        keys = [s.key for s in steps]
        assert len(set(keys)) == len(keys) == 14
        assert all(re.fullmatch(r"[a-z_]{1,40}", k) for k in keys)
        assert keys[0] == FIRST_STAGE == "prospect"


def test_manual_stages_are_the_manual_keys_in_order():
    for bdm_type, steps in PIPELINES.items():
        assert MANUAL_STAGES[bdm_type] == tuple(s.key for s in steps if s.kind == MANUAL)
    assert MANUAL_STAGES["college"][-1] == "college_activated"  # S2
    assert MANUAL_STAGES["agent"][-1] == "agreement_signed" and MANUAL_STAGES["school"][-1] == "signed"


def test_agent_status_is_derived_per_s4():
    assert AGENT_STATUSES == ("Prospect", "Contacted", "Meeting", "Interested", "Agreement", "Onboarding", "Active", "Inactive")
    assert AGENT_STATUS == {
        "prospect": "Prospect", "contacted": "Contacted", "meeting_scheduled": "Meeting", "meeting_completed": "Meeting",
        "interested": "Interested", "proposal_agreement": "Agreement", "agreement_signed": "Agreement",
        "agent_onboarding": "Onboarding", "master_login_created": "Onboarding", "staff_logins_created": "Onboarding",
        "active_agent": "Active",
    }
    assert set(AGENT_STATUS.values()) <= set(AGENT_STATUSES)
