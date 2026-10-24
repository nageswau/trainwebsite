"""ccrm-025 -- the request bodies: the offer decision and the manual deposit record, and the `_not_future` shadowing fix (ccrm-007 had
redefined it with two arguments, so every three-argument caller -- offers, agency applications, deposit remit/refund -- raised a TypeError)."""

from datetime import date, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas import AgentApplicationUpdate, ApplicationOfferCreate, DepositRecordSave, DepositRemit, OfferDecisionSet, StudentEnglishTestIn

FUTURE = (date.today() + timedelta(days=5)).isoformat()


def test_the_offer_and_deposit_date_rules_answer_422_not_a_type_error():
    with pytest.raises(ValidationError, match="Issue date cannot be in the future"):
        ApplicationOfferCreate(offer_type="other", issue_date=FUTURE, offer_document_id=uuid4())
    with pytest.raises(ValidationError, match="Submission date cannot be in the future"):
        AgentApplicationUpdate(submitted_on=FUTURE)
    with pytest.raises(ValidationError, match="The date cannot be in the future"):
        DepositRemit(remitted_on=FUTURE, reference="UTR-1")


def test_the_profile_rule_still_refuses_a_future_test_date():
    with pytest.raises(ValidationError):
        StudentEnglishTestIn(test_type="IELTS", status="taken", test_date=FUTURE)


def test_a_decision_is_accepted_or_declined_and_a_decline_needs_a_reason():
    assert OfferDecisionSet(decision="accepted").decision_date is None
    with pytest.raises(ValidationError, match="Give the reason"):
        OfferDecisionSet(decision="declined")
    with pytest.raises(ValidationError):
        OfferDecisionSet(decision="expired")  # only the job expires an offer
    with pytest.raises(ValidationError, match="only with a decline"):
        OfferDecisionSet(decision="accepted", another_offer_preferred=True)
    with pytest.raises(ValidationError, match="cannot be in the future"):
        OfferDecisionSet(decision="accepted", decision_date=FUTURE)


def test_a_deposit_record_needs_its_fields_for_its_status():
    ok = DepositRecordSave(required=True, amount="3000", currency="gbp", due_date="2026-11-30", payment_status="pending")
    assert ok.currency == "GBP"
    assert DepositRecordSave(required=False, payment_status="not_required").amount is None
    for bad, message in (
        ({"required": False, "payment_status": "not_required", "amount": "10"}, "no amount"),
        ({"required": True, "payment_status": "not_required", "amount": "10", "currency": "GBP"}, "Choose the payment status"),
        ({"required": True, "payment_status": "pending", "currency": "GBP"}, "Enter the deposit amount"),
        ({"required": True, "payment_status": "pending", "amount": "10"}, "Choose the currency"),
        ({"required": True, "payment_status": "pending", "amount": "0", "currency": "GBP"}, "greater than 0"),
        ({"required": True, "payment_status": "paid_to_university", "amount": "10", "currency": "GBP"}, "Enter the date it was paid"),
        ({"required": True, "payment_status": "pending", "amount": "10", "currency": "GBP", "paid_on": "2026-10-01"}, "only for a paid deposit"),
        ({"required": True, "payment_status": "paid_via_edusphere", "amount": "10", "currency": "GBP", "paid_on": FUTURE}, "cannot be in the future"),
    ):
        with pytest.raises(ValidationError, match=message):
            DepositRecordSave(**bad)
