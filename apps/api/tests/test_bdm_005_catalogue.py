"""bdm-005 -- the MoU status catalogue (spec §4; AC5) and the D28 signed stage per type."""

from app.bdm_stages import MANUAL, MOU_SIGNED_STAGE, PIPELINES
from app.models import BDM_MOU_SETTABLE, BDM_MOU_STATUS_LABELS, BDM_MOU_STATUSES

SOURCE = ["Prospect", "Discussion Started", "Proposal Sent", "Under Negotiation", "Draft Shared", "Signed", "Active", "Expired", "Rejected"]


def test_the_status_list_matches_the_source_exactly_and_in_order():
    assert [BDM_MOU_STATUS_LABELS[k] for k in BDM_MOU_STATUSES] == SOURCE
    assert list(BDM_MOU_STATUS_LABELS) == list(BDM_MOU_STATUSES)


def test_expired_is_derived_never_settable():
    assert BDM_MOU_SETTABLE == tuple(k for k in BDM_MOU_STATUSES if k != "expired")


def test_signed_stage_is_a_manual_stage_of_each_pipeline():
    assert set(MOU_SIGNED_STAGE) == {"agent", "school", "college"}
    for bdm_type, key in MOU_SIGNED_STAGE.items():
        assert any(s.key == key and s.kind == MANUAL for s in PIPELINES[bdm_type])
    assert MOU_SIGNED_STAGE == {"agent": "agreement_signed", "school": "signed", "college": "mou_signed"}
