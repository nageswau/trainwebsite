import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import SchoolSkillBatchesPanel from "@/components/SchoolSkillBatchesPanel";
import type { SkillBatch } from "@/lib/skills";

// ENH-011 spec §7: the counselor's batch list (filters, Load more, empty/no-school states) and the create form (validation, errors,
// one request per submit, then straight to the new batch).
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push, refresh: vi.fn() }) }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const SUN = { id: "s1", name: "Sunrise School" };
const LAKE = { id: "s2", name: "Lakeview School" };

function batch(n: string, over: Partial<SkillBatch> = {}): SkillBatch {
  return { id: `b${n}`, school: SUN, module_type: "soft_skills", title: `Batch ${n}`, topic: null, trainer_name: null, start_date: "2026-10-01", end_date: null, status: "open", enrolled_count: 3, created_at: "2026-09-22T10:00:00Z", ...over };
}
const page = (items: SkillBatch[], total = items.length, offset = 0) => ({ items, total, limit: 25, offset });

function stubFetch(handler: (url: string, init?: RequestInit) => Response | Promise<Response>) {
  const fn = vi.fn((url: string, init?: RequestInit) => Promise.resolve(handler(String(url), init)));
  vi.stubGlobal("fetch", fn);
  return fn;
}
const rowOf = (text: RegExp) => screen.getAllByRole("listitem").find((li) => text.test(li.textContent ?? ""))!;

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  push.mockReset();
});

describe("SchoolSkillBatchesPanel", () => {
  it("lists batches with a link, the module and status in words, and the enrolled count", () => {
    render(<SchoolSkillBatchesPanel initial={page([batch("1", { status: "closed", module_type: "digital_skills" })])} schools={[SUN]} />);
    const row = rowOf(/Batch 1/);
    expect(within(row).getByRole("link", { name: "Batch 1" }).getAttribute("href")).toBe("/school/career-counselor/skills/b1");
    expect(within(row).getByText(/Digital Skills/)).toBeTruthy();
    expect(within(row).getByText("Closed")).toBeTruthy();
    expect(within(row).getByText("3 enrolled")).toBeTruthy();
  });

  it("explains a counselor with no school and shows no create form", () => {
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[]} />);
    expect(screen.getByText(/not assigned to any school yet/i)).toBeTruthy();
    expect(screen.queryByRole("button", { name: /create/i })).toBeNull();
    expect(screen.queryByLabelText("Title")).toBeNull();
  });

  it("offers a first batch when there are none and moves focus to the form", () => {
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[SUN]} />);
    expect(screen.getByText("No skills batches yet.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Create a batch" }));
    expect(document.activeElement).toBe(screen.getByLabelText("Title"));
  });

  it("replaces the rows behind a skeleton when a filter changes", async () => {
    let resolve!: (r: Response) => void;
    const fetchMock = stubFetch(() => new Promise<Response>((r) => { resolve = r; }));
    render(<SchoolSkillBatchesPanel initial={page([batch("1")])} schools={[SUN]} />);
    fireEvent.change(screen.getByLabelText("Module"), { target: { value: "digital_skills" } });
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/school/career-counselor/skill-batches?limit=25&offset=0&module_type=digital_skills");
    expect(screen.getByRole("list", { name: "Skills batches" }).getAttribute("aria-busy")).toBe("true");
    await act(async () => resolve(json(page([batch("2", { module_type: "digital_skills" })]))));
    expect(screen.queryByText("Batch 1")).toBeNull();
    expect(screen.getByText("Batch 2")).toBeTruthy();
  });

  it("appends with Load more and keeps the rows on screen", async () => {
    const fetchMock = stubFetch(() => json(page([batch("2")], 2, 1)));
    render(<SchoolSkillBatchesPanel initial={page([batch("1")], 2)} schools={[SUN]} />);
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await waitFor(() => expect(screen.getByText("Batch 2")).toBeTruthy());
    expect(screen.getByText("Batch 1")).toBeTruthy();
    expect(fetchMock.mock.calls[0][0]).toContain("offset=1");
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
  });

  it("shows a retry when a list reload fails", async () => {
    stubFetch(() => json({ detail: "boom" }, 500));
    render(<SchoolSkillBatchesPanel initial={page([batch("1")])} schools={[SUN]} />);
    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "closed" } });
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
  });
});

