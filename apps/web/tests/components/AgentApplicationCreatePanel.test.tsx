import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationCreatePanel from "@/components/AgentApplicationCreatePanel";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const page = (items: unknown[]) => ({ items, total: items.length, limit: 20, offset: 0 });
const students = [
  { id: "r1", has_login: false, full_name: "Asha Rao", email: null, status: "active" },
  { id: "r2", has_login: true, full_name: "Ravi Iyer", email: "ravi@example.local", status: "active" },
];

function stub(post: (body: Record<string, unknown>) => Response) {
  const fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/workflows/overseas/agent/crm/students")) return Promise.resolve(json(page(students)));
    if (url === "/api/v1/public/universities") return Promise.resolve(json([{ id: "u1", slug: "u1", name: "Uni One", city: "X" }]));
    if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
    if (init?.method === "POST") return Promise.resolve(post(JSON.parse(String(init.body))));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function pick(name: string) {
  const input = await screen.findByRole("combobox", { name: "Linked student" });
  fireEvent.focus(input);
  fireEvent.click(await screen.findByRole("option", { name }));
}

describe("AgentApplicationCreatePanel (AGN-008)", () => {
  it("offers agency students with and without a login", async () => {
    stub(() => json({}, 201));
    render(<AgentApplicationCreatePanel />);
    const input = await screen.findByRole("combobox", { name: "Linked student" });
    fireEvent.focus(input);
    expect(await screen.findByRole("option", { name: "Asha Rao — no login" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "Ravi Iyer — ravi@example.local" })).toBeInTheDocument();
  });

  it("posts the record id and the new fields, then reports and resets", async () => {
    const onCreated = vi.fn();
    const fetchMock = stub(() => json({ application: { id: "a1" } }, 201));
    render(<AgentApplicationCreatePanel onCreated={onCreated} />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Application ID"), { target: { value: "UCAS-1" } });
    fireEvent.change(screen.getByLabelText("Offer deadline"), { target: { value: "2027-01-15" } });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));
    const status = await screen.findByText("Application created.");
    expect(status).toHaveFocus();
    expect(onCreated).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls.find(([, i]) => (i as RequestInit | undefined)?.method === "POST")!;
    expect(url).toBe("/api/v1/workflows/overseas/agent/crm/applications");
    expect(JSON.parse(String((init as RequestInit).body))).toMatchObject({ agent_student_id: "r1", university_id: "u1", application_reference: "UCAS-1", offer_deadline: "2027-01-15", submitted_on: null });
  });

  it("shows the server's 409 in an alert and keeps the entry", async () => {
    stub(() => json({ detail: "An application for this university/course already exists" }, 409));
    render(<AgentApplicationCreatePanel />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.change(screen.getByLabelText("Application ID"), { target: { value: "KEEP" } });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    expect(screen.getByLabelText("Application ID")).toHaveValue("KEEP");
  });

  it("limits the submission date to today", async () => {
    stub(() => json({}, 201));
    render(<AgentApplicationCreatePanel />);
    await screen.findByRole("combobox", { name: "Linked student" });
    expect(screen.getByLabelText("Submitted on")).toHaveAttribute("max");
  });
  // QA8-06: a same-tick second submit sends nothing.
  it("sends one POST for two same-tick Create submits", async () => {
    let resolvePost: (r: Response) => void = () => {};
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/workflows/overseas/agent/crm/students")) return Promise.resolve(json(page(students)));
      if (url === "/api/v1/public/universities") return Promise.resolve(json([{ id: "u1", slug: "u1", name: "Uni One", city: "X" }]));
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "POST") return new Promise<Response>((r) => (resolvePost = r));
      return Promise.resolve(json({}));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationCreatePanel />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    const form = screen.getByRole("form", { name: "Create application" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, i]) => (i as RequestInit | undefined)?.method === "POST")).toHaveLength(1);
    resolvePost(json({ application: { id: "a1" } }, 201));
    expect(await screen.findByText("Application created.")).toBeInTheDocument();
  });

  // QA8-12: a stale server message goes when the browser blocks a submit, or when the user edits a field after an error.
  it("clears the previous server message on an invalid submit", async () => {
    stub(() => json({ detail: "An application for this university/course already exists" }, 409));
    render(<AgentApplicationCreatePanel />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    fireEvent.invalid(screen.getByLabelText("Intake (required)"));
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("clears the previous server message when a field changes after an error", async () => {
    stub(() => json({ detail: "An application for this university/course already exists" }, 409));
    render(<AgentApplicationCreatePanel />);
    await pick("Asha Rao — no login");
    fireEvent.change(screen.getByLabelText("University (required)"), { target: { value: "u1" } });
    fireEvent.click(screen.getByRole("button", { name: "Create application" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("already exists");
    fireEvent.change(screen.getByLabelText("Application ID"), { target: { value: "NEW-1" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
