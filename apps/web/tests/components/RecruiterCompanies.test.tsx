import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCompaniesPanel from "@/components/RecruiterCompaniesPanel";
import RecruiterCompanyDetail from "@/components/RecruiterCompanyDetail";
import RecruiterCompanyForm from "@/components/RecruiterCompanyForm";
import { type Company, companyBody, companyShell, duplicateOf, safeLink, valuesOf, wire } from "@/lib/recruiterCompanies";

const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn(), refresh: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, refresh: nav.refresh, replace: nav.push }),
  usePathname: () => "/recruiter/companies",
  useSearchParams: () => nav.params,
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 50, offset: 0 });
const perms = { can_edit: true, can_archive: true, can_restore: false, can_reassign: false };
const priya = { id: "u1", full_name: "Priya Recruiter", active: true };
const row = { id: "c1", code: "CMP-000007", name: "ABC Technologies", city: "Pune", priority: "hot", industry: null, lead_source: { id: "s1", name: "LinkedIn", active: true }, assigned_recruiter: priya, archived: false, permissions: perms, stage: "new_lead", stage_label: "New Lead", lost: false };
const company: Company = {
  ...(row as Company), website: "https://abc.example.com", linkedin_url: "javascript:alert(1)", company_size: null, employee_count: 250, state: "MH",
  country: "India", head_office: null, branches: "Mumbai\nDelhi", description: null, campaign: null, assigned_bdm: null, owner_type: "internal",
  created_by: priya, assignment_history: [], archived_at: null,
  pipeline: { stage: "new_lead", stage_label: "New Lead", stage_changed_at: "2026-10-08T10:00:00Z", lost: null, can_move: false, can_reopen: false, steps: [{ key: "new_lead", label: "New Lead", kind: "start", state: "current" }] }, created_at: "2026-10-08T10:00:00Z", updated_at: "2026-10-08T10:00:00Z",
};

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
const emptyPickers = (url: string) => (url.includes("/catalogue/") ? res(page([])) : res(page([row])));

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("sends every filled field on create and only the changed ones on edit; blank clears", () => {
    const values = { ...valuesOf(), name: " ABC ", employee_count: "250", priority: "hot" };
    expect(companyBody(values)).toEqual({ name: "ABC", employee_count: 250, priority: "hot" });
    const original = valuesOf(company);
    expect(companyBody({ ...original, city: "", priority: "warm" }, original)).toEqual({ city: null, priority: "warm" });
    expect(wire("employee_count", "12a")).toBe("12a"); // the server names the field
  });

  it("reads the duplicate warning and only links http(s)", () => {
    expect(duplicateOf({ code: "possible_duplicate", message: "m", matches: [], total: 2 })).toEqual({ message: "m", matches: [], total: 2 });
    expect(duplicateOf("A company with this name already exists")).toBeNull();
    expect(safeLink("javascript:alert(1)")).toBeNull();
    expect(safeLink("https://abc.example.com")).toBe("https://abc.example.com");
  });

  it("puts each role in its own workspace", () => {
    expect(companyShell("placement_team").roleLabel).toBe("Recruiter");
    expect(companyShell("placement_manager").roleLabel).toBe("Placement Manager");
    expect(companyShell("super_admin").roleLabel).toBe("Super Administrator");
    expect(companyShell("bdm").nav.map((x) => x.href)).toContain("/bdm/organizations"); // QA-04: the BDM keeps their own menu
  });
});

describe("RecruiterCompaniesPanel", () => {
  it("lists companies from the API with the URL's filters", async () => {
    nav.params = new URLSearchParams("priority=hot&assigned=unassigned&archived=1");
    const calls = serve(() => res(page([row])));
    render(<RecruiterCompaniesPanel canCreate />);
    const table = await screen.findByRole("region", { name: "Companies" });
    expect(within(table).getByRole("link", { name: "ABC Technologies" }).getAttribute("href")).toBe("/recruiter/companies/c1");
    expect(within(table).getByText("CMP-000007")).toBeTruthy();
    expect(within(table).getByText("Hot")).toBeTruthy();
    expect(within(table).getByText("Priya Recruiter")).toBeTruthy();
    const url = calls.find((c) => c.url.startsWith("/api/v1/recruiter/companies?"))!.url;
    expect(url).toContain("priority=hot");
    expect(url).toContain("assigned=unassigned");
    expect(url).toContain("include_archived=true");
    expect(screen.getAllByRole("link", { name: "Add company" })[0].getAttribute("href")).toBe("/recruiter/companies/new");
  });

  it("labels every cell, so the house card layout can stack each row below 980px (QA-02)", async () => {
    serve(() => res(page([row])));
    const { container } = render(<RecruiterCompaniesPanel canCreate />);
    await screen.findByRole("region", { name: "Companies" });
    expect(container.querySelector(".telecaller-list")).toBeTruthy();
    const labels = [...container.querySelectorAll("tbody td")].map((td) => td.getAttribute("data-label"));
    expect(labels).toEqual(["Code", "Name", "City", "Priority", "Stage", "Lead source", "Industry", "Recruiter", "Next follow-up"]); // rec-005, rec-024
  });

  it("shows the empty state, and an error with Retry", async () => {
    let fail = true;
    serve((url) => (url.includes("/catalogue/") ? res(page([])) : fail ? res({ detail: "boom" }, 500) : res(page([]))));
    render(<RecruiterCompaniesPanel canCreate={false} />);
    expect(await screen.findByText("Unable to load companies.")).toBeTruthy();
    fail = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("No companies yet.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Add company" })).toBeNull();
  });

  it("puts a priority choice in the URL", async () => {
    serve(emptyPickers);
    render(<RecruiterCompaniesPanel canCreate />);
    await screen.findByRole("region", { name: "Companies" });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "cold" } });
    expect(nav.push).toHaveBeenCalledWith("/recruiter/companies?priority=cold", { scroll: false });
  });
});

