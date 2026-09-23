import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import CareerPreferencesCard from "@/components/CareerPreferencesCard";

// ENH-025 -- the Career Counsellor's career-preferences card (spec §4.5).
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const students = [{ id: "s1", full_name: "Asha Rao", school_name: "Sunrise" }];
const prefs = { student_id: "s1", career_interests: ["Design"], global_education_interest: true, preferred_countries: null, preferred_courses: null };
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("CareerPreferencesCard", () => {
  it("loads the selected student's preferences with a busy state", async () => {
    let resolve!: (r: Response) => void;
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>((r) => { resolve = r; })));
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    expect(await screen.findByText("Loading…")).toBeTruthy();
    resolve(json(prefs));
    expect(((await screen.findByLabelText("Career interests")) as HTMLInputElement).value).toBe("Design");
    expect((screen.getByLabelText("Interested in studying abroad") as HTMLSelectElement).value).toBe("yes");
  });

  it("shows an error with Retry when loading fails", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json({}, 500)).mockResolvedValueOnce(json(prefs));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    expect((await screen.findByRole("alert")).textContent).toContain("Could not load");
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Career interests")).toBeTruthy();
  });

  it("saves only the four career fields", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(prefs)).mockResolvedValueOnce(json({ ...prefs, preferred_countries: ["Japan", "Korea"] }));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    fireEvent.change(await screen.findByLabelText("Preferred countries"), { target: { value: "Japan, Korea" } });
    fireEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
    const [url, init] = fetchMock.mock.calls[1];
    expect(url).toBe("/api/v1/school/students/s1/career-preferences");
    expect(init.method).toBe("PATCH");
    const body = JSON.parse(init.body);
    expect(Object.keys(body).sort()).toEqual(["career_interests", "global_education_interest", "preferred_countries", "preferred_courses"]);
    expect(body.preferred_countries).toEqual(["Japan", "Korea"]);
    expect((await screen.findByRole("status")).textContent).toContain("saved");
  });

  it("shows the server's message when saving fails", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(json(prefs)).mockResolvedValueOnce(json({ detail: "preferred_countries items must be at most 80 characters" }, 422));
    vi.stubGlobal("fetch", fetchMock);
    render(<CareerPreferencesCard students={students} />);
    fireEvent.change(screen.getByLabelText("Student"), { target: { value: "s1" } });
    fireEvent.click(await screen.findByRole("button", { name: "Save preferences" }));
    expect((await screen.findByRole("alert")).textContent).toBe("preferred_countries items must be at most 80 characters");
  });

  it("empty portfolio shows the existing message", () => {
    render(<CareerPreferencesCard students={[]} />);
    expect(screen.getByText(/No students in your portfolio yet/)).toBeTruthy();
  });
});
