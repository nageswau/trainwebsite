import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { contactChanges, contactDraft } from "@/components/LeadContactFields";
import LeadDetailPanel from "@/components/LeadDetailPanel";
import NewLeadForm from "@/components/NewLeadForm";
import type { LeadContact, TelecallerLeadDetail } from "@/lib/telecallerLeads";

// ccrm-005 (DEC-SCOPE-260; LF1, LF4-LF6): the spec §3 contact, consent and referral fields on the New Lead form and the Lead details edit.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const pageOf = <T,>(items: T[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const NONE: LeadContact = { contact_preference: null, enquiry_date: "2026-10-06", marketing_opt_in: null, marketing_consent_at: null, referral_name: null, referral_contact: null };
const products = pageOf([{ id: "p1", group: "overseas", name: "UK", team: "overseas", program: null, active: true, sort_order: 1 }]);
const detail = (over: Partial<TelecallerLeadDetail> = {}): TelecallerLeadDetail => ({
  id: "L1", lead_code: "LD-000042", name: "Asha Rao", email: "asha@example.com", phone: "+91 98765 43210", whatsapp_number: null,
  city: "Hyderabad", state: "Telangana", qualification: null, passing_year: null, institution: null, division: "overseas", subject: "UK",
  status: "contacted", status_label: "Contacted", source: "walk_in", priority: "warm", created_at: "2026-10-06T05:00:00Z",
  stage_changed_at: "2026-10-06T05:00:00Z", product: { id: "p1", name: "UK" }, campaign: null, telecaller: { id: "t1", full_name: "Tara Caller" },
  counselor: null, read_only: false, message: "", whatsapp_to: null, ...NONE, ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
const sent = (method: string) => fetchMock.mock.calls.filter(([, init]) => (init?.method ?? "GET") === method).map(([, init]) => JSON.parse(String(init.body)));
beforeEach(() => {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    if (url.startsWith("/api/v1/telecaller/products")) return Promise.resolve(res(products));
    if (url.startsWith("/api/v1/telecaller/campaigns")) return Promise.resolve(res(pageOf([])));
    if (method === "POST" && url === "/api/v1/telecaller/leads") return Promise.resolve(res({ id: "NEW1", lead_code: "LD-000100" }, 201));
    if (method === "PATCH") return Promise.resolve(res({ ...detail(), ...JSON.parse(String(init?.body)), marketing_consent_at: "2026-10-25T05:00:00Z" }));
    if (["/timeline", "/notes", "/calls", "/messages", "/follow-ups", "/scripts"].some((part) => url.includes(part))) {
      return Promise.resolve(res(pageOf([])));
    }
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("contact draft helpers", () => {
  it("sends only the changed values, consent as a boolean, and never a cleared enquiry date", () => {
    const lead = { ...NONE, marketing_opt_in: true, marketing_consent_at: "x", referral_name: "Kiran" };
    expect(contactDraft(lead).marketing_opt_in).toBe("yes");
    expect(contactChanges({ ...contactDraft(lead), marketing_opt_in: "no", referral_name: " ", enquiry_date: "" }, lead))
      .toEqual({ marketing_opt_in: false, referral_name: null });
    expect(contactChanges({ ...contactDraft(lead), marketing_opt_in: "" }, lead)).toEqual({ marketing_opt_in: null });
  });
});

describe("New Lead form (ccrm-005)", () => {
  it("creates a lead with the contact preference, enquiry date, consent and referral", async () => {
    render(<NewLeadForm basePath="/telecaller/leads" />);
    await waitFor(() => expect(screen.getByRole("option", { name: "UK" })).toBeTruthy());
    fireEvent.change(screen.getByLabelText("Student name *"), { target: { value: "Ravi" } });
    fireEvent.change(screen.getByLabelText("Mobile number *"), { target: { value: "9876500000" } });
    fireEvent.change(screen.getByLabelText("Product interest *"), { target: { value: "p1" } });
    fireEvent.change(screen.getByLabelText("Lead source *"), { target: { value: "walk_in" } });
    fireEvent.change(screen.getByLabelText("Preferred contact method"), { target: { value: "whatsapp" } });
    fireEvent.change(screen.getByLabelText("Enquiry date"), { target: { value: "2026-09-14" } });
    fireEvent.change(screen.getByLabelText("Marketing consent"), { target: { value: "yes" } });
    fireEvent.change(screen.getByLabelText("Referred by (name)"), { target: { value: " Priya " } });
    fireEvent.click(screen.getByRole("button", { name: "Create lead" }));
    await waitFor(() => expect(sent("POST")).toHaveLength(1));
    expect(sent("POST")[0]).toMatchObject({ contact_preference: "whatsapp", enquiry_date: "2026-09-14", marketing_opt_in: true, referral_name: "Priya" });
    expect(sent("POST")[0]).not.toHaveProperty("referral_contact");
  });
});

describe("Lead details (ccrm-005)", () => {
  it("shows the contact fields and edits them, sending only the changes", async () => {
    render(<LeadDetailPanel initial={detail({ marketing_opt_in: false, marketing_consent_at: "2026-10-01T05:00:00Z" })} timeline={pageOf([])} canReopen={false} />);
    expect(screen.getByText("Preferred contact")).toBeTruthy();
    expect(screen.getByText(/^No ·/)).toBeTruthy(); // the consent and when it was recorded
    fireEvent.click(screen.getByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText("Preferred contact method"), { target: { value: "email" } });
    fireEvent.change(screen.getByLabelText("Marketing consent"), { target: { value: "yes" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByText("Details saved.")).toBeTruthy();
    expect(sent("PATCH")[0]).toEqual({ contact_preference: "email", marketing_opt_in: true });
    expect(screen.getByText("Email", { selector: "dd" })).toBeTruthy();
  });
});
