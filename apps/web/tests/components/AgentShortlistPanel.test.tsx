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
});
