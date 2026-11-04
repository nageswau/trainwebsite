import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RequirementVisibility from "@/components/RequirementVisibility";
import sitemap from "@/app/sitemap";
import type { Requirement, VisibilityDetail } from "@/lib/recruiterRequirements";

// hrc-008 (DEC-SCOPE-385 V1/V4/V7/V8): the requirement's Visibility card and the sitemap. The server decides the grant and validates the
// pool; these check what is shown, what is sent and how the answer is shown.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const visibility = (over: Partial<VisibilityDetail> = {}): VisibilityDetail => ({ key: "public", label: "Public website", segment_pool: null, can_change: true, ...over });
const requirement = (v: VisibilityDetail) => ({ id: "R1", code: "REQ-0001", title: "Java Dev", updated_at: "2026-11-04T04:00:00Z", visibility: v }) as Requirement;

let sent: { url: string; method: string; body: Record<string, unknown> }[];
let replies: Response[];
let poolsReply: () => Promise<Response>;

beforeEach(() => {
  sent = [];
  replies = [];
  poolsReply = () => Promise.resolve(res({ items: [{ id: "P1", name: "Cloud Engineers" }, { id: "P2", name: "Java Developers" }] }));
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    if (init?.method && init.method !== "GET") {
      sent.push({ url, method: init.method, body: JSON.parse(String(init.body ?? "{}")) });
      return Promise.resolve(replies.shift()!);
    }
    return poolsReply();
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("hrc-008 requirement visibility", () => {
  it("shows the current visibility read-only to a reader without the publish grant", () => {
    render(<RequirementVisibility requirement={requirement(visibility({ key: "segment", label: "Segment (talent pool)", segment_pool: { id: "P1", name: "Cloud Engineers", active: true }, can_change: false }))} onDone={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Visibility" })).toBeTruthy();
    expect(screen.getByText("Segment (talent pool): Cloud Engineers")).toBeTruthy();
    expect(screen.getByText(/Listed in the student portal only for members of one talent pool/)).toBeTruthy();
    expect(screen.queryByLabelText("Who can see this job")).toBeNull();
    expect(screen.queryByRole("button", { name: "Save visibility" })).toBeNull();
  });

  it("saves Internal only with a PUT and reports the server's answer", async () => {
    const onDone = vi.fn();
    replies.push(res({ requirement: requirement(visibility({ key: "internal", label: "Internal only" })) }));
    render(<RequirementVisibility requirement={requirement(visibility())} onDone={onDone} />);
    const save = screen.getByRole("button", { name: "Save visibility" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true); // nothing changed yet
    expect(screen.getAllByText("Listed on the careers page and in the student portal.")).toHaveLength(1); // QA-02: said once
    const select = screen.getByLabelText("Who can see this job");
    expect(document.getElementById(select.getAttribute("aria-describedby")!)?.textContent).toBe("Listed on the careers page and in the student portal."); // QA-03
    fireEvent.change(screen.getByLabelText("Who can see this job"), { target: { value: "internal" } });
    expect(screen.getByText("Seen by staff only. Candidates cannot see or apply to it.")).toBeTruthy();
    fireEvent.click(save);
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(sent).toEqual([{ url: "/api/v1/recruiter/requirements/R1/visibility", method: "PUT", body: { visibility: "internal" } }]);
    expect(onDone.mock.calls[0][1]).toBe("Visibility saved: Internal only.");
  });

  it("a segment needs a talent pool before it is sent", async () => {
    const onDone = vi.fn();
    replies.push(res({ requirement: requirement(visibility({ key: "segment", label: "Segment (talent pool)", segment_pool: { id: "P2", name: "Java Developers", active: true } })) }));
    render(<RequirementVisibility requirement={requirement(visibility())} onDone={onDone} />);
    fireEvent.change(screen.getByLabelText("Who can see this job"), { target: { value: "segment" } });
    await waitFor(() => expect(screen.getByRole("option", { name: "Java Developers" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Save visibility" }));
    expect((await screen.findByRole("alert")).textContent).toBe("Choose the talent pool that may see this job.");
    expect(sent).toEqual([]);
    fireEvent.change(screen.getByLabelText("Talent pool"), { target: { value: "P2" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visibility" }));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(sent[0].body).toEqual({ visibility: "segment", segment_pool_id: "P2" });
  });

  it("shows the server's refusal and keeps the form", async () => {
    replies.push(res({ detail: "You cannot change who sees job requirements" }, 403));
    render(<RequirementVisibility requirement={requirement(visibility())} onDone={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Who can see this job"), { target: { value: "portal" } });
    fireEvent.click(screen.getByRole("button", { name: "Save visibility" }));
    expect((await screen.findByRole("alert")).textContent).toContain("You cannot change who sees job requirements");
    expect((screen.getByLabelText("Who can see this job") as HTMLSelectElement).value).toBe("portal");
  });

  it("says so when the talent pools cannot be loaded", async () => {
    poolsReply = () => Promise.resolve(res({ detail: "no" }, 403));
    render(<RequirementVisibility requirement={requirement(visibility())} onDone={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Who can see this job"), { target: { value: "segment" } });
    expect(await screen.findByRole("option", { name: "Talent pools could not be loaded" })).toBeTruthy();
  });
});

describe("hrc-008 public job list is never cached (QA-01)", () => {
  const jobsInit = () => (fetch as unknown as { mock: { calls: [string, RequestInit][] } }).mock.calls.find(([url]) => url.endsWith("/api/v1/public/jobs"))?.[1];

  it("the careers page reads the public jobs fresh, so a job made internal leaves it at once", async () => {
    poolsReply = () => Promise.resolve(res([]));
    const { default: Careers } = await import("@/app/it/careers/page");
    await Careers();
    expect(jobsInit()).toEqual({ cache: "no-store" });
  });

  it("so does the IT home page's Current openings", async () => {
    poolsReply = () => Promise.resolve(res([]));
    const { default: ITPage } = await import("@/app/it/page");
    await ITPage();
    expect(jobsInit()).toEqual({ cache: "no-store" });
  });
});

describe("hrc-008 sitemap (V8)", () => {
  it("lists no individual job, so an internal job cannot leak through it", () => {
    const urls = sitemap().map((entry) => new URL(entry.url).pathname);
    expect(urls).toContain("/it/careers");
    expect(urls.filter((path) => /jobs?\//.test(path) || path.startsWith("/it/careers/"))).toEqual([]);
  });
});
