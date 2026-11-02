import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import AdminTimetablePanel from "@/components/BatchTimetableEditor";
import TimetableCalendar from "@/components/TimetableCalendar";
import { addDays, byDay, mondayOf, type Occurrence, slotBody, todayIst } from "@/lib/timetable";

// itc-020 (DEC-SCOPE-344): the week of classes every IT role reads, and the IT Admin's weekly-slot editor.
const res = (body: unknown, status = 200) => new Response(status === 204 ? null : JSON.stringify(body), { status });
const NOW = new Date("2026-11-04T06:00:00Z"); // Wednesday 4 Nov 2026, 11:30 IST

const occ = (over: Partial<Occurrence>): Occurrence => ({
  id: "s1:2026-11-04", kind: "class", slot_id: "s1", batch_id: "b1", batch: "PY-DEC", program: "Python", date: "2026-11-04",
  starts_at: "2026-11-04T19:00:00+05:30", ends_at: "2026-11-04T21:00:00+05:30", mode: "online", room: null, meeting_url: "https://meet.example/py",
  topic: "Loops", status: "scheduled", cancel_reason: null, ...over,
});

let fetchMock: ReturnType<typeof vi.fn>;
let feed: { from: string; to: string; can_edit: boolean; items: Occurrence[] };
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
  feed = { from: "2026-11-02", to: "2026-11-08", can_edit: false, items: [] };
  fetchMock = vi.fn(() => Promise.resolve(res(feed)));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("timetable helpers", () => {
  it("works in IST weeks starting on Monday", () => {
    expect(todayIst(new Date("2026-11-04T20:00:00Z"))).toBe("2026-11-05"); // 01:30 IST the next day
    expect(mondayOf("2026-11-04")).toBe("2026-11-02");
    expect(mondayOf("2026-11-08")).toBe("2026-11-02");
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(byDay([occ({ date: "2026-11-06" }), occ({ date: "2026-11-04" }), occ({ id: "x", date: "2026-11-04" })]).map((d) => [d.date, d.items.length])).toEqual([["2026-11-04", 2], ["2026-11-06", 1]]);
    expect(slotBody({ weekday: 0, start_time: "19:00", end_time: "21:00", mode: "online", room: " ", meeting_url: "", topic: " Loops " })).toMatchObject({ room: null, meeting_url: null, topic: "Loops" });
  });
});

describe("TimetableCalendar", () => {
  it("asks for this IST week and lists its classes by day with today marked", async () => {
    feed.items = [occ({}), occ({ id: "s2:2026-11-06", date: "2026-11-06", starts_at: "2026-11-06T10:00:00+05:30", ends_at: "2026-11-06T12:00:00+05:30", mode: "offline", room: "Lab 2", meeting_url: null, topic: null })];
    render(<TimetableCalendar />);
    expect(screen.getByText("Loading classes…")).toBeTruthy();
    expect(await screen.findByText("Loops")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/it/timetable?from=2026-11-02&to=2026-11-08");
    expect(screen.getByRole("heading", { name: /Wednesday, 4 Nov.*Today/ })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Join Loops/ }).getAttribute("href")).toBe("https://meet.example/py");
    expect(screen.getByText("In person · Lab 2")).toBeTruthy();
    expect(screen.getByText("7:00 pm – 9:00 pm")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Cancel/ })).toBeNull(); // can_edit false
  });

  it("moves between weeks and shows the empty state", async () => {
    render(<TimetableCalendar batchId="b1" />);
    expect(await screen.findByText("No classes this week.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Next week" }));
    await waitFor(() => expect(fetchMock).toHaveBeenLastCalledWith("/api/v1/it/timetable?from=2026-11-09&to=2026-11-15&batch_id=b1", { method: "GET" }));
    expect((screen.getByRole("button", { name: "This week" }) as HTMLButtonElement).disabled).toBe(false);
  });

  it("shows the server's error and retries", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "You cannot view a batch timetable" }, 403)));
    render(<TimetableCalendar />);
    expect((await screen.findByRole("alert")).textContent).toContain("You cannot view a batch timetable");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("No classes this week.")).toBeTruthy();
  });

  it("words a server failure itself (browser QA-03)", async () => {
    fetchMock.mockImplementationOnce(() => Promise.resolve(res({ detail: "Internal Server Error" }, 500)));
    render(<TimetableCalendar />);
    expect((await screen.findByRole("alert")).textContent).toContain("Unable to load the timetable.");
  });

  it("lets an editor cancel a future class with a reason and shows cancelled classes", async () => {
    feed = { ...feed, can_edit: true, items: [occ({}), occ({ id: "s1:2026-11-02", date: "2026-11-02", topic: "Past" }), occ({ id: "s3:2026-11-05", slot_id: "s3", date: "2026-11-05", status: "cancelled", cancel_reason: "Holiday", topic: "Off" })] };
    fetchMock.mockImplementation((_url: string, init?: RequestInit) => Promise.resolve(init?.method === "POST" ? res({ slot_id: "s1", occurs_on: "2026-11-04", reason: "Trainer unwell" }, 201) : res(feed)));
    render(<TimetableCalendar />);
    expect(await screen.findByText("Cancelled: Holiday")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Cancel Past/ })).toBeNull(); // a past class
    fireEvent.click(screen.getByRole("button", { name: /Cancel Loops/ }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
    expect((await screen.findByRole("alert")).textContent).toContain("at least 3 characters");
    fireEvent.change(screen.getByLabelText(/Reason for cancelling/), { target: { value: "Trainer unwell" } });
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancellation" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/it/batches/b1/timetable/s1/cancellations", expect.objectContaining({ method: "POST", body: JSON.stringify({ occurs_on: "2026-11-04", reason: "Trainer unwell" }) })));
    await waitFor(() => expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "GET").length).toBe(2)); // reloaded
  });
});

