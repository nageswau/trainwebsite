import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentStudentCounselingForm from "@/components/AgentStudentCounselingForm";
import type { AgentStudentDetail, Counseling } from "@/lib/agentStudents";

const student: AgentStudentDetail = {
  id: "s1", has_login: false, full_name: "Asha", email: null, phone: null, preferred_country: null, preferred_intake: null, status: "active",
  assigned_to: null, created_at: "", date_of_birth: null, highest_qualification: null, institution: null, graduation_year: null,
  preferred_course: null, notes: null, created_by: "M", archived_at: null, archived_by: null, updated_at: "", counseling: null,
};
const recorded: Counseling = {
  counseling_completed: true, completed_at: "2026-10-01T09:00:00Z", completed_by: "Priya", career_interest: "Law", course_preference: null,
  country_preference: null, budget_amount: "1000.00", budget_currency: "INR", remarks: null, updated_at: "2026-10-01T09:00:00Z", updated_by: "Priya",
};
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const type = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const save = () => fireEvent.click(screen.getByRole("button", { name: /^Sav/ }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("AgentStudentCounselingForm (AGN-006)", () => {
  it("names the form, opens on the checkbox and offers the seven currencies", () => {
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("form", { name: "Record counseling for Asha" })).toBeInTheDocument();
    expect(screen.getByLabelText("Counseling completed")).toHaveFocus();
    expect(screen.getByLabelText("Amount")).toHaveAttribute("inputmode", "decimal");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual(["INR", "USD", "GBP", "EUR", "CAD", "AUD", "NZD"]);
  });

  it("refuses a negative budget without sending and focuses the amount", () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Amount", "-500");
    save();
    expect(screen.getByText("Budget cannot be negative")).toBeInTheDocument();
    expect(screen.getByLabelText("Amount")).toHaveFocus();
    expect(screen.getByLabelText("Amount")).toHaveAttribute("aria-invalid", "true");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("closes without a request when nothing changed", () => {
    const fetchMock = vi.fn();
    const onCancel = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={{ ...student, counseling: recorded }} onSaved={vi.fn()} onCancel={onCancel} />);
    expect(screen.getByRole("form", { name: "Edit counseling for Asha" })).toBeInTheDocument();
    save();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(onCancel).toHaveBeenCalled();
  });

  it("PUTs the whole record and hands back the saved student", async () => {
    const savedStudent = { ...student, counseling: recorded };
    const fetchMock = vi.fn().mockResolvedValue(res({ student: savedStudent }));
    const onSaved = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={onSaved} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByLabelText("Counseling completed"));
    type("Career interest", "Law");
    type("Amount", "1,000");
    save();
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(savedStudent));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/workflows/overseas/agent/crm/students/s1/counseling");
    expect(init.method).toBe("PUT");
    expect(JSON.parse(init.body)).toEqual({ counseling_completed: true, career_interest: "Law", course_preference: null, country_preference: null, budget_amount: "1000", budget_currency: "INR", remarks: null });
  });

  it("puts a 422 on its field and a 409 or 404 in one alert", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(res({ detail: [{ loc: ["body", "career_interest"], msg: "Value error, must be 200 characters or fewer" }] }, 422))
      .mockResolvedValueOnce(res({ detail: "Unarchive this student first" }, 409))
      .mockResolvedValueOnce(res({ detail: "Student not found" }, 404));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Career interest", "Law");
    save();
    expect(await screen.findByText("Must be 200 characters or fewer")).toBeInTheDocument();
    expect(screen.getByLabelText("Career interest")).toHaveAttribute("aria-invalid", "true");
    type("Career interest", "Law again");
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("Unarchive this student first");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save counseling" })).not.toBeDisabled());
    save();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Student not found"));
  });

  it("keeps the entry when the network drops", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Career interest", "Law");
    save();
    expect(await screen.findByRole("alert")).toHaveTextContent("The request did not complete");
    expect(screen.getByLabelText("Career interest")).toHaveValue("Law");
  });

  it("disables the form while saving and sends once on a double click", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    vi.stubGlobal("fetch", fetchMock);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Career interest", "Law");
    save();
    save();
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    resolve(res({ student }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Save counseling" })).toBeInTheDocument());
  });

  it("asks before cancelling unsaved changes", () => {
    const onCancel = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={onCancel} />);
    type("Remarks", "Draft");
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(confirm).toHaveBeenCalled();
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("counts remarks characters", () => {
    render(<AgentStudentCounselingForm detail={student} onSaved={vi.fn()} onCancel={vi.fn()} />);
    type("Remarks", "Hello");
    expect(screen.getByText("5 / 2000")).toBeInTheDocument();
  });
});
