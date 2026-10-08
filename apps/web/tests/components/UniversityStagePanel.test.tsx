import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import UniversityStagePanel from "@/components/UniversityStagePanel";
import type { UniversityPipeline } from "@/lib/partnershipPipeline";
import type { University } from "@/lib/universities";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const STAGES = [
  { key: "target_university", label: "Target University", column: "target" },
  { key: "interested", label: "Interested", column: "interested" },
  { key: "meeting_scheduled", label: "Meeting Scheduled", column: "meeting_scheduled" },
];
const pipeline = (stage = "interested", over: Partial<UniversityPipeline> = {}): UniversityPipeline => ({
  stage, stage_label: STAGES.find((s) => s.key === stage)!.label, column: stage, column_label: "Interested", changed_at: "2026-10-08T10:00:00Z",
  lost: null, stages: STAGES, ...over,
});
const perms = { can_edit: true, can_assign: false, can_publish: false, can_deactivate: false, can_move_stage: true, can_reopen: false };
const uni = (p = pipeline(), over: Partial<University["permissions"]> = {}) =>
  ({ id: "u1", name: "ABC", active: true, pipeline: p, permissions: { ...perms, ...over } }) as unknown as University;
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("UniversityStagePanel (upc-007 PS4-PS8)", () => {
  it("lists every stage with its state as text and marks the current one", () => {
    render(<UniversityStagePanel university={uni()} />);
    const list = screen.getByRole("list", { name: "Partnership stages" });
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["✓Target UniversityDone", "•InterestedCurrent", "–Meeting ScheduledUpcoming"]);
    expect(within(list).getByText("Interested").closest("li")).toHaveAttribute("aria-current", "step");
    expect(screen.getByText(/Kanban column/)).toHaveTextContent("Kanban column: Interested");
  });

  it("is read-only without can_move_stage", () => {
    render(<UniversityStagePanel university={uni(pipeline(), { can_move_stage: false })} />);
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.queryByRole("button", { name: /Mark lost|Reopen|Move/ })).toBeNull();
  });

  it("disables the current stage and needs a reason to move back", () => {
    render(<UniversityStagePanel university={uni()} />);
    const select = screen.getByLabelText("Move to") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["Choose a stage", "Target University", "Interested (current)", "Meeting Scheduled"]);
    expect(select.querySelector('option[value="interested"]')).toBeDisabled();
    fireEvent.change(select, { target: { value: "target_university" } });
    expect(screen.getByLabelText("Reason (required when moving back)")).toBeRequired();
    fireEvent.change(select, { target: { value: "meeting_scheduled" } });
    expect(screen.getByLabelText("Note (optional)")).not.toBeRequired();
    // QA7-02 / QA7-03: the select keeps its own height; the Lost button is not stretched across the card
    expect(screen.getByRole("form", { name: "Move stage" })).toHaveStyle({ alignItems: "start" });
    expect(screen.getByRole("button", { name: "Mark lost" })).toHaveStyle({ justifySelf: "start" });
  });

  it("moves, says so and refreshes the page", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ university: { id: "u1" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<UniversityStagePanel university={uni()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting_scheduled" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent("Moved to Meeting Scheduled.");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/u1/stage");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ from_stage: "interested", to_stage: "meeting_scheduled" });
  });

  it("sends nothing twice on a double click", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn(() => new Promise<Response>((r) => { resolve = r; }));
    vi.stubGlobal("fetch", fetchMock);
    render(<UniversityStagePanel university={uni()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting_scheduled" } });
    const form = screen.getByRole("form", { name: "Move stage" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    resolve(res({ university: { id: "u1" } }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("shows a 422 beside its field and a refusal as an alert, keeping the entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "note"], msg: "Add a note to move a university back" }] }, 422)));
    render(<UniversityStagePanel university={uni()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "target_university" } });
    fireEvent.change(screen.getByLabelText("Reason (required when moving back)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(screen.getByLabelText("Reason (required when moving back)")).toHaveAccessibleDescription("Add a note to move a university back"));
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Only the university's partnership managers or their head can change its stage" }, 403)));
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the university's partnership managers");
    expect(screen.getByLabelText("Move to")).toHaveValue("target_university");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("explains a move someone else made meanwhile and shows the page as it is now", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: { message: "This university moved to Proposal Sent meanwhile", code: "stage_changed", current_stage: "proposal_sent" } }, 409)));
    render(<UniversityStagePanel university={uni()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting_scheduled" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This university moved to Proposal Sent meanwhile. Check the stage and try again.");
    expect(refresh).toHaveBeenCalled();
  });

  it("marks lost with a reason, or cancels", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ university: { id: "u1" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<UniversityStagePanel university={uni()} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    expect(screen.getByLabelText("Reason")).toBeRequired();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Reason")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "Chose another agency" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark lost" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/u1/lost");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: "Chose another agency" });
  });

  it("a lost university shows the reason; only can_reopen offers Reopen", async () => {
    const lost = pipeline("interested", { lost: { at: "2026-10-08T10:00:00Z", reason: "Budget freeze" } });
    render(<UniversityStagePanel university={uni(lost)} />);
    expect(screen.getByText(/Marked lost on/)).toHaveTextContent("Budget freeze");
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.queryByRole("button", { name: /Mark lost|Reopen/ })).toBeNull();
    cleanup();
    const fetchMock = vi.fn().mockResolvedValue(res({ university: { id: "u1" } }));
    vi.stubGlobal("fetch", fetchMock);
    render(<UniversityStagePanel university={uni(lost, { can_reopen: true })} />);
    fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "They called back" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, reopen" }));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/partnership/universities/u1/reopen");
  });
});
