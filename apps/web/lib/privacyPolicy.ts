// PUB-026 (DEC-SCOPE-442): the facts the public privacy policy (/privacy) depends on.
// Everything here that is `null` has not been confirmed by EduSphere yet; the page shows it as a visible
// "to be confirmed" note rather than a guess, and `PENDING_FACTS` lists what is still open. Do not link the page from
// an ad or a lead form until `PENDING_FACTS` is empty.

export type PolicyFact = { label: string; value: string | null };

export const POLICY_FACTS = {
  /** The registered legal entity (data fiduciary under India's DPDP Act 2023; controller under UK GDPR). */
  legalEntity: { label: "Registered legal name and registered address", value: null },
  /** Where privacy requests and complaints go (DPDP s.8(9) / s.13: a published contact for questions and grievances). */
  privacyContact: { label: "Privacy contact email address", value: null },
  /** Named grievance officer or data protection contact, if EduSphere appoints one. */
  grievanceOfficer: { label: "Grievance officer name", value: null },
  /** How long enquiry and lead records are kept (PRD_OPEN_ITEMS item 15: exact retention periods remain open). */
  leadRetention: { label: "Retention period for enquiries and leads that do not become students", value: null },
  /** UK GDPR Art. 27: a non-UK organisation targeting people in the UK may need a UK representative. */
  ukRepresentative: { label: "UK representative (if required)", value: null },
} satisfies Record<string, PolicyFact>;

export const PENDING_FACTS: PolicyFact[] = Object.values(POLICY_FACTS).filter((fact) => fact.value === null);

/** The date the policy text last changed; update it with every change to the page. */
export const POLICY_UPDATED = "16 November 2026";
