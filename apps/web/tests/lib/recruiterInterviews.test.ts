import { describe, expect, it } from "vitest";

import { interviewOf, interviewsUrl, isInterviewListPage, istDay, isView, noticeText, ROUNDS } from "@/lib/recruiterInterviews";

// rec-020 (IV1, IV9, IV12): the §14 rounds in source order, the list URL and views, the reply shapes and the notice wording.
describe("recruiterInterviews (rec-020)", () => {
  it("has the five EVID-018 §14 rounds in source order", () => {
    expect(ROUNDS.map((r) => r.label)).toEqual(["HR Round", "Technical Round", "Manager Round", "Final Round", "Client Round"]);
  });

  it("builds the list URL and recognises the views and a list page", () => {
    expect(interviewsUrl("awaiting_update", 50)).toBe("/api/v1/recruiter/interviews?view=awaiting_update&limit=50&offset=50");
    expect(isView("on_hold")).toBe(true);
    expect(isView("today")).toBe(false);
    expect(isInterviewListPage({ items: [], total: 0, limit: 50, offset: 0, counts: {} })).toBe(true);
    expect(isInterviewListPage({ items: [], total: 0, limit: 50, offset: 0 })).toBe(false);
  });

  it("reads the item from either reply shape", () => {
    const item = { id: "I1", scheduled_at: "2026-10-10T04:30:00Z", history: [], allowed_statuses: [] };
    expect(interviewOf(item)?.id).toBe("I1");
    expect(interviewOf({ interview: item, notifications: { candidate: "off", contact: null } })?.id).toBe("I1");
    expect(interviewOf({ detail: "nope" })).toBeNull();
  });

  it("words the notices and groups by the IST day", () => {
    expect(noticeText({ candidate: "queued", contact: "no_email" })).toBe("Candidate: email queued. Contact: no email address.");
    expect(noticeText({ candidate: "in_app", contact: null })).toBe("Candidate: notified in the portal.");
    expect(noticeText(undefined)).toBe("");
    expect(istDay("2026-10-10T20:00:00Z")).toBe("Sun, 11 Oct 2026"); // 01:30 IST the next day
  });
});
