import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmOrganizationMou from "@/components/BdmOrganizationMou";
import { mou, res } from "./BdmMouFixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const card = (initial: Parameters<typeof BdmOrganizationMou>[0]["initial"], extra: Partial<Parameters<typeof BdmOrganizationMou>[0]> = {}) =>
  render(<BdmOrganizationMou orgId="o1" initial={initial} onNotice={vi.fn()} onPipelineChanged={vi.fn()} {...extra} />);

describe("BdmOrganizationMou (bdm-005 §8)", () => {
  it("offers Start MoU when there is none and the caller may start one", () => {
    card({ current: null, can_start: true });
    expect(screen.getByText("No MoU yet.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start MoU" }));
    expect(screen.getByRole("form", { name: "Start MoU" })).toBeInTheDocument();
  });

  it("is read-only without rights", () => {
    card({ current: mou("prospect", { permissions: { can_edit: false, can_upload: false, can_renew: false } }), can_start: false });
    expect(screen.queryByRole("button", { name: /Edit MoU|Start MoU|Start renewal/ })).toBeNull();
    card({ current: null, can_start: false });
    expect(screen.queryByRole("button", { name: "Start MoU" })).toBeNull();
  });

  it("explains a failed first load and tries again", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ current: mou(), can_start: false })));
    card(null);
    expect(screen.getByRole("alert")).toHaveTextContent("Unable to load the MoU.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getByText("MOU-14")).toBeInTheDocument());
  });

  it("shows the status as text with the current step marked, and the details", () => {
    card({ current: mou("proposal_sent", { proposal_sent_on: "2026-10-01" }), can_start: false });
    const steps = screen.getByRole("list", { name: "MoU statuses" });
    const current = within(steps).getByText("Proposal Sent").closest("li");
    expect(current).toHaveAttribute("aria-current", "step");
    expect(current).toHaveTextContent("Current");
    expect(within(steps).getAllByRole("listitem")).toHaveLength(7);
    expect(screen.getByText("Met the dean")).toBeInTheDocument();
  });

  it("names an expired MoU's outcome and offers a renewal behind a confirmation", async () => {
    const expired = mou("expired", { signed_on: "2025-10-01", valid_from: "2025-10-01", valid_until: "2026-10-05", expired_on: "2026-10-06", permissions: { can_edit: true, can_upload: true, can_renew: true } });
    const fresh = mou("prospect", { id: "m2", reference: null });
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ mou: fresh }, 201)).mockResolvedValueOnce(res({ current: fresh, can_start: false }));
    vi.stubGlobal("fetch", fetchMock);
    const onNotice = vi.fn();
    card({ current: expired, can_start: true }, { onNotice });
    expect(screen.getByText(/Expired on/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Start renewal" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm renewal" })).getByRole("button", { name: "Yes, start renewal" }));
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("Renewal started."));
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/bdm/organizations/o1/mou");
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
  });

  it("tells the page when signing moved the pipeline", async () => {
    const before = mou("under_negotiation");
    const after = mou("signed", { signed_on: "2026-10-06", pipeline_on_sign: null });
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ mou: after })).mockResolvedValueOnce(res({ current: after, can_start: false })));
    const onNotice = vi.fn();
    const onPipelineChanged = vi.fn();
    card({ current: before, can_start: false }, { onNotice, onPipelineChanged });
    fireEvent.click(screen.getByRole("button", { name: "Edit MoU" }));
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "signed" } });
    fireEvent.change(screen.getByLabelText("Signed date (required)"), { target: { value: "2026-10-06" } });
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm signing" })).getByRole("button", { name: "Yes, save" }));
    await waitFor(() => expect(onPipelineChanged).toHaveBeenCalled());
    expect(onNotice).toHaveBeenCalledWith("MoU saved. The pipeline moved to MoU Signed.");
  });
});
