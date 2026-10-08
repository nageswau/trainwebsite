"""upc-007 -- the partnership stage catalogue and its fixed groupings (spec PS1, PS3; AC2). Pure: no database."""

import re

from app.partnership_stages import COLUMN_LABELS, COLUMNS, FIRST_STAGE, GROUPS, PROBABILITY, STAGE_KEYS, STAGES, column_of, label_of

# EVID-020 §3 (L98-L154) and §4 (L164-L172), in source order and wording.
SOURCE_STAGES = [
    "Target University",
    "Researching",
    "Contact Identified",
    "Initial Contact",
    "Interested",
    "Meeting Scheduled",
    "Meeting Completed",
    "Proposal Sent",
    "Commercial Discussion",
    "Documents Shared",
    "Agreement Under Review",
    "Agreement Signed",
    "Partner Activated",
    "Student Recruitment Started",
    "Active Partner",
]
SOURCE_COLUMNS = ["Target", "Contacted", "Interested", "Meeting Scheduled", "Proposal Sent", "Negotiation", "Agreement Pending", "Signed", "Active Partners"]
# Appendix B "Stage groupings": stored stage -> (K column label, G group, P probability).
APPENDIX_B = {
    "Target University": ("Target", "target", 10),
    "Researching": ("Target", "target", 10),
    "Contact Identified": ("Target", "target", 10),
    "Initial Contact": ("Contacted", "in_progress", 25),
    "Interested": ("Interested", "in_progress", 40),
    "Meeting Scheduled": ("Meeting Scheduled", "in_progress", 40),
    "Meeting Completed": ("Meeting Scheduled", "in_progress", 60),
    "Proposal Sent": ("Proposal Sent", "in_progress", 75),
    "Commercial Discussion": ("Negotiation", "in_progress", 75),
    "Documents Shared": ("Negotiation", "in_progress", 75),
    "Agreement Under Review": ("Agreement Pending", "in_progress", 90),
    "Agreement Signed": ("Signed", "in_progress", 100),
    "Partner Activated": ("Signed", "partner", 100),
    "Student Recruitment Started": ("Active Partners", "partner", 100),
    "Active Partner": ("Active Partners", "partner", 100),
}


def test_stages_match_the_source_in_order():
    assert [s.label for s in STAGES] == SOURCE_STAGES
    assert STAGE_KEYS == tuple(s.key for s in STAGES)
    assert len(set(STAGE_KEYS)) == 15 and all(re.fullmatch(r"[a-z_]{1,40}", k) for k in STAGE_KEYS)
    assert FIRST_STAGE == STAGE_KEYS[0] == "target_university"


def test_columns_match_the_source_kanban_in_order():
    assert [COLUMN_LABELS[c] for c in COLUMNS] == SOURCE_COLUMNS
    assert len(COLUMNS) == 9


def test_groupings_equal_appendix_b():
    for stage in STAGES:
        column, group, probability = APPENDIX_B[stage.label]
        assert COLUMN_LABELS[column_of(stage.key)] == column, stage.label
        assert GROUPS[stage.key] == group, stage.label
        assert PROBABILITY[stage.key] == probability, stage.label


def test_columns_follow_stage_order_and_every_column_is_used():
    order = [COLUMNS.index(column_of(k)) for k in STAGE_KEYS]
    assert order == sorted(order) and set(order) == set(range(9))


def test_label_of_falls_back_to_the_stored_key():
    assert label_of("interested") == "Interested"
    assert label_of("retired_stage") == "retired_stage"
