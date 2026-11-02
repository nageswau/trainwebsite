import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItStudentProfileForm from "@/components/ItStudentProfileForm";
import type { ItEnrollment, ItStudentProfileResponse } from "@/lib/itStudentProfile";

const URL = "/api/v1/counselor/it/students/s1/profile";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const enrollment = (extra: Partial<ItEnrollment> = {}): ItEnrollment => ({
  id: "e1", enrollment_code: "EDU-1", program: "Python Full Stack", batch: "Batch A", status: "active",
  start_date: "2026-11-10", end_date: "2027-01-10", delivery_mode: "Hybrid", start_date_override: null, end_date_override: null,
  delivery_mode_override: null, batch_start_date: "2026-11-10", batch_end_date: "2027-01-10", batch_mode: "Hybrid", ...extra,
});
const data = (extra: Partial<ItStudentProfileResponse["profile"]> = {}, enrollments: ItEnrollment[] = [enrollment()]): ItStudentProfileResponse => ({
  student: { id: "s1", full_name: "Asha Rao", student_code: "AB12CD34" },
  profile: {
    exists: true, date_of_birth: "2001-04-05", address: "12 MG Road", city: "Bengaluru", qualification: "B.Tech", graduation_year: 2023,
    emergency_contact_name: "Ravi Kumar", emergency_contact_relation: "Father", emergency_contact_phone: "+91 98765 43210",
    updated_at: "2026-11-02T10:00:00Z", updated_by_name: "Nora Counselor", ...extra,
  },
  enrollments,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ItStudentProfileForm (itc-012)", () => {
  it("shows the saved record, who saved it last and each enrolment's dates", () => {
    render(<ItStudentProfileForm initial={data({}, [enrollment(), enrollment({ id: "e2", enrollment_code: "EDU-2", program: "Data Science", start_date: "2027-02-01", start_date_override: "2027-02-01" })])} url={URL} />);
    expect(screen.getByLabelText("Emergency contact name")).toHaveValue("Ravi Kumar");
    expect(screen.getByLabelText("Emergency contact phone")).toHaveValue("+91 98765 43210");
    expect(screen.getByLabelText("Graduation year")).toHaveValue(2023);
    expect(screen.getByText(/Last saved by Nora Counselor/)).toBeInTheDocument();
    const rows = within(screen.getByRole("table", { name: "Enrolments" })).getAllByRole("row");
    expect(rows).toHaveLength(3);
    expect(rows[2]).toHaveTextContent("Data Science");
    expect(rows[2]).toHaveTextContent("Set for this student");
    expect(screen.queryByRole("button", { name: /Save dates/ })).not.toBeInTheDocument(); // no overrides without enrollmentsUrl
  });

  it("says when nothing is saved and when there are no enrolments", () => {
    render(<ItStudentProfileForm initial={data({ exists: false, updated_by_name: null, updated_at: null, emergency_contact_name: null }, [])} url={URL} />);
    expect(screen.getByText("No details saved yet.")).toBeInTheDocument();
    expect(screen.getByText("No enrolments yet.")).toBeInTheDocument();
  });

  it("saves only the profile fields with PATCH and shows success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(data({ city: "Mysuru", updated_by_name: "Asha Rao" })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItStudentProfileForm initial={data()} url={URL} />);
    fireEvent.change(screen.getByLabelText("City"), { target: { value: "Mysuru" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("status")).toHaveTextContent("Details saved.");
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe(URL);
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(init.body);
    expect(body.city).toBe("Mysuru");
    expect(body.graduation_year).toBe(2023);
    expect(Object.keys(body)).not.toContain("exists");
    expect(screen.getByText(/Last saved by Asha Rao/)).toBeInTheDocument();
  });

  it("shows a refused save with the field name and keeps the entries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: [{ loc: ["body", "emergency_contact_phone"], msg: "Enter a phone number of 7–20 digits" }] }, 422)));
    render(<ItStudentProfileForm initial={data()} url={URL} />);
    fireEvent.change(screen.getByLabelText("Emergency contact phone"), { target: { value: "call me" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Emergency contact phone");
    expect(alert).toHaveTextContent("Enter a phone number");
    expect(screen.getByLabelText("Emergency contact phone")).toHaveValue("call me");
  });

  it("ignores a second click while saving", async () => {
    let resolve: (r: Response) => void = () => {};
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((r) => (resolve = r)));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItStudentProfileForm initial={data()} url={URL} />);
    const button = screen.getByRole("button", { name: "Save details" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    resolve(res(data()));
    expect(await screen.findByRole("status")).toHaveTextContent("Details saved.");
  });

  it("lets staff override an enrolment's dates and mode, or go back to the batch", async () => {
    const after = data({}, [enrollment({ start_date: "2026-11-17", start_date_override: "2026-11-17", delivery_mode: "Offline", delivery_mode_override: "Offline" })]);
    const fetchMock = vi.fn().mockResolvedValue(res(after));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItStudentProfileForm initial={data()} url={URL} enrollmentsUrl="/api/v1/counselor/it/students/s1/enrollments" />);
    const editor = screen.getByRole("group", { name: "Dates for EDU-1" });
    fireEvent.change(within(editor).getByLabelText("Start date"), { target: { value: "2026-11-17" } });
    fireEvent.change(within(editor).getByLabelText("Delivery mode"), { target: { value: "Offline" } });
    fireEvent.click(within(editor).getByRole("button", { name: "Save dates" }));
    expect(await screen.findByText("Dates saved.")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/v1/counselor/it/students/s1/enrollments/e1");
    expect(JSON.parse(init.body)).toEqual({ start_date: "2026-11-17", end_date: null, delivery_mode: "Offline" });
    expect(within(screen.getByRole("table", { name: "Enrolments" })).getAllByRole("row")[1]).toHaveTextContent("Set for this student");

    fetchMock.mockResolvedValue(res(data()));
    fireEvent.click(within(screen.getByRole("group", { name: "Dates for EDU-1" })).getByRole("button", { name: "Use batch dates" }));
    expect(await screen.findByText("Dates saved.")).toBeInTheDocument();
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ start_date: null, end_date: null, delivery_mode: null });
  });
});