describe("AdminTimetablePanel", () => {
  const slot = { id: "s1", batch_id: "b1", weekday: 0, day: "Monday", start_time: "19:00", end_time: "21:00", mode: "online", room: null, meeting_url: null, topic: null };
  let slots: unknown[];
  let writeStatus: number;
  beforeEach(() => {
    slots = [slot];
    writeStatus = 201;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url === "/api/v1/admin/batches") return Promise.resolve(res([{ id: "b1", name: "PY-DEC", program: "Python" }]));
      if (url.startsWith("/api/v1/it/timetable")) return Promise.resolve(res(feed));
      if (init?.method === "DELETE") return Promise.resolve(res(null, 204));
      if (init?.method === "POST" || init?.method === "PUT") {
        return Promise.resolve(writeStatus < 300 ? res({ ...slot, id: "s2" }, writeStatus) : res({ detail: "The trainer already teaches PY-NOV at that time" }, writeStatus));
      }
      return Promise.resolve(res({ batch_id: "b1", items: slots }));
    });
  });

  async function pick() {
    render(<AdminTimetablePanel />);
    await screen.findByRole("option", { name: "PY-DEC — Python" });
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "b1" } });
    await screen.findByRole("cell", { name: "Monday" });
  }

  it("adds a slot and shows an overlap refusal", async () => {
    await pick();
    expect(screen.getByText("Online · no link yet")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Day"), { target: { value: "2" } });
    fireEvent.change(screen.getByLabelText("Mode"), { target: { value: "offline" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    expect((await screen.findByRole("alert")).textContent).toBe("An in-person class needs a room.");
    fireEvent.change(screen.getByLabelText(/Room/), { target: { value: "Lab 2" } });
    writeStatus = 409;
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    expect((await screen.findByRole("alert")).textContent).toBe("The trainer already teaches PY-NOV at that time");
    writeStatus = 201;
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    expect(await screen.findByText("Slot added.")).toBeTruthy();
    const post = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "POST").at(-1)!;
    expect(post[0]).toBe("/api/v1/it/batches/b1/timetable");
    expect(JSON.parse((post[1] as RequestInit).body as string)).toEqual({ weekday: 2, start_time: "19:00", end_time: "21:00", mode: "offline", room: "Lab 2", meeting_url: null, topic: null });
  });

  it("refuses a link that is not http(s) before sending (browser QA-02) and keeps the batch in the URL (QA-04)", async () => {
    window.history.replaceState(null, "", "/it/admin/timetable?batch=b1");
    render(<AdminTimetablePanel />);
    await screen.findByRole("cell", { name: "Monday" }); // preselected from ?batch=
    fireEvent.change(screen.getByLabelText(/Class link/), { target: { value: "javascript:alert(1)" } });
    fireEvent.click(screen.getByRole("button", { name: "Add slot" }));
    expect((await screen.findByRole("alert")).textContent).toContain("must start with https://");
    expect(fetchMock.mock.calls.some(([, init]) => (init as RequestInit)?.method === "POST")).toBe(false);
    fireEvent.change(screen.getByLabelText("Batch"), { target: { value: "" } });
    expect(window.location.search).toBe("");
  });

  it("sends one request for a double click: the button is disabled while saving", async () => {
    await pick();
    const add = screen.getByRole("button", { name: "Add slot" });
    fireEvent.click(add);
    fireEvent.click(add);
    expect(await screen.findByText("Slot added.")).toBeTruthy();
    expect(fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === "POST").length).toBe(1);
  });

  it("edits with PUT and removes after confirming", async () => {
    await pick();
    fireEvent.click(screen.getByRole("button", { name: "Edit Monday 19:00" }));
    expect(screen.getByRole("heading", { name: "Edit slot" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText(/Topic/), { target: { value: "Loops" } });
    fireEvent.click(screen.getByRole("button", { name: "Save slot" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/it/batches/b1/timetable/s1", expect.objectContaining({ method: "PUT" })));
    expect(await screen.findByText("Slot updated.")).toBeTruthy();
    const row = screen.getByRole("cell", { name: "Monday" }).closest("tr")!;
    fireEvent.click(within(row).getByRole("button", { name: "Remove Monday 19:00" }));
    fireEvent.click(within(row).getByRole("button", { name: "Confirm remove" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith("/api/v1/it/batches/b1/timetable/s1", { method: "DELETE" }));
    expect(await screen.findByText("Slot removed.")).toBeTruthy();
  });
});
