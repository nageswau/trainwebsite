import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementForm from "@/components/RecruiterRequirementForm";
import type { Requirement } from "@/lib/recruiterRequirements";

// hrc-003 (DEC-SCOPE-370 S7, AC1-AC3): the requirement edit form sends the token it opened with; a 409 `record_changed` shows the
// notice, and Review / Reload re-base the form on the latest version (the next save carries its token).
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const requirement = (over: Partial<Requirement> = {}) =>
  ({
    id: "R1", code: "REQ-0001", title: "Java Dev", company: { id: "C1", code: "CO-1", name: "Acme" }, location: "Pune", status: "sourcing", status_label: "Sourcing",
    priority: null, vacancies: null, closes_on: null, requirement_date: null, deadline_state: null, assigned_recruiter: null,
    permissions: { can_edit: true, can_change_status: true, can_reassign: false, can_view_matches: true }, description: "", department: null, job_category: null,
    qualification: null, experience_min_months: null, experience_max_months: null, salary_min: null, salary_max: null, work_mode: null, shift: null,
    employment_type: null, joining_requirement: null, skills: [], joined_count: 0, allowed_statuses: [], status_history: [], created_by: null,
    created_at: "2026-11-01T00:00:00Z", updated_at: "2026-11-04T04:00:00.111111+00:00", ...over,
  }) as Requirement;
const conflict = {
  code: "record_changed", message: "This record changed since you opened it", changed_by: { id: "u2", full_name: "Priya Admin" },
  changed_at: "2026-11-04T04:45:00.222222+00:00", changed_fields: ["location"],
  current: requirement({ location: "Chennai", updated_at: "2026-11-04T04:45:00.222222+00:00" }),
};

let patches: Record<string, unknown>[];
let replies: Response[];
const onSaved = vi.fn();
const onLatest = vi.fn();

beforeEach(() => {
  patches = [];
  onSaved.mockReset();
  onLatest.mockReset();
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "PATCH") {
        patches.push(JSON.parse(String(init.body)));
        return Promise.resolve(replies.shift()!);
      }
      if (url.includes("/statuses")) return Promise.resolve(res({ statuses: [], vocabularies: {}, expiring_days: 7 }));
      return Promise.resolve(res({ items: [], total: 0, limit: 100, offset: 0 }));
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const field = (label: RegExp) => screen.getByLabelText(label) as HTMLInputElement;

describe("RecruiterRequirementForm — changed since you opened it", () => {
  it("sends the token, and Review re-applies only the user's edits over the latest version", async () => {
    replies = [res({ detail: conflict }, 409), res({ requirement: requirement({ title: "Senior Java Dev", location: "Chennai", updated_at: "T3" }) })];
    render(<RecruiterRequirementForm mode="edit" requirement={requirement()} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.change(field(/^Job title/), { target: { value: "Senior Java Dev" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    const alert = await screen.findByText(/This record changed since you opened it \(by Priya Admin/);
    expect(alert.closest("[role=alert]")).toHaveTextContent("Changed: Job location.");
    expect(patches[0]).toEqual({ title: "Senior Java Dev", expected_updated_at: "2026-11-04T04:00:00.111111+00:00" });
    expect(onSaved).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Review my changes" }));
    expect(field(/^Job title/).value).toBe("Senior Java Dev");
    expect(field(/^Job location/).value).toBe("Chennai");
    expect(screen.getByRole("list", { name: "Your changes" })).toHaveTextContent("Job title: yours “Senior Java Dev”, now on record “Java Dev”");

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(patches[1]).toEqual({ title: "Senior Java Dev", expected_updated_at: "2026-11-04T04:45:00.222222+00:00" });
  });

  it("Reload drops the user's edits and shows the latest version", async () => {
    replies = [res({ detail: conflict }, 409)];
    render(<RecruiterRequirementForm mode="edit" requirement={requirement()} onSaved={onSaved} onLatest={onLatest} onCancel={vi.fn()} />);
    fireEvent.change(field(/^Job title/), { target: { value: "Senior Java Dev" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    fireEvent.click(await screen.findByRole("button", { name: "Reload latest" }));
    expect(onLatest).toHaveBeenCalledWith(conflict.current); // QA-01: the page behind the form shows the latest too
    expect(field(/^Job title/).value).toBe("Java Dev");
    expect(field(/^Job location/).value).toBe("Chennai");
    expect(screen.queryByRole("button", { name: "Review my changes" })).toBeNull();
  });
});
