import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InterviewAutomationSettings from "@/components/InterviewAutomationSettings";
import RecruiterInterviewForm from "@/components/RecruiterInterviewForm";

// pob-022 (DEC-SCOPE-421 A1/A2/A9): the confirmation template select in the schedule form, and the Team Lead's automation settings.
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const TEMPLATES = { items: [
  { id: "T1", name: "Warm confirmation", kind: "interview_confirmation" }, { id: "T2", name: "Proposal", kind: "recruitment_proposal" },
], total: 2, limit: 100, offset: 0 };
const SETTINGS = { first_reminder_hours: 24, second_reminder_hours: 2, reminder_template_id: null, chase_after_hours: 24, escalate_after_hours: 24, chase_template_id: null };

let sent: { url: string; method: string; body: Record<string, unknown> | null }[];
let reply: (url: string, method: string) => Response;

beforeEach(() => {
  sent = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const method = init?.method ?? "GET";
    sent.push({ url, method, body: init?.body ? JSON.parse(String(init.body)) : null });
    return Promise.resolve(reply(url, method));
  }));
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("schedule form confirmation template", () => {
  it("offers only approved interview confirmations, hides with Notify off and sends the chosen id", async () => {
    reply = (url) => (url.includes("/templates") ? res(TEMPLATES) : res({ interview: { id: "I1" } }, 201));
    render(<RecruiterInterviewForm applicationId="A1" draftRound="hr_round" contacts={[]} onSaved={vi.fn()} onCancel={vi.fn()} />);
    const select = await screen.findByLabelText("Confirmation message");
    await waitFor(() => expect(select).not.toBeDisabled());
    expect(screen.getByRole("option", { name: "Warm confirmation" })).toBeTruthy();
    expect(screen.queryByRole("option", { name: "Proposal" })).toBeNull();
    fireEvent.change(select, { target: { value: "T1" } });
    fireEvent.change(screen.getByLabelText("Date and time (IST, required)"), { target: { value: "2030-01-10T10:30" } });
    fireEvent.click(screen.getByRole("button", { name: "Schedule interview" }));
    await waitFor(() => expect(sent.some((s) => s.method === "POST")).toBe(true));
    expect(sent.find((s) => s.method === "POST")!.body).toMatchObject({ template_id: "T1", notify: true });
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.queryByLabelText("Confirmation message")).toBeNull();
  });

  it("falls back to the standard text when templates cannot be loaded", async () => {
    reply = () => res({ detail: "boom" }, 500);
    render(<RecruiterInterviewForm applicationId="A1" contacts={[]} onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(await screen.findByText("Templates could not be loaded; the standard text is used.")).toBeTruthy();
    expect(screen.getByLabelText("Confirmation message")).not.toBeDisabled();
  });
});

describe("InterviewAutomationSettings", () => {
  it("loads, saves blank hours as null and confirms", async () => {
    reply = (url, method) => (url.includes("/templates") ? res(TEMPLATES) : method === "PUT" ? res({ ...SETTINGS, second_reminder_hours: null }) : res(SETTINGS));
    render(<InterviewAutomationSettings />);
    const second = await screen.findByLabelText("Second reminder (hours before)");
    expect((second as HTMLInputElement).value).toBe("2");
    fireEvent.change(second, { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
    expect(await screen.findByText("Interview automation saved.")).toBeTruthy();
    expect(sent.find((s) => s.method === "PUT")!.body).toMatchObject({ second_reminder_hours: null, first_reminder_hours: 24, chase_template_id: null });
  });

  it("places the server's 422 on its field and refuses out-of-range hours locally", async () => {
    reply = (url, method) => url.includes("/templates") ? res(TEMPLATES) : method === "PUT"
      ? res({ detail: [{ loc: ["body", "second_reminder_hours"], msg: "The second reminder must come closer to the interview than the first" }] }, 422)
      : res(SETTINGS);
    render(<InterviewAutomationSettings />);
    const first = await screen.findByLabelText("First reminder (hours before)");
    fireEvent.change(first, { target: { value: "200" } });
    fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
    expect(await screen.findByText("Enter whole hours from 1 to 168, or leave it blank")).toBeTruthy();
    expect(sent.some((s) => s.method === "PUT")).toBe(false);
    fireEvent.change(first, { target: { value: "1" } });
    fireEvent.click(screen.getByRole("button", { name: "Save automation" }));
    expect(await screen.findByText("The second reminder must come closer to the interview than the first")).toBeTruthy();
  });

  it("shows an error when the settings cannot be read", async () => {
    reply = () => res({ detail: "Only a Team Lead can change interview automation" }, 403);
    render(<InterviewAutomationSettings />);
    expect(await screen.findByRole("alert")).toHaveTextContent("could not be loaded");
  });
});
