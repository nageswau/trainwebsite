import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import type { CandidateDetail } from "@/lib/recruiterCandidates";

// hrc-003 (DEC-SCOPE-370 S7): the candidate edit form sends the token it opened with; a stale save shows the notice and Review puts the
// user's edits over the latest version, whose token the next save carries.
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn(), push: vi.fn(), refresh: vi.fn() }) }));
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const sources = { items: [{ id: "s1", name: "Referral", active: true, sort_order: 1 }], total: 1, limit: 100, offset: 0 };
const candidate = (over: Partial<CandidateDetail> = {}) =>
  ({
    id: "C1", candidate_code: "CAN-000001", name: "Rahul K", location: null, experience_months: null, preferred_role: null, source: { id: "s1", name: "Referral", active: true },
    source_detail: null, status: "available", archived: false, created_at: "2026-11-01T00:00:00Z", mobile: "9876543210", email: null, qualification: null,
    college: null, passing_year: null, current_company: "Acme", current_salary: null, expected_salary: null, notice_days: null, preferred_locations: [],
    linkedin: null, archived_at: null, created_by: null, updated_by: null, updated_at: "2026-11-04T04:00:00.111111+00:00", resumes: [], can_edit: true, ...over,
  }) as CandidateDetail;
const conflict = {
  code: "record_changed", message: "This record changed since you opened it", changed_by: { id: "u2", full_name: "Priya Admin" },
  changed_at: "2026-11-04T04:45:00.222222+00:00", changed_fields: ["current_company"],
  current: candidate({ current_company: "Globex", location: "Pune", updated_at: "2026-11-04T04:45:00.222222+00:00" }),
};

let patches: Record<string, unknown>[];
let replies: Response[];
const onSaved = vi.fn();
const onLatest = vi.fn();

beforeEach(() => {
  patches = [];
  onSaved.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        patches.push(JSON.parse(String(init.body)));
        return Promise.resolve(replies.shift()!);
      }
      if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res(sources));
      return Promise.resolve(res({ matches: [] }));
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const field = (label: RegExp) => screen.getByLabelText(label) as HTMLInputElement;

describe("RecruiterCandidateForm — changed since you opened it", () => {
  it("sends the token; Review keeps the user's edit over the latest version and the resave carries the new token", async () => {
    replies = [res({ detail: conflict }, 409), res(candidate({ id: "C1", location: "Hyderabad" }))];
    render(<RecruiterCandidateForm initial={candidate()} onSaved={onSaved} onLatest={onLatest} onCancel={vi.fn()} />);
    await screen.findByRole("option", { name: "Referral" });
    fireEvent.change(field(/^Location/), { target: { value: "Hyderabad" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByText(/This record changed since you opened it \(by Priya Admin/)).toBeInTheDocument();
    expect(screen.getByText("Changed: Current company.")).toBeInTheDocument();
    expect(patches[0]).toMatchObject({ location: "Hyderabad", expected_updated_at: "2026-11-04T04:00:00.111111+00:00" });
    expect(onSaved).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Review my changes" }));
    expect(onLatest).toHaveBeenCalledWith(conflict.current); // QA-02: the page behind the form shows the latest too
    expect(field(/^Location/).value).toBe("Hyderabad");
    expect(field(/^Current company/).value).toBe("Globex");
    expect(screen.getByRole("list", { name: "Your changes" })).toHaveTextContent("Location: yours “Hyderabad”, now on record “Pune”");

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(patches[1]).toMatchObject({ location: "Hyderabad", current_company: "Globex", expected_updated_at: "2026-11-04T04:45:00.222222+00:00" });
  });
});
