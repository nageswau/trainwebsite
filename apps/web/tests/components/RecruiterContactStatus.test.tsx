import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyContacts from "@/components/RecruiterCompanyContacts";
import RecruiterMessages from "@/components/RecruiterMessages";
import { type Contact, contactBody, contactValuesOf, duplicatesUrl } from "@/lib/recruiterContacts";
import { timelineEntry, type RecTimelineRow } from "@/lib/recruiterTimeline";

// pob-005 (DEC-SCOPE-411): contact status, decision-maker, source/verification, duplicates, the per-contact Activity and Log reply.
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }), usePathname: () => "/recruiter/companies" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const contact = (over: Partial<Contact>): Contact => ({
  id: "k1", name: "Priya", designation: null, department: null, role: null, mobile: null, email: null, linkedin_url: null, preferred_channel: null,
  notes: null, is_primary: false, active: true, last_contacted_at: null, created_at: "2026-10-08T10:00:00Z", updated_at: "2026-10-08T10:00:00Z", ...over,
});
type Call = { url: string; init?: RequestInit };
function serve(read: (url: string) => Response, onWrite: (call: Call) => Response = () => res({})) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    return Promise.resolve(init?.method ? onWrite(call) : read(String(url)));
  }));
  return calls;
}
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("sends the decision-maker box as a boolean and the status only when it changes", () => {
    expect(contactBody({ ...contactValuesOf(), name: "Priya" })).toEqual({ name: "Priya" }); // defaults are the server's
    expect(contactBody({ ...contactValuesOf(), name: "Priya", is_decision_maker: "true", source: "referral", status: "do_not_contact" }))
      .toEqual({ name: "Priya", is_decision_maker: true, source: "referral", status: "do_not_contact" });
    const original = contactValuesOf(contact({ is_decision_maker: true, status: "replied", verified_on: "2026-10-01" }));
    expect(contactBody({ ...original, is_decision_maker: "", verified_on: "" }, original)).toEqual({ is_decision_maker: false, verified_on: null });
  });

  it("builds the duplicate check only when there is something to check", () => {
    expect(duplicatesUrl("c1", { mobile: " ", email: "" })).toBeNull();
    expect(duplicatesUrl("c1", { mobile: "98765 43210", email: "" }, "k1")).toBe("/api/v1/recruiter/companies/c1/contacts/duplicates?mobile=98765+43210&exclude=k1");
  });

  it("labels a status change and a logged reply on the timeline", () => {
    const row = { id: "a", at: "2026-11-05T10:00:00Z", actor: null, from_value: "contacted", from_label: "Contacted", to_value: "replied", to_label: "Replied",
      subject: null, status: null, reason: null, context: null, duration_seconds: null, scheduled_for: null } as const;
    expect(timelineEntry({ ...row, kind: "contact_status", event: "reply" } as RecTimelineRow)).toMatchObject({ badge: "Status", title: "Status: Contacted → Replied", meta: ["After a reply"] });
    expect(timelineEntry({ ...row, kind: "message_reply", event: "whatsapp", to_label: "Priya" } as RecTimelineRow)).toMatchObject({ badge: "Reply", title: "WhatsApp reply received", meta: ["From Priya"] });
  });
});

