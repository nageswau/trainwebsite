import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentUniversitiesPanel from "@/components/AgentUniversitiesPanel";

const uni = (over: Record<string, unknown> = {}) => ({ id: "u1", name: "Trinity", country: "Ireland", city: "Dublin", entry_requirements: "IELTS 6.5", created_at: "", updated_at: "", ...over });
const page = (items: unknown[], total = items.length) => ({ items, total, limit: 20, offset: 0 });
const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

// Browser QA (2026-10-02): in a real browser the animation frame can fire before React commits a state change made after an await,
// so focus asked for "on the next frame" can miss a control that is not rendered yet. These tests run frames immediately to model that.
const frameBeforeCommit = () => vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => (cb(0), 0));

describe("AgentUniversitiesPanel browser QA fixes (AGN-007)", () => {
  it("QA-02: after a successful edit save focus returns to that university's Edit button", async () => {
    frameBeforeCommit();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => Promise.resolve(init?.method === "PATCH" ? res({ university: uni({ city: "Cork" }) }) : res(page([uni()])))));
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Trinity" }));
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Cork" } });
    fireEvent.click(screen.getByRole("button", { name: "Save university" }));
    expect(await screen.findByText("Trinity saved.")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByRole("button", { name: "Edit Trinity" })).toHaveFocus());
  });

  it("QA-02: after an add is cancelled focus returns to Add university", async () => {
    frameBeforeCommit();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([uni()])))));
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add university" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Add university" })).toHaveFocus());
  });

  it("QA-01: Save stays focusable while saving (aria-disabled, never disabled) and a second submit is ignored", async () => {
    let release: (r: Response) => void = () => {};
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      init?.method === "POST" ? new Promise<Response>((r) => (release = r)) : Promise.resolve(res(page([]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add university" }));
    fireEvent.change(screen.getByLabelText("Name (required)"), { target: { value: "UCD" } });
    fireEvent.change(screen.getByLabelText("Country (required)"), { target: { value: "Ireland" } });
    const save = screen.getByRole("button", { name: "Save university" });
    save.focus();
    fireEvent.click(save);
    const saving = await screen.findByRole("button", { name: "Saving…" });
    expect(saving).not.toBeDisabled();
    expect(saving).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(saving);
    expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
    release(res({ detail: "This university is already in your agency's list" }, 409));
    expect(await screen.findByRole("alert")).toHaveTextContent("already in your agency's list");
    expect(screen.getByRole("button", { name: "Save university" })).toHaveFocus();
  });

  it("QA-03: a search with no matches says so and offers Clear search", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(res(page(String(url).includes("q=zzz") ? [] : [uni()]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    await screen.findByText("Trinity");
    fireEvent.change(screen.getByLabelText("Search universities"), { target: { value: "zzz" } });
    fireEvent.submit(screen.getByRole("search"));
    expect(await screen.findByText("No universities match “zzz”.")).toBeInTheDocument();
    expect(screen.queryByText("Your agency hasn't added any universities yet.")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Clear search" }));
    expect(await screen.findByText("Trinity")).toBeInTheDocument();
    expect(screen.getByLabelText("Search universities")).toHaveValue("");
  });

  it("QA-04: the catalogue link looks like a link (brand colour, underlined)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentUniversitiesPanel memberRole="staff" />);
    const link = screen.getByRole("link", { name: "Browse the university catalogue" });
    expect(link).toHaveStyle({ textDecoration: "underline" });
    expect(link.style.color).toBe("var(--blue)");
  });

  it("QA-08: a server error (5xx) is worded as a retry, not the raw server text", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Internal Server Error" }, 500))));
    render(<AgentUniversitiesPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The server couldn't complete this. Please try again in a moment.");
  });
});

describe("AgentUniversitiesPanel (AGN-007)", () => {
  it("shows loading, then the agency's universities as a list", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([uni()])))));
    render(<AgentUniversitiesPanel memberRole="master" />);
    expect(screen.getByText("Loading universities…")).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Agency universities" });
    expect(within(list).getByText("Trinity")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Browse the university catalogue" })).toHaveAttribute("href", "/overseas/universities");
  });

  it("gives Masters Add, Edit and Delete; Staff see none", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([uni()])))));
    const { unmount } = render(<AgentUniversitiesPanel memberRole="master" />);
    await screen.findByText("Trinity");
    expect(screen.getByRole("button", { name: "Add university" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Edit Trinity" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete Trinity" })).toBeInTheDocument();
    unmount();
    render(<AgentUniversitiesPanel memberRole="staff" />);
    await screen.findByText("Trinity");
    expect(screen.queryByRole("button", { name: /Add university|Edit|Delete/ })).toBeNull();
  });

  it("shows the empty state (with Add only for Masters)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([])))));
    render(<AgentUniversitiesPanel memberRole="staff" />);
    expect(await screen.findByText("Your agency hasn't added any universities yet.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Add university" })).toBeNull();
  });

  it("shows an error with Retry", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res(page([uni()])));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("The server couldn't complete this. Please try again in a moment."); // QA-08 wording for a 5xx
    fireEvent.click(screen.getByRole("button", { name: "Retry loading universities" }));
    expect(await screen.findByText("Trinity")).toBeInTheDocument();
  });

  it("explains an in-use delete inline and keeps the row", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "DELETE" ? res({ detail: "This university is on 2 shortlist entries; remove it from them first" }, 409) : res(page([uni()]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete Trinity" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));
    expect(await screen.findByText(/on 2 shortlist entries/)).toBeInTheDocument();
    expect(screen.getByText("Trinity")).toBeInTheDocument();
  });

  it("adds a university and shows it", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res({ university: uni({ id: "u2", name: "UCD" }) }, 201) : res(page([]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Add university" }));
    const form = screen.getByRole("form", { name: "Add university" });
    fireEvent.change(within(form).getByLabelText("Name (required)"), { target: { value: "UCD" } });
    fireEvent.change(within(form).getByLabelText("Country (required)"), { target: { value: "Ireland" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save university" }));
    expect(await screen.findByText("UCD added.")).toBeInTheDocument();
    const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toEqual({ name: "UCD", country: "Ireland", city: null, entry_requirements: null });
  });

  describe("focus and Escape", () => {
    const listFetch = () => vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(page([uni()])))));

    it("returns focus to Add university when the Add form is cancelled", async () => {
      listFetch();
      render(<AgentUniversitiesPanel memberRole="master" />);
      fireEvent.click(await screen.findByRole("button", { name: "Add university" }));
      fireEvent.click(within(screen.getByRole("form", { name: "Add university" })).getByRole("button", { name: "Cancel" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "Add university" })).toHaveFocus());
    });

    it("returns focus to Edit <name> when the Edit form is cancelled", async () => {
      listFetch();
      render(<AgentUniversitiesPanel memberRole="master" />);
      fireEvent.click(await screen.findByRole("button", { name: "Edit Trinity" }));
      fireEvent.click(within(screen.getByRole("form", { name: "Edit university" })).getByRole("button", { name: "Cancel" }));
      await waitFor(() => expect(screen.getByRole("button", { name: "Edit Trinity" })).toHaveFocus());
    });

    it("focuses Cancel when the delete confirm opens", async () => {
      listFetch();
      render(<AgentUniversitiesPanel memberRole="master" />);
      fireEvent.click(await screen.findByRole("button", { name: "Delete Trinity" }));
      const group = screen.getByRole("group", { name: "Confirm delete Trinity" });
      expect(within(group).getByRole("button", { name: "Cancel" })).toHaveFocus();
    });

    it("closes the delete confirm on Escape and returns focus to Delete <name>", async () => {
      listFetch();
      render(<AgentUniversitiesPanel memberRole="master" />);
      fireEvent.click(await screen.findByRole("button", { name: "Delete Trinity" }));
      fireEvent.keyDown(screen.getByRole("group", { name: "Confirm delete Trinity" }), { key: "Escape" });
      expect(screen.queryByRole("group", { name: "Confirm delete Trinity" })).toBeNull();
      await waitFor(() => expect(screen.getByRole("button", { name: "Delete Trinity" })).toHaveFocus());
    });
  });

  it("with a form open the other rows' Edit/Delete are not actionable; a different Edit starts from that row and PATCHes only it", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "PATCH" ? res({ university: uni({ id: "u2", name: "UCD", city: "Cork" }) }) : res(page([uni(), uni({ id: "u2", name: "UCD", city: "Galway" })]))),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit Trinity" }));
    fireEvent.change(within(screen.getByRole("form", { name: "Edit university" })).getByLabelText("City"), { target: { value: "A draft" } });
    expect(screen.queryByRole("button", { name: "Edit UCD" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete UCD" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Delete Trinity" })).toBeNull();
    fireEvent.click(within(screen.getByRole("form", { name: "Edit university" })).getByRole("button", { name: "Cancel" }));
    fireEvent.click(await screen.findByRole("button", { name: "Edit UCD" }));
    const form = screen.getByRole("form", { name: "Edit university" });
    expect(within(form).getByLabelText("City")).toHaveValue("Galway");
    fireEvent.change(within(form).getByLabelText("City"), { target: { value: "Cork" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save university" }));
    await screen.findByText("UCD saved.");
    const patches = fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH");
    expect(patches).toHaveLength(1);
    expect(String(patches[0][0])).toMatch(/\/universities\/u2$/);
    expect(JSON.parse(String(patches[0][1]!.body))).toEqual({ city: "Cork" });
  });

  it("disables Confirm delete while the DELETE is in flight (no double DELETE)", async () => {
    let release: () => void = () => {};
    const deletes = vi.fn();
    vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "DELETE") {
        deletes();
        return new Promise<Response>((r) => { release = () => r(res(null, 204)); });
      }
      return Promise.resolve(res(page([uni()])));
    }));
    render(<AgentUniversitiesPanel memberRole="master" />);
    fireEvent.click(await screen.findByRole("button", { name: "Delete Trinity" }));
    const confirm = screen.getByRole("button", { name: "Confirm delete" });
    fireEvent.click(confirm);
    await waitFor(() => expect(confirm).toBeDisabled());
    fireEvent.click(confirm);
    expect(deletes).toHaveBeenCalledTimes(1);
    release();
    await screen.findByText("Trinity deleted.");
  });
});
