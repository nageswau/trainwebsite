import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterCompanyPipeline from "@/components/RecruiterCompanyPipeline";
import RecruiterPipelineBoard from "@/components/RecruiterPipelineBoard";
import RecruiterStageHistory from "@/components/RecruiterStageHistory";
import { RECRUITER_MANAGER_NAV, RECRUITER_NAV, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { Company } from "@/lib/recruiterCompanies";
import { type BoardView, isBackward, type Pipeline } from "@/lib/recruiterPipeline";

const STAGES: [string, string, "start" | "manual" | "driven"][] = [
  ["new_lead", "New Lead", "start"], ["contacted", "Contacted", "manual"], ["interested", "Interested", "manual"],
  ["meeting_scheduled", "Meeting Scheduled", "manual"], ["requirement_discussion", "Requirement Discussion", "manual"],
  ["requirement_received", "Requirement Received", "driven"], ["joined", "Joined", "driven"],
];
function pipeline(stage: string, extra: Partial<Pipeline> = {}): Pipeline {
  const at = STAGES.findIndex(([k]) => k === stage);
  return {
    stage, stage_label: STAGES[at][1], stage_changed_at: "2026-10-08T10:00:00Z", lost: null, can_move: true, can_reopen: false,
    steps: STAGES.map(([key, label, kind], i) => ({ key, label, kind, state: i < at ? "done" : i === at ? "current" : "upcoming" })),
    ...extra,
  };
}
const company = (p: Pipeline) => ({ id: "c1", code: "CMP-000007", name: "ABC", pipeline: p }) as unknown as Company;
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterCompanyPipeline", () => {
  it("shows every stage as text and offers only the manual stages", () => {
    render(<RecruiterCompanyPipeline company={company(pipeline("contacted"))} onChanged={vi.fn()} />);
    const steps = screen.getByRole("list", { name: "Pipeline stages" });
    expect(within(steps).getAllByRole("listitem")).toHaveLength(7);
    expect(within(steps).getByText("Contacted").closest("li")).toHaveAttribute("aria-current", "step");
    const options = within(screen.getByLabelText("Move to")).getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["Choose a stage", "Contacted (current)", "Interested", "Meeting Scheduled", "Requirement Discussion"]);
  });

  it("moves forward and hands the returned company up", async () => {
    const next = company(pipeline("interested"));
    const fetchMock = vi.fn(() => Promise.resolve(res({ company: next })));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<RecruiterCompanyPipeline company={company(pipeline("contacted"))} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "interested" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(next, "Moved to Interested."));
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/recruiter/companies/c1/stage");
    expect(JSON.parse(String(init.body))).toEqual({ from_stage: "contacted", to_stage: "interested" });
  });

  it("asks for a reason when moving back", () => {
    render(<RecruiterCompanyPipeline company={company(pipeline("meeting_scheduled"))} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "contacted" } });
    expect(screen.getByLabelText("Reason (required when moving back)")).toBeRequired();
  });

  it("says the stage follows the requirements once a driven stage is reached", () => {
    render(<RecruiterCompanyPipeline company={company(pipeline("requirement_received"))} onChanged={vi.fn()} />);
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.getByText(/moves with its job requirements/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark lost" })).toBeInTheDocument();
  });

  it("shows the Lost banner and Reopen for a manager, nothing to move", () => {
    const lost = pipeline("interested", { lost: { at: "2026-10-08T10:00:00Z", reason: "Chose a competitor" }, can_move: false, can_reopen: true });
    render(<RecruiterCompanyPipeline company={company(lost)} onChanged={vi.fn()} />);
    expect(screen.getByText(/Chose a competitor/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Move to")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    expect(screen.getByLabelText("Reason")).toBeRequired();
  });

  it("read-only viewers get the stepper only", () => {
    render(<RecruiterCompanyPipeline company={company(pipeline("contacted", { can_move: false }))} onChanged={vi.fn()} />);
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("keeps a refused move's reason and shows the server's words", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: [{ loc: ["body", "reason"], msg: "Value error, Add a reason to move a company back" }] }, 422))));
    render(<RecruiterCompanyPipeline company={company(pipeline("meeting_scheduled"))} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "contacted" } });
    fireEvent.change(screen.getByLabelText("Reason (required when moving back)"), { target: { value: " x " } });
    fireEvent.submit(screen.getByRole("form", { name: "Move stage" }));
    expect(await screen.findByText("Add a reason to move a company back")).toBeInTheDocument();
  });
});

describe("RecruiterStageHistory", () => {
  it("labels system moves and lists the reason", () => {
    const initial = {
      items: [
        { id: "h2", event: "requirement_received", from_stage: "contacted", from_label: "Contacted", to_stage: "requirement_received", to_label: "Requirement Received", reason: null, actor: null, created_at: "2026-10-08T11:00:00Z" },
        { id: "h1", event: "lost", from_stage: "contacted", from_label: "Contacted", to_stage: "contacted", to_label: "Contacted", reason: "No budget", actor: { id: "u1", full_name: "Priya" }, created_at: "2026-10-08T10:00:00Z" },
      ],
      total: 2, limit: 20, offset: 0,
    };
    render(<RecruiterStageHistory companyId="c1" initial={initial} version={0} />);
    expect(screen.getByText("Contacted → Requirement Received")).toBeInTheDocument();
    expect(screen.getByText("By the system (requirement received)")).toBeInTheDocument();
    expect(screen.getByText("Marked lost at Contacted")).toBeInTheDocument();
    expect(screen.getByText("Reason: No budget")).toBeInTheDocument();
  });
});

describe("RecruiterPipelineBoard", () => {
  const view: BoardView = {
    stages: STAGES.map(([key, label, kind]) => ({ key, label, kind, count: key === "contacted" ? 2 : 0 })), lost_count: 1,
    items: [{ id: "c1", code: "CMP-000007", name: "ABC", city: "Pune", priority: "hot", assigned_recruiter: null, stage: "contacted", stage_label: "Contacted", lost: false }],
    total: 1, limit: 50, offset: 0,
  };
  it("renders a tile per stage plus Lost, and the companies as links", () => {
    render(<RecruiterPipelineBoard view={view} href={(c) => `/recruiter/pipeline?stage=${c.stage ?? ""}`} selected="contacted" />);
    const tiles = screen.getByRole("navigation", { name: "Pipeline stages" });
    expect(within(tiles).getAllByRole("link")).toHaveLength(8);
    expect(within(tiles).getByRole("link", { name: /Contacted\s*2/ })).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("link", { name: "ABC" })).toHaveAttribute("href", "/recruiter/companies/c1");
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });
});

describe("helpers and navigation", () => {
  it("knows a backward move", () => {
    expect(isBackward(pipeline("interested"), "contacted")).toBe(true);
    expect(isBackward(pipeline("contacted"), "interested")).toBe(false);
  });
  it("links the board for recruiters, managers and super admin", () => {
    expect(RECRUITER_NAV).toContainEqual({ label: "Pipeline", href: "/recruiter/pipeline" });
    expect(RECRUITER_MANAGER_NAV).toContainEqual({ label: "Pipeline", href: "/recruiter/pipeline" });
    expect(SUPER_ADMIN_NAV).toContainEqual({ label: "Recruiter Pipeline", href: "/recruiter/pipeline" });
  });
});