describe("RecruiterCompanyContacts (pob-005)", () => {
  it("shows the status, decision-maker, follow-up due and a Do Not Contact warning", async () => {
    serve(() => res({ items: [contact({ is_decision_maker: true, follow_up_due: true, status: "do_not_contact", source: "linkedin" })], can_edit: false }));
    render(<RecruiterCompanyContacts companyId="c1" />);
    const list = await screen.findByRole("list", { name: "Contacts" });
    expect(within(list).getByText("Decision-maker")).toBeTruthy();
    expect(within(list).getByText("Follow-up due")).toBeTruthy();
    expect(within(list).getByText("Do not contact")).toBeTruthy();
    expect(within(list).getByText("LinkedIn")).toBeTruthy();
    expect(within(list).getByText(/messages, outgoing calls, profile shares and meeting invites to Priya are blocked/)).toBeTruthy();
  });

  it("QA-02: shows Verified on as a calendar date, without a time", async () => {
    serve(() => res({ items: [contact({ verified_on: "2026-11-01" })], can_edit: false }));
    render(<RecruiterCompanyContacts companyId="c1" />);
    const list = await screen.findByRole("list", { name: "Contacts" });
    expect(within(list).getByText("Verified on").nextSibling?.textContent).toBe("01 Nov 2026");
  });

  it("warns about a duplicate before saving and saves only on Save anyway", async () => {
    const duplicates = { matches: [{ id: "x1", name: "Asha", active: true, company: { id: "c9", name: "Beta Ltd" }, same_company: false, on: ["mobile"] }], others: 2 };
    const calls = serve(
      (url) => (url.includes("/duplicates") ? res(duplicates) : url.includes("/catalogue/") ? res(page([])) : res({ items: [], can_edit: true })),
      () => res({ items: [contact({ name: "Ravi" })], can_edit: true }, 201),
    );
    render(<RecruiterCompanyContacts companyId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Contact name (required)"), { target: { value: "Ravi" } });
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "98765 43210" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(await screen.findByText(/Asha at Beta Ltd \(mobile\)/)).toBeTruthy();
    expect(screen.getByText("2 more at companies outside your list")).toBeTruthy();
    expect(calls.filter((c) => c.init?.method)).toHaveLength(0); // nothing saved yet
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(calls.filter((c) => c.init?.method)).toHaveLength(1));
    expect(JSON.parse(String(calls.find((c) => c.init?.method)?.init?.body))).toEqual({ name: "Ravi", mobile: "98765 43210" });
  });

  it("opens a contact's Activity: its follow-ups and its own timeline", async () => {
    const calls = serve((url) => {
      if (url.includes("/follow-ups")) return res(page([{ id: "f1", reason: "jd", due_at: "2026-11-06T05:00:00Z", status: "open", overdue: false }]));
      if (url.includes("/timeline")) return res(page([]));
      return res({ items: [contact({})], can_edit: false });
    });
    render(<RecruiterCompanyContacts companyId="c1" />);
    const toggle = await screen.findByRole("button", { name: "Activity Priya" });
    expect(toggle.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(toggle);
    expect(await screen.findByRole("list", { name: "Follow-ups with Priya" })).toBeTruthy();
    await waitFor(() => expect(calls.some((c) => c.url.startsWith("/api/v1/recruiter/companies/c1/timeline?contact_id=k1&limit="))).toBe(true));
    expect(calls.some((c) => c.url === "/api/v1/recruiter/companies/c1/follow-ups?contact_id=k1&limit=50")).toBe(true);
    expect(screen.getByRole("button", { name: "Hide activity Priya" }).getAttribute("aria-expanded")).toBe("true");
  });
});

describe("RecruiterMessages Log reply (pob-005)", () => {
  const message = (over: object) => ({
    id: "m1", kind: "contact", company_id: "c1", contact: { id: "k1", name: "Priya" }, candidate: null, channel: "whatsapp", template: null, subject: null, body: "Hi",
    delivery_status: null, sent_at: "2026-11-05T05:00:00Z", sender: { id: "u1", full_name: "Asha" }, replied_at: null, ...over,
  });

  it("logs a reply on a contact message and shows it once logged", async () => {
    let replied = false;
    const calls = serve(
      (url) => (url.includes("/messages") ? res(page([message(replied ? { replied_at: "2026-11-05T06:00:00Z" } : {})])) : res({ items: [], can_edit: true })),
      () => {
        replied = true;
        return res(message({ replied_at: "2026-11-05T06:00:00Z" }));
      },
    );
    render(<RecruiterMessages source={{ kind: "company", companyId: "c1" }} canWrite />);
    fireEvent.click(await screen.findByRole("button", { name: "Log reply from Priya" }));
    expect(await screen.findByText(/^Reply received – /)).toBeTruthy();
    expect(calls.find((c) => c.init?.method)?.url).toBe("/api/v1/recruiter/messages/m1/reply");
    expect(screen.queryByRole("button", { name: /Log reply/ })).toBeNull();
  });

  it("QA-01: never offers a Do Not Contact person as a recipient", async () => {
    serve((url) =>
      url.includes("/messages")
        ? res(page([]))
        : res({ items: [contact({ id: "k1", name: "Priya", mobile: "98765 43210" }), contact({ id: "k2", name: "Ravi", mobile: "90000 00001", status: "do_not_contact" })], can_edit: true }),
    );
    render(<RecruiterMessages source={{ kind: "company", companyId: "c1" }} canWrite />);
    const picker = await screen.findByLabelText("To");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Priya"]);
  });

  it("offers no Log reply to a reader", async () => {
    serve(() => res(page([message({})])));
    render(<RecruiterMessages source={{ kind: "company", companyId: "c1" }} canWrite={false} />);
    await screen.findByText("Hi");
    expect(screen.queryByRole("button", { name: /Log reply/ })).toBeNull();
  });
});
