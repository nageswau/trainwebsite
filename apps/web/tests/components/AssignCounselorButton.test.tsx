import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssignCounselorButton, { clearCounselorListCache } from "@/components/AssignCounselorButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  clearCounselorListCache();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const USERS = [
  { id: "c1", name: "Asha Rao", division: "overseas", active: true },
  { id: "c2", name: "Old Hand", division: "overseas", active: false },
  { id: "c3", name: "IT Person", division: "it", active: true },
];

function stub(put: () => Promise<unknown>) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? put() : json(200, USERS)));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("AssignCounselorButton", () => {
  it("lists active overseas counselors only and assigns one", async () => {
    const fetchMock = stub(() => json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha Rao", changed: true }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Choose…", "Asha Rao"]);
    fireEvent.change(select, { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha Rao assigned.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workflows/overseas/applications/a1/counselor", expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c1" }) }));
    expect(refresh).toHaveBeenCalled();
  });

  it("reads Change counsellor when one is set, with no clear option", async () => {
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(select.value).toBe("c1");
    expect(Array.from(select.options).some((o) => o.value === "" && o.textContent !== "Choose…")).toBe(false);
  });

  it("shows the API's refusal", async () => {
    stub(() => json(409, { detail: "This application is closed" }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    fireEvent.change(await screen.findByLabelText("EduSphere counsellor"), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This application is closed");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("shows an alert, disables Save and sends no PUT when the list fails to load", async () => {
    const fetchMock = vi.fn<(url: string, init?: RequestInit) => Promise<unknown>>(() => json(500, {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't load the counsellors -- try again.");
    expect(screen.queryByLabelText("EduSphere counsellor")).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("says so when there are no active overseas counsellors", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(200, [])));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    expect(await screen.findByText("No active overseas counsellors.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("names the counsellor from the API response, not the loaded list", async () => {  // F3
    stub(() => json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha R. Rao", changed: true }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    fireEvent.change(await screen.findByLabelText("EduSphere counsellor"), { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha R. Rao assigned.");
  });

  it("focuses the select on open, and Cancel closes and refocuses the button", async () => {  // F2
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const select = await screen.findByLabelText("EduSphere counsellor");
    await waitFor(() => expect(document.activeElement).toBe(select));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByLabelText("EduSphere counsellor")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Assign counsellor" }));
  });

  it("focuses the alert when the list fails to load", async () => {  // F2
    vi.stubGlobal("fetch", vi.fn(() => json(500, {})));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(document.activeElement).toBe(alert));
  });

  it("Escape closes the form and refocuses the button", async () => {  // F2
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const select = await screen.findByLabelText("EduSphere counsellor");
    fireEvent.keyDown(select, { key: "Escape" });
    expect(screen.queryByLabelText("EduSphere counsellor")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Change counsellor" }));
  });

  it("Escape does nothing while a save is in flight, and Save success refocuses the button", async () => {  // F2
    let finish: (value: unknown) => void = () => {};
    stub(() => new Promise((resolve) => { finish = resolve; }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const select = await screen.findByLabelText("EduSphere counsellor");
    fireEvent.change(select, { target: { value: "c1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Saving…" });
    fireEvent.keyDown(select, { key: "Escape" });
    expect(screen.getByLabelText("EduSphere counsellor")).toBeInTheDocument();
    finish(await json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha Rao", changed: true }));
    await screen.findByRole("status");
    expect(screen.queryByLabelText("EduSphere counsellor")).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Assign counsellor" })));
  });

  it("fetches the counsellor list once for two buttons", async () => {  // F5
    const fetchMock = stub(() => json(200, {}));
    render(<><AssignCounselorButton applicationId="a1" currentId={null} /><AssignCounselorButton applicationId="a2" currentId={null} /></>);
    const [first, second] = screen.getAllByRole("button", { name: "Assign counsellor" });
    fireEvent.click(first);
    await screen.findByLabelText("EduSphere counsellor");
    fireEvent.click(second);
    await waitFor(() => expect(screen.getAllByLabelText("EduSphere counsellor")).toHaveLength(2));
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/v1/admin/users?role=counselor")).toHaveLength(1);
  });

  it("retries a failed load on the next open", async () => {  // F5
    let calls = 0;
    const fetchMock = vi.fn(() => (++calls === 1 ? json(500, {}) : json(200, USERS)));
    vi.stubGlobal("fetch", fetchMock);
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    expect(await screen.findByLabelText("EduSphere counsellor")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("a slow first load that resolves after close does not overwrite a reopened form", async () => {  // F5
    let release: (value: unknown) => void = () => {};
    let calls = 0;
    vi.stubGlobal("fetch", vi.fn(() => (++calls === 1 ? new Promise((resolve) => { release = resolve; }) : json(200, [USERS[0]]))));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    clearCounselorListCache();
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const select = (await screen.findByLabelText("EduSphere counsellor")) as HTMLSelectElement;
    expect(Array.from(select.options).map((o) => o.textContent)).toEqual(["Choose…", "Asha Rao"]);
    release(await json(200, [{ id: "c9", name: "Stale One", division: "overseas", active: true }]));
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(Array.from((screen.getByLabelText("EduSphere counsellor") as HTMLSelectElement).options).map((o) => o.textContent)).toEqual(["Choose…", "Asha Rao"]);
  });
});
