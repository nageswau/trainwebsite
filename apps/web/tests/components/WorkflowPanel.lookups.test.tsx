import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import WorkflowPanel from "@/components/WorkflowPanel";
import type { User } from "@/lib/types";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn(), push: vi.fn() }), useSearchParams: () => new URLSearchParams() }));

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const user = (role: string, division = "overseas") => ({ id: "u1", email: "u@example.local", full_name: "U", role, division, profile: {} }) as unknown as User;

function stub(lookups: Record<string, unknown>) {
  const mock = vi.fn((url: string, init?: RequestInit) => {
    const lookup = Object.keys(lookups).find((key) => url.startsWith(`/api/v1/lookups/${key}?`));
    if (lookup) return Promise.resolve(json(lookups[lookup]));
    if (init?.method && init.method !== "GET") return Promise.resolve(json({ id: "new" }, 201));
    return Promise.resolve(json([]));
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WorkflowPanel reference fields (ENH-031)", () => {
  it("Create visa case picks an application from the lookup and posts its id", async () => {
    const mock = stub({ "overseas-applications": { items: [{ id: "a1", label: "Asha Rao", detail: "Uni X · offer" }], truncated: false } });
    render(<WorkflowPanel user={user("overseas_admin")} section="visa" />);
    const input = await screen.findByRole("combobox", { name: "Application reference" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "Asha" } });
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — Uni X · offer" }));
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-applications?limit=20&q=Asha")).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Create visa case" }));
    await waitFor(() => {
      const post = mock.mock.calls.find(([url, init]) => url === "/api/v1/workflows/overseas/visa" && init?.method === "POST");
      expect(JSON.parse(String(post?.[1]?.body))).toMatchObject({ application_id: "a1" });
    });
  });

  it("a path-parameter reference (University Rep admission update) fills the URL from the pick", async () => {
    const mock = stub({ "overseas-applications": { items: [{ id: "a9", label: "Ravi Iyer", detail: "Uni Y · offer" }], truncated: false } });
    render(<WorkflowPanel user={user("university_rep")} section="student-communication" />);
    const input = await screen.findByRole("combobox", { name: "Application reference" });
    fireEvent.focus(input);
    fireEvent.click(await screen.findByRole("option", { name: "Ravi Iyer — Uni Y · offer" }));
    fireEvent.change(screen.getByLabelText("Update message"), { target: { value: "Offer is on the way" } });
    fireEvent.click(screen.getByRole("button", { name: "Post admission update" }));
    await waitFor(() => expect(mock.mock.calls.some(([url]) => url === "/api/v1/workflows/overseas/university-rep/applications/a9/updates")).toBe(true));
  });

  it("Schedule interview searches job applications", async () => {
    const mock = stub({ "it-job-applications": { items: [], truncated: false } });
    render(<WorkflowPanel user={user("placement_team", "it")} section="interviews" />);
    const input = await screen.findByRole("combobox", { name: "Job application reference" });
    fireEvent.focus(input);
    await waitFor(() => expect(mock.mock.calls.some(([url]) => String(url).startsWith("/api/v1/lookups/it-job-applications?"))).toBe(true));
  });

  it("the agent's Link student needs 3 characters and searches with purpose=link", async () => {
    const mock = stub({ "overseas-students": { items: [{ id: "s1", label: "Asha Rao", detail: "a***@example.local" }], truncated: false } });
    render(<WorkflowPanel user={user("agent")} section="students" />);
    const input = await screen.findByRole("combobox", { name: "Overseas student reference" });
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "as" } });
    expect(await screen.findByText("Type at least 3 characters.")).toBeInTheDocument();
    fireEvent.change(input, { target: { value: "ash" } });
    await screen.findByRole("option", { name: "Asha Rao — a***@example.local" });
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-students?limit=20&q=ash&purpose=link")).toBe(true);
  });

  it("document upload narrows the application lookup to the chosen student", async () => {
    const mock = stub({
      "overseas-students": { items: [{ id: "s1", label: "Asha Rao", detail: "asha@example.local" }], truncated: false },
      "overseas-applications": { items: [], truncated: false },
    });
    render(<WorkflowPanel user={user("agent")} section="documents" />);
    const student = await screen.findByRole("combobox", { name: "Student reference" });
    fireEvent.focus(student);
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — asha@example.local" }));
    fireEvent.focus(screen.getByRole("combobox", { name: "Application reference (optional)" }));
    await waitFor(() => expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/overseas-applications?limit=20&student_id=s1")).toBe(true));
  });

  it("document upload keeps the application picker disabled until a student is picked (final review)", async () => {
    stub({ "overseas-students": { items: [{ id: "s1", label: "Asha Rao", detail: "asha@example.local" }], truncated: false }, "overseas-applications": { items: [], truncated: false } });
    render(<WorkflowPanel user={user("agent")} section="documents" />);
    const student = await screen.findByRole("combobox", { name: "Student reference" });
    const application = () => screen.getByRole("combobox", { name: "Application reference (optional)" });
    expect(application()).toBeDisabled();
    fireEvent.focus(student);
    fireEvent.click(await screen.findByRole("option", { name: "Asha Rao — asha@example.local" }));
    expect(application()).toBeEnabled();
  });

  it("no student or application reference is a plain text box any more", async () => {
    stub({});
    for (const [role, section, division] of [["counselor", "appointments", "overseas"], ["overseas_admin", "applications", "overseas"], ["placement_team", "offers", "it"]] as const) {
      const { unmount } = render(<WorkflowPanel user={user(role, division)} section={section} />);
      await waitFor(() => expect(screen.getAllByRole("combobox").length).toBeGreaterThan(0));
      expect(document.querySelector('input[type="text"][name="student_id"], input[type="text"][name="application_id"], input:not([type])[name="student_id"], input:not([type])[name="application_id"]')).toBeNull();
      unmount();
    }
  });
});
