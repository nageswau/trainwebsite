import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import TelecallerRulesPanel from "@/components/TelecallerRulesPanel";
import { assignTargets, ruleMatch } from "@/lib/telecallerDistribution";

// tel-007 (DI3, D6): the manager's distribution rules -- create, list, change telecaller, delete.
const nav = vi.hoisted(() => ({ params: new URLSearchParams(), push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: nav.push }), usePathname: () => "/telecaller/manager/distribution", useSearchParams: () => nav.params }));

const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 100, offset: 0 });
const ravi = { id: "u1", full_name: "Ravi", email: "r@x", phone: null, active: true, team: "it", employee_id: "E1" } as const;
const sita = { id: "u2", full_name: "Sita", email: "s@x", phone: null, active: true, team: "it", employee_id: "E2" } as const;
const omar = { id: "u3", full_name: "Omar", email: "o@x", phone: null, active: true, team: "overseas", employee_id: "E3" } as const;
const gone = { ...sita, id: "u4", full_name: "Gone", active: false } as const;
const cyber = { id: "p1", group: "it", name: "Cyber Security", team: "it", program: null, active: true, sort_order: 1 };
const uk = { id: "p2", group: "overseas", name: "UK", team: "overseas", program: null, active: true, sort_order: 2 };
const hyd = { id: "r1", team: "it", kind: "city", product: null, city: "Hyderabad", telecaller: { id: "u1", full_name: "Ravi", active: true }, editable: true } as const;
const theirs = { ...hyd, id: "r2", city: "Pune", telecaller: { id: "u9", full_name: "Other", active: true }, editable: false };

type Call = { url: string; init?: RequestInit };
function serve(rules: unknown[], onWrite?: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (init?.method) return Promise.resolve(onWrite ? onWrite(call) : res({}));
    if (call.url.includes("/manager/team")) return Promise.resolve(res(page([ravi, sita, omar, gone])));
    if (call.url.includes("/telecaller/products")) return Promise.resolve(res(page([cyber, uk])));
    return Promise.resolve(res(page(rules)));
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  nav.params = new URLSearchParams();
  nav.push.mockReset();
  vi.unstubAllGlobals();
});

describe("helpers", () => {
  it("names a rule's match and offers only active reports on the team", () => {
    expect(ruleMatch(hyd)).toBe("City: Hyderabad");
    expect(ruleMatch({ kind: "product", city: null, product: { id: "p1", name: "Cyber Security", active: false } })).toBe("Product: Cyber Security (inactive)");
    expect(assignTargets([ravi, sita, omar, gone], "it").map((r) => r.id)).toEqual(["u1", "u2"]);
  });
});

describe("TelecallerRulesPanel", () => {
  it("lists rules, marking those it cannot change", async () => {
    serve([hyd, theirs]);
    render(<TelecallerRulesPanel />);
    const table = await screen.findByRole("table");
    expect(within(table).getByText("City: Hyderabad")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Change telecaller for City: Hyderabad" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Change telecaller for City: Pune" })).toBeNull();
    expect(within(table).getByText("Another manager's report")).toBeTruthy();
  });

  it("shows the empty state and the retry on a failed load", async () => {
    serve([]);
    render(<TelecallerRulesPanel />);
    expect(await screen.findByText(/No rules yet/)).toBeTruthy();
    cleanup();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "x" }, 500))));
    render(<TelecallerRulesPanel />);
    expect(await screen.findByText("Unable to load rules.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Retry" })).toBeTruthy();
  });

  it("creates a city rule with the team's active reports only", async () => {
    const calls = serve([], () => res(hyd, 201));
    render(<TelecallerRulesPanel />);
    const picker = await screen.findByLabelText("Telecaller (required)");
    await waitFor(() => expect(within(picker).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a telecaller", "Ravi", "Sita"]));
    fireEvent.change(screen.getByLabelText("Rule type (required)"), { target: { value: "city" } });
    fireEvent.change(screen.getByLabelText("City (required)"), { target: { value: " Hyderabad " } });
    fireEvent.change(picker, { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create rule" }));
    expect(await screen.findByText("Created City: Hyderabad.")).toBeTruthy();
    const post = calls.find((c) => c.init?.method === "POST")!;
    expect(JSON.parse(String(post.init!.body))).toEqual({ team: "it", kind: "city", city: "Hyderabad", telecaller_user_id: "u1" });
  });

  it("narrows products and telecallers to the chosen team", async () => {
    serve([]);
    render(<TelecallerRulesPanel />);
    fireEvent.change(await screen.findByLabelText("Team (required)"), { target: { value: "overseas" } });
    await waitFor(() => expect(within(screen.getByLabelText("Telecaller (required)")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a telecaller", "Omar"]));
    expect(within(screen.getByLabelText("Product (required)")).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a product", "UK"]);
  });

  it("shows the server's refusal inline", async () => {
    serve([], () => res({ detail: "This team already has a rule for this city" }, 409));
    render(<TelecallerRulesPanel />);
    const picker = await screen.findByLabelText("Telecaller (required)");
    await waitFor(() => expect(within(picker).getAllByRole("option").length).toBe(3));
    fireEvent.change(screen.getByLabelText("Rule type (required)"), { target: { value: "city" } });
    fireEvent.change(screen.getByLabelText("City (required)"), { target: { value: "Hyderabad" } });
    fireEvent.change(picker, { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create rule" }));
    expect(await screen.findByText("This team already has a rule for this city")).toBeTruthy();
  });

  it("changes a rule's telecaller and deletes a rule after confirming", async () => {
    const calls = serve([hyd], (call) => (call.init?.method === "DELETE" ? res(null, 204) : res({ ...hyd, telecaller: { id: "u2", full_name: "Sita", active: true } })));
    render(<TelecallerRulesPanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Change telecaller for City: Hyderabad" }));
    fireEvent.change(screen.getByLabelText("New telecaller for City: Hyderabad"), { target: { value: "u2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByText("City: Hyderabad now goes to Sita.")).toBeTruthy();
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "PATCH")!.init!.body))).toEqual({ telecaller_user_id: "u2" });
    fireEvent.click(await screen.findByRole("button", { name: "Delete City: Hyderabad" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByText("Deleted City: Hyderabad.")).toBeTruthy();
    expect(calls.some((c) => c.init?.method === "DELETE" && c.url.endsWith("/distribution-rules/r1"))).toBe(true);
  });
});
