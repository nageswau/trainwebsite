import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorWalkInStudents from "@/components/CounselorWalkInStudents";

const URL = "/api/v1/counselor/students";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const student = (n: number, setup: string | null = "pending_setup") => ({ id: `s${n}`, full_name: `Walk-in ${n}`, email: `w${n}@example.local`, phone: null, student_code: `CODE${n}`, setup });
const page = (items: unknown[], total = items.length, offset = 0) => ({ items, total, limit: 20, offset });

function fillForm(name = "Vikram Walk-in", email = "vikram@example.local", phone = "") {
  const form = screen.getByRole("form", { name: "Add a walk-in student" });
  fireEvent.change(within(form).getByLabelText("Full name"), { target: { value: name } });
  fireEvent.change(within(form).getByLabelText("Email"), { target: { value: email } });
  fireEvent.change(within(form).getByLabelText("Phone (optional)"), { target: { value: phone } });
  return form;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("CounselorWalkInStudents (csc-002)", () => {
  it("shows loading, then the counselor's students with their set-up status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([student(1), student(2, "link_expired"), student(3, null)]))));
    render(<CounselorWalkInStudents />);
    expect(screen.getByText("Loading your students…")).toBeInTheDocument();
    const row = (await screen.findByText("Walk-in 1")).closest("li") as HTMLElement;
    expect(within(row).getByText("w1@example.local")).toBeInTheDocument();
    expect(within(row).getByText("Student ID CODE1")).toBeInTheDocument();
    expect(within(row).getByText("Set-up pending")).toBeInTheDocument();
    expect(screen.getByText("Link expired")).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("shows an empty state", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([]))));
    render(<CounselorWalkInStudents />);
    expect(await screen.findByText("No students yet. Add a walk-in student below.")).toBeInTheDocument();
  });

  it("shows an error with Retry, including for a non-page body", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res({ detail: "boom" }, 500)).mockResolvedValueOnce(res("<html>")).mockResolvedValueOnce(res(page([student(1)]))));
    render(<CounselorWalkInStudents />);
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Walk-in 1")).toBeInTheDocument();
  });

  it("pages through students", async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => student(i + 1));
    const mock = vi.fn().mockResolvedValueOnce(res(page(twenty, 21))).mockResolvedValueOnce(res(page([student(21)], 21, 20)));
    vi.stubGlobal("fetch", mock);
    render(<CounselorWalkInStudents />);
    const pager = await screen.findByRole("navigation", { name: "Student pages" });
    expect(within(pager).getByText("Showing 1–20 of 21")).toBeInTheDocument();
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    expect(await screen.findByText("Walk-in 21")).toBeInTheDocument();
    expect(mock.mock.calls[1][0]).toBe(`${URL}?limit=20&offset=20`);
  });

  it("creates an account, announces the emailed link, clears the form and reloads the list", async () => {
    const mock = vi
      .fn()
      .mockResolvedValueOnce(res(page([])))
      .mockResolvedValueOnce(res({ student: student(9), email_status: "sent", expires_at: "2026-10-22T10:00:00Z" }, 201))
      .mockResolvedValueOnce(res(page([student(9)])));
    vi.stubGlobal("fetch", mock);
    render(<CounselorWalkInStudents />);
    await screen.findByText("No students yet. Add a walk-in student below.");
    const form = fillForm("Vikram Walk-in", "vikram@example.local", " ");
    fireEvent.click(within(form).getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Account created for Walk-in 9. A set-password link was emailed to w9@example.local.")).toBeInTheDocument();
    const [url, init] = mock.mock.calls[1];
    expect(url).toBe(URL);
    expect(JSON.parse(init.body)).toEqual({ full_name: "Vikram Walk-in", email: "vikram@example.local", phone: null });
    expect((within(form).getByLabelText("Email") as HTMLInputElement).value).toBe("");
    expect(await screen.findByText("Walk-in 9")).toBeInTheDocument();
  });

  it("says so when the email was not delivered", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(page([]))).mockResolvedValueOnce(res({ student: student(9), email_status: "not_configured" }, 201)).mockResolvedValue(res(page([student(9)]))));
    render(<CounselorWalkInStudents />);
    await screen.findByText("No students yet. Add a walk-in student below.");
    fireEvent.click(within(fillForm()).getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Account created for Walk-in 9, but the set-password email was not delivered.")).toBeInTheDocument();
  });

  it("keeps the entry and shows the server's reason on a refusal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(page([]))).mockResolvedValueOnce(res({ detail: "Email already exists" }, 409)));
    render(<CounselorWalkInStudents />);
    await screen.findByText("No students yet. Add a walk-in student below.");
    const form = fillForm();
    fireEvent.click(within(form).getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("Email already exists")).toBeInTheDocument();
    expect((within(form).getByLabelText("Email") as HTMLInputElement).value).toBe("vikram@example.local");
  });

  it("words a server error as a retry", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValueOnce(res(page([]))).mockResolvedValueOnce(res({ detail: "Internal Server Error" }, 500)));
    render(<CounselorWalkInStudents />);
    await screen.findByText("No students yet. Add a walk-in student below.");
    fireEvent.click(within(fillForm()).getByRole("button", { name: "Create account" }));
    expect(await screen.findByText("The server couldn't complete this. Please try again in a moment.")).toBeInTheDocument();
  });

  it("sends one request for a double click", async () => {
    let finish: (value: Response) => void = () => {};
    const mock = vi.fn().mockResolvedValueOnce(res(page([]))).mockReturnValueOnce(new Promise<Response>((resolve) => (finish = resolve))).mockResolvedValue(res(page([student(9)])));
    vi.stubGlobal("fetch", mock);
    render(<CounselorWalkInStudents />);
    await screen.findByText("No students yet. Add a walk-in student below.");
    const form = fillForm();
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(within(form).getByRole("button", { name: "Creating…" })).toBeDisabled();
    finish(res({ student: student(9), email_status: "sent" }, 201));
    await screen.findByText(/Account created for Walk-in 9/);
    expect(mock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  });

  // ccrm-043 (DEC-SCOPE-317): all my students, with how they arrived, filterable by source and searchable.
  it("is titled My students and shows each student's source, applications and since when", async () => {
    const mine = { ...student(1, null), source: "agency", applications: 2, linked_since: "2026-10-01T09:00:00Z", linked: false };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([mine]))));
    render(<CounselorWalkInStudents />);
    expect(screen.getByRole("heading", { name: "My students" })).toBeInTheDocument();
    const row = (await screen.findByText("Walk-in 1")).closest("li") as HTMLElement;
    expect(within(row).getByText("Agency")).toBeInTheDocument();
    expect(within(row).getByText("2 applications")).toBeInTheDocument();
    expect(within(row).getByText(/^Since /)).toBeInTheDocument();
  });

  it("offers Edit and Resend only for a pending student linked to me", async () => {
    const linked = { ...student(1), source: "walk_in", applications: 0, linked_since: "2026-10-01T09:00:00Z", linked: true };
    const viaApplication = { ...student(2), source: "self_registered", applications: 1, linked_since: "2026-10-01T09:00:00Z", linked: false };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res(page([linked, viaApplication]))));
    render(<CounselorWalkInStudents />);
    const one = (await screen.findByText("Walk-in 1")).closest("li") as HTMLElement;
    const two = screen.getByText("Walk-in 2").closest("li") as HTMLElement;
    expect(within(one).getByRole("button", { name: "Resend link to Walk-in 1" })).toBeInTheDocument();
    expect(within(two).queryByRole("button", { name: /Resend|Edit/ })).toBeNull();
    expect(within(one).getByText("0 applications")).toBeInTheDocument();
    expect(within(two).getByText("1 application")).toBeInTheDocument();
  });

  it("filters by source at once and by search on submit, from the first page, and can clear", async () => {
    const twenty = Array.from({ length: 20 }, (_, i) => student(i + 1));
    const mock = vi.fn().mockResolvedValueOnce(res(page(twenty, 21))).mockImplementation(async () => res(page([])));
    vi.stubGlobal("fetch", mock);
    render(<CounselorWalkInStudents />);
    const pager = await screen.findByRole("navigation", { name: "Student pages" });
    fireEvent.click(within(pager).getByRole("button", { name: "Next page" }));
    await waitFor(() => expect(mock).toHaveBeenCalledTimes(2));
    const filters = screen.getByRole("search", { name: "Filter my students" });
    fireEvent.change(within(filters).getByLabelText("Source"), { target: { value: "lead_conversion" } });
    await waitFor(() => expect(mock.mock.calls.at(-1)?.[0]).toBe(`${URL}?limit=20&offset=0&source=lead_conversion`));
    fireEvent.change(within(filters).getByLabelText("Search"), { target: { value: " Asha 98 " } });
    fireEvent.click(within(filters).getByRole("button", { name: "Search" }));
    await waitFor(() => expect(mock.mock.calls.at(-1)?.[0]).toBe(`${URL}?limit=20&offset=0&source=lead_conversion&q=Asha+98`));
    expect(await screen.findByText("No students match these filters.")).toBeInTheDocument();
    fireEvent.click(within(filters).getByRole("button", { name: "Clear" }));
    await waitFor(() => expect(mock.mock.calls.at(-1)?.[0]).toBe(`${URL}?limit=20&offset=0`));
    expect((within(filters).getByLabelText("Search") as HTMLInputElement).value).toBe("");
    expect(await screen.findByText("No students yet. Add a walk-in student below.")).toBeInTheDocument();
  });
});
