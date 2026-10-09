import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityAgreements from "@/components/UniversityAgreements";
import { type Agreement, type AgreementOptions, AGREEMENT_STATUSES, agreementPageHref, dateText, expiryText } from "@/lib/universityAgreements";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const person = { id: "p1", full_name: "Rahul Mehta", active: true };
const agreement = (over: Partial<Agreement> = {}): Agreement => ({
  id: "a1", mou_number: "MOU-000007", university: { id: "u1", name: "ABC", university_code: "UNV-000001" }, agreement_type: "mou", type_label: "MoU",
  status: "draft", effective_status: "draft", status_label: "Draft", days_to_expiry: 1000, start_date: "2026-10-01", expiry_date: "2029-10-01",
  renewal_date: null, commercial_terms: "Standard terms", exclusivity: "exclusive", territory: "India", recruitment_rights: null, all_courses: true,
  courses: [], countries: [{ id: "c1", name: "India" }], payment_terms: null, marketing_rights: null, document: null, edusphere_signatory: null,
  edusphere_signed_on: null, university_signatory_name: null, university_signed_on: null, previous: null, renewed_by: null, created_by: person,
  created_at: "2026-10-09T05:00:00Z", updated_at: "2026-10-09T05:00:00Z", permissions: { can_edit_terms: true, can_edit_signing: true, can_renew: false },
  moves: [{ to_status: "sent", label: "Sent" }],
  events: [{ kind: "create", from_status: null, to_status: "draft", note: null, changed: [], actor: person, created_at: "2026-10-09T05:00:00Z" }],
  ...over,
});
const options: AgreementOptions = {
  courses: [{ id: "k1", title: "MSc Data Science", level: "PG" }],
  documents: [{ id: "d1", kind: "mou", title: "Signed MoU", current_version: 1 }, { id: "d2", kind: "partnership_agreement", title: "PA", current_version: 1 }],

};

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("universityAgreements lib (upc-014)", () => {
  it("names §13's nine statuses in source order, plus the derived Expired", () => {
    expect(Object.values(AGREEMENT_STATUSES)).toEqual(["Draft", "Sent", "Under Review", "Negotiation", "Approved", "Signed", "Active", "Expiring", "Expired", "Renewed"]);
  });

  it("words the time to expiry only for an agreement in force (AC3)", () => {
    expect(expiryText({ status: "signed", days_to_expiry: 30 })).toBe("Expires in 30 days");
    expect(expiryText({ status: "active", days_to_expiry: 1 })).toBe("Expires in 1 day");
    expect(expiryText({ status: "active", days_to_expiry: 0 })).toBe("Expires today");
    expect(expiryText({ status: "signed", days_to_expiry: -3 })).toBe("Expired 3 days ago");
    expect(expiryText({ status: "draft", days_to_expiry: 3 })).toBeNull();
    expect(dateText("2026-10-09")).toBe("09 Oct 2026");
  });

  it("keeps only the known filters in the menu URL", () => {
    expect(agreementPageHref({ status: "expiring", q: " MOU ", offset: "50" }, 0)).toBe("/partnership/agreements?status=expiring&q=MOU");
    expect(agreementPageHref({}, 50)).toBe("/partnership/agreements?offset=50");
  });
});

