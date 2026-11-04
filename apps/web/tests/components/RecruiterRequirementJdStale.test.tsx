import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterRequirementJd from "@/components/RecruiterRequirementJd";
import type { Jd, JdVersion } from "@/lib/recruiterJd";
import type { Requirement } from "@/lib/recruiterRequirements";

// hrc-003 (DEC-SCOPE-370 S1, S7, S8): the JD form sends the version it opened (0 = none); a stale save shows the notice and Review
// re-applies the user's edits over the latest version. "Update requirement from JD" sends the requirement's token; a stale one shows the
// latest requirement with the conflict summary.
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
const version = (over: Partial<JdVersion> = {}): JdVersion => ({
  version: 1, is_current: true, role: "Backend engineer", experience: null, qualification: null, skills: null, salary: null, location: null, description: null,
  responsibilities: null, requirements: null, openings: null, contact: null, closing_date: null, closing_date_differs: false, file: null, created_by: null,
  created_at: "2026-11-04T04:00:00Z", ...over,
});
const jd = (...versions: JdVersion[]): Jd => ({ jd_number: "JD-0001", versions, can_edit: true });
const record = (detail: object) => ({
  code: "record_changed", message: "This record changed since you opened it", changed_by: { id: "u2", full_name: "Priya Admin" },
  changed_at: "2026-11-04T04:45:00.222222+00:00", ...detail,
});

let posts: { url: string; method: string; body: Record<string, unknown> }[];
let replies: Response[];
const onRequirementChanged = vi.fn();

beforeEach(() => {
  posts = [];
  onRequirementChanged.mockReset();
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST" || init?.method === "PATCH") {
      posts.push({ url, method: init.method, body: JSON.parse(String(init.body)) });
      return Promise.resolve(replies.shift()!);
    }
    return Promise.resolve(res({ items: [] }));
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const field = (label: RegExp) => screen.getByLabelText(label) as HTMLInputElement;

describe("RecruiterRequirementJd — changed since you opened it", () => {
  it("the JD form sends the version it opened; Review keeps the user's edits over the latest version", async () => {
    const latest = jd(version({ version: 2, location: "Chennai" }), version());
    replies = [res({ detail: record({ changed_fields: ["location"], current: latest }) }, 409), res(jd(version({ version: 3, role: "Senior backend engineer", location: "Chennai" }), ...latest.versions))];
    render(<RecruiterRequirementJd requirement={requirement()} initial={jd(version())} onRequirementChanged={onRequirementChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Edit JD" }));
    fireEvent.change(field(/^Job role/), { target: { value: "Senior backend engineer" } });
    fireEvent.click(screen.getByRole("button", { name: "Save JD" }));

    expect(await screen.findByText(/This record changed since you opened it \(by Priya Admin/)).toBeInTheDocument();
    expect(screen.getByText("Changed: Location.")).toBeInTheDocument();
    expect(posts[0].body).toMatchObject({ role: "Senior backend engineer", expected_version: 1 });

    fireEvent.click(screen.getByRole("button", { name: "Review my changes" }));
    expect(field(/^Job role/).value).toBe("Senior backend engineer");
    expect(field(/^Location/).value).toBe("Chennai");
    expect(screen.getByRole("heading", { name: "Edit JD (saves version 3)" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save JD" }));
    await waitFor(() => expect(screen.getByText("JD saved as version 3.")).toBeInTheDocument());
    expect(posts[1].body).toMatchObject({ role: "Senior backend engineer", location: "Chennai", expected_version: 2 });
  });

  it("a first JD sends version 0", async () => {
    replies = [res(jd(version()), 201)];
    render(<RecruiterRequirementJd requirement={requirement()} initial={jd()} onRequirementChanged={onRequirementChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Create JD" }));
    fireEvent.click(screen.getByRole("button", { name: "Save JD" }));
    await waitFor(() => expect(posts).toHaveLength(1));
    expect(posts[0].body).toMatchObject({ expected_version: 0 });
  });

  it("Update requirement from JD sends the requirement's token and, when stale, shows the latest requirement", async () => {
    const latest = requirement({ location: "Mumbai", updated_at: "2026-11-04T04:45:00.222222+00:00" });
    replies = [res({ detail: record({ changed_fields: ["location"], current: latest }) }, 409)];
    render(<RecruiterRequirementJd requirement={requirement()} initial={jd(version({ location: "Chennai" }))} onRequirementChanged={onRequirementChanged} />);
    fireEvent.click(screen.getByRole("button", { name: "Update requirement from JD" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, update requirement" }));
    await waitFor(() => expect(onRequirementChanged).toHaveBeenCalledTimes(1));
    expect(posts[0]).toMatchObject({ method: "PATCH", body: { location: "Chennai", expected_updated_at: "2026-11-04T04:00:00.111111+00:00" } });
    const [next, text] = onRequirementChanged.mock.calls[0];
    expect(next).toEqual(latest);
    expect(text).toMatch(/^This record changed since you opened it \(by Priya Admin at .+\)\. It now shows the latest version: check the JD changes and apply again\.$/);
  });
});
