// ccrm-040 (DEC-SCOPE-276 CN1-CN5, API_CONTRACT.md §12GC): the overseas student's own data-processing and document-sharing consents.

export type MyConsent = { id: string; kind: string; title: string; body: string; version: string; accepted_at: string | null };

export const MY_CONSENTS_URL = "/api/v1/overseas/me/consents";
export const acceptConsentUrl = (id: string) => `${MY_CONSENTS_URL}/${encodeURIComponent(id)}/accept`;