describe("UniversityAgreements (upc-014)", () => {
  it("shows each agreement with its status, expiry, links, details and history", () => {
    const signed = agreement({
      id: "a2", mou_number: "MOU-000008", status: "signed", effective_status: "expiring", status_label: "Expiring", days_to_expiry: 30, moves: [{ to_status: "active", label: "Active" }],
      permissions: { can_edit_terms: false, can_edit_signing: false, can_renew: true }, renewed_by: { id: "a3", mou_number: "MOU-000009", status: "draft", effective_status: "draft" },
      document: { id: "d1", title: "Signed MoU", kind: "mou", current_version: 2 }, university_signatory_name: "Prof. Registrar", university_signed_on: "2026-10-02",
    });
    render(<UniversityAgreements universityId="u1" agreements={[agreement(), signed]} options={null} canManage={false} />);
    const [, second] = screen.getAllByRole("listitem").filter((li) => li.className === "card");
    expect(within(second).getByText("Expiring")).toBeInTheDocument();
    expect(within(second).getByText("Expires in 30 days")).toBeInTheDocument();
    expect(within(second).getByText(/Renewed by MOU-000009/)).toBeInTheDocument();
    expect(within(second).getByRole("link", { name: "Signed MoU (version 2)" })).toHaveAttribute("href", "/api/v1/partnership/universities/u1/documents/d1/file?version=2");
    expect(within(second).getByText("Prof. Registrar, 02 Oct 2026")).toBeInTheDocument();
    expect(within(second).getByRole("button", { name: "Move to Active (MOU-000008)" })).toBeInTheDocument();
    expect(within(second).getByRole("button", { name: "Renew MOU-000008" })).toBeInTheDocument();
    expect(within(second).queryByRole("button", { name: /^Edit/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New agreement" })).not.toBeInTheDocument(); // canManage false
  });

  it("shows an empty state", () => {
    render(<UniversityAgreements universityId="u1" agreements={[]} options={options} canManage />);
    expect(screen.getByText("No agreements recorded yet.")).toBeInTheDocument();
  });

  it("creates a draft with only the filled fields, then refreshes", async () => {
    const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(res({ agreement: agreement() }, 201)));
    vi.stubGlobal("fetch", mock);
    render(<UniversityAgreements universityId="u1" agreements={[]} options={options} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "New agreement" }));
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Choose the agreement type.");
    fireEvent.change(screen.getByLabelText("Agreement type (required)"), { target: { value: "mou" } });
    fireEvent.change(screen.getByLabelText("Exclusivity (required)"), { target: { value: "exclusive" } });
    fireEvent.change(screen.getByLabelText("Start date (required)"), { target: { value: "2026-10-10" } });
    fireEvent.change(screen.getByLabelText("Expiry date (required)"), { target: { value: "2026-10-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    expect(screen.getByRole("alert")).toHaveTextContent("The expiry date must be after the start date.");
    fireEvent.change(screen.getByLabelText("Expiry date (required)"), { target: { value: "2029-10-10" } });
    fireEvent.change(screen.getByLabelText("Territory"), { target: { value: " India " } });
    fireEvent.click(screen.getByLabelText(/MSc Data Science/));
    expect(within(screen.getByLabelText("Agreement document")).getAllByRole("option").map((o) => o.textContent)).toEqual(["None yet", "Signed MoU (version 1)"]);
    fireEvent.click(screen.getByRole("button", { name: "Create draft" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("/api/v1/partnership/universities/u1/agreements");
    expect(JSON.parse(init!.body as string)).toEqual({
      agreement_type: "mou", start_date: "2026-10-10", expiry_date: "2029-10-10", exclusivity: "exclusive", territory: "India",
      all_courses: false, course_ids: ["k1"], country_ids: [],
    });
    expect(screen.getByRole("status")).toHaveTextContent("Agreement MOU-000007 created as a draft.");
  });

  it("edits only the changed fields, and only the signing fields once approved", async () => {
    const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(res({ agreement: agreement() })));
    vi.stubGlobal("fetch", mock);
    const approved = agreement({ status: "approved", permissions: { can_edit_terms: false, can_edit_signing: true, can_renew: false }, moves: [] });
    render(<UniversityAgreements universityId="u1" agreements={[approved]} options={options} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Edit MOU-000007" }));
    expect(screen.queryByLabelText("Territory")).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Agreement document"), { target: { value: "d1" } });
    fireEvent.change(screen.getByLabelText("Signed by the university (name)"), { target: { value: "Prof. Registrar" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    const [url, init] = mock.mock.calls[0];
    expect([url, init!.method]).toEqual(["/api/v1/partnership/agreements/a1", "PATCH"]);
    expect(JSON.parse(init!.body as string)).toEqual({ document_id: "d1", university_signatory_name: "Prof. Registrar" });
  });

  it("moves with the shown status and a note, and shows the API's refusal", async () => {
    const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(res({ detail: "Add the agreement document before signing" }, 422)));
    vi.stubGlobal("fetch", mock);
    render(<UniversityAgreements universityId="u1" agreements={[agreement()]} options={options} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Move to Sent (MOU-000007)" }));
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "Emailed" } });
    fireEvent.click(screen.getByRole("button", { name: "Move to Sent" }));
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Add the agreement document before signing"));
    const [url, init] = mock.mock.calls[0];
    expect(url).toBe("/api/v1/partnership/agreements/a1/status");
    expect(JSON.parse(init!.body as string)).toEqual({ from_status: "draft", to_status: "sent", note: "Emailed" });
    expect(refresh).not.toHaveBeenCalled();
  });

  it("renews with dates prefilled after the current expiry", async () => {
    const mock = vi.fn<(url: string, init?: RequestInit) => Promise<Response>>(() => Promise.resolve(res({ agreement: agreement() }, 201)));
    vi.stubGlobal("fetch", mock);
    const active = agreement({ status: "active", start_date: "2026-01-01", expiry_date: "2027-01-01", moves: [], permissions: { can_edit_terms: false, can_edit_signing: false, can_renew: true } });
    render(<UniversityAgreements universityId="u1" agreements={[active]} options={options} canManage />);
    fireEvent.click(screen.getByRole("button", { name: "Renew MOU-000007" }));
    expect(screen.getByLabelText("New start date")).toHaveValue("2027-01-02");
    expect(screen.getByLabelText("New expiry date")).toHaveValue("2028-01-02");
    fireEvent.click(screen.getByRole("button", { name: "Start renewal" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(mock.mock.calls[0][0]).toBe("/api/v1/partnership/agreements/a1/renew");
    expect(JSON.parse(mock.mock.calls[0][1]!.body as string)).toEqual({ start_date: "2027-01-02", expiry_date: "2028-01-02" });
  });
});
