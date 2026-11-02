import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ItStudentNotesPanel from "@/components/ItStudentNotesPanel";
import ItStudentUpdatesPanel from "@/components/ItStudentUpdatesPanel";
import type { ItStudentNotes } from "@/lib/itStudentNotes";

const URL = "/api/v1/it/students/s1/notes";
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const note = (n: number, extra: Record<string, unknown> = {}) => ({
  id: `n${n}`, body: `Note ${n}`, visibility: "internal", author_name: "Nora Counselor", author_role: "counselor", created_at: "2026-11-02T10:00:00Z",
  shared_at: null, can_change_visibility: true, ...extra,
});
const initial = (items = [note(1)], total = items.length): ItStudentNotes => ({
  student: { id: "s1", full_name: "Asha Rao", student_code: "AB12CD34" }, items, total, limit: 20, offset: 0,
} as ItStudentNotes);

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("ItStudentNotesPanel (itc-028)", () => {
  it("lists notes with author, role and who can see each", () => {
    render(<ItStudentNotesPanel initial={initial([note(2, { visibility: "student", shared_at: "2026-11-02T11:00:00Z", author_role: "hr_team", author_name: "Hari HR" }), note(1, { can_change_visibility: false })])} />);
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByText("Hari HR")).toBeInTheDocument();
    expect(within(items[0]).getByText("HR")).toBeInTheDocument();
    expect(within(items[0]).getByText("Shared with student")).toBeInTheDocument();
    expect(within(items[0]).getByRole("button", { name: "Stop sharing" })).toBeInTheDocument();
    expect(within(items[1]).getByText("Internal")).toBeInTheDocument();
    expect(within(items[1]).queryByRole("button")).not.toBeInTheDocument(); // not the author: no control
  });

  it("shows an empty state", () => {
    render(<ItStudentNotesPanel initial={initial([])} />);
    expect(screen.getByText("No notes yet.")).toBeInTheDocument();
  });

  it("saves an internal note first and clears the box; a blank note is refused locally", async () => {
    const fetchMock = vi.fn().mockResolvedValue(res(note(9, { body: "Discussed SQL" }), 201));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItStudentNotesPanel initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Write a note first.")).toBeInTheDocument();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Discussed SQL" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Note saved. Only staff can see it.")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(URL, expect.objectContaining({ method: "POST", body: JSON.stringify({ body: "Discussed SQL" }) }));
    expect(within(screen.getAllByRole("listitem")[0]).getByText("Discussed SQL")).toBeInTheDocument();
    expect(screen.getByLabelText("New note")).toHaveValue("");
  });

  it("keeps the text when saving fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Student not found" }, 404)));
    render(<ItStudentNotesPanel initial={initial()} />);
    fireEvent.change(screen.getByLabelText("New note"), { target: { value: "Keep me" } });
    fireEvent.click(screen.getByRole("button", { name: "Save note" }));
    expect(await screen.findByText("Student not found")).toBeInTheDocument();
    expect(screen.getByLabelText("New note")).toHaveValue("Keep me");
  });

  it("shares a note only after confirmation and shows the new state", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValueOnce(false).mockReturnValueOnce(true);
    const fetchMock = vi.fn().mockResolvedValue(res({ ...note(1, { visibility: "student", shared_at: "2026-11-02T12:00:00Z" }), changed: true }));
    vi.stubGlobal("fetch", fetchMock);
    render(<ItStudentNotesPanel initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Share with student" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled(); // cancelled
    fireEvent.click(screen.getByRole("button", { name: "Share with student" }));
    expect(await screen.findByText("Shared with student")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(`${URL}/n1/visibility`, expect.objectContaining({ method: "PUT", body: JSON.stringify({ visibility: "student" }) }));
    expect(screen.getByRole("button", { name: "Stop sharing" })).toBeInTheDocument();
  });

  it("reports a failed share and keeps the note internal", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "Only the note's author or the IT Admin can change who sees it" }, 403)));
    render(<ItStudentNotesPanel initial={initial()} />);
    fireEvent.click(screen.getByRole("button", { name: "Share with student" }));
    expect(await screen.findByText("Only the note's author or the IT Admin can change who sees it")).toBeInTheDocument();
    expect(screen.getByText("Internal")).toBeInTheDocument();
  });

  it("loads older notes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ items: [note(0)], total: 2, limit: 20, offset: 1 })));
    render(<ItStudentNotesPanel initial={initial([note(1)], 2)} />);
    fireEvent.click(screen.getByRole("button", { name: "Load older notes" }));
    expect(await screen.findByText("Note 0")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load older notes" })).not.toBeInTheDocument();
  });
});

describe("ItStudentUpdatesPanel (itc-028)", () => {
  it("lists shared updates with author and role", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ items: [{ id: "u1", body: "Please add your GitHub link", author_name: "Hari HR", author_role: "hr_team", shared_at: "2026-11-02T12:00:00Z" }], total: 1, limit: 20, offset: 0 })));
    render(<ItStudentUpdatesPanel />);
    expect(await screen.findByText("Please add your GitHub link")).toBeInTheDocument();
    expect(screen.getByText("Hari HR")).toBeInTheDocument();
    expect(screen.getByText("HR")).toBeInTheDocument();
  });

  it("has empty and error states", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ items: [], total: 0, limit: 20, offset: 0 })));
    render(<ItStudentUpdatesPanel />);
    expect(await screen.findByText("No updates yet. When your counselor, trainer or HR team shares something with you, it appears here.")).toBeInTheDocument();
    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(res({ detail: "boom" }, 500)));
    render(<ItStudentUpdatesPanel />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Your updates could not be loaded.");
  });
});
