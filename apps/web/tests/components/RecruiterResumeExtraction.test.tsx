import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterResumeExtraction from "@/components/RecruiterResumeExtraction";
import type { Extraction } from "@/lib/recruiterResumeExtract";
import { extraction } from "@/tests/helpers/recruiterResumeExtract";

// rec-012 (spec §5; AC2, AC3): the "Review extracted details" panel -- loading, the suggestions with their default ticks, Save sends only
// what is ticked, the server's refusal is shown with the ticks kept, no text, an unreadable file with Retry, and Discard.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const EXTRACT = "/api/v1/recruiter/candidates/C1/resume/2/extract";
const APPLY = "/api/v1/recruiter/candidates/C1/resume/2/apply";

let extractReply: () => Response;
let applyReply: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
const onApplied = vi.fn();
const onClose = vi.fn();

beforeEach(() => {
  extractReply = () => res(extraction());
  applyReply = () => res({ skills_added: 2, fields: ["experience_months", "qualification"] });
  fetchMock = vi.fn((url: string) => Promise.resolve(url === EXTRACT ? extractReply() : url === APPLY ? applyReply() : res({}, 404)));
  vi.stubGlobal("fetch", fetchMock);
  onApplied.mockReset();
  onClose.mockReset();
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const show = (over?: Partial<Extraction>) => {
  if (over) extractReply = () => res(extraction(over));
  render(<RecruiterResumeExtraction candidateId="C1" version={2} current={{ qualification: null, experience_months: null, location: "Hyderabad" }} onApplied={onApplied} onClose={onClose} />);
};
const applied = () => JSON.parse(String((fetchMock.mock.calls.find(([url]) => url === APPLY)![1] as RequestInit).body));

describe("RecruiterResumeExtraction (rec-012)", () => {
  it("reads the resume, then lists the skills with the one on the profile locked and the new ones ticked", async () => {
    show();
    expect(screen.getByText("Reading the resume…")).toBeTruthy();
    const skills = await screen.findByRole("group", { name: /Skills found/ });
    const java = within(skills).getByRole("checkbox", { name: /^Java Programming/ }) as HTMLInputElement;
    expect(java.disabled).toBe(true);
    expect(java.checked).toBe(false);
    expect(within(skills).getByText("Already on profile")).toBeTruthy();
    expect((within(skills).getByRole("checkbox", { name: /^Spring Boot/ }) as HTMLInputElement).checked).toBe(true);
    expect(within(skills).getByText(/found as “REST APIs”/)).toBeTruthy();
    expect((within(skills).getByRole("combobox", { name: "Level for Spring Boot" }) as HTMLSelectElement).value).toBe("intermediate");
    expect(fetchMock).toHaveBeenCalledWith(EXTRACT, expect.objectContaining({ method: "POST" }));
  });

  it("ticks the profile fields the candidate lacks and shows the current value", async () => {
    show();
    const fields = await screen.findByRole("group", { name: "Profile details" });
    expect((within(fields).getByRole("checkbox", { name: /Qualification: B\.Tech/ }) as HTMLInputElement).checked).toBe(true);
    expect((within(fields).getByRole("checkbox", { name: /Total experience: 3 yr/ }) as HTMLInputElement).checked).toBe(true);
    const location = within(fields).getByRole("checkbox", { name: /Location: Pune/ }) as HTMLInputElement;
    expect(location.checked).toBe(false);
    expect(within(fields).getByText(/current: Hyderabad/)).toBeTruthy();
    expect(screen.getByText("Senior Java Developer")).toBeTruthy();
    expect(screen.getByText("Banking & Finance")).toBeTruthy();
  });

  it("saves only what is ticked, then reports it", async () => {
    show();
    const skills = await screen.findByRole("group", { name: /Skills found/ });
    fireEvent.click(within(skills).getByRole("checkbox", { name: /^REST API/ }));
    fireEvent.change(within(skills).getByRole("combobox", { name: "Level for Spring Boot" }), { target: { value: "advanced" } });
    fireEvent.click(screen.getByRole("button", { name: "Save selected" }));
    await waitFor(() => expect(onApplied).toHaveBeenCalledWith("Added 2 skills and updated total experience and qualification."));
    expect(applied()).toEqual({ skills: [{ skill_id: "K-boot", level: "advanced" }], qualification: "B.Tech", experience_months: 36 });
  });

  it("keeps the ticks and shows the server's sentence when Save is refused, and sends once on a double click", async () => {
    applyReply = () => res({ detail: "Spring Boot is already on this candidate's skills" }, 409);
    show();
    const save = await screen.findByRole("button", { name: "Save selected" });
    fireEvent.click(save);
    fireEvent.click(save);
    expect((await screen.findByRole("alert")).textContent).toBe("Spring Boot is already on this candidate's skills");
    expect(fetchMock.mock.calls.filter(([url]) => url === APPLY)).toHaveLength(1);
    expect((screen.getByRole("checkbox", { name: /^Spring Boot/ }) as HTMLInputElement).checked).toBe(true);
    expect(onApplied).not.toHaveBeenCalled();
  });

  it("disables Save when nothing is ticked", async () => {
    show({ skills: [], qualification: null, experience_months: null, location: null, job_titles: [], certifications: [], industries: [] });
    expect(await screen.findByText("No skills from the Skills Master were found in this resume.")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Save selected" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("says when no text was found (AC3)", async () => {
    show({ no_text: true, skills: [], text_chars: 0 });
    expect(await screen.findByText(/No text found in this resume/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Save selected" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });

  it("notes a truncated resume", async () => {
    show({ truncated: true });
    expect(await screen.findByText(/Only the first part of this long resume was read/)).toBeTruthy();
  });

  it("shows an unreadable file's sentence with Retry", async () => {
    extractReply = () => res({ detail: "This PDF is password-protected. Upload a copy without a password." }, 422);
    show();
    expect((await screen.findByRole("alert")).textContent).toBe("This PDF is password-protected. Upload a copy without a password.");
    extractReply = () => res(extraction());
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("group", { name: /Skills found/ })).toBeTruthy();
  });

  it("Discard closes without saving", async () => {
    show();
    fireEvent.click(await screen.findByRole("button", { name: "Discard" }));
    expect(onClose).toHaveBeenCalled();
    expect(fetchMock.mock.calls.some(([url]) => url === APPLY)).toBe(false);
  });
});
