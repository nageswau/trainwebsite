import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentShortlistPanel from "@/components/AgentShortlistPanel";

const entry = (over: Record<string, unknown> = {}) => ({
  id: "e1", university: { source: "agency", id: "a1", name: "Agency U", slug: null, country: "Malta" }, course: { id: null, title: "BA Typed" },
  intake: "Sep 2027", tuition_fee: "EUR 9,000", entry_requirements: "Interview", created_by: "M", created_at: "", updated_at: "", ...over,
});
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const props = { studentId: "s1", archived: false, onStudentGone: vi.fn(), onStudentChanged: vi.fn() };
// Shortlist URLs get the given page; the form's option loads (catalogue, countries, agency universities) get harmless empty answers.
const router = (shortlist: () => unknown[]) =>
  vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "DELETE") return Promise.resolve(res(null, 204));
    if (String(url).includes("/shortlist")) return Promise.resolve(res(page(shortlist())));
    return Promise.resolve(res(String(url).includes("universities") && String(url).includes("crm") ? { items: [] } : []));
  });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentShortlistPanel (AGN-007)", () => {
  it("lists entries with an Agency badge and paging text", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([entry()])))));
    render(<AgentShortlistPanel {...props} />);
    const list = await screen.findByRole("list", { name: "Shortlist" });
    expect(within(list).getByText("Agency U")).toBeInTheDocument();
    expect(within(list).getByText("Agency")).toBeInTheDocument();
    expect(within(list).getByText("Malta")).toBeInTheDocument();
    expect(screen.getByText("Showing 1–1 of 1")).toBeInTheDocument();
  });

  it("shows the empty state with an Add button", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentShortlistPanel {...props} />);
    expect(await screen.findByText("No universities shortlisted yet.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Add university to shortlist" })).toBeInTheDocument();
  });

  it("is read-only for an archived student", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([entry()])))));
    render(<AgentShortlistPanel {...props} archived />);
    await screen.findByText("Agency U");
    expect(screen.getByText("This student is archived; the shortlist is read-only.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Add university|Edit|Remove/ })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "Nope" }, 500)).mockResolvedValueOnce(res(page([entry()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nope");
    fireEvent.click(screen.getByRole("button", { name: "Retry loading the shortlist" }));
    expect(await screen.findByText("Agency U")).toBeInTheDocument();
  });

  it("removes after confirmation; Cancel has focus; a 404 after own delete counts as done", async () => {
    let listed = [entry()];
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        listed = [];
        return Promise.resolve(res(null, 404));
      }
      return Promise.resolve(res(page(listed)));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    expect(await screen.findByText("No universities shortlisted yet.")).toBeInTheDocument();
  });

  it("tells the parent when the student is gone", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Student not found" }, 404))));
    render(<AgentShortlistPanel {...props} />);
    await waitFor(() => expect(props.onStudentGone).toHaveBeenCalled());
  });

  it("returns focus to Add after the add form is cancelled", async () => {
    vi.stubGlobal("fetch", router(() => []));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add university to shortlist" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add university to shortlist" })).toHaveFocus());
  });

  it("returns focus to that entry's Edit button after the edit form is cancelled", async () => {
    vi.stubGlobal("fetch", router(() => [entry()]));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Agency U" }));
    fireEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Agency U" })).toHaveFocus());
  });

  it("Escape in the remove confirm closes only the confirm, keeps the parent out, and focuses that Remove button", async () => {
    vi.stubGlobal("fetch", router(() => [entry()]));
    const parentKey = vi.fn();
    render(
      <div onKeyDown={parentKey}>
        <AgentShortlistPanel {...props} />
      </div>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Cancel" }), { key: "Escape" });
    expect(screen.queryByRole("button", { name: "Confirm remove" })).toBeNull();
    expect(parentKey).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove Agency U" })).toHaveFocus());
  });

  it("Cancel in the remove confirm returns focus to that Remove button", async () => {
    vi.stubGlobal("fetch", router(() => [entry()]));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove Agency U" })).toHaveFocus());
  });

  it("moves focus to Add after a completed remove, and announces it", async () => {
    let listed = [entry()];
    const base = router(() => listed);
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") listed = [];
      return base(url, init);
    }));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await screen.findByText("No universities shortlisted yet.");
    expect(screen.getByText("Agency U removed from the shortlist.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Add university to shortlist" })).toHaveFocus());
  });

  it("reports a failed remove as an alert and returns focus to Remove", async () => {
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "DELETE" ? res({ detail: "Cannot remove" }, 500) : res(page([entry()]))),
    ));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Cannot remove");
    await waitFor(() => expect(screen.getByRole("button", { name: "Remove Agency U" })).toHaveFocus());
  });

  // --- fix round 1 ---------------------------------------------------------------------------------------------------------
  // A router for the real form: one agency university to choose, an empty catalogue, and a configurable write answer.
  const formRouter = (listed: () => unknown[], write: (method: string) => Response) =>
    vi.fn((url: string, init?: RequestInit) => {
      const u = String(url);
      if (init?.method === "POST" || init?.method === "PATCH") return Promise.resolve(write(init.method));
      if (u.includes("/shortlist")) return Promise.resolve(res(page(listed())));
      if (u.includes("crm/universities")) return Promise.resolve(res({ items: [{ id: "a1", name: "Agency U", country: "Malta", city: null, entry_requirements: null }] }));
      return Promise.resolve(res([]));
    });

  it("returns focus to Add after a successful save from the Add form", async () => {
    vi.stubGlobal("fetch", formRouter(() => [], () => res({ entry: entry() }, 201)));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Add university to shortlist" }));
    const uni = await screen.findByLabelText("University (required)");
    await waitFor(() => expect(uni).not.toBeDisabled());
    fireEvent.change(uni, { target: { value: "a:a1" } });
    fireEvent.change(await screen.findByLabelText("Course"), { target: { value: "BA Typed" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByText("Saved to shortlist.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Add university to shortlist" })).toHaveFocus());
  });

  it("returns focus to that entry's Edit button after a successful save from the Edit form", async () => {
    vi.stubGlobal("fetch", formRouter(() => [entry()], () => res({ entry: entry({ intake: "Jan 2028" }) })));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Agency U" }));
    fireEvent.change(await screen.findByLabelText("Intake"), { target: { value: "Jan 2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByText("Saved to shortlist.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Agency U" })).toHaveFocus());
  });

  it("tells the parent when a remove hits a 409", async () => {
    const onStudentChanged = vi.fn();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "DELETE" ? res({ detail: "changed" }, 409) : res(page([entry()])))));
    render(<AgentShortlistPanel {...props} onStudentChanged={onStudentChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(onStudentChanged).toHaveBeenCalledTimes(1));
  });

  it("pages: Showing 1–20 of 25, Next fetches offset 20 and shows 21–25", async () => {
    const many = (from: number, n: number) => Array.from({ length: n }, (_, i) => entry({ id: `e${from + i}`, university: { source: "agency", id: `a${from + i}`, name: `Uni ${from + i}`, slug: null, country: "Malta" } }));
    const fetchMock = vi.fn((url: string) =>
      Promise.resolve(String(url).includes("offset=20") ? res(page(many(20, 5), 25, 20)) : res(page(many(0, 20), 25, 0))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    expect(await screen.findByText("Showing 1–20 of 25")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Next page of the shortlist" }));
    expect(await screen.findByText("Showing 21–25 of 25")).toBeInTheDocument();
    expect(fetchMock.mock.calls.some(([u]) => String(u).includes("offset=20"))).toBe(true);
  });

  it("steps back a page when the page it lands on is empty", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes("offset=20")) return Promise.resolve(res(page([], 20, 20)));
      return Promise.resolve(res(page([entry()], 25, 0)));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    await screen.findByText("Agency U");
    fireEvent.click(screen.getByRole("button", { name: "Next page of the shortlist" }));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([u]) => String(u).includes("offset=0")).length).toBe(2));
    expect(await screen.findByText("Showing 1–1 of 25")).toBeInTheDocument();
  });

  it("does not refetch when the parent re-renders with new callback identities", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([entry()]))));
    vi.stubGlobal("fetch", fetchMock);
    const { rerender } = render(<AgentShortlistPanel {...props} />);
    await screen.findByText("Agency U");
    rerender(<AgentShortlistPanel studentId="s1" archived={false} onStudentGone={vi.fn()} onStudentChanged={vi.fn()} />);
    await new Promise((r) => setTimeout(r, 30));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("disables Confirm remove while the DELETE is in flight (no double DELETE)", async () => {
    let release: () => void = () => {};
    const deletes = vi.fn();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        deletes();
        return new Promise<Response>((r) => { release = () => r(res(null, 204)); });
      }
      return Promise.resolve(res(page([entry()])));
    }));
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    const confirm = screen.getByRole("button", { name: "Confirm remove" });
    fireEvent.click(confirm);
    await waitFor(() => expect(confirm).toBeDisabled());
    fireEvent.click(confirm);
    expect(deletes).toHaveBeenCalledTimes(1);
    release();
    await waitFor(() => expect(screen.getByText("Agency U removed from the shortlist.")).toBeInTheDocument());
  });

  // --- final review fixes ---------------------------------------------------------------------------------------------------
  const two = () => [entry(), entry({ id: "e2", university: { source: "agency", id: "a1", name: "Agency V", slug: null, country: "Malta" }, intake: "Jan 2029" })];

  it("with a form open the other rows' Edit/Remove are not actionable; a different Edit reinitialises the draft and PATCHes only B", async () => {
    const fetchMock = formRouter(two, () => res({ entry: entry({ id: "e2", intake: "May 2029" }) }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Agency U" }));
    fireEvent.change(await screen.findByLabelText("Intake"), { target: { value: "A draft" } });
    expect(screen.queryByRole("button", { name: "Edit Agency V" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Agency V" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Remove Agency U" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit Agency V" }));
    expect(await screen.findByLabelText("Intake")).toHaveValue("Jan 2029");
    fireEvent.change(screen.getByLabelText("Intake"), { target: { value: "May 2029" } });
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    await screen.findByText("Saved to shortlist.");
    const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(String(patches[0][0])).toMatch(/\/shortlist\/e2$/);
    expect(JSON.parse(String(patches[0][1]!.body))).toEqual({ intake: "May 2029" });
  });

  it("an entry 404 on save closes the form, reloads and tells the user; the parent is not told the student is gone", async () => {
    const onStudentGone = vi.fn();
    const fetchMock = formRouter(() => [entry()], () => res({ detail: "Shortlist entry not found" }, 404));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentShortlistPanel {...props} onStudentGone={onStudentGone} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Agency U" }));
    fireEvent.change(await screen.findByLabelText("Intake"), { target: { value: "Jan 2028" } });
    const lists = () => fetchMock.mock.calls.filter(([u, init]) => String(u).includes("/shortlist?") && !init?.method).length;
    const before = lists();
    fireEvent.click(screen.getByRole("button", { name: "Save to shortlist" }));
    expect(await screen.findByText("This entry was removed by someone else.")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Edit shortlist entry" })).toBeNull();
    expect(lists()).toBeGreaterThan(before);
    expect(onStudentGone).not.toHaveBeenCalled();
  });

  it("a Student not found 404 on remove tells the parent", async () => {
    const onStudentGone = vi.fn();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "DELETE" ? res({ detail: "Student not found" }, 404) : res(page([entry()])))));
    render(<AgentShortlistPanel {...props} onStudentGone={onStudentGone} />);
    fireEvent.click(await screen.findByRole("button", { name: "Remove Agency U" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(onStudentGone).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Agency U removed from the shortlist.")).toBeNull();
  });
});
