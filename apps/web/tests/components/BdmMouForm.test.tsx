import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmMouForm from "@/components/BdmMouForm";
import { mou, res } from "./BdmMouFixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const form = (props: Partial<Parameters<typeof BdmMouForm>[0]> = {}) => {
  const handlers = { onSaved: vi.fn(), onCancel: vi.fn(), onConflict: vi.fn() };
  render(<BdmMouForm orgId="o1" mou={mou()} {...handlers} {...props} />);
  return handlers;
};

describe("BdmMouForm (bdm-005 §8)", () => {
  it("offers the eight settable statuses, never Expired", () => {
    form();
    const options = [...(screen.getByLabelText("Status") as HTMLSelectElement).options].map((o) => o.textContent);
    expect(options).toEqual(["Prospect", "Discussion Started", "Proposal Sent", "Under Negotiation", "Draft Shared", "Signed", "Active", "Rejected"]);
  });

  it("marks the dates a status needs as required", () => {
    form();
    expect(screen.getByLabelText("Signed date")).not.toBeRequired();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "signed" } });
    expect(screen.getByLabelText("Signed date (required)")).toBeRequired();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "active" } });
    expect(screen.getByLabelText("Valid from (required)")).toBeRequired();
    expect(screen.getByLabelText("Valid until (required)")).toBeRequired();
  });

  it("creates with only the filled fields", async () => {
    const created = mou();
    const fetchMock = vi.fn().mockResolvedValue(res({ mou: created }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const { onSaved } = form({ mou: null });
    fireEvent.change(screen.getByLabelText("Reference"), { target: { value: "MOU-14" } });
    fireEvent.click(screen.getByRole("button", { name: "Start MoU" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(created));
    expect(fetchMock.mock.calls[0][1].method).toBe("POST");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ status: "prospect", reference: "MOU-14" });
  });

  it("sends only what changed, with the status it was showing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ mou: mou("discussion_started") }));
    vi.stubGlobal("fetch", fetchMock);
    form();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "discussion_started" } });
    fireEvent.change(screen.getByLabelText("Notes"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ status: "discussion_started", from_status: "prospect", notes: null, expected_updated_at: "2026-10-01T10:00:00Z" });
  });

  it("QA5-02: Not yet and Escape return focus to Save MoU", async () => {
    vi.stubGlobal("fetch", vi.fn());
    form();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "signed" } });
    fireEvent.change(screen.getByLabelText("Signed date (required)"), { target: { value: "2026-10-06" } });
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    fireEvent.click(within(screen.getByRole("group", { name: "Confirm signing" })).getByRole("button", { name: "Not yet" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save MoU" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    fireEvent.keyDown(screen.getByRole("group", { name: "Confirm signing" }), { key: "Escape" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Save MoU" })).toHaveFocus());
  });

  it("puts a 422 on its field and focuses it", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "signed_on"], msg: "Add the signed date" }] }, 422)));
    form({ mou: mou("rejected", { pipeline_on_sign: null }) });
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "signed" } });
    const field = screen.getByLabelText("Signed date (required)");
    fireEvent.change(field, { target: { value: "2026-10-06" } }); // the browser's own required check would stop an empty one first
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    await waitFor(() => expect(field).toHaveAccessibleDescription("Add the signed date"));
    await waitFor(() => expect(field).toHaveFocus());
  });

  it("asks before a signing that moves the pipeline, and can be cancelled", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    form();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "signed" } });
    fireEvent.change(screen.getByLabelText("Signed date (required)"), { target: { value: "2026-10-06" } });
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    const group = screen.getByRole("group", { name: "Confirm signing" });
    expect(group).toHaveTextContent("This also moves the pipeline to MoU Signed.");
    fireEvent.click(within(group).getByRole("button", { name: "Not yet" }));
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("hands a 409 conflict to the card", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: { code: "mou_status_changed", message: "This MoU moved to Signed meanwhile", current_status: "signed" } }, 409)));
    const { onConflict } = form();
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "rejected" } });
    fireEvent.click(screen.getByRole("button", { name: "Save MoU" }));
    await waitFor(() => expect(onConflict).toHaveBeenCalledWith("This MoU moved to Signed meanwhile."));
  });

  it("locks the status of an expired MoU and still allows a date correction", () => {
    form({ mou: mou("expired", { valid_until: "2026-10-05", signed_on: "2025-10-01", valid_from: "2025-10-01" }) });
    expect(screen.getByLabelText("Status")).toBeDisabled();
    expect(screen.getByText("Expired. Start a renewal to change the status, or correct the valid-until date.")).toBeInTheDocument();
    expect(screen.getByLabelText("Valid until")).toBeEnabled();
  });
});
