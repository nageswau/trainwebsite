import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import LiveClassesPanel from "@/components/LiveClassesPanel";
import LiveSessionManagePanel, { toZoneInput } from "@/components/LiveSessionManagePanel";

// nehn-029: the trainer reschedules (only changed fields are sent, times in the batch zone) or cancels (reason required) a class that
// has not started; the provider warning and kept-attendance count are shown; learners see "Cancelled" with the reason and no join button.
const refresh = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn(), refresh }) }));

const FUTURE = new Date(Date.now() + 3 * 86400000);
FUTURE.setUTCSeconds(0, 0);
const SESSION = {
  id: "s1", batch: "Batch A", title: "Python basics", starts_at: FUTURE.toISOString(), ends_at: new Date(FUTURE.getTime() + 3600000).toISOString(),
  provider: "google_meet", meeting_url: "https://meet.example.com/a", host_url: null, recording_url: null, recording_status: "not_available",
  sync_status: "created", status: "scheduled", cancel_reason: null, timezone: "Asia/Kolkata",
};
const CANCELLED = { ...SESSION, id: "s2", title: "Old class", status: "cancelled", cancel_reason: "Trainer unwell" };
const PAST = { ...SESSION, id: "s3", title: "Yesterday", starts_at: new Date(Date.now() - 86400000).toISOString() };

type Call = { url: string; method: string; body: unknown };
const calls: Call[] = [];

function serve(list: unknown[], reply: { status: number; body: unknown } = { status: 200, body: {} }) {
  calls.length = 0;
  vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
    const method = init?.method || "GET";
    calls.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : undefined });
    const ok = method === "GET" ? true : reply.status < 400;
    return { ok, status: method === "GET" ? 200 : reply.status, json: async () => (method === "GET" ? list : reply.body) } as Response;
  }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  refresh.mockReset();
});

describe("toZoneInput", () => {
  it("renders an instant as a datetime-local value in the batch zone", () => {
    expect(toZoneInput("2026-11-02T13:30:00Z", "Asia/Kolkata")).toBe("2026-11-02T19:00");
    expect(toZoneInput(null, "Asia/Kolkata")).toBe("");
  });
});

describe("LiveSessionManagePanel", () => {
  it("lists only upcoming scheduled classes as changeable, and cancelled ones with their reason", async () => {
    serve([SESSION, CANCELLED, PAST]);
    render(<LiveSessionManagePanel />);
    expect(await screen.findByRole("heading", { name: "Python basics" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Yesterday" })).toBeNull();
    expect(screen.getByText(/Trainer unwell/)).toBeTruthy();
  });

  it("shows an empty state", async () => {
    serve([PAST]);
    render(<LiveSessionManagePanel />);
    expect(await screen.findByText("No upcoming live class can be changed.")).toBeTruthy();
  });

  it("sends only the changed time and shows the provider warning", async () => {
    serve([SESSION], { status: 200, body: { warning: "Update the Google Meet meeting yourself." } });
    render(<LiveSessionManagePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Reschedule" }));
    const start = screen.getByLabelText("Starts (Asia/Kolkata)") as HTMLInputElement;
    const moved = start.value.replace(/T(\d\d)/, (_, h) => `T${String((Number(h) + 1) % 24).padStart(2, "0")}`);
    fireEvent.change(start, { target: { value: moved } });
    fireEvent.submit(screen.getByRole("form", { name: "Reschedule Python basics" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Google Meet"));
    const patch = calls.find(call => call.method === "PATCH")!;
    expect(patch.url).toBe("/api/v1/communications/it/live-sessions/s1");
    expect(patch.body).toEqual({ starts_at: moved });
    expect(refresh).toHaveBeenCalled();
  });

  it("does not send an unchanged reschedule", async () => {
    serve([SESSION]);
    render(<LiveSessionManagePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Reschedule" }));
    fireEvent.submit(screen.getByRole("form", { name: "Reschedule Python basics" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Nothing was changed.");
    expect(calls.some(call => call.method === "PATCH")).toBe(false);
  });

  it("cancels with a reason and reports attendance that was kept", async () => {
    serve([SESSION], { status: 200, body: { warning: null, attendance_records: 2 } });
    render(<LiveSessionManagePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel class" }));
    fireEvent.change(screen.getByLabelText("Reason learners will see"), { target: { value: "  Public holiday " } });
    fireEvent.submit(screen.getByRole("form", { name: "Cancel Python basics" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("2 learner(s)"));
    expect(calls.find(call => call.method === "POST")).toMatchObject({ url: "/api/v1/communications/it/live-sessions/s1/cancel", body: { reason: "Public holiday" } });
  });

  it("refuses a blank reason without calling the API", async () => {
    serve([SESSION]);
    render(<LiveSessionManagePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel class" }));
    fireEvent.submit(screen.getByRole("form", { name: "Cancel Python basics" }));
    expect((await screen.findByRole("alert")).textContent).toContain("at least 3 characters");
    expect(calls.some(call => call.method === "POST")).toBe(false);
  });

  it("shows the server's refusal", async () => {
    serve([SESSION], { status: 409, body: { detail: "Past sessions cannot be rescheduled or cancelled" } });
    render(<LiveSessionManagePanel />);
    fireEvent.click(await screen.findByRole("button", { name: "Cancel class" }));
    fireEvent.change(screen.getByLabelText("Reason learners will see"), { target: { value: "Holiday" } });
    fireEvent.submit(screen.getByRole("form", { name: "Cancel Python basics" }));
    expect((await screen.findByRole("alert")).textContent).toContain("Past sessions");
  });
});

describe("LiveClassesPanel", () => {
  it("shows a cancelled class with its reason and no join button", async () => {
    serve([CANCELLED]);
    render(<LiveClassesPanel />);
    expect(await screen.findByText("Cancelled")).toBeTruthy();
    expect(screen.getByText("Trainer unwell")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /Join class/ })).toBeNull();
  });
});
