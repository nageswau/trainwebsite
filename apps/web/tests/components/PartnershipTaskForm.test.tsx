import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PartnershipTaskForm from "@/components/PartnershipTaskForm";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const saved = { id: "t1", title: "Send MoU", due_on: "2030-01-10", permissions: {} };
const university = { id: "u1", name: "XYZ University" };

let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
beforeEach(() => {
  fetchMock = vi.fn<typeof fetch>((input) =>
    Promise.resolve(String(input).endsWith("/catalogue") ? res({ titles: ["Follow up with university", "Send MoU"] }) : res({ task: saved }, 201)),
  );
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.clearAllMocks(); });

const posted = () => fetchMock.mock.calls.find(([u, init]) => String(u) === "/api/v1/partnership/tasks" && init?.method === "POST");

describe("PartnershipTaskForm (upc-020)", () => {
  it("adds a task for a fixed university with the §19 titles as suggestions", async () => {
    const onSaved = vi.fn();
    render(<PartnershipTaskForm university={university} canAssign={false} onSaved={onSaved} onCancel={vi.fn()} />);
    expect(screen.getByText("XYZ University")).toBeInTheDocument();
    await waitFor(() => expect(document.querySelectorAll("datalist option")).toHaveLength(2));
    fireEvent.click(screen.getByLabelText("Task"));
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Send MoU" } });
    fireEvent.change(screen.getByLabelText("Due date (IST, required)"), { target: { value: "2030-01-10" } });
    fireEvent.change(screen.getByLabelText("Priority"), { target: { value: "high" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(JSON.parse(String(posted()![1]!.body))).toEqual({ university_id: "u1", kind: "task", title: "Send MoU", due_on: "2030-01-10", priority: "high", notes: null });
    expect(screen.queryByText("Assign to")).toBeNull(); // a manager assigns only themselves
  });

  it("checks the required fields before sending", () => {
    render(<PartnershipTaskForm university={university} canAssign={false} onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(screen.getByText("Title is required")).toBeInTheDocument();
    expect(screen.getByText("Choose a due date")).toBeInTheDocument();
    expect(posted()).toBeUndefined();
  });

  it("puts the server's 422 on the field it is about and keeps the typed text", async () => {
    fetchMock.mockImplementation((input) =>
      Promise.resolve(String(input).endsWith("/catalogue") ? res({ titles: [] }) : res({ detail: "Choose yourself or an active partnership manager from your team" }, 422)),
    );
    render(<PartnershipTaskForm university={university} canAssign onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Call" } });
    fireEvent.change(screen.getByLabelText("Due date (IST, required)"), { target: { value: "2030-01-10" } });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));
    expect(await screen.findByText("Choose yourself or an active partnership manager from your team")).toBeInTheDocument();
    expect(screen.getByLabelText("Title (required)")).toHaveValue("Call");
  });

  it("edits title, priority and notes only (the date moves through Reschedule)", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ task: saved })));
    const task = {
      id: "t1", university: { id: "u1", university_code: "UNV-1", name: "XYZ" }, kind: "follow_up" as const, title: "Call", notes: null, due_on: "2030-01-10",
      priority: "medium", status: "open" as const, band: "upcoming", overdue: false, source: "manual", assignee: { id: "p", full_name: "R", active: true },
      created_by: { id: "p", full_name: "R", active: true }, completed_at: null, cancelled_at: null, cancel_reason: null, created_at: "", updated_at: "",
      permissions: { can_edit: true, can_reschedule: true, can_complete: true, can_cancel: true },
    };
    render(<PartnershipTaskForm task={task} canAssign={false} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.queryByLabelText("Due date (IST, required)")).toBeNull();
    fireEvent.change(screen.getByLabelText("Title (required)"), { target: { value: "Call again" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PATCH")).toBe(true));
    const [url, init] = fetchMock.mock.calls.find(([, i]) => i?.method === "PATCH")!;
    expect(url).toBe("/api/v1/partnership/tasks/t1");
    expect(JSON.parse(String(init!.body))).toEqual({ title: "Call again", priority: "medium", notes: null });
  });
});
