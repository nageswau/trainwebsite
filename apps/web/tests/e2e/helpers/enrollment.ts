import { expect, type APIRequestContext } from "@playwright/test";

// ccrm-027 (DEC-SCOPE-262, E3): `enrolled` is reached only through the enrolment confirmation. For specs that need an enrolled
// application as setup: as the signed-in Overseas Admin, move it to Offer, upload an enrolment confirmation and confirm.
export async function confirmEnrollment(request: APIRequestContext, applicationId: string) {
  const url = `/api/v1/workflows/overseas/applications/${applicationId}`;
  const moved = await request.patch(url, { data: { status: "offer" } });
  expect(moved.ok(), await moved.text()).toBeTruthy();
  const uploaded = await request.post(`${url}/enrollment-documents`, {
    multipart: { file: { name: "confirmation.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF\n") } },
  });
  expect(uploaded.ok(), await uploaded.text()).toBeTruthy();
  const confirmed = await request.put(`${url}/enrollment`, {
    data: {
      expected_status: "offer",
      enrollment_date: new Date().toISOString().slice(0, 10),
      enrollment_document_id: (await uploaded.json()).document.id,
      pre_enrollment_checklist_complete: true,
    },
  });
  expect(confirmed.ok(), await confirmed.text()).toBeTruthy();
}
