import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorWalkInStudentRow from "@/components/CounselorWalkInStudentRow";
import DataTable from "@/components/DataTable";
import StudentNotesPanel from "@/components/StudentNotesPanel";
import type { StudentNotes } from "@/lib/studentNotes";

const URL = "/api/v1/counselor/students/s1/notes";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const note = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `n${n}`, body: `Note ${n}`, author_name: "Nora Counselor", author_role: "counselor", application: null, created_at: "2026-10-22T10:00:00Z", ...extra,
});
const initial = (items = [note(1)], total = items.length): StudentNotes => ({
  student: { id: "s1", full_name: "Asha Rao", student_code: "AB12CD34" },
  applications: [{ id: "a1", label: "Leeds · REF-1" }],
  items, total, limit: 20, offset: 0,
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("StudentNotesPanel (ccrm-010)", () => {
  it("lists the history with author, role, application and body", () => {
    render(<StudentNotesPanel initial={initial([note(2, { application: { id: "a1", label: "Leeds · REF-1" }, author_role: "overseas_admin", author_name: "Ada Admin" }), note(1)])} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(within(items[0]).getByText("Ada Admin")).toBeInTheDocument();
    expect(within(items[0]).getByText("Overseas Admin")).toBeInTheDocument();
    expect(within(items[0]).getByText("Leeds · REF-1")).toBeInTheDocument();
    expect(within(items[1]).getByText("Note 1")).toBeInTheDocument();
    expect(within(items[1]).getByText("Counselor")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    render(<StudentNotesPanel initial={initial([])} />);
    expect(screen.getByText("No notes yet.")).toBeInTheDocument();
    expect(screen.queryByText("0 notes")).not.toBeInTheDocument(); // QA-03: the empty state says it once
  });

  it("saves a note on an application, shows it first and clears the box", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(note(9, { body: "Chased the offer", application: { id: "a1", label: "Leeds · REF-1" } }), 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentNotesPanel initial={initial()} />);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Chased the offer" } });
    fireEvent.change(screen.getByLabelText("About an application (optional)"), { target: { value: "a1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Note saved.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(URL, expect.objectContaining({ method: "POST", body: JSON.stringify({ body: "Chased the offer", application_id: "a1" }) }));
    expect(within(screen.getAllByRole("listitem")[0]).getByText("Chased the offer")).toBeInTheDocument();
    expect(screen.getByLabelText("New note")).toHaveValue("");
    expect(screen.getByText("2 notes")).toBeInTheDocument();
  });

  it("keeps the text and shows the reason when saving fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Choose one of this student's applications" }, 422)));
    render(<StudentNotesPanel initial={initial()} />);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Choose one of this student's applications")).toBeInTheDocument();
    expect(screen.getByLabelText("New note")).toHaveValue("Keep me");
  });

  it("does not send a blank note and sends a note only once", async () => {
    const fetchMock = vi.fn().mockReturnValue(new Promise(() => {}));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentNotesPanel initial={initial()} />);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Write a note first.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Once" } });
    const form = screen.getByRole("form", { name: "Add a note" });
    fireEvent.submit(form);
    fireEvent.submit(form);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("loads older notes", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res({ ...initial([note(1)], 2), items: [note(1), note(0)], offset: 1 }));
    vi.stubGlobal("fetch", fetchMock);
    render(<StudentNotesPanel initial={initial([note(1)], 2)} />);
    fireEvent.click(screen.getByRole("button", { name: "Load older notes" }));
    expect(await screen.findByText("Note 0")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${URL}?limit=20&offset=1`);
    expect(screen.getAllByRole("listitem")).toHaveLength(2); // the repeated note is not shown twice
    expect(screen.queryByRole("button", { name: "Load older notes" })).not.toBeInTheDocument();
  });

  it("says when older notes cannot be loaded", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "boom" }, 500)));
    render(<StudentNotesPanel initial={initial([note(1)], 2)} />);
    fireEvent.click(screen.getByRole("button", { name: "Load older notes" }));
    expect(await screen.findByText("Unable to load older notes. Try again.")).toBeInTheDocument();
  });
});

describe("DataTable student_notes column (ccrm-010)", () => {
  it("links a student row to its notes and leaves other rows empty", () => {
    render(
      <DataTable
        label="Students"
        columns={[{ key: "student", label: "Student" }, { key: "notes", label: "", type: "student_notes" }]}
        rows={[{ id: "a1", student: "Asha Rao", notes: "/overseas/counselor/students/s1/notes" }, { id: "a2", student: "Agency Kid", notes: null }]}
      />,
    );
    const link = screen.getByRole("link", { name: "Notes for Asha Rao" });
    expect(link).toHaveAttribute("href", "/overseas/counselor/students/s1/notes");
    expect(screen.getAllByRole("link", { name: /Notes for/ })).toHaveLength(1);
  });
});

describe("CounselorWalkInStudentRow notes link (ccrm-010)", () => {
  it("links every walk-in student to their notes", () => {
    render(<ul><CounselorWalkInStudentRow student={{ id: "s1", full_name: "Asha Rao", email: "a@example.local", phone: null, student_code: null, setup: null }} onChanged={() => {}} /></ul>);
    expect(screen.getByRole("link", { name: "Notes for Asha Rao" })).toHaveAttribute("href", "/overseas/counselor/students/s1/notes");
  });
});