describe("create form", () => {
  function fill() {
    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Public speaking" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2026-10-01" } });
  }

  it("asks for a school when the counselor has several, then creates and opens the batch", async () => {
    const fetchMock = stubFetch(() => json(batch("9"), 201));
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[SUN, LAKE]} />);
    fireEvent.change(screen.getByLabelText("School"), { target: { value: "s2" } });
    fireEvent.change(screen.getByLabelText("Skills module"), { target: { value: "digital_skills" } });
    fill();
    fireEvent.change(screen.getByLabelText("Trainer name (optional)"), { target: { value: "R. Iyer" } });
    fireEvent.click(screen.getByRole("button", { name: "Create batch" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/school/career-counselor/skills/b9"));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/school/career-counselor/skill-batches");
    expect(JSON.parse(String(init?.body))).toEqual({ school_id: "s2", module_type: "digital_skills", title: "Public speaking", topic: null, trainer_name: "R. Iyer", start_date: "2026-10-01", end_date: null });
  });

  it("sends one request however fast the button is pressed", async () => {
    const fetchMock = stubFetch(() => new Promise<Response>(() => undefined));
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[SUN]} />);
    fill();
    const button = screen.getByRole("button", { name: "Create batch" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Creating…" }).hasAttribute("disabled")).toBe(true);
  });

  it("marks the field the server rejected, keeps the entry, and does not repeat the message in the alert (QA-07)", async () => {
    stubFetch(() => json({ detail: [{ loc: ["body", "topic"], msg: "Value error, must not contain control or bidirectional-override characters" }] }, 422));
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[SUN]} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create batch" }));
    const topic = screen.getByLabelText("Topic (optional)");
    await waitFor(() => expect(topic.getAttribute("aria-invalid")).toBe("true"));
    expect(document.getElementById(topic.getAttribute("aria-describedby")!)!.textContent).toBe("Must not contain control or bidirectional-override characters");
    expect(screen.getByRole("alert").textContent).toBe("Check the highlighted fields.");
    expect((screen.getByLabelText("Title") as HTMLInputElement).value).toBe("Public speaking");
  });

  it("checks the required fields and the date order in the browser, in plain words, before sending (QA-05, QA-06)", () => {
    const fetchMock = stubFetch(() => json({}));
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[SUN]} />);
    fireEvent.click(screen.getByRole("button", { name: "Create batch" }));
    expect(fetchMock).not.toHaveBeenCalled();
    const title = screen.getByLabelText("Title");
    const start = screen.getByLabelText("Start date");
    expect(title.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(title.getAttribute("aria-describedby")!)!.textContent).toBe("Enter a title");
    expect(document.getElementById(start.getAttribute("aria-describedby")!)!.textContent).toBe("Choose a start date");
    expect(document.activeElement).toBe(title); // the first invalid field

    fill();
    fireEvent.change(screen.getByLabelText("End date (optional)"), { target: { value: "2026-09-30" } });
    fireEvent.click(screen.getByRole("button", { name: "Create batch" }));
    expect(fetchMock).not.toHaveBeenCalled();
    const end = screen.getByLabelText("End date (optional)");
    expect(end.getAttribute("aria-invalid")).toBe("true");
    expect(document.getElementById(end.getAttribute("aria-describedby")!)!.textContent).toBe("The end date must be on or after the start date");
  });

  it("names the page with a level-1 heading (QA-13)", () => {
    render(<SchoolSkillBatchesPanel initial={page([batch("1")])} schools={[SUN]} />);
    expect(screen.getByRole("heading", { level: 1, name: "Skills batches" })).toBeTruthy();
  });

  it("offers sign-in again when the session has expired", async () => {
    stubFetch(() => json({ detail: "Not authenticated" }, 401));
    render(<SchoolSkillBatchesPanel initial={page([])} schools={[SUN]} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Create batch" }));
    const alert = await screen.findByRole("alert");
    expect(within(alert).getByRole("link", { name: "Sign in again" }).getAttribute("href")).toBe("/overseas/login");
    expect(document.activeElement).toBe(alert);
  });
});
