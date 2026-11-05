import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterInterviewItem from "@/components/RecruiterInterviewItem";
import { durationOf, endsAt, type RecInterview, zoneOptions } from "@/lib/recruiterInterviews";
import { timelineEntry } from "@/lib/recruiterTimeline";
import { recInterview } from "@/tests/helpers/recruiterInterviews";

// hrc-028 (DEC-SCOPE-399 I1-I8): the new interview fields on the form and the item, Cancel with a required reason, the link history lines
// and the candidate-zone time.
vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), usePathname: () => "/recruiter/interviews",
  useSearchParams: () => new URLSearchParams() }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let reply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  reply = () => res({ interview: recInterview({ status: "cancelled", status_label: "Cancelled", cancel_reason: "Panel unavailable", can_cancel: false }),
    notifications: { candidate: "in_app", contact: null } });
  fetchMock = vi.fn(() => Promise.resolve(reply()));
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const writes = () => fetchMock.mock.calls.map(([url, init]) => [url, init.method, JSON.parse(init.body)]);
const item = (i: RecInterview, onChanged = vi.fn()) => render(<ul><RecruiterInterviewItem interview={i} onChanged={onChanged} /></ul>);

describe("hrc-028 helpers", () => {
  it("derives the duration and the end, and keeps a stored zone in the list", () => {
    expect(durationOf(recInterview({ ends_at: "2026-10-12T06:15:00Z" }))).toBe("45");
    expect(durationOf(recInterview())).toBe("");
    expect(endsAt("2030-01-15T11:00:00+05:30", "90")).toBe("2030-01-15T07:00:00.000Z");
    expect(endsAt("2030-01-15T11:00:00+05:30", "")).toBeNull();
    expect(zoneOptions("Asia/Dubai")).toContain("Asia/Dubai");
    expect(zoneOptions("Pacific/Fiji").at(-1)).toBe("Pacific/Fiji");
  });

  it("titles a details event on the timeline", () => {
    const entry = timelineEntry({ kind: "interview", event: "details", status: "hr_round" } as never);
    expect(entry.title).toBe("Interview details changed: HR Round");
  });
});

describe("RecruiterInterviewItem (hrc-028)", () => {
  it("shows the new details and the candidate's time when the zone is not IST", () => {
    item(recInterview({ round_number: 2, time_zone: "Asia/Dubai", local_when: "12 Oct 2026, 09:30 AM – 10:15 AM Asia/Dubai (UTC+04:00)",
      platform: "zoom", platform_label: "Zoom", phone_details: "+91 98450 00000", instructions: "Bring a pen", documents_required: "ID proof" }));
    const card = screen.getAllByRole("listitem")[0];
    for (const text of ["HR Round (round 2)", "Candidate's time", "09:30 AM – 10:15 AM Asia/Dubai (UTC+04:00)", "Zoom", "+91 98450 00000", "Bring a pen", "ID proof"]) {
      expect(card.textContent).toContain(text);
    }
  });

  it("shows a same-day end as a time only (QA-01)", () => {
    item(recInterview({ ends_at: "2026-10-12T06:15:00Z" }));
    const when = screen.getByText("When").nextElementSibling?.textContent ?? "";
    expect(when.match(/12 Oct 2026/g)).toHaveLength(1);
    expect(when).toMatch(/– 11:45/);
  });

  it("cancels with a required reason and the notice choice", async () => {
    const onChanged = vi.fn();
    item(recInterview(), onChanged);
    fireEvent.click(screen.getByRole("button", { name: /Cancel interview/ }));
    const form = screen.getByRole("form", { name: "Cancel INT-000001" });
    fireEvent.click(within(form).getByRole("button", { name: "Cancel interview" }));
    expect(within(form).getByText("Enter the reason")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(within(form).getByLabelText("Reason (required, shown to the candidate)"), { target: { value: "Panel unavailable" } });
    fireEvent.click(within(form).getByRole("button", { name: "Cancel interview" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(writes()).toEqual([["/api/v1/recruiter/interviews/I1/cancel", "POST", { reason: "Panel unavailable", notify: true }]]);
    expect(onChanged.mock.calls[0][1]).toBe("Interview cancelled. Candidate: notified in the portal.");
  });

  it("shows a cancelled interview with its reason, no link and no actions", () => {
    item(recInterview({ status: "cancelled", status_label: "Cancelled", cancel_reason: "Panel unavailable", can_cancel: false, can_edit: false,
      can_reschedule: false, allowed_statuses: [] }));
    const card = screen.getAllByRole("listitem")[0];
    expect(card.textContent).toContain("Cancelled — Panel unavailable");
    expect(within(card).queryByRole("link", { name: /Meeting link/ })).toBeNull();
    expect(within(card).queryByRole("button")).toBeNull();
  });

  it("names a link replacement and a location change in the history", () => {
    item(recInterview({ history: [
      { event: "details", from_status: "scheduled", to_status: "scheduled", old_scheduled_at: null, new_scheduled_at: null, note: null, actor: { id: "r1", full_name: "Riya" },
        created_at: "2026-10-09T05:30:00Z", old_meeting_url: "https://a", new_meeting_url: "https://b", old_location: "Room 1", new_location: "Room 2" },
    ] }));
    const text = screen.getAllByRole("listitem")[0].textContent ?? "";
    expect(text).toContain("Meeting link replaced");
    expect(text).toContain("Location changed from Room 1 to Room 2");
    expect(text).not.toContain("https://a");
  });

  it("edits the new fields and sends only what changed", async () => {
    reply = () => res(recInterview({ round_number: 3 }));
    item(recInterview());
    fireEvent.click(screen.getByRole("button", { name: /Edit/ }));
    const form = screen.getByRole("form", { name: "Edit interview INT-000001" });
    fireEvent.change(within(form).getByLabelText("Round number"), { target: { value: "3" } });
    fireEvent.change(within(form).getByLabelText("Duration"), { target: { value: "45" } });
    fireEvent.change(within(form).getByLabelText("Candidate's time zone"), { target: { value: "Asia/Dubai" } });
    fireEvent.change(within(form).getByLabelText("Platform"), { target: { value: "google_meet" } });
    fireEvent.change(within(form).getByLabelText("Instructions"), { target: { value: "Line 1\nLine 2" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [[url, method, body]] = writes();
    expect([url, method]).toEqual(["/api/v1/recruiter/interviews/I1", "PATCH"]);
    expect(body).toEqual({ round_number: 3, ends_at: "2026-10-12T06:15:00.000Z", time_zone: "Asia/Dubai", platform: "google_meet", instructions: "Line 1\nLine 2",
      expected_updated_at: "2026-10-09T05:30:00.123456+00:00" });
  });

  it("refuses a round number outside 1-20 before sending", () => {
    item(recInterview());
    fireEvent.click(screen.getByRole("button", { name: /Edit/ }));
    const form = screen.getByRole("form", { name: "Edit interview INT-000001" });
    fireEvent.change(within(form).getByLabelText("Round number"), { target: { value: "21" } });
    fireEvent.click(within(form).getByRole("button", { name: "Save changes" }));
    expect(within(form).getByText("Enter a round number from 1 to 20")).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
