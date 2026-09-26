import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolEditPanel from "@/components/AdminSchoolEditPanel";

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

function stubFetch(responses: Response[]) {
  const mock = vi.fn();
  responses.forEach((r) => mock.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolEditPanel", () => {
  it("looks up a school by code, then patches the fields the admin changes", async () => {
    stubFetch([
      json({ id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School", branch: null, board: null }, 200),
      json({ id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School", branch: "North Campus", board: "CBSE" }, 200),
    ]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Branch");

    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North Campus" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/updated/i);
  });

  it("sends an explicit null for a cleared field and omits the fields that did not change", async () => {
    const loaded = {
      id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School",
      branch: "North Campus", address: "1 Main Street", contact_number: "0123456789",
      email: "school@example.local", website: "https://example.local", grades_available: "1-12",
      board: "CBSE", partnership_date: "2026-01-01", mou_reference: "MOU-1",
      edusphere_bdm: "A Manager", monthly_visit_schedule: "First Monday", vice_principal_name: "A Deputy",
    };
    const mock = stubFetch([json(loaded, 200), json({ ...loaded, branch: null }, 200)]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Branch");

    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/updated/i);

    const body = JSON.parse(mock.mock.calls[1][1].body);
    // The cleared field is sent as an explicit null (never omitted -- otherwise it can never
    // be cleared), and nothing else is sent, so `changed_fields` stays accurate.
    expect(body).toEqual({ branch: null });
  });

  it("shows a not-found message for an unknown code", async () => {
    stubFetch([json({ detail: "No school found with that School ID" }, 404)]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ZZZZZZZZ" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    const outcome = await screen.findByText("No school found with that School ID");
    expect(outcome).toHaveClass("form-error");
  });

  const ID = "11111111-1111-1111-1111-111111111111";
  const base = { id: ID, school_code: "ABCD1234", name: "Test School", branch: null, tier: "platinum", tier_valid_until: null };
  const downgrade = { direction: "downgrade", from_tier: "platinum", to_tier: "gold", gained: [], lost: [{ key: "visa_support", label: "Visa support" }] };
  const upgrade = { direction: "upgrade", from_tier: "gold", to_tier: "platinum", gained: [{ key: "visa_support", label: "Visa support" }], lost: [] };

  async function lookUp() {
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Partnership tier");
  }

  async function askToDowngrade(to = "gold") {
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: to } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    return screen.findByRole("button", { name: "Confirm downgrade" });
  }

  it("groups the tier under Partnership and explains the current tier", async () => {
    stubFetch([json(base, 200)]);
    await lookUp();
    const group = screen.getByRole("group", { name: "Partnership" });
    expect(within(group).getByLabelText("Partnership tier")).toHaveAccessibleDescription("Currently Platinum. Changing it notifies the school; a downgrade asks you to confirm first.");
    expect(within(group).getByLabelText("Valid until")).toHaveAccessibleDescription("Leave empty for no end date.");
  });

  it("saves an upgrade straight away, names what became available and focuses the outcome", async () => {
    const mock = stubFetch([json({ ...base, tier: "gold" }, 200), json(upgrade, 200), json({ ...base, tier_change: upgrade }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "platinum" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const outcome = await screen.findByText("School profile updated. Partnership is now Platinum; newly available: Visa support.");
    await waitFor(() => expect(outcome).toHaveFocus());
    expect(mock.mock.calls[1][0]).toBe(`/api/v1/overseas-admin/schools/${ID}/tier-change-preview?tier=platinum`);
    expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({ tier: "platinum", expected_tier: "gold" });
  });

  it("asks before a downgrade and saves only on confirm", async () => {
    const mock = stubFetch([json(base, 200), json(downgrade, 200), json({ ...base, tier: "gold", tier_change: downgrade }, 200)]);
    await lookUp();
    const confirm = await askToDowngrade();
    expect(confirm).toHaveFocus();
    expect(within(screen.getByRole("group", { name: "Downgrading Test School from Platinum to Gold." })).getByRole("listitem")).toHaveTextContent("Visa support");
    expect(mock).toHaveBeenCalledTimes(2);
    fireEvent.click(confirm);
    const outcome = await screen.findByText("School profile updated. Partnership is now Gold.");
    await waitFor(() => expect(outcome).toHaveFocus());
    expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({ tier: "gold", expected_tier: "platinum" });
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
  });

  it("Escape cancels, keeps the input, saves nothing and returns focus to Save", async () => {
    const mock = stubFetch([json(base, 200), json(downgrade, 200)]);
    await lookUp();
    fireEvent.keyDown(await askToDowngrade(), { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
    expect((screen.getByLabelText("Partnership tier") as HTMLSelectElement).value).toBe("gold");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toHaveFocus());
    expect(mock).toHaveBeenCalledTimes(2);
  });

  it("Cancel does the same as Escape", async () => {
    stubFetch([json(base, 200), json(downgrade, 200)]);
    await lookUp();
    await askToDowngrade();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toHaveFocus());
  });

  it("editing the form after the confirmation clears it", async () => {
    stubFetch([json(base, 200), json(downgrade, 200)]);
    await lookUp();
    await askToDowngrade();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
  });

  it("removing the tier asks for confirmation", async () => {
    const removal = { ...downgrade, to_tier: null };
    const mock = stubFetch([json(base, 200), json(removal, 200), json({ ...base, tier: null, tier_change: removal }, 200)]);
    await lookUp();
    fireEvent.click(await askToDowngrade(""));
    expect(mock.mock.calls[1][0]).toBe(`/api/v1/overseas-admin/schools/${ID}/tier-change-preview?tier=`);
    await screen.findByText("School profile updated. Partnership is now no partnership tier.");
    expect(JSON.parse(mock.mock.calls[2][1].body)).toEqual({ tier: null, expected_tier: "platinum" });
  });

  it("a tier changed by someone else since lookup is a focused 409 alert and keeps the input", async () => {
    const stale = "This school's tier changed to Silver since you looked it up. Look it up again before changing the tier.";
    stubFetch([json(base, 200), json(downgrade, 200), json({ detail: stale }, 409)]);
    await lookUp();
    fireEvent.click(await askToDowngrade());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(stale);
    await waitFor(() => expect(alert).toHaveFocus());
    expect(screen.queryByRole("button", { name: "Confirm downgrade" })).toBeNull();
    expect((screen.getByLabelText("Partnership tier") as HTMLSelectElement).value).toBe("gold");
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("a failed preview is an alert, saves nothing and frees the button", async () => {
    const mock = stubFetch([json(base, 200), json({ detail: "Overseas Admin role required" }, 403)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Overseas Admin role required");
    expect(mock).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("a network failure during the preview says nothing was saved", async () => {
    const mock = vi.fn().mockResolvedValueOnce(json(base, 200)).mockRejectedValueOnce(new TypeError("offline"));
    vi.stubGlobal("fetch", mock);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Network error -- nothing was saved. Check your connection and try again.");
    expect(screen.getByRole("button", { name: "Save changes" })).not.toBeDisabled();
  });

  it("shows the checking state and marks the form busy while the preview runs", async () => {
    let release!: (r: Response) => void;
    const mock = vi.fn().mockResolvedValueOnce(json(base, 200)).mockReturnValueOnce(new Promise<Response>((r) => { release = r; }));
    vi.stubGlobal("fetch", mock);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Partnership tier"), { target: { value: "gold" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const checking = await screen.findByRole("button", { name: "Checking tier change…" });
    expect(checking).toBeDisabled();
    expect(checking.closest("form")).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText("Partnership tier")).toBeDisabled();
    expect(screen.getByLabelText("Branch")).toBeDisabled();
    release(json(downgrade, 200));
    await screen.findByRole("button", { name: "Confirm downgrade" });
    expect(screen.getByLabelText("Partnership tier")).not.toBeDisabled();
  });

  it("an untouched tier is never sent and needs no preview", async () => {
    const mock = stubFetch([json({ ...base, tier_valid_until: "2027-01-01" }, 200), json({ ...base, branch: "North", tier_change: null }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("School profile updated.");
    expect(mock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ branch: "North" });
  });

  it("a legacy school stored with tier \"\" sends no tier and needs no preview on an untouched edit", async () => {
    const mock = stubFetch([json({ ...base, tier: "" }, 200), json({ ...base, tier: "", branch: "North", tier_change: null }, 200)]);
    await lookUp();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText("School profile updated.");
    expect(mock).toHaveBeenCalledTimes(2);
    expect(JSON.parse(mock.mock.calls[1][1].body)).toEqual({ branch: "North" });
  });
});

// QA-023-04 / QA-023-05 (browser QA 2026-09-25): save outcomes say exactly what happened.
describe("AdminSchoolEditPanel save outcomes", () => {
  const loaded = { id: "22222222-2222-2222-2222-222222222222", school_code: "QA000001", name: "QA School", branch: null, tier: "gold", tier_valid_until: null };

  async function open() {
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "QA000001" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Partnership tier");
  }

  it("saving with nothing changed says so and sends no request", async () => {
    const mock = stubFetch([json(loaded, 200)]);
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    const status = await screen.findByText("No changes to save.");
    expect(status).toHaveAttribute("role", "status");
    expect(mock).toHaveBeenCalledTimes(1);
  });

  it("a rejected save says it was not saved", async () => {
    stubFetch([json(loaded, 200), json({ detail: "Enter a valid email address" }, 422)]);
    await open();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Not saved: Enter a valid email address");
  });

  it("a server error on save says the save could not be confirmed", async () => {
    stubFetch([json(loaded, 200), new Response("Internal Server Error", { status: 500 })]);
    await open();
    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The save could not be confirmed. Look the school up again to check before retrying.");
  });
});
