import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ApplicationDetailsPanel from "@/components/ApplicationDetailsPanel";
import { changedFields, CURRENCIES, detailsProblem, SCHOLARSHIP_STATUSES } from "@/lib/applicationDetails";

// ccrm-013 (DEC-SCOPE-256): the counselor's Application details panel on an application card -- view, edit, save the changed fields.
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const json = (body: unknown, ok = true, status = 200) => Promise.resolve({ ok, status, json: async () => body });
const URL = "/api/v1/workflows/overseas/applications/a1/details";
const details = (over: Record<string, unknown> = {}) => ({
  id: "a1", application_code: "APP-000001", faculty: "Engineering", campus: null, course_start_date: "2027-09-20", university_portal_url: "https://portal.example.ac.uk",
  university_contact_name: null, university_contact_email: null, tuition_fee: 18500, currency: "GBP", scholarship_status: "awarded", scholarship_amount: 2000,
  submitted_on: null, application_deadline: "2026-11-30", offer_deadline: null, documents_completed_on: null, decision_due_on: null, scholarship_label: "Awarded", ...over,
});

describe("applicationDetails lib", () => {
  it("mirrors the server lists", () => {
    expect(CURRENCIES).toEqual(["INR", "GBP", "USD", "EUR", "CAD", "AUD", "NZD", "SGD", "AED"]);
    expect(SCHOLARSHIP_STATUSES).toEqual(["none", "applied", "awarded", "declined"]);
  });

  it("asks for a currency with money and an award with an amount", () => {
    expect(detailsProblem({ tuition_fee: "100", currency: "" })).toMatch(/Currency is required/);
    expect(detailsProblem({ scholarship_amount: "5", scholarship_status: "applied", currency: "GBP" })).toMatch(/only when the scholarship is awarded/);
    expect(detailsProblem({ tuition_fee: "100", currency: "GBP" })).toBeNull();
  });

  it("sends only what changed, blanks as null", () => {
    expect(changedFields({ faculty: "A", campus: "", tuition_fee: "18500" }, { faculty: "A", campus: "B", tuition_fee: 18500 })).toEqual({ campus: null });
  });
});

describe("ApplicationDetailsPanel", () => {
  it("shows loading, then the details read-only", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(details())));
    render(<ApplicationDetailsPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(screen.getByText("Loading details…")).toBeInTheDocument();
    expect(await screen.findByText("Engineering")).toBeInTheDocument();
    expect(screen.getByText("GBP 18,500.00")).toBeInTheDocument();
    expect(screen.getByText("Awarded — GBP 2,000.00")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "https://portal.example.ac.uk" })).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("shows a load failure with a retry", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json({ detail: "Application is outside your assigned scope" }, false, 403)).mockReturnValue(json(details()));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDetailsPanel applicationId="a1" onChanged={vi.fn()} />);
    expect(await screen.findByText("Application is outside your assigned scope")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByText("Engineering")).toBeInTheDocument();
  });

  it("saves only the changed fields and reports success", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json(details())).mockReturnValueOnce(json({ ...details({ campus: "North" }), changed: true })).mockReturnValue(json(details({ campus: "North" })));
    vi.stubGlobal("fetch", fetchMock);
    const onChanged = vi.fn();
    render(<ApplicationDetailsPanel applicationId="a1" onChanged={onChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText("Campus"), { target: { value: "North" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith("Application details saved."));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe(URL);
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(init.body)).toEqual({ campus: "North" });
  });

  it("blocks a fee without a currency before sending", async () => {
    const fetchMock = vi.fn(() => json(details({ tuition_fee: null, currency: null, scholarship_status: null, scholarship_amount: null })));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDetailsPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText("Tuition fee"), { target: { value: "1000" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Currency is required");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("disables the amount unless the scholarship is awarded, and shows a server error", async () => {
    const fetchMock = vi.fn().mockReturnValueOnce(json(details())).mockReturnValueOnce(json({ detail: "This date cannot be in the future" }, false, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDetailsPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    fireEvent.change(screen.getByLabelText("Scholarship"), { target: { value: "applied" } });
    expect(screen.getByLabelText("Scholarship amount")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Submitted on"), { target: { value: "2030-01-01" } });
    fireEvent.click(screen.getByRole("button", { name: "Save details" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("This date cannot be in the future");
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual({ scholarship_status: "applied", submitted_on: "2030-01-01" });
  });

  it("cancel returns to the read-only view without saving", async () => {
    const fetchMock = vi.fn(() => json(details()));
    vi.stubGlobal("fetch", fetchMock);
    render(<ApplicationDetailsPanel applicationId="a1" onChanged={vi.fn()} />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit details" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("button", { name: "Edit details" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
