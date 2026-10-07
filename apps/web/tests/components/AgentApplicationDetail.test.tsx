import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentApplicationDetail from "@/components/AgentApplicationDetail";

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const detail = (over: Record<string, unknown> = {}) => ({
  id: "a1", agent_student_id: "r1", student: "Asha Rao", has_login: false, university: "Uni One", university_id: "u1", university_slug: "u1",
  course: null, course_id: null, intake: "Fall 2027", status: "offer", application_reference: "UCAS-1", submitted_on: "2026-09-01",
  application_deadline: null, offer_deadline: "2027-01-15", nearest_deadline: { kind: "offer", date: "2027-01-15" }, next_action: "Send deposit",
  updated_at: "", created_at: "", read_only_reason: null, counselor_name: null,
  history: [{ from_status: null, to_status: "enquiry", next_action: null, notes: null, changed_by: "Master One", created_at: "2026-09-01T10:00:00Z" }],
  ...over,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AgentApplicationDetail (AGN-008)", () => {
  it("loads, focuses its heading, and shows fields and history", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail() }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const heading = await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
    await waitFor(() => expect(heading).toHaveFocus());
    expect(screen.getByText("UCAS-1")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Status history" })).getByText(/Enquiry/)).toBeInTheDocument();
  });

  it("shows the EduSphere counsellor, or that none is assigned yet", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail({ counselor_name: "Asha Rao" }) }))));
    const first = render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
    expect(screen.getByText("EduSphere counsellor")).toBeInTheDocument();
    expect(screen.getByText("Asha Rao", { selector: "dd" })).toBeInTheDocument();
    first.unmount();
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail({ counselor_name: null }) }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    expect(await screen.findByText("Not assigned yet")).toBeInTheDocument();
  });

  it("offers only later stages up to status tracking", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail() }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const select = await screen.findByLabelText("Move to");
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Visa documentation", "Status tracking"]);
  });

  it("sends the displayed status as expected_status and reports success", async () => {
    const onChanged = vi.fn();
    const fetchMock = vi.fn((_: string, init?: RequestInit) => Promise.resolve(json({ application: init?.method === "POST" ? detail({ status: "visa_documentation" }) : detail() })));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={onChanged} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Update status" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Status updated to Visa documentation.");
    const post = fetchMock.mock.calls.find(([, i]) => i?.method === "POST")!;
    expect(JSON.parse(String(post[1]!.body))).toMatchObject({ to_status: "visa_documentation", expected_status: "offer" });
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "visa_documentation" }));
  });

  it("asks before withdrawing, and Escape cancels", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail() }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw application" }));
    const confirm = screen.getByRole("group", { name: "Confirm withdrawal" });
    fireEvent.keyDown(confirm, { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Confirm withdrawal" })).toBeNull();
    expect(screen.getByRole("button", { name: "Withdraw application" })).toHaveFocus();
  });

  it("on a 409 shows the server's words and reloads the application", async () => {
    let posted = false;
    const fetchMock = vi.fn((_: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted = true;
        return Promise.resolve(json({ detail: "This application changed since you opened it -- reload to see its current status" }, 409));
      }
      return Promise.resolve(json({ application: posted ? detail({ status: "withdrawn", read_only_reason: "withdrawn" }) : detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Update status" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed since you opened it");
    expect(await screen.findByText("This application is withdrawn, so it can no longer be changed.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  });

  it("edits, saving only changed fields, and Cancel returns focus to Edit", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "PATCH") return Promise.resolve(json({ application: detail({ intake: "Spring 2028" }) }));
      return Promise.resolve(json({ application: detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Intake (required)"), { target: { value: "Spring 2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
    const patch = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(JSON.parse(String(patch[1]!.body))).toEqual({ intake: "Spring 2028" });
  });

  it("on a 409 from Save shows the server's words and closes the edit form", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "PATCH") return Promise.resolve(json({ detail: "Unarchive this student first" }, 409));
      return Promise.resolve(json({ application: detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Intake (required)"), { target: { value: "Spring 2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Unarchive this student first");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).toBeNull());
    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByText("Fall 2027")).toBeInTheDocument();
  });

  it("returns focus to Withdraw application after a failed withdraw", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) =>
      Promise.resolve(init?.method === "POST" ? json({ detail: "This application changed since you opened it -- reload to see its current status" }, 409) : json({ application: detail() })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw application" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, withdraw" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("changed since you opened it");
    await waitFor(() => expect(screen.getByRole("button", { name: "Withdraw application" })).toHaveFocus());
  });

  it("says when the application is gone", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ detail: "Application not found" }, 404))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    expect(await screen.findByText("This application is no longer available.")).toBeInTheDocument();
  });

  it("keeps Edit but hides the status control for an enrolled application", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail({ status: "enrolled" }) }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    expect(await screen.findByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.queryByLabelText("Move to")).toBeNull();
    expect(screen.queryByRole("button", { name: "Withdraw application" })).toBeNull();
  });
  // QA8-01: a 422 from Save keeps the form open with the user's input, shows the server's words and focuses the alert (no reload).
  it("on a 422 from Save keeps the edit form open with the input and focuses the alert", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "PATCH") return Promise.resolve(json({ detail: "Course does not belong to selected university" }, 422));
      return Promise.resolve(json({ application: detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Intake (required)"), { target: { value: "Spring 2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Course does not belong to selected university");
    await waitFor(() => expect(alert).toHaveFocus());
    expect(screen.getByLabelText("Intake (required)")).toHaveValue("Spring 2028");
    expect(screen.getByRole("button", { name: "Save" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([u, i]) => u === "/api/v1/workflows/overseas/agent/crm/applications/a1" && !i?.method)).toHaveLength(1);
  });

  // QA8-01: a 409 from Save closes the form, reloads, and focuses the alert.
  it("on a 409 from Save focuses the alert after the reload", async () => {
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "PATCH") return Promise.resolve(json({ detail: "Unarchive this student first" }, 409));
      return Promise.resolve(json({ application: detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Intake (required)"), { target: { value: "Spring 2028" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Save" })).toBeNull());
    await waitFor(() => expect(fetchMock.mock.calls.filter(([u, i]) => u === "/api/v1/workflows/overseas/agent/crm/applications/a1" && !i?.method)).toHaveLength(2));
    expect(alert).toHaveFocus();
  });

  // QA8-02: after a successful withdraw, focus lands on the read-only notice.
  it("moves focus to the read-only notice after a withdraw", async () => {
    const fetchMock = vi.fn((_: string, init?: RequestInit) =>
      Promise.resolve(json({ application: init?.method === "POST" ? detail({ status: "withdrawn", read_only_reason: "withdrawn" }) : detail() })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Withdraw application" }));
    fireEvent.click(screen.getByRole("button", { name: "Yes, withdraw" }));
    const notice = await screen.findByText("This application is withdrawn, so it can no longer be changed.");
    await waitFor(() => expect(notice).toHaveFocus());
  });

  it("does not move focus to the read-only notice on the first load", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(json({ application: detail({ status: "withdrawn", read_only_reason: "withdrawn" }) }))));
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const heading = await screen.findByRole("heading", { name: "Asha Rao — Uni One" });
    await waitFor(() => expect(heading).toHaveFocus());
  });

  // QA8-03: the reload after a 409 updates the list card too.
  it("calls onChanged with the reloaded application after a 409", async () => {
    const onChanged = vi.fn();
    let posted = false;
    vi.stubGlobal("fetch", vi.fn((_: string, init?: RequestInit) => {
      if (init?.method === "POST") {
        posted = true;
        return Promise.resolve(json({ detail: "This application changed since you opened it -- reload to see its current status" }, 409));
      }
      return Promise.resolve(json({ application: posted ? detail({ status: "visa_documentation" }) : detail() }));
    }));
    render(<AgentApplicationDetail id="a1" onChanged={onChanged} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Update status" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ status: "visa_documentation" })));
    expect(onChanged).toHaveBeenCalledTimes(1);
  });

  // QA8-06: a same-tick second submit sends nothing.
  it("sends one PATCH for two same-tick Save submits", async () => {
    let resolvePatch: (r: Response) => void = () => {};
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/public/universities/")) return Promise.resolve(json({ courses: [] }));
      if (init?.method === "PATCH") return new Promise<Response>((r) => (resolvePatch = r));
      return Promise.resolve(json({ application: detail() }));
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByLabelText("Intake (required)"), { target: { value: "Spring 2028" } });
    const form = screen.getByRole("form", { name: "Edit application" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "PATCH")).toHaveLength(1);
    resolvePatch(json({ application: detail({ intake: "Spring 2028" }) }));
    expect(await screen.findByRole("status")).toHaveTextContent("Saved.");
  });

  it("sends one status POST for two same-tick Update status submits", async () => {
    let resolvePost: (r: Response) => void = () => {};
    const fetchMock = vi.fn((_: string, init?: RequestInit) =>
      init?.method === "POST" ? new Promise<Response>((r) => (resolvePost = r)) : Promise.resolve(json({ application: detail() })),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentApplicationDetail id="a1" onChanged={vi.fn()} onClose={vi.fn()} />);
    const button = await screen.findByRole("button", { name: "Update status" });
    const form = button.closest("form")!;
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock.mock.calls.filter(([, i]) => i?.method === "POST")).toHaveLength(1);
    resolvePost(json({ application: detail({ status: "visa_documentation" }) }));
    expect(await screen.findByRole("status")).toHaveTextContent("Status updated to Visa documentation.");
  });
});
