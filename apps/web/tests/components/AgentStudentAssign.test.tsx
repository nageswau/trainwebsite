import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentAssign from "@/components/AgentStudentAssign";

const student = (over: Record<string, unknown> = {}) => ({
  id: "s1", has_login: false, full_name: "Asha Rao", email: null, phone: null, preferred_country: null, preferred_intake: null,
  status: "active" as const, assigned_to: null, created_at: "", ...over,
});
const staff = (id: string, code: string, full_name: string, status = "active") => ({ id, code, full_name, email: `${id}@x.com`, phone: null, status, setup: null });
const STAFF = { items: [staff("m1", "EDU-S001", "Priya Nair"), staff("m2", "EDU-S002", "Old Hand", "deactivated"), staff("m3", "EDU-S003", "Ravi Iyer")], total: 3, limit: 100, offset: 0 };
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function open(onAssigned = vi.fn(), over: Record<string, unknown> = {}) {
  render(<AgentStudentAssign student={student(over)} onAssigned={onAssigned} />);
  fireEvent.click(screen.getByRole("button", { name: "Assign Asha Rao" }));
  return screen.findByLabelText("Assign to");
}

describe("AgentStudentAssign (AGN-004 AC09, spec §6)", () => {
  it("offers Unassigned and the agency's active staff only, fetched when opened", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(STAFF)));
    vi.stubGlobal("fetch", fetchMock);
    const select = (await open()) as HTMLSelectElement;
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workflows/overseas/agent/team/staff?limit=100");
    await waitFor(() => expect(select.options).toHaveLength(3));
    expect([...select.options].map((o) => o.textContent)).toEqual(["Unassigned", "EDU-S001 · Priya Nair", "EDU-S003 · Ravi Iyer"]);
    expect(select.value).toBe("");
  });

  it("moves keyboard focus into the choice once the staff list has loaded (browser check)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(STAFF))));
    const select = (await open()) as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(3));
    await waitFor(() => expect(select).toHaveFocus());
  });

  it("starts on the current assignee, and Save waits for a different choice", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(STAFF))));
    const select = (await open(vi.fn(), { assigned_to: { id: "m1", code: "EDU-S001", full_name: "Priya Nair", status: "active" } })) as HTMLSelectElement;
    await waitFor(() => expect(select.value).toBe("m1"));
    expect(screen.getByRole("button", { name: "Save assignment" })).toBeDisabled();
    fireEvent.change(select, { target: { value: "m3" } });
    expect(screen.getByRole("button", { name: "Save assignment" })).toBeEnabled();
  });

  it("shows a deactivated assignee as the current, unselectable choice (G5)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(STAFF))));
    const select = (await open(vi.fn(), { assigned_to: { id: "m2", code: "EDU-S002", full_name: "Old Hand", status: "deactivated" } })) as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(4));
    const old = [...select.options].find((o) => o.value === "m2")!;
    expect(old.textContent).toBe("EDU-S002 · Old Hand (deactivated)");
    expect(old.disabled).toBe(true);
    expect(select.value).toBe("m2");
    expect(screen.getByRole("button", { name: "Save assignment" })).toBeDisabled();
  });

  it("saves the chosen staff member and hands back the updated student", async () => {
    const updated = { ...student(), assigned_to: { id: "m3", code: "EDU-S003", full_name: "Ravi Iyer", status: "active" } };
    const fetchMock = vi.fn().mockResolvedValueOnce(res(STAFF)).mockResolvedValueOnce(res({ student: updated }));
    vi.stubGlobal("fetch", fetchMock);
    const onAssigned = vi.fn();
    const select = await open(onAssigned);
    await waitFor(() => expect((select as HTMLSelectElement).options).toHaveLength(3));
    fireEvent.change(select, { target: { value: "m3" } });
    fireEvent.click(screen.getByRole("button", { name: "Save assignment" }));
    await waitFor(() => expect(onAssigned).toHaveBeenCalledWith(updated));
    expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/workflows/overseas/agent/crm/students/s1/assign", expect.objectContaining({ method: "POST", body: JSON.stringify({ member_id: "m3" }) }));
  });

  it("unassigns with member_id null", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res(STAFF)).mockResolvedValueOnce(res({ student: student() }));
    vi.stubGlobal("fetch", fetchMock);
    const select = await open(vi.fn(), { assigned_to: { id: "m1", code: "EDU-S001", full_name: "Priya Nair", status: "active" } });
    await waitFor(() => expect((select as HTMLSelectElement).value).toBe("m1"));
    fireEvent.change(select, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save assignment" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    expect(fetchMock.mock.calls[1][1]).toMatchObject({ body: JSON.stringify({ member_id: null }) });
  });

  it("keeps the choice open and shows the server's reason when refused", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res(STAFF)).mockResolvedValueOnce(res({ detail: "Choose an active Staff member of this agency" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    const onAssigned = vi.fn();
    const select = await open(onAssigned);
    await waitFor(() => expect((select as HTMLSelectElement).options).toHaveLength(3));
    fireEvent.change(select, { target: { value: "m1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save assignment" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Choose an active Staff member of this agency");
    expect(screen.getByLabelText("Assign to")).toBeInTheDocument();
    expect(onAssigned).not.toHaveBeenCalled();
  });

  it("says when the staff list cannot load and offers Retry; Save stays off", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(STAFF));
    vi.stubGlobal("fetch", fetchMock);
    await open();
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load your staff.");
    expect(screen.getByRole("button", { name: "Save assignment" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Retry loading staff" }));
    await waitFor(() => expect((screen.getByLabelText("Assign to") as HTMLSelectElement).options).toHaveLength(3));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("Cancel closes the choice and returns focus to Assign", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(STAFF))));
    await open();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("Assign to")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Assign Asha Rao" })).toHaveFocus());
  });
});
