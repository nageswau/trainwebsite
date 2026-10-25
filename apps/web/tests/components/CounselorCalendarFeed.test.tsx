import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorCalendarFeed from "@/components/CounselorCalendarFeed";
import { CALENDAR_FEED_API, REGENERATE_PROMPT, REVOKE_PROMPT } from "@/lib/counselorCalendar";

// ccrm-038 (DEC-SCOPE-273 CA4): create / copy / regenerate / turn off the counselor's calendar feed.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });
const OFF = { active: false, created_at: null, url: null };
const ON = { active: true, created_at: "2026-10-25T08:00:00Z", url: null };
const URL1 = "http://localhost:3138/api/v1/calendar/feeds/tok1.ics";

describe("CounselorCalendarFeed (ccrm-038)", () => {
  it("creates the link, shows it once and copies it", async () => {
    const fetch = vi.fn(() => json(201, { ...ON, url: URL1 }));
    vi.stubGlobal("fetch", fetch);
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    render(<CounselorCalendarFeed initial={OFF} />);
    expect(screen.getByText(/Off/)).toBeTruthy();
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Create calendar link" })));
    expect(fetch).toHaveBeenCalledWith(CALENDAR_FEED_API, expect.objectContaining({ method: "POST" }));
    expect((screen.getByLabelText("Your calendar link") as HTMLInputElement).value).toBe(URL1);
    expect(screen.getByRole("status").textContent).toMatch(/shown only once/);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Copy link" })));
    expect(writeText).toHaveBeenCalledWith(URL1);
    expect(screen.getByRole("status").textContent).toMatch(/Link copied/);
  });

  it("asks before regenerating and does nothing when declined", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<CounselorCalendarFeed initial={ON} />);
    expect(screen.queryByLabelText("Your calendar link")).toBeNull(); // an existing link is never shown again
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Create a new link" })));
    expect(confirm).toHaveBeenCalledWith(REGENERATE_PROMPT);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("turns the feed off after confirming", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve({ ok: true, status: 204, json: async () => { throw new Error("no body"); } })));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<CounselorCalendarFeed initial={ON} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Turn off feed" })));
    expect(confirm).toHaveBeenCalledWith(REVOKE_PROMPT);
    expect(screen.getByRole("button", { name: "Create calendar link" })).toBeTruthy();
    expect(screen.getByRole("status").textContent).toMatch(/feed is off/);
  });

  it("shows the API's refusal as an alert", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(403, { detail: "Only an overseas counselor has a calendar feed" })));
    render(<CounselorCalendarFeed initial={OFF} />);
    await act(async () => fireEvent.click(screen.getByRole("button", { name: "Create calendar link" })));
    expect(screen.getByRole("alert").textContent).toBe("Only an overseas counselor has a calendar feed");
  });
});
