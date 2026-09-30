import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentsPanel from "@/components/AgentStudentsPanel";

const item = (over: Record<string, unknown> = {}) => ({
  id: "s1", has_login: false, full_name: "Asha Rao", email: "a@x.com", phone: null, preferred_country: "Canada", preferred_intake: "Sep 2027",
  status: "active", assigned_to: null, created_at: "", ...over,
});
const detail = (over: Record<string, unknown> = {}) => ({
  ...item(), date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null, preferred_course: null, notes: null,
  created_by: "Master One", archived_at: null, archived_by: null, updated_at: "", ...over,
});
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const sleep = (ms: number) => act(() => new Promise((r) => setTimeout(r, ms)));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AgentStudentsPanel (AGN-004)", () => {
  it("shows a loading state, then rows", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item()])))));
    render(<AgentStudentsPanel memberRole="master" />);
    expect(screen.getByText("Loading students…")).toBeInTheDocument();
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
  });

  it("shows the empty state with an Add student action", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentStudentsPanel memberRole="staff" />);
    expect(await screen.findByText(/No students yet/)).toBeInTheDocument();
  });

  it("shows a filtered empty state with Clear filters", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentStudentsPanel memberRole="master" />);
    await screen.findByText(/No students yet/);
    fireEvent.click(screen.getByLabelText("Show archived"));
    expect(await screen.findByText(/No students match/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    expect(await screen.findByText(/No students yet/)).toBeInTheDocument();
  });

  it("shows an error with Retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "Your agency's account is suspended" }, 403)).mockImplementation(() => Promise.resolve(res(page([item()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your agency's account is suspended");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
  });

  it("does not trust a 200 that is not a page", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({}))));
    render(<AgentStudentsPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load students.");
  });

  it("hides Master-only controls from staff", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item()])))));
    render(<AgentStudentsPanel memberRole="staff" />);
    await screen.findByText("Asha Rao");
    expect(screen.queryByRole("button", { name: "Archive Asha Rao" })).toBeNull();
    expect(screen.queryByLabelText("Assigned to")).toBeNull();
    expect(screen.getByRole("button", { name: "View Asha Rao" })).toBeInTheDocument();
  });

  it("archives inline with a confirmation, announces it and returns focus on cancel", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res({ student: detail({ status: "archived", archived_by: "Master One" }) }) : res(page([item()]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsPanel memberRole="master" />);
    const archive = await screen.findByRole("button", { name: "Archive Asha Rao" });
    fireEvent.click(archive);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Archive Asha Rao" })).toHaveFocus());
    fireEvent.click(screen.getByRole("button", { name: "Archive Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
    expect(await screen.findByText("Asha Rao archived.")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u, i]) => u === "/api/v1/workflows/overseas/agent/crm/students/s1/archive" && i?.method === "POST")).toBe(true);
  });

  it("shows the server's message when an action fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? res({ detail: "Already archived" }, 409) : res(page([item()])))),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Archive Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
    expect(await screen.findByText("Already archived")).toBeInTheDocument();
  });

  it("opens the detail panel, and Escape closes it", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/s1") ? res({ student: detail({ notes: "Line one\nLine two" }) }) : res(page([item()])))));
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Asha Rao" }));
    const panel = await screen.findByRole("region", { name: "Asha Rao" });
    expect(within(panel).getByText("Master One")).toBeInTheDocument();
    expect(within(panel).getByRole("button", { name: "Edit" })).toBeInTheDocument();
    fireEvent.keyDown(panel, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("region", { name: "Asha Rao" })).toBeNull());
  });

  it("says a student is no longer available when the detail is 404", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/s1") ? res({ detail: "Student not found" }, 404) : res(page([item()])))));
    render(<AgentStudentsPanel memberRole="staff" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Asha Rao" }));
    expect(await screen.findByText("This student is no longer available.")).toBeInTheDocument();
  });

  it("does not offer Edit for a student with a login", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/s1") ? res({ student: detail({ has_login: true }) }) : res(page([item({ has_login: true })])))));
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Asha Rao" }));
    const panel = await screen.findByRole("region", { name: "Asha Rao" });
    expect(within(panel).queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("keeps the newest search when an older response arrives late", async () => {
    let releaseOld: () => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.includes("q=old")) return new Promise<Response>((r) => { releaseOld = () => r(res(page([item({ id: "o", full_name: "Old Result" })]))); });
        if (url.includes("q=new")) return Promise.resolve(res(page([item({ id: "n", full_name: "New Result" })])));
        return Promise.resolve(res(page([])));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    const box = await screen.findByLabelText("Search students");
    fireEvent.change(box, { target: { value: "old" } });
    await sleep(350);
    fireEvent.change(box, { target: { value: "new" } });
    expect(await screen.findByText("New Result")).toBeInTheDocument();
    await act(async () => releaseOld());
    await sleep(20);
    expect(screen.queryByText("Old Result")).toBeNull();
    expect(screen.getByText("New Result")).toBeInTheDocument();
  });

  it("keeps rows visible while a new page loads", async () => {
    let releaseNext: () => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        url.includes("offset=20")
          ? new Promise<Response>((r) => { releaseNext = () => r(res({ items: [item({ id: "b", full_name: "Page Two" })], total: 21, limit: 20, offset: 20 })); })
          : Promise.resolve(res({ items: [item()], total: 21, limit: 20, offset: 0 })),
      ),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    expect(screen.getByText("Asha Rao")).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Student list" })).toHaveAttribute("aria-busy", "true");
    await act(async () => releaseNext());
    expect(await screen.findByText("Page Two")).toBeInTheDocument();
  });

  it("renders markup in a name as text", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item({ full_name: "<img src=x onerror=alert(1)>" })])))));
    const { container } = render(<AgentStudentsPanel memberRole="master" />);
    expect(await screen.findByText("<img src=x onerror=alert(1)>")).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows login and assignment as text, including a deactivated assignee", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(res(page([item({ has_login: true, assigned_to: { id: "m", code: "ABC-S001", full_name: "Rahul", status: "deactivated" } })]))),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    const row = (await screen.findByText("Asha Rao")).closest("tr")!;
    expect(within(row).getByText("Has login")).toBeInTheDocument();
    expect(within(row).getByText("ABC-S001 · Rahul (deactivated)")).toBeInTheDocument();
  });
});
