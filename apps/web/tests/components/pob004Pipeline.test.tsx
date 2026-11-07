import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyPipeline from "@/components/RecruiterCompanyPipeline";
import RecruiterPipelineBoard from "@/components/RecruiterPipelineBoard";
import RecruiterStageHistory from "@/components/RecruiterStageHistory";
import { TABS } from "@/lib/recruiterCatalogue";
import type { Company } from "@/lib/recruiterCompanies";
import type { BoardView, Pipeline } from "@/lib/recruiterPipeline";

const STEPS: Pipeline["steps"] = [
  { key: "new_lead", label: "Target Identified", kind: "start", state: "current" },
  { key: "research_completed", label: "Research Completed", kind: "manual", state: "upcoming" },
];
const open: Pipeline = {
  stage: "new_lead", stage_label: "Target Identified", stage_changed_at: "2026-11-01T10:00:00Z", lost: null, inactive: null, client_status: "prospect",
  client_status_label: "Prospect", follow_up_due: false, can_move: true, can_reopen: false, steps: STEPS,
};
const company = (pipeline: Partial<Pipeline> = {}) => ({ id: "c1", pipeline: { ...open, ...pipeline } }) as unknown as Company;
const REASONS = { items: [{ id: "r1", name: "Not hiring at present", active: true, sort_order: 1 }, { id: "r2", name: "No response", active: true, sort_order: 2 }], total: 2, limit: 100, offset: 0 };

