import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterRoutingPanel from "@/components/RecruiterRoutingPanel";

// hrc-024 (DEC-SCOPE-393): the candidate routing page -- settings (R4/R6), rules in routing order (R1/R2), the queue link (R10).
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const REC = { id: "r1", full_name: "Asha Recruiter", active: true };
const ROUTING = {
  default_recruiter: null, strategy: "round_robin", can_edit: true,
  rules: [
    { id: "x1", kind: "source", value_id: "s1", value_label: "Website", recruiter: REC, created_at: "2026-11-04T10:00:00Z" },
    { id: "x2", kind: "location", value_id: null, value_label: "Pune", recruiter: { ...REC, id: "r2", full_name: "Old Hand", active: false }, created_at: "2026-11-04T10:00:00Z" },
  ],
};

function server(overrides: (url: string, init?: RequestInit) => Response | undefined = () => undefined) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    const hit = overrides(url, init);
    if (hit) return Promise.resolve(hit);
    if (url.includes("candidate-sources")) return Promise.resolve(res({ items: [{ id: "s1", name: "Website" }, { id: "s2", name: "Referral" }] }));
    if (url.includes("skill-categories")) return Promise.resolve(res({ items: [{ id: "c1", name: "Programming" }] }));
    if (url.includes("/assignees")) return Promise.resolve(res([{ id: "r1", full_name: "Asha Recruiter", role: "placement_team" }]));
    return Promise.resolve(res(ROUTING));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("RecruiterRoutingPanel", () => {
  it("lists the rules in routing order with the queue link, and marks an inactive recruiter", async () => {
    server();
    render(<RecruiterRoutingPanel />);
    const table = await screen.findByRole("table", { name: "Routing rules" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows.map((r) => r.textContent)).toEqual([expect.stringContaining("Candidate sourceWebsiteAsha Recruiter"), expect.stringContaining("LocationPuneOld Hand (inactive)")]);
    expect(screen.getByRole("link", { name: "unassigned queue" })).toHaveAttribute("href", "/recruiter/candidates?owner=unassigned");
    expect(screen.getByRole("radio", { name: /Round robin/ })).toBeChecked();
  });

  it("says so when there are no rules", async () => {
    server((url) => (url.endsWith("/candidate-routing") ? res({ ...ROUTING, rules: [] }) : undefined));
    render(<RecruiterRoutingPanel />);
    expect(await screen.findByText(/No rules yet/)).toBeInTheDocument();
  });

  it("offers a retry when the page cannot load", async () => {
    server((url) => (url.endsWith("/candidate-routing") ? res({ detail: "x" }, 500) : undefined));
    render(<RecruiterRoutingPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("We couldn't load candidate routing.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
  });

  it("saves the strategy", async () => {
    const fetchMock = server((url, init) => (init?.method === "PUT" ? res({ ...ROUTING, strategy: "least_workload" }) : undefined));
    render(<RecruiterRoutingPanel />);
    fireEvent.click(await screen.findByRole("radio", { name: /Least workload/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(await screen.findByText("Routing settings saved.")).toBeInTheDocument();
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(String(put[1]!.body))).toEqual({ default_recruiter_user_id: null, strategy: "least_workload" });
  });

  it("adds a location rule and shows a server refusal", async () => {
    let posts = 0;
    const fetchMock = server((_url, init) => {
      if (init?.method !== "POST") return undefined;
      posts += 1;
      return posts === 1 ? res({ id: "x3" }, 201) : res({ detail: "This recruiter already has this rule" }, 409);
    });
    render(<RecruiterRoutingPanel />);
    fireEvent.change(await screen.findByLabelText("Rule type"), { target: { value: "location" } });
    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Pune" } });
    const picker = screen.getByRole("combobox", { name: /Recruiter/ });
    fireEvent.focus(picker);
    fireEvent.change(picker, { target: { value: "Asha" } });
    fireEvent.click(await screen.findByRole("option", { name: /Asha Recruiter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    expect(await screen.findByText("Rule added.")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ kind: "location", location: "Pune", recruiter_user_id: "r1" });

    fireEvent.change(screen.getByLabelText("Location"), { target: { value: "Pune" } });
    fireEvent.focus(screen.getByRole("combobox", { name: /Recruiter/ }));
    fireEvent.change(screen.getByRole("combobox", { name: /Recruiter/ }), { target: { value: "Asha" } });
    fireEvent.click(await screen.findByRole("option", { name: /Asha Recruiter/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add rule" }));
    expect(await screen.findByText("This recruiter already has this rule")).toBeInTheDocument();
  });

  it("deletes a rule after confirming", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const fetchMock = server((_url, init) => (init?.method === "DELETE" ? res(null, 204) : undefined));
    render(<RecruiterRoutingPanel />);
    fireEvent.click(await screen.findByRole("button", { name: /Delete rule Candidate source Website/ }));
    expect(await screen.findByText("Rule deleted.")).toBeInTheDocument();
    await waitFor(() => expect(fetchMock.mock.calls.some(([url, init]) => init?.method === "DELETE" && String(url).endsWith("/rules/x1"))).toBe(true));
  });
});
