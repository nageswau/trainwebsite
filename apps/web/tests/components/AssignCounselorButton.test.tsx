import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AssignCounselorButton from "@/components/AssignCounselorButton";

const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const LOOKUP = "/api/v1/lookups/overseas-counselors";
const PAGE = { items: [{ id: "c1", label: "Asha Rao", detail: null }], truncated: false };

function stub(put: () => Promise<unknown>, lookup: () => Promise<unknown> = () => json(200, PAGE)) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => (init?.method === "PUT" ? put() : lookup()));
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

// Type into the type-ahead and choose the matching option, as a user would.
async function choose(name = "Asha") {
  const input = await screen.findByRole("combobox", { name: "EduSphere counsellor" });
  fireEvent.change(input, { target: { value: name } });
  fireEvent.click(await screen.findByRole("option", { name: /Asha Rao/ }));
}

describe("AssignCounselorButton", () => {
  it("searches the overseas-counselors lookup as the admin types and assigns the chosen one", async () => {
    const fetchMock = stub(() => json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha Rao", changed: true }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await choose();
    expect(fetchMock.mock.calls.some(([url]) => String(url).startsWith(`${LOOKUP}?`) && String(url).includes("q=Asha"))).toBe(true);
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/admin/users"))).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha Rao assigned.");
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/workflows/overseas/applications/a1/counselor", expect.objectContaining({ method: "PUT", body: JSON.stringify({ counselor_id: "c1" }) }));
    expect(refresh).toHaveBeenCalled();
  });

  it("keeps Save disabled until a counsellor is chosen", async () => {
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const input = await screen.findByRole("combobox", { name: "EduSphere counsellor" });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.change(input, { target: { value: "Ash" } });
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    fireEvent.click(await screen.findByRole("option", { name: /Asha Rao/ }));
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    fireEvent.change(input, { target: { value: "Ash" } }); // editing the text drops the pick again
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("reads Change counsellor when one is set, starts empty and has no clear option", async () => {
    const fetchMock = stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const input = (await screen.findByRole("combobox", { name: "EduSphere counsellor" })) as HTMLInputElement;
    expect(input.value).toBe("");
    expect(screen.queryByRole("option", { name: /none|clear|unassign/i })).toBeNull();
    expect(screen.queryByRole("button", { name: /clear|remove|unassign/i })).toBeNull();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("shows the API's refusal", async () => {
    stub(() => json(409, { detail: "This application is closed" }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await choose();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This application is closed");
    expect(refresh).not.toHaveBeenCalled();
  });

  it("says the search failed, keeps Save disabled and sends no PUT when the lookup fails", async () => {
    const fetchMock = stub(() => json(200, {}), () => json(500, {}));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    expect(await screen.findByText("Could not load the counsellors.")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
  });

  it("names the counsellor from the API response, not the picked label", async () => {  // F3
    stub(() => json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha R. Rao", changed: true }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await choose();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Asha R. Rao assigned.");
  });

  it("focuses the search field on open, and Cancel closes and refocuses the button", async () => {  // F2
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const input = await screen.findByRole("combobox", { name: "EduSphere counsellor" });
    await waitFor(() => expect(document.activeElement).toBe(input));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("combobox", { name: "EduSphere counsellor" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Assign counsellor" }));
  });

  it("Escape closes the form and refocuses the button", async () => {  // F2
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const input = await screen.findByRole("combobox", { name: "EduSphere counsellor" });
    fireEvent.keyDown(input, { key: "Escape" }); // the focused field's list is open and takes this one
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("combobox", { name: "EduSphere counsellor" })).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Change counsellor" }));
  });

  it("Escape does nothing while a save is in flight, and Save success refocuses the button", async () => {  // F2
    let finish: (value: unknown) => void = () => {};
    stub(() => new Promise((resolve) => { finish = resolve; }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await choose();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("button", { name: "Saving…" });
    fireEvent.keyDown(screen.getByRole("combobox", { name: "EduSphere counsellor" }), { key: "Escape" });
    expect(screen.getByRole("combobox", { name: "EduSphere counsellor" })).toBeInTheDocument();
    finish(await json(200, { id: "a1", counselor_id: "c1", counselor_name: "Asha Rao", changed: true }));
    await screen.findByRole("status");
    expect(screen.queryByRole("combobox", { name: "EduSphere counsellor" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Assign counsellor" })));
  });

  it("the first Escape closes only the suggestions list; the second closes the form and refocuses the button", async () => {
    stub(() => json(200, {}));
    render(<AssignCounselorButton applicationId="a1" currentId="c1" />);
    fireEvent.click(screen.getByRole("button", { name: "Change counsellor" }));
    const input = await screen.findByRole("combobox", { name: "EduSphere counsellor" });
    fireEvent.change(input, { target: { value: "Ash" } });
    await screen.findByRole("option", { name: /Asha Rao/ });
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("option", { name: /Asha Rao/ })).toBeNull();
    expect(screen.getByRole("combobox", { name: "EduSphere counsellor" })).toBeInTheDocument();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("combobox", { name: "EduSphere counsellor" })).toBeNull();
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("button", { name: "Change counsellor" })));
  });

  it("says No matching counsellors. and keeps Save disabled when the lookup returns nothing", async () => {
    stub(() => json(200, {}), () => json(200, { items: [], truncated: false }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    const input = await screen.findByRole("combobox", { name: "EduSphere counsellor" });
    fireEvent.change(input, { target: { value: "Zzz" } });
    expect(await screen.findByText("No matching counsellors.")).toBeTruthy();
    expect(screen.queryByRole("option")).toBeNull();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
  });

  it("returns focus to the search field after a failed save", async () => {
    stub(() => json(409, { detail: "This application is closed" }));
    render(<AssignCounselorButton applicationId="a1" currentId={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Assign counsellor" }));
    await choose();
    screen.getByRole("button", { name: "Save" }).focus(); // clicking Save focuses it, and it is disabled while saving
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    await screen.findByRole("alert");
    await waitFor(() => expect(document.activeElement).toBe(screen.getByRole("combobox", { name: "EduSphere counsellor" })));
  });
});
