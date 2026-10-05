import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmActivityTimeline from "@/components/BdmActivityTimeline";
import type { Activity } from "@/lib/bdmActivities";
import type { Organization } from "@/lib/bdmOrganizations";

const res = (body: unknown, status = 200) => new Response(body === null ? null : JSON.stringify(body), { status });
const act = (id: string, at: string, over: Partial<Activity> = {}): Activity => ({
  id, organization: { id: "o1", code: "ORG-000001", name: "St Mary", org_type: "college" }, bdm: { id: "b1", full_name: "Asha" },
  contact_id: null, contact_name: null, contact_removed: false, channel: "call", direction: "outbound", occurred_at: at, note: null,
  created_at: at, updated_at: at, permissions: { can_change: true }, ...over,
});
const org = { id: "o1", contacts: [{ id: "c1", name: "Dr Rao" }] } as unknown as Organization;
const page = (items: Activity[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });
const onNotice = vi.fn();
afterEach(() => {
  onNotice.mockClear();
  cleanup();
  vi.unstubAllGlobals();
});

describe("BdmActivityTimeline (bdm-009 §6.3, AC6, AC11)", () => {
  it("shows the empty state", () => {
    render(<BdmActivityTimeline organization={org} initial={page([])} canLog={false} orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    expect(screen.getByText("No activity logged yet.")).toBeInTheDocument();
  });

  it("a failed first load offers Try again, which reads the first page", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([act("a1", "2026-10-03T04:00:00Z")]))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={null} canLog={false} orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Activity couldn't be loaded.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=0");
  });

  it("offers Log activity only when allowed and inserts the saved one in time order", async () => {
    const { rerender } = render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z")])} canLog={false} orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    expect(screen.queryByRole("button", { name: "Log activity" })).toBeNull();
    rerender(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z")])} canLog orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(act("a2", "2026-10-03T05:00:00Z", { channel: "visit", direction: null }), 201))));
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "visit" } });
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    const list = await screen.findByRole("list", { name: "Activity" });
    await waitFor(() => expect(within(list).getAllByRole("listitem")[0]).toHaveTextContent("Visit"));
    expect(onNotice).toHaveBeenCalledWith("Activity logged.", true);
    expect(screen.queryByRole("status")).toBeNull(); // QA9-01: the profile owns the one live region
  });

  it("loads more with the next offset", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(page([act("a3", "2026-10-01T04:00:00Z")], 3, 2))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z"), act("a2", "2026-10-02T04:00:00Z")], 3)} canLog={false} orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(3));
    expect(fetchMock).toHaveBeenCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=2");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("delete drops the total and keeps the next offset", async () => {
    const fetchMock = vi.fn((url: string) => Promise.resolve(url.includes("offset=") ? res(page([act("a9", "2026-09-30T04:00:00Z")], 2, 1)) : res(null, 204)));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z"), act("a2", "2026-10-02T04:00:00Z")], 3)} canLog={false} orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    fireEvent.click(screen.getAllByRole("button", { name: "Delete" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    await waitFor(() => expect(screen.getAllByRole("listitem")).toHaveLength(1));
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=1"));
  });

  it("a refused delete (409) makes the item read-only and announces no success", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "Only today's activities can be changed" }, 409))));
    render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z")])} canLog={false} orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, delete" }));
    expect(await screen.findByText("Only today's activities can be changed")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("button", { name: "Delete" })).toBeNull());
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
    expect(onNotice).toHaveBeenCalledWith(""); // locked: clears any old success text, announces nothing new
    expect(onNotice).not.toHaveBeenCalledWith(expect.stringMatching(/\S/));
  });

  it("a backdated activity older than the loaded rows does not move the next Load more offset", async () => {
    const loaded = Array.from({ length: 20 }, (_, i) => act(`i${String(i).padStart(2, "0")}`, `2026-10-03T${String(10 - Math.floor(i / 6)).padStart(2, "0")}:${String(59 - (i % 6) * 5).padStart(2, "0")}:00Z`));
    const fetchMock = vi.fn((_url: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? res(act("old1", "2026-09-30T04:00:00Z"), 201) : res(page([act("z1", "2026-09-29T04:00:00Z")], 26, 20))));
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmActivityTimeline organization={org} initial={page(loaded, 25)} canLog orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    await waitFor(() => expect(onNotice).toHaveBeenCalledWith("Activity logged.", true));
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/bdm/organizations/o1/activities?limit=20&offset=20"));
  });

  it("opening Log activity or Edit clears the previous notice (QA9-03)", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res(act("a2", "2026-10-03T05:00:00Z"), 201))));
    render(<BdmActivityTimeline organization={org} initial={page([act("a1", "2026-10-03T04:00:00Z")])} canLog orgBasePath="/bdm/organizations" onNotice={onNotice} />);
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    expect(onNotice).toHaveBeenLastCalledWith("");
    fireEvent.click(screen.getByLabelText("Outgoing"));
    fireEvent.click(screen.getByRole("button", { name: "Save activity" }));
    await waitFor(() => expect(onNotice).toHaveBeenLastCalledWith("Activity logged.", true));
    fireEvent.click(screen.getByRole("button", { name: "Log activity" }));
    expect(onNotice).toHaveBeenLastCalledWith("");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Edit" })[0]);
    expect(onNotice).toHaveBeenLastCalledWith("");
  });
});
