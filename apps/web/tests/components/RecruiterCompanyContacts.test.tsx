import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyContacts from "@/components/RecruiterCompanyContacts";
import RecruiterCompanyForm from "@/components/RecruiterCompanyForm";
import { businessContacts, type Contact, contactBody, contactErrorsOf, contactValuesOf } from "@/lib/recruiterContacts";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh: vi.fn(), replace: vi.fn() }), usePathname: () => "/recruiter/companies" }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const role = (name: string) => ({ id: `r-${name}`, name, active: true });
const contact = (over: Partial<Contact>): Contact => ({
  id: "k1", name: "Priya", designation: null, department: null, role: null, mobile: null, email: null, linkedin_url: null, preferred_channel: null,
  notes: null, is_primary: false, active: true, last_contacted_at: null, created_at: "2026-10-08T10:00:00Z", updated_at: "2026-10-08T10:00:00Z", ...over,
});
const priya = contact({ id: "k1", name: "Priya", is_primary: true, role: role("Talent Acquisition Manager"), mobile: "98765 43210", email: "priya@abc.example.com", linkedin_url: "javascript:alert(1)" });
const ravi = contact({ id: "k2", name: "Ravi", role: role("HR Manager"), email: "ravi@abc.example.com", mobile: "90000 00001" });

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
const writes = (calls: Call[]) => calls.filter((c) => c.init?.method);
const roles = { items: [role("HR Manager"), role("Hiring Manager")], total: 2, limit: 100, offset: 0 };
const reads = (list: unknown) => (url: string) => (url.includes("/catalogue/") ? res(roles) : res(list));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("sends every filled field on create and only changes on edit; blank clears", () => {
    expect(contactBody({ ...contactValuesOf(), name: " Priya ", email: "p@x.com" })).toEqual({ name: "Priya", email: "p@x.com" });
    const original = contactValuesOf(priya);
    expect(contactBody({ ...original, mobile: "", department: "HR" }, original)).toEqual({ mobile: null, department: "HR" });
  });

  it("maps 422 items to contact fields under the given location only", () => {
    const item = (loc: unknown[]) => ({ loc, msg: "Value error, Enter a valid email address", type: "value_error" });
    expect(contactErrorsOf([item(["body", "email"])], ["body"])).toEqual({ email: expect.stringContaining("valid email") });
    expect(contactErrorsOf([item(["body", "contact", "email"])], ["body", "contact"])).toEqual({ email: expect.stringContaining("valid email") });
    expect(contactErrorsOf([item(["body", "name"])], ["body", "contact"])).toBeNull(); // a company field: not the contact's
    expect(contactErrorsOf("Choose an active contact role", ["body"])).toBeNull();
  });

  it("reads §3 Business Details from active contacts by role; HR email/phone from the first HR contact", () => {
    const head = contact({ id: "k3", name: "Old HR", role: role("HR Head"), email: "old@x.com", active: false });
    const summary = businessContacts([priya, ravi, head, contact({ id: "k4", name: "Hari", role: role("hiring manager ") })]);
    expect(summary.hr.map((c) => c.name)).toEqual(["Ravi"]);
    expect(summary.talentAcquisition.map((c) => c.name)).toEqual(["Priya"]);
    expect(summary.hiringManager.map((c) => c.name)).toEqual(["Hari"]);
    expect([summary.hrEmail, summary.hrPhone]).toEqual(["ravi@abc.example.com", "90000 00001"]);
    expect(businessContacts([]).hrEmail).toBeNull();
  });
});

