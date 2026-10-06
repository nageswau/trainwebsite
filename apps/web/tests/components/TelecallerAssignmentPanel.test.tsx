import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerAssignmentPanel from "@/components/TelecallerAssignmentPanel";

// tel-007 (DI4, D3): the manager's Lead assignment page -- Unassigned queue and Assigned to my team, bulk assign/reassign.
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }), usePathname: () => "/telecaller/manager/assignment", useSearchParams: () => nav.params }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 50, offset: 0 });
const ravi = { id: "u1", full_name: "Ravi", email: "r@x", phone: null, active: true, team: "it", employee_id: "E1" };
const omar = { id: "u3", full_name: "Omar", email: "o@x", phone: null, active: true, team: "overseas", employee_id: "E3" };
const lead = (id: string, extra = {}) => ({
  id, lead_code: `LD-00000${id}`, name: `Lead ${id}`, division: "it", city: "Pune", product: null, source: "website", status: "new",
  status_label: "New Lead", telecaller: null, created_at: "2026-10-06T05:00:00Z", ...extra,
});

type Call = { url: string; init?: RequestInit };
function serve(leads: unknown[], onWrite?: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (init?.method) return Promise.resolve(onWrite ? onWrite(call) : res({ assigned: 1, unchanged: 0 }));
    if (call.url.includes("/manager/team")) return Promise.resolve(res(page([ravi, omar])));
    return Promise.resolve(res(page(leads)));
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("TelecallerAssignmentPanel", () => {
  it("lists the unassigned queue by default", async () => {
    const calls = serve([lead("1"), lead("2")]);
    render(<TelecallerAssignmentPanel />);
    expect(await screen.findByText("Lead 1")).toBeTruthy();
    expect(screen.getByRole("tab", { name: "Unassigned" }).getAttribute("aria-selected")).toBe("true");
    expect(calls.some((c) => c.url.includes("/telecaller/leads/unassigned"))).toBe(true);
    expect(screen.getByRole("button", { name: /Assign/ }).hasAttribute("disabled")).toBe(true);  // nothing selected yet
  });

  it("shows empty and error states", async () => {
    serve([]);
    render(<TelecallerAssignmentPanel />);
    expect(await screen.findByText("No unassigned leads. New leads with no matching rule or available telecaller appear here.")).toBeTruthy();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "x" }, 500))));
    render(<TelecallerAssignmentPanel />);
    expect(await screen.findByText("Unable to load leads.")).toBeTruthy();
  });

  it("assigns the selected leads to an active report on their team, once", async () => {
    let finish!: (r: Response) => void;
    const calls = serve([lead("1"), lead("2")], () => new Promise<Response>((resolve) => { finish = resolve; }) as unknown as Response);
    render(<TelecallerAssignmentPanel />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select all leads on this page" }));
    const picker = screen.getByLabelText("Assign to");
    expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a telecaller", "Ravi (IT)", "Omar (Overseas)"]);
    fireEvent.change(picker, { target: { value: "u1" } });
    const button = screen.getByRole("button", { name: "Assign 2 selected" });
    fireEvent.click(button);
    fireEvent.click(button);  // a double click posts once
    finish(res({ assigned: 2, unchanged: 0 }));
    expect(await screen.findByText("Assigned 2 leads to Ravi.")).toBeTruthy();
    const posts = calls.filter((c) => c.init?.method === "POST");
    expect(posts).toHaveLength(1);
    expect(JSON.parse(String(posts[0].init!.body))).toEqual({ lead_ids: ["1", "2"], telecaller_user_id: "u1" });
  });

  it("says a team mismatch before posting", async () => {
    const calls = serve([lead("1")]);
    render(<TelecallerAssignmentPanel />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Lead 1" }));
    fireEvent.change(screen.getByLabelText("Assign to"), { target: { value: "u3" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign 1 selected" }));
    expect(await screen.findByText("Omar is on the Overseas team; choose leads from that team.")).toBeTruthy();
    expect(calls.some((c) => c.init?.method === "POST")).toBe(false);
  });

  it("shows the server's refusal", async () => {
    serve([lead("1")], () => res({ detail: "You can only assign leads to your direct reports" }, 403));
    render(<TelecallerAssignmentPanel />);
    fireEvent.click(await screen.findByRole("checkbox", { name: "Select Lead 1" }));
    fireEvent.change(screen.getByLabelText("Assign to"), { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: "Assign 1 selected" }));
    expect(await screen.findByText("You can only assign leads to your direct reports")).toBeTruthy();
  });

  // QA-01: a manager with reports on both teams narrows the list to one team, so "Select all" can be assigned in one go.
  it("filters by team through the URL", async () => {
    nav.params = new URLSearchParams({ team: "overseas" });
    const calls = serve([]);
    render(<TelecallerAssignmentPanel />);
    expect(await screen.findByText("No unassigned leads on the Overseas team.")).toBeTruthy();
    expect(calls.some((c) => c.url.includes("/telecaller/leads/unassigned") && c.url.includes("team=overseas"))).toBe(true);
    fireEvent.change(screen.getByLabelText("Team"), { target: { value: "it" } });
    expect(nav.push).toHaveBeenCalledWith("/telecaller/manager/assignment?team=it", { scroll: false });
  });

  // QA-02: the empty state names the filter instead of claiming the whole team has no leads.
  it("words the empty state for a telecaller filter", async () => {
    nav.params = new URLSearchParams({ view: "assigned", telecaller: "u1" });
    serve([]);
    render(<TelecallerAssignmentPanel />);
    expect(await screen.findByText("No leads are assigned to Ravi.")).toBeTruthy();
  });

  it("switches to the team's assigned leads and filters by telecaller", async () => {
    nav.params = new URLSearchParams({ view: "assigned", telecaller: "u1" });
    const calls = serve([lead("3", { status: "contacted", status_label: "Contacted", telecaller: { id: "u1", full_name: "Ravi", active: true } })]);
    render(<TelecallerAssignmentPanel />);
    expect(await screen.findByText("Lead 3")).toBeTruthy();
    await waitFor(() => expect(calls.some((c) => c.url.includes("/telecaller/leads/assigned") && c.url.includes("telecaller_user_id=u1"))).toBe(true));
    expect(screen.getByRole("tab", { name: "Assigned to my team" }).getAttribute("aria-selected")).toBe("true");
    expect(screen.getByRole("button", { name: /Reassign/ })).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "Unassigned" }));
    expect(nav.push).toHaveBeenCalledWith("/telecaller/manager/assignment", { scroll: false });
  });
});