function json(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}
function server(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const mock = vi.fn(async (url: string, init?: RequestInit) => handler(String(url), init));
  vi.stubGlobal("fetch", mock);
  return mock;
}
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterCompanyPipeline closing a company", () => {
  it("marks lost with a reason from the list and an optional note", async () => {
    const mock = server((url) => (url.includes("/catalogue/lost-reasons") ? json(REASONS) : json({ company: company() })));
    const onChanged = vi.fn();
    render(<RecruiterCompanyPipeline company={company()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    const select = await screen.findByLabelText("Reason");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Choose a reason", "Not hiring at present", "No response"]);
    expect(screen.getByRole("button", { name: "Yes, mark lost" })).toBeDisabled();
    fireEvent.change(select, { target: { value: "r2" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "Three emails, no reply" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark lost" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.anything(), "Marked lost."));
    const [url, init] = mock.mock.calls.find(([u]) => String(u).endsWith("/c1/lost"))!;
    expect(url).toContain("/api/v1/recruiter/companies/c1/lost");
    expect(JSON.parse(String(init?.body))).toEqual({ reason_id: "r2", note: "Three emails, no reply" });
  });

  it("marks inactive from the inactive list, leaving out an empty note", async () => {
    const mock = server((url) => (url.includes("/catalogue/inactive-reasons") ? json(REASONS) : json({ company: company() })));
    const onChanged = vi.fn();
    render(<RecruiterCompanyPipeline company={company()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark inactive" }));
    fireEvent.change(await screen.findByLabelText("Reason"), { target: { value: "r1" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark inactive" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.anything(), "Marked inactive."));
    const [, init] = mock.mock.calls.find(([u]) => String(u).endsWith("/c1/inactive"))!;
    expect(JSON.parse(String(init?.body))).toEqual({ reason_id: "r1" });
  });

  it("says when the reasons cannot load and retries", async () => {
    let calls = 0;
    server(() => (++calls === 1 ? json({ detail: "No" }, 500) : json(REASONS)));
    render(<RecruiterCompanyPipeline company={company()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load the reasons.");
    expect(screen.getByRole("button", { name: "Yes, mark lost" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByLabelText("Reason")).toBeInTheDocument();
  });

  it("says when the list is empty", async () => {
    server(() => json({ items: [], total: 0, limit: 100, offset: 0 }));
    render(<RecruiterCompanyPipeline company={company()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark inactive" }));
    expect(await screen.findByText(/Ask a placement manager to add one/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yes, mark inactive" })).toBeDisabled();
  });

  it("shows a refused reason on its field and keeps what was typed", async () => {
    server((url) => (url.includes("/catalogue/") ? json(REASONS)
      : json({ detail: [{ loc: ["body", "reason_id"], msg: "Choose a reason from the list" }] }, 422)));
    render(<RecruiterCompanyPipeline company={company()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    fireEvent.change(await screen.findByLabelText("Reason"), { target: { value: "r1" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "Keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark lost" }));
    expect(await screen.findByText("Choose a reason from the list")).toBeInTheDocument();
    expect(screen.getByLabelText("Note (optional)")).toHaveValue("Keep me");
  });

  it("cancel closes the form without a request to change anything", async () => {
    const mock = server(() => json(REASONS));
    render(<RecruiterCompanyPipeline company={company()} onChanged={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark inactive" }));
    await screen.findByLabelText("Reason");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Reason")).not.toBeInTheDocument();
    expect(mock.mock.calls.every(([, init]) => (init?.method ?? "GET") === "GET")).toBe(true);
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Mark inactive" })));
  });
});

describe("RecruiterCompanyPipeline status", () => {
  it("shows an inactive company's reason, and a manager's Reopen with a typed reason", async () => {
    const mock = server(() => json({ company: company() }));
    const onChanged = vi.fn();
    render(<RecruiterCompanyPipeline company={company({ inactive: { at: "2026-11-02T10:00:00Z", reason: "No current hiring" }, can_move: false, can_reopen: true })} onChanged={onChanged} />);
    expect(screen.getByText(/Marked inactive on/)).toHaveTextContent("No current hiring");
    expect(screen.queryByRole("button", { name: "Mark lost" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark inactive" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Hiring again" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, reopen" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.anything(), "Reopened."));
    expect(JSON.parse(String(mock.mock.calls[0][1]?.body))).toEqual({ reason: "Hiring again" });
  });

  it("a recruiter on an inactive company has no actions", () => {
    render(<RecruiterCompanyPipeline company={company({ inactive: { at: "2026-11-02T10:00:00Z", reason: "No response" }, can_move: false })} onChanged={vi.fn()} />);
    expect(screen.queryAllByRole("button")).toHaveLength(0);
  });

  it("shows the client status and a due follow-up as text; a prospect gets no badge", () => {
    render(<RecruiterCompanyPipeline company={company({ client_status: "active_client", client_status_label: "Active Client", follow_up_due: true })} onChanged={vi.fn()} />);
    expect(screen.getByText("Active Client")).toBeInTheDocument();
    expect(screen.getByText("Follow-up due")).toBeInTheDocument();
    cleanup();
    render(<RecruiterCompanyPipeline company={company()} onChanged={vi.fn()} />);
    expect(screen.queryByText("Prospect")).not.toBeInTheDocument();
    expect(screen.queryByText("Follow-up due")).not.toBeInTheDocument();
  });
});

describe("RecruiterPipelineBoard buckets", () => {
  const view: BoardView = {
    stages: [{ key: "new_lead", label: "Target Identified", kind: "start", count: 1 }],
    buckets: [
      { key: "active_client", label: "Active Client", count: 1 }, { key: "repeat_business", label: "Repeat Business", count: 0 },
      { key: "follow_up_due", label: "Follow-up Due", count: 1 }, { key: "inactive", label: "Inactive", count: 2 }, { key: "lost", label: "Lost", count: 3 },
    ],
    lost_count: 3,
    items: [{ id: "c1", code: "CMP-1", name: "ABC", city: null, priority: null, assigned_recruiter: null, stage: "new_lead", stage_label: "Target Identified", lost: false, inactive: true,
      client_status: "active_client", client_status_label: "Active Client", follow_up_due: true }],
    total: 1, limit: 50, offset: 0,
  };
  it("offers a filter tile per bucket after the stages and names the selected one", () => {
    render(<RecruiterPipelineBoard view={view} href={(c) => `?stage=${c.stage ?? ""}`} selected="inactive" />);
    const tiles = screen.getByRole("navigation", { name: "Pipeline stages" });
    expect(within(tiles).getAllByRole("link").map((l) => l.querySelector("span")?.textContent)).toEqual(["Target Identified", "Active Client", "Repeat Business", "Follow-up Due", "Inactive", "Lost"]);
    expect(within(tiles).getByRole("link", { name: /Inactive\s*2/ })).toHaveAttribute("href", "?stage=inactive");
    expect(screen.getByRole("heading", { name: "Inactive" })).toBeInTheDocument();
  });
  it("marks a row's status as text", () => {
    render(<RecruiterPipelineBoard view={view} href={() => "#"} selected={null} />);
    const cell = screen.getByRole("cell", { name: /Target Identified/ });
    expect(cell).toHaveTextContent("Inactive");
    expect(cell).toHaveTextContent("Active Client");
    expect(cell).toHaveTextContent("Follow-up due");
  });
});

describe("the wording of pob-004's history rows", () => {
  const row = (event: string) => ({ id: event, event, from_stage: "contacted", from_label: "Outreach Sent", to_stage: "contacted", to_label: "Outreach Sent", reason: null, actor: null, created_at: "2026-11-01T10:00:00Z" });
  it("names each event instead of a same-stage arrow", () => {
    const items = [row("inactive"), row("active_client"), row("repeat_business")];
    render(<RecruiterStageHistory companyId="c1" version={0} initial={{ items, total: 3, limit: 20, offset: 0 }} />);
    expect(screen.getByText("Marked inactive at Outreach Sent")).toBeInTheDocument();
    expect(screen.getByText("Became an active client at Outreach Sent")).toBeInTheDocument();
    expect(screen.getByText("Became repeat business at Outreach Sent")).toBeInTheDocument();
  });
});

describe("the reason catalogues", () => {
  it("are manager tabs", () => {
    expect(TABS["lost-reasons"].label).toBe("Lost reasons");
    expect(TABS["inactive-reasons"].label).toBe("Inactive reasons");
  });
});
