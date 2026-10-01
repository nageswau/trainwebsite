import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentForm from "@/components/AgentStudentForm";
import type { AgentStudentDetail } from "@/lib/agentStudents";

const saved: AgentStudentDetail = {
  id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: null, preferred_intake: null, status: "active",
  assigned_to: null, created_at: "", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null,
  preferred_course: null, notes: null, created_by: "M", archived_at: null, archived_by: null, updated_at: "",
};
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const type = (label: RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("AgentStudentForm (AGN-004)", () => {
  it("groups the fields and marks only Full name as required", () => {
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    for (const legend of ["Personal", "Contact", "Academic", "Preferences"]) expect(screen.getByRole("group", { name: legend })).toBeInTheDocument();
    expect(screen.getByLabelText("Full name (required)")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Phone")).toHaveAttribute("type", "tel");
    expect(screen.getByLabelText("Date of birth")).toHaveAttribute("type", "date");
  });

  it("moves focus to the first invalid field and does not submit", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/^Email$/, "bad");
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    const name = screen.getByLabelText("Full name (required)");
    expect(name).toHaveFocus();
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(screen.getByText("Full name is required")).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toHaveAccessibleDescription("Enter a valid email address");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("shows the duplicate warning and saves anyway with confirmation", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        res({ detail: { code: "possible_duplicate", message: "A student with this email or phone already exists in your agency", matches: [{ id: "x", full_name: "Asha R", has_login: false, status: "archived", matched_on: ["email"] }], hidden_matches: 1 } }, 409),
      )
      .mockResolvedValueOnce(res({ student: saved }, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<AgentStudentForm mode="create" onSaved={onSaved} onCancel={vi.fn()} />);
    type(/Full name/, "Asha");
    type(/^Email$/, "A@X.com");
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    expect(await screen.findByText(/Asha R/)).toBeInTheDocument();
    expect(screen.getByText("1 more you can't view.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(JSON.parse(String(fetchMock.mock.calls[1][1].body))).toEqual({ full_name: "Asha", email: "a@x.com", confirm_duplicate: true });
  });

  it("blocks a double submit", () => {
    const fetchMock = vi.fn(() => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/Full name/, "Asha");
    const save = screen.getByRole("button", { name: "Save student" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("sends only changed fields when editing", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ student: saved }));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentForm mode="edit" student={{ ...saved, phone: "123" }} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/^Phone$/, "");
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(fetchMock.mock.calls[0][0]).toBe("/api/v1/workflows/overseas/agent/crm/students/s1");
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
    expect(JSON.parse(String(fetchMock.mock.calls[0][1].body))).toEqual({ phone: null });
  });

  it("shows the server's message when saving fails and keeps the entry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Your agency's account is suspended" }, 403)));
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/Full name/, "Asha");
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Your agency's account is suspended");
    expect(screen.getByLabelText("Full name (required)")).toHaveValue("Asha");
  });

  it("says so when the network drops", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/Full name/, "Asha");
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/did not complete/);
  });

  // --- browser QA fixes ----------------------------------------------------------------------------------------------------
  it("asks before Cancel throws away unsaved changes (QA-03)", () => {
    const onCancel = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={onCancel} />);
    type(/Full name/, "Asha");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("cancels a clean form without asking (QA-03)", () => {
    const onCancel = vi.fn();
    const confirm = vi.spyOn(window, "confirm");
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalledTimes(1);
  });

  it("asks before an in-app link leaves unsaved changes, and stays when declined (QA-03)", () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(
      <>
        <a href="/overseas/agent/dashboard">Dashboard</a>
        <AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />
      </>,
    );
    type(/Full name/, "Asha");
    const click = new MouseEvent("click", { bubbles: true, cancelable: true, button: 0 });
    screen.getByRole("link", { name: "Dashboard" }).dispatchEvent(click);
    expect(window.confirm).toHaveBeenCalled();
    expect(click.defaultPrevented).toBe(true);
  });

  it("puts a server validation error on its field (QA-05)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(res({ detail: [{ type: "value_error", loc: ["body", "full_name"], msg: "Value error, must not contain control or bidirectional-override characters" }] }, 422)),
    );
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/Full name/, "Asha");
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    const name = screen.getByLabelText("Full name (required)");
    await waitFor(() => expect(name).toHaveAttribute("aria-invalid", "true"));
    expect(name).toHaveAccessibleDescription("Must not contain control or bidirectional-override characters");
    expect(name).toHaveFocus();
  });

  it("offers one next step while the duplicate warning is shown (QA-08)", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(res({ detail: { code: "possible_duplicate", message: "m", matches: [{ id: "x", full_name: "Asha R", has_login: false, status: "active", matched_on: ["email"] }], hidden_matches: 0 } }, 409)),
    );
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/Full name/, "Asha");
    fireEvent.click(screen.getByRole("button", { name: "Save student" }));
    await screen.findByRole("button", { name: "Save anyway" });
    expect(screen.getByRole("button", { name: "Save student" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Go back" }));
    expect(screen.getByRole("button", { name: "Save student" })).toBeEnabled();
  });

  it("asks before leaving with unsaved changes", () => {
    render(<AgentStudentForm mode="create" onSaved={vi.fn()} onCancel={vi.fn()} />);
    type(/Full name/, "A");
    const event = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });
});