describe("RecruiterCompanyContacts", () => {
  it("lists contacts read-only for a reader: badges, summary, no actions, no role picker load", async () => {
    const calls = serve(reads({ items: [priya, { ...ravi, active: false }], can_edit: false }));
    render(<RecruiterCompanyContacts companyId="c1" />);
    const list = await screen.findByRole("list", { name: "Contacts" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(within(list).getByText("Primary")).toBeTruthy();
    expect(within(list).getByText("Inactive")).toBeTruthy();
    expect(screen.getByText("Talent acquisition contact").nextSibling?.textContent).toBe("Priya");
    expect(screen.getByText("HR contact").nextSibling?.textContent).toBe("—"); // Ravi is inactive
    expect(screen.queryByRole("button", { name: /Edit|Deactivate|Add contact/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /javascript/ })).toBeNull(); // only http(s) links
    expect(calls.some((c) => c.url.includes("/catalogue/"))).toBe(false);
  });

  it("shows the empty state and adds a contact; the list re-renders from the response", async () => {
    const calls = serve(reads({ items: [], can_edit: true }), () => res({ items: [priya], can_edit: true }, 201));
    render(<RecruiterCompanyContacts companyId="c1" />);
    expect(await screen.findByText(/No contacts yet/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Add contact" }));
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(screen.getByText("Contact name is required")).toBeTruthy(); // checked before a round trip
    fireEvent.change(screen.getByLabelText("Contact name (required)"), { target: { value: "Priya" } });
    fireEvent.change(screen.getByLabelText("Preferred communication"), { target: { value: "whatsapp" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    await screen.findByText("Contact added.");
    const [post] = writes(calls);
    expect(post.url).toBe("/api/v1/recruiter/companies/c1/contacts");
    expect(JSON.parse(String(post.init?.body))).toEqual({ name: "Priya", preferred_channel: "whatsapp" });
  });

  it("puts a server 422 on its field and keeps the entry", async () => {
    serve(reads({ items: [], can_edit: true }), () => res({ detail: [{ loc: ["body", "mobile"], msg: "Value error, Enter a valid mobile number", type: "value_error" }] }, 422));
    render(<RecruiterCompanyContacts companyId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add contact" }));
    fireEvent.change(screen.getByLabelText("Contact name (required)"), { target: { value: "Priya" } });
    fireEvent.change(screen.getByLabelText("Mobile"), { target: { value: "12" } });
    fireEvent.click(screen.getByRole("button", { name: "Save contact" }));
    expect(await screen.findByText(/Enter a valid mobile number/)).toBeTruthy();
    expect((screen.getByLabelText("Mobile") as HTMLInputElement).value).toBe("12");
  });

  it("makes primary, and deactivates only after confirming; a 409 is shown", async () => {
    const calls = serve(reads({ items: [priya, ravi], can_edit: true }), (call) =>
      JSON.parse(String(call.init?.body)).active === false ? res({ detail: "Make another contact primary first" }, 409) : res({ items: [{ ...ravi, is_primary: true }, { ...priya, is_primary: false }], can_edit: true }),
    );
    render(<RecruiterCompanyContacts companyId="c1" />);
    fireEvent.click(await screen.findByRole("button", { name: "Make primary Ravi" }));
    await screen.findByText("Ravi is now the primary contact.");
    expect(writes(calls)[0].url).toBe("/api/v1/recruiter/contacts/k2");
    fireEvent.click(screen.getByRole("button", { name: "Deactivate Ravi" }));
    expect(writes(calls)).toHaveLength(1); // nothing sent before the confirm
    fireEvent.click(screen.getByRole("button", { name: "Yes, deactivate" }));
    expect(await screen.findByText("Make another contact primary first")).toBeTruthy();
  });

  it("offers Retry when the list cannot be loaded", async () => {
    let fail = true;
    serve((url) => (url.includes("/catalogue/") ? res(roles) : fail ? res({ detail: "boom" }, 500) : res({ items: [priya], can_edit: false })));
    render(<RecruiterCompanyContacts companyId="c1" />);
    expect(await screen.findByText(/could not be loaded/)).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("list", { name: "Contacts" })).toBeTruthy();
  });
});

describe('"+ Add Recruiter" form', () => {
  const catalogue = (url: string) => (url.includes("contact-roles") ? res(roles) : res({ items: [], total: 0, limit: 100, offset: 0 }));

  it("requires the contact's name and sends the company with its first contact", async () => {
    const saved = vi.fn();
    const calls = serve(catalogue, () => res({ company: { id: "c9" } }, 201));
    render(<RecruiterCompanyForm mode="create" canChooseRecruiter={false} withContact onSaved={saved} onCancel={vi.fn()} />);
    const section = screen.getByRole("group", { name: "Recruiter contact" });
    fireEvent.change(screen.getByLabelText(/Company name/), { target: { value: "ABC Technologies" } });
    fireEvent.click(screen.getByRole("button", { name: "Save company" }));
    expect(within(section).getByText("Contact name is required")).toBeTruthy();
    expect(writes(calls)).toHaveLength(0);
    fireEvent.change(within(section).getByLabelText("Contact name (required)"), { target: { value: "Priya" } });
    fireEvent.change(within(section).getByLabelText("Designation"), { target: { value: "TA Manager" } });
    await waitFor(() => expect(within(section).getByRole("option", { name: "HR Manager" })).toBeTruthy());
    fireEvent.change(within(section).getByLabelText("Role"), { target: { value: "r-HR Manager" } });
    fireEvent.click(screen.getByRole("button", { name: "Save company" }));
    await waitFor(() => expect(saved).toHaveBeenCalled());
    expect(JSON.parse(String(writes(calls)[0].init?.body))).toEqual({ name: "ABC Technologies", contact: { name: "Priya", designation: "TA Manager", role_id: "r-HR Manager" } });
  });

  it("puts a contact 422 on the contact's field", async () => {
    serve(catalogue, () => res({ detail: [{ loc: ["body", "contact", "email"], msg: "Value error, Enter a valid email address", type: "value_error" }] }, 422));
    render(<RecruiterCompanyForm mode="create" canChooseRecruiter={false} withContact onSaved={vi.fn()} onCancel={vi.fn()} />);
    const section = screen.getByRole("group", { name: "Recruiter contact" });
    fireEvent.change(screen.getByLabelText(/Company name/), { target: { value: "ABC Technologies" } });
    fireEvent.change(within(section).getByLabelText("Contact name (required)"), { target: { value: "Priya" } });
    fireEvent.change(within(section).getByLabelText("Email"), { target: { value: "nope" } });
    fireEvent.click(screen.getByRole("button", { name: "Save company" }));
    expect(await within(section).findByText(/Enter a valid email address/)).toBeTruthy();
  });

  it("has no contact section on a plain Add Company", () => {
    serve(catalogue);
    render(<RecruiterCompanyForm mode="create" canChooseRecruiter={false} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByRole("group", { name: "Recruiter contact" })).toBeNull();
  });
});
