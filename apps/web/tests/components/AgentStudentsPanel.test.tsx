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
  window.history.replaceState(null, "", "/"); // the panel keeps its filters in the URL (QA-06); jsdom keeps the URL between tests
});

describe("AgentStudentsPanel (AGN-004)", () => {
  it("shows a loading state, then rows", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item()])))));
    render(<AgentStudentsPanel memberRole="master" />);
    expect(screen.getByText("Loading students…")).toBeInTheDocument();
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
  });

  it("lists students as cards, not a second table (the page's roster table stays the only one)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item(), item({ id: "s2", full_name: "Ravi Iyer" })])))));
    const { container } = render(<AgentStudentsPanel memberRole="master" />);
    const list = await screen.findByRole("list", { name: "Students" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(2);
    expect(container.querySelector("table")).toBeNull();
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
    expect(screen.queryByRole("button", { name: "Assign Asha Rao" })).toBeNull();
    expect(screen.queryByLabelText("Assigned to")).toBeNull();
    expect(screen.getByRole("button", { name: "View Asha Rao" })).toBeInTheDocument();
  });

  it("hides Unarchive from staff on an archived student (AGN-005-AC06)", async () => {
    window.history.replaceState(null, "", "/?archived=1"); // Show archived on (QA-06 keeps it in the URL; afterEach resets it)
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(() => Promise.resolve(res(page([item({ status: "archived" })]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsPanel memberRole="staff" />);
    await screen.findByText("Asha Rao");
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes("include_archived=true"))).toBe(true);
    expect(screen.queryByRole("button", { name: "Unarchive Asha Rao" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Archive Asha Rao" })).toBeNull();
    expect(screen.getByRole("button", { name: "View Asha Rao" })).toBeInTheDocument();
  });

  it("lets a Master assign an active student to a staff member and updates the card (AC09)", async () => {
    const priya = { id: "m1", code: "EDU-S001", full_name: "Priya Nair", status: "active" };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/workflows/overseas/agent/team/staff")) return Promise.resolve(res({ items: [{ ...priya, email: "p@x.com", phone: null, setup: null }], total: 1, limit: 100, offset: 0 }));
      if (init?.method === "POST") return Promise.resolve(res({ student: detail({ assigned_to: priya }) }));
      return Promise.resolve(res(page([item(), item({ id: "s2", full_name: "Ravi Iyer", status: "archived" })])));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Assign Asha Rao" }));
    expect(screen.queryByRole("button", { name: "Assign Ravi Iyer" })).toBeNull(); // archived: unarchive first
    const select = (await screen.findByLabelText("Assign to")) as HTMLSelectElement;
    await waitFor(() => expect(select.options).toHaveLength(2));
    fireEvent.change(select, { target: { value: "m1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save assignment" }));
    expect(await screen.findByText("Asha Rao assigned to EDU-S001 · Priya Nair.")).toBeInTheDocument();
    const card = screen.getByRole("heading", { name: "Asha Rao" }).closest("li")!;
    expect(within(card).getByText("EDU-S001 · Priya Nair")).toBeInTheDocument();
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

  it("shows the detail above the list, so list refreshes never move it", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string) => Promise.resolve(url.endsWith("/s1") ? res({ student: detail() }) : res(page([item()])))));
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Asha Rao" }));
    const panel = await screen.findByRole("region", { name: "Asha Rao" });
    const list = screen.getByRole("region", { name: "Student list" });
    expect(panel.compareDocumentPosition(list) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
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

  // --- final review fixes -----------------------------------------------------------------------------------------------------
  it("steps back a page when the current page empties, instead of a false 'No students yet'", async () => {
    const calls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        calls.push(url);
        if (init?.method === "POST") return Promise.resolve(res({ student: detail({ id: "z", full_name: "Last One", status: "archived" }) }));
        if (url.includes("offset=20")) {
          const archived = calls.some((u) => u.endsWith("/z/archive"));
          return Promise.resolve(res({ items: archived ? [] : [item({ id: "z", full_name: "Last One" })], total: archived ? 20 : 21, limit: 20, offset: 20 }));
        }
        return Promise.resolve(res({ items: [item()], total: 21, limit: 20, offset: 0 }));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Next page" }));
    fireEvent.click(await screen.findByRole("button", { name: "Archive Last One" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
    expect(await screen.findByText("Asha Rao")).toBeInTheDocument();
    expect(screen.queryByText(/No students yet/)).toBeNull();
  });

  it("reloads the list after adding a student rather than inserting it into any page or filter", async () => {
    const lists: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === "POST") return Promise.resolve(res({ student: detail({ id: "new", full_name: "Brand New" }) }, 201));
        lists.push(url);
        return Promise.resolve(res(page([item()])));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    await screen.findByText("Asha Rao");
    const before = lists.length;
    fireEvent.click(screen.getByRole("button", { name: "Add student" }));
    fireEvent.change(screen.getByLabelText("Full name (required)"), { target: { value: "Brand New" } });
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    expect(await screen.findByText("Brand New added.")).toBeInTheDocument();
    await waitFor(() => expect(lists.length).toBeGreaterThan(before));
    expect(within(screen.getByRole("list", { name: "Students" })).queryByText("Brand New")).toBeNull();
  });

  it("shows the student last asked for when an earlier detail request answers late", async () => {
    let releaseA: () => void = () => {};
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/a")) return new Promise<Response>((r) => { releaseA = () => r(res({ student: detail({ id: "a", full_name: "Alpha" }) })); });
        if (url.endsWith("/b")) return Promise.resolve(res({ student: detail({ id: "b", full_name: "Bravo" }) }));
        return Promise.resolve(res(page([item({ id: "a", full_name: "Alpha" }), item({ id: "b", full_name: "Bravo" })])));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Alpha" }));
    fireEvent.click(screen.getByRole("button", { name: "View Bravo" }));
    expect(await screen.findByRole("region", { name: "Bravo" })).toBeInTheDocument();
    await act(async () => releaseA());
    await sleep(20);
    expect(screen.queryByRole("region", { name: "Alpha" })).toBeNull();
    expect(screen.getByRole("region", { name: "Bravo" })).toBeInTheDocument();
  });

  it("keeps keyboard focus after an archive: on the row's new Unarchive button, or on the list when the row leaves it", async () => {
    let archived = false;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === "POST") {
          archived = true;
          return Promise.resolve(res({ student: detail({ status: "archived", archived_by: "M" }) }));
        }
        return Promise.resolve(res(page([item(archived ? { status: "archived" } : {})])));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    await screen.findByText("Asha Rao");
    fireEvent.click(screen.getByLabelText("Show archived"));
    await waitFor(() => expect(screen.getByRole("region", { name: "Student list" })).toHaveAttribute("aria-busy", "false"));
    fireEvent.click(await screen.findByRole("button", { name: "Archive Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Unarchive Asha Rao" })).toHaveFocus());
  });

  it("moves focus to the list when an archived row leaves the default view", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) =>
        Promise.resolve(init?.method === "POST" ? res({ student: detail({ status: "archived", archived_by: "M" }) }) : res(page([item()]))),
      ),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Archive Asha Rao" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm archive" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Student list" })).toHaveFocus());
  });

  it("returns focus to the detail heading after an edit is saved", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string, init?: RequestInit) => {
        if (init?.method === "PATCH") return Promise.resolve(res({ student: detail({ preferred_country: "Ireland" }) }));
        if (url.endsWith("/s1")) return Promise.resolve(res({ student: detail() }));
        return Promise.resolve(res(page([item()])));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Asha Rao" }));
    const panel = await screen.findByRole("region", { name: "Asha Rao" });
    fireEvent.click(within(panel).getByRole("button", { name: "Edit" }));
    fireEvent.change(within(panel).getByLabelText("Preferred country"), { target: { value: "Ireland" } });
    const save = within(panel).getByRole("button", { name: "Save changes" });
    save.focus(); // a keyboard user is on the button; it unmounts when the form closes
    fireEvent.click(save);
    await waitFor(() => expect(within(panel).getByRole("heading", { name: "Asha Rao" })).toHaveFocus());
  });

  // --- browser QA fixes ----------------------------------------------------------------------------------------------------
  it("is headed 'All students' (the page itself is titled Students) (QA-01)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item()])))));
    render(<AgentStudentsPanel memberRole="master" />);
    expect(screen.getByRole("heading", { name: "All students", level: 3 })).toBeInTheDocument();
  });

  it("keeps search, Show archived and page in the URL, and reads them back (QA-06)", async () => {
    window.history.replaceState(null, "", "/overseas/agent/students?q=Asha&archived=1&page=2");
    const fetchMock = vi.fn<(url: string) => Promise<Response>>(() => Promise.resolve(res({ items: [item()], total: 25, limit: 20, offset: 20 })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentsPanel memberRole="master" />);
    await screen.findByText("Asha Rao");
    expect(screen.getByLabelText("Search students")).toHaveValue("Asha");
    expect(screen.getByLabelText("Show archived")).toBeChecked();
    const firstUrl = String(fetchMock.mock.calls[0][0]);
    expect(firstUrl).toContain("q=Asha");
    expect(firstUrl).toContain("include_archived=true");
    expect(firstUrl).toContain("offset=20");
    fireEvent.click(screen.getByLabelText("Show archived"));
    await waitFor(() => expect(window.location.search).toBe("?q=Asha"));
    window.history.replaceState(null, "", "/");
  });

  it("offers Retry when a student's details fail to load (QA-09)", async () => {
    let detailCalls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) => {
        if (url.endsWith("/s1")) return Promise.resolve(++detailCalls === 1 ? res({ detail: "Internal Server Error" }, 500) : res({ student: detail() }));
        return Promise.resolve(res(page([item()])));
      }),
    );
    render(<AgentStudentsPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "View Asha Rao" }));
    expect(await screen.findByText("Unable to load this student.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry loading the student" }));
    expect(await screen.findByRole("region", { name: "Asha Rao" })).toBeInTheDocument();
  });

  it("lets long emails break after @ and dots instead of mid-word (QA-10)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([item({ email: "student.overseas@edusphere.local" })])))));
    const { container } = render(<AgentStudentsPanel memberRole="master" />);
    await screen.findByText("Asha Rao");
    const contact = container.querySelector("ul[aria-label='Students'] dd") as HTMLElement;
    expect(contact.querySelectorAll("wbr").length).toBeGreaterThanOrEqual(3);
    expect(contact.textContent).toBe("student.overseas@edusphere.local");
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
    const row = (await screen.findByText("Asha Rao")).closest("li")!;
    expect(within(row).getByText("Has login")).toBeInTheDocument();
    expect(within(row).getByText("ABC-S001 · Rahul (deactivated)")).toBeInTheDocument();
  });
});