describe("RecruiterCompanyForm", () => {
  it("requires a name before calling the server", async () => {
    const calls = serve(emptyPickers);
    render(<RecruiterCompanyForm mode="create" canChooseRecruiter={false} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save company" }));
    expect(await screen.findByText("Company name is required")).toBeTruthy();
    expect(writes(calls)).toEqual([]);
  });

  it("warns on a likely duplicate and saves anyway with confirm_duplicate", async () => {
    const dup = { detail: { code: "possible_duplicate", message: "A similar company already exists", total: 1, matches: [{ id: "c9", code: "CMP-000009", name: "ABC Tech", city: "Pune", archived: false }] } };
    const calls = serve(emptyPickers, (call) => (JSON.parse(String(call.init!.body)).confirm_duplicate ? res({ company }, 201) : res(dup, 409)));
    const onSaved = vi.fn();
    render(<RecruiterCompanyForm mode="create" canChooseRecruiter={false} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Company name/), { target: { value: "ABC Technologies" } });
    fireEvent.click(screen.getByRole("button", { name: "Save company" }));
    expect(await screen.findByText("A similar company already exists")).toBeTruthy();
    expect(screen.getByText(/CMP-000009 — ABC Tech, Pune/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(company, true));
    expect(JSON.parse(String(writes(calls)[1].init!.body))).toEqual({ name: "ABC Technologies", confirm_duplicate: true });
  });

  it("shows a server 422 at its field", async () => {
    const invalid = { detail: [{ loc: ["body", "website"], msg: "Value error, Website must start with http:// or https://", type: "value_error" }] };
    serve(emptyPickers, () => res(invalid, 422));
    render(<RecruiterCompanyForm mode="create" canChooseRecruiter={false} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Company name/), { target: { value: "ABC" } });
    fireEvent.change(screen.getByLabelText("Website"), { target: { value: "ftp://abc" } });
    fireEvent.click(screen.getByRole("button", { name: "Save company" }));
    expect(await screen.findByText("Website must start with http:// or https://")).toBeTruthy();
    expect(screen.getByLabelText("Website").getAttribute("aria-invalid")).toBe("true");
  });
});

describe("RecruiterCompanyDetail", () => {
  it("shows the company, never links an unsafe URL, and offers only the permitted actions", () => {
    serve(emptyPickers);
    render(<RecruiterCompanyDetail initial={company} created={false} />);
    expect(screen.getByRole("heading", { name: "ABC Technologies" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /abc\.example\.com/ }).getAttribute("href")).toBe("https://abc.example.com");
    expect(screen.queryByRole("link", { name: /javascript/ })).toBeNull();
    expect(screen.getByRole("button", { name: "Edit" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Archive" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Restore" })).toBeNull();
    expect(screen.queryByRole("heading", { name: "Assignment" })).toBeNull();
  });

  it("archives after confirming and shows the outcome", async () => {
    const archived = { ...company, archived: true, archived_at: "2026-10-08T11:00:00Z", permissions: { ...perms, can_edit: false, can_archive: false } };
    const calls = serve(emptyPickers, () => res({ company: archived }));
    render(<RecruiterCompanyDetail initial={company} created={false} />);
    fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, archive" }));
    expect(await screen.findByText("Company archived.")).toBeTruthy();
    expect(writes(calls)[0].url).toBe("/api/v1/recruiter/companies/c1/archive");
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("shows the assignment section and history to a manager", () => {
    const managed = {
      ...company, permissions: { can_edit: false, can_archive: false, can_restore: false, can_reassign: true },
      assignment_history: [{ from_user: null, to_user: priya, changed_by: { id: "m1", full_name: "Meena Manager", active: true }, created_at: "2026-10-08T10:00:00Z" }],
    };
    serve(emptyPickers);
    render(<RecruiterCompanyDetail initial={managed} created={false} />);
    expect(screen.getByRole("heading", { name: "Assignment" })).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "Reassign to" })).toBeTruthy();
    expect(screen.getByText(/Unassigned → Priya Recruiter/)).toBeTruthy();
    expect(screen.getByText(/by Meena Manager/)).toBeTruthy();
  });
});
