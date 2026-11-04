import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterInterviewForm from "@/components/RecruiterInterviewForm";
import type { RecInterview } from "@/lib/recruiterInterviews";

// hrc-003 (DEC-SCOPE-370 S7): the interview edit form sends the token it opened with; a stale save shows the notice, Review re-applies
// the user's edits over the latest details and the next save sends only what differs from them, with their token.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const interview = (over: Partial<RecInterview> = {}) =>
  ({
    id: "I1", code: "INT-0001", round: "hr_round", round_label: "HR round", scheduled_at: "2026-11-10T05:00:00Z", mode: "Online", meeting_url: null,
    interviewer: null, location: null, status: "scheduled", status_label: "Scheduled", result: null, updated_at: "2026-11-04T04:00:00.111111+00:00",
    application: { id: "A1", status: "interview", status_label: "Interview" }, candidate: { id: "C1", code: "CAN-1", name: "Rahul" },
    requirement: { id: "R1", code: "REQ-1", title: "Java Dev" }, company: { id: "CO1", name: "Acme" }, contact: null, history: [], allowed_statuses: [],
    can_edit: true, can_reschedule: true, feedback: null, can_feedback: false, ...over,
  }) as RecInterview;
const conflict = {
  code: "record_changed", message: "This record changed since you opened it", changed_by: { id: "u2", full_name: "Priya Admin" },
  changed_at: "2026-11-04T04:45:00.222222+00:00", changed_fields: ["location"],
  current: interview({ location: "Office 2", updated_at: "2026-11-04T04:45:00.222222+00:00" }),
};

let patches: Record<string, unknown>[];
let replies: Response[];
const onSaved = vi.fn();
const onLatest = vi.fn();

beforeEach(() => {
  patches = [];
  onSaved.mockReset();
  vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => {
    patches.push(JSON.parse(String(init?.body)));
    return Promise.resolve(replies.shift()!);
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const field = (label: RegExp) => screen.getByLabelText(label) as HTMLInputElement;

describe("RecruiterInterviewForm — changed since you opened it", () => {
  it("sends the token, and Review keeps the user's edit over the latest details", async () => {
    replies = [res({ detail: conflict }, 409), res(interview({ interviewer: "Arun", location: "Office 2", updated_at: "T3" }))];
    render(<RecruiterInterviewForm interview={interview()} contacts={[]} onSaved={onSaved} onLatest={onLatest} onCancel={vi.fn()} />);
    fireEvent.change(field(/^Interviewer/), { target: { value: "Arun" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(/This record changed since you opened it \(by Priya Admin/)).toBeInTheDocument();
    expect(screen.getByText("Changed: Location.")).toBeInTheDocument();
    expect(patches[0]).toEqual({ interviewer: "Arun", expected_updated_at: "2026-11-04T04:00:00.111111+00:00" });

    fireEvent.click(screen.getByRole("button", { name: "Review my changes" }));
    expect(onLatest).toHaveBeenCalledWith(conflict.current); // QA-03: the page behind the form shows the latest too
    expect(field(/^Interviewer/).value).toBe("Arun");
    expect(field(/^Location/).value).toBe("Office 2");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(patches[1]).toEqual({ interviewer: "Arun", expected_updated_at: "2026-11-04T04:45:00.222222+00:00" });
  });
});
