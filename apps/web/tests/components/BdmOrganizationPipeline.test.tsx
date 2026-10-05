import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationPipeline from "@/components/BdmOrganizationPipeline";
import type { Organization } from "@/lib/bdmOrganizations";
import type { Pipeline } from "@/lib/bdmPipeline";

const KEYS = [["prospect", "College Prospect", "manual"], ["contacted", "Contacted", "manual"], ["meeting", "Meeting", "manual"], ["placement", "Placement", "volume"]] as const;
const pipeline = (stage = "contacted", over: Partial<Pipeline> = {}): Pipeline => {
  const at = KEYS.findIndex(([k]) => k === stage);
  return {
    stage, stage_label: KEYS[at][1], lost: null, agent_status: null,
    steps: KEYS.map(([key, label, kind], i) => ({ key, label, kind, state: i < at ? "done" : i === at ? "current" : kind === "volume" ? "not_tracked" : "upcoming" })),
    ...over,
  };
};
const org = (p: Pipeline = pipeline(), canEdit = true) =>
  ({ id: "o1", code: "ORG-000001", name: "St Mary", bdm_type: "college", permissions: { can_edit: canEdit, can_archive: canEdit, can_restore: false, can_reassign: false }, pipeline: p }) as unknown as Organization;
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmOrganizationPipeline (bdm-004 §8.2)", () => {
  it("shows every step with its state as text and marks the current one", () => {
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    const steps = screen.getByRole("list", { name: "Pipeline stages" });
    expect(within(steps).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["✓College ProspectDone", "•ContactedCurrent", "–MeetingUpcoming", "–PlacementNot tracked"]);
    expect(within(steps).getByText("Contacted").closest("li")).toHaveAttribute("aria-current", "step");
  });

  it("is read-only without can_edit", () => {
    render(<BdmOrganizationPipeline organization={org(pipeline(), false)} onChanged={vi.fn()} />);
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.queryByRole("button", { name: /Mark lost|Revive|Move/ })).toBeNull();
  });

  it("offers only manual stages, the current one disabled, and needs a reason to move back", () => {
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    const select = screen.getByLabelText("Move to") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["Choose a stage", "College Prospect", "Contacted (current)", "Meeting"]);
    expect(select.querySelector('option[value="contacted"]')).toBeDisabled();
    fireEvent.change(select, { target: { value: "prospect" } });
    expect(screen.getByLabelText("Reason (required when moving back)")).toBeRequired();
    fireEvent.change(select, { target: { value: "meeting" } });
    expect(screen.getByLabelText("Note (optional)")).not.toBeRequired();
  });

  it("moves and reports the new stage", async () => {
    const moved = org(pipeline("meeting"));
    const fetchMock = vi.fn().mockResolvedValue(res({ organization: moved }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(moved, "Moved to Meeting."));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/stage");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ from_stage: "contacted", to_stage: "meeting" });
  });

  it("shows a 422 beside its field", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "note"], msg: "Add a note to move an organization back" }] }, 422)));
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "prospect" } });
    fireEvent.change(screen.getByLabelText("Reason (required when moving back)"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    const note = screen.getByLabelText("Reason (required when moving back)");
    await waitFor(() => expect(note).toHaveAccessibleDescription("Add a note to move an organization back"));
  });

  it("a refusal keeps the choice and note", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Only the assigned BDM can edit this organization" }, 403)));
    render(<BdmOrganizationPipeline organization={org()} onChanged={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.change(screen.getByLabelText("Note (optional)"), { target: { value: "Met the dean" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the assigned BDM can edit this organization");
    expect(screen.getByLabelText("Move to")).toHaveValue("meeting");
    expect(screen.getByLabelText("Note (optional)")).toHaveValue("Met the dean");
  });

  it("a stale move reloads the organization and says where it is now", async () => {
    const fresh = org(pipeline("prospect"));
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(res({ detail: { code: "stage_changed", current_stage: "prospect", message: "This organization moved to College Prospect meanwhile" } }, 409))
      .mockResolvedValueOnce(res({ organization: fresh })));
    const onChanged = vi.fn();
    render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(fresh, "This organization moved to College Prospect meanwhile. Check the stage and try again."));
  });

  it("a retried move that already landed reads as done", async () => {
    const fresh = org(pipeline("meeting"));
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(res({ detail: { code: "stage_changed", current_stage: "meeting", message: "x" } }, 409))
      .mockResolvedValueOnce(res({ organization: fresh })));
    const onChanged = vi.fn();
    render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.change(screen.getByLabelText("Move to"), { target: { value: "meeting" } });
    fireEvent.click(screen.getByRole("button", { name: "Move" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(fresh, "Moved to Meeting."));
  });

  it("marks lost with a reason; a lost organization shows the reason and offers Revive only", async () => {
    const lost = org(pipeline("contacted", { lost: { at: "2026-10-05T10:00:00Z", reason: "No budget" } }));
    const fetchMock = vi.fn().mockResolvedValue(res({ organization: lost }));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    const { rerender } = render(<BdmOrganizationPipeline organization={org()} onChanged={onChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Mark lost" }));
    fireEvent.change(screen.getByLabelText("Reason"), { target: { value: "No budget" } });
    fireEvent.click(screen.getByRole("button", { name: "Yes, mark lost" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(lost, "Marked lost."));
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ reason: "No budget" });
    rerender(<BdmOrganizationPipeline organization={lost} onChanged={onChanged} />);
    expect(screen.getByText(/Marked lost on/)).toHaveTextContent("No budget");
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.getByRole("button", { name: "Revive" })).toBeInTheDocument();
  });

  it("shows the derived agent status", () => {
    render(<BdmOrganizationPipeline organization={org(pipeline("contacted", { agent_status: "Contacted" }))} onChanged={vi.fn()} />);
    expect(screen.getByText("Agent status:")).toHaveTextContent("Agent status: Contacted");
  });
});
