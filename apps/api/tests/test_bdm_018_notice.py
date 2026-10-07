"""bdm-018 -- the BDM's outcome notice wording (H7; QA18-03: the School usually carries the organization's name)."""

from app.models import BdmOnboardingRequest, BdmOrganization, School
from app.services.bdm_onboarding import outcome_notice

ORG = BdmOrganization(code="ORG-000001", name="St Mary", bdm_type="school")  # bdm-019: the rejection title follows the type


def test_a_school_with_the_organizations_name_is_not_named_twice():
    title, body = outcome_notice(ORG, BdmOnboardingRequest(), School(name="St Mary", school_code="AB12CD34"))
    assert (title, body) == ("School onboarded", "ORG-000001 · St Mary is now onboarded (School ID AB12CD34).")


def test_a_differently_named_school_is_named():
    _, body = outcome_notice(ORG, BdmOnboardingRequest(), School(name="St Mary Senior Secondary", school_code="AB12CD34"))
    assert body == "ORG-000001 · St Mary is now onboarded as St Mary Senior Secondary (School ID AB12CD34)."


def test_a_rejection_carries_the_reason():
    assert outcome_notice(ORG, BdmOnboardingRequest(reject_reason="Board missing"), None) == ("School onboarding not approved", "ORG-000001 · St Mary: Board missing")
