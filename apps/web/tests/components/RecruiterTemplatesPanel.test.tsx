import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import RecruiterTemplatesPanel from "@/components/RecruiterTemplatesPanel";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
  usePathname: () => "/recruiter/manager/templates",
  useSearchParams: () => new URLSearchParams(),
}));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const row = { id: "t1", channel: "email", kind: "interview_confirmation", name: "Interview confirmation", subject: "Interview – {company}", body: "Dear {name}", active: true };

type Call = { url: string; init?: RequestInit };
function serve(onWrite: (call: Call) => Response) {
  const calls: Call[] = [];
  vi.stubGlobal("fetch", vi.fn((url: string, init?: RequestInit) => {
    const call = { url: String(url), init };
    calls.push(call);
    if (init?.method && init.method !== "GET") return Promise.resolve(onWrite(call));
    if (String(url).endsWith("/preview")) return Promise.resolve(res({ subject: "Interview – Acme Technologies", body: "Dear Priya Sharma" }));
    return Promise.resolve(res({ items: [row], total: 1, limit: 50, offset: 0 }));
  }));
  return calls;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("rec-026 RecruiterTemplatesPanel", () => {
  it("lists templates with their source kind and previews with sample values", async () => {
    serve(() => res({}));
    render(<RecruiterTemplatesPanel />);
    expect(await screen.findAllByText("Interview confirmation", { selector: "td" })).toHaveLength(2); // the name and the kind label
    fireEvent.click(screen.getByRole("button", { name: "Preview Interview confirmation" }));
    expect(await screen.findByText("Dear Priya Sharma")).toBeTruthy();
  });

  it("warns about an unknown placeholder as you type and shows the API's refusal", async () => {
    const calls = serve(() => res({ detail: "Unknown placeholder {student}. Use {name}, {company} or {recruiter}" }, 422));
    render(<RecruiterTemplatesPanel />);
    await screen.findAllByText("Interview confirmation", { selector: "td" });
    fireEvent.change(screen.getByLabelText("Template name (required)"), { target: { value: "Hello" } });
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Hi {student}" } });
    expect(screen.getByText("Unknown placeholder: {student}")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Create template" }));
    expect(await screen.findByText(/Unknown placeholder \{student\}\. Use/)).toBeTruthy();
    const body = JSON.parse(String(calls.find((c) => c.init?.method === "POST")?.init?.body));
    expect(body).toEqual({ channel: "whatsapp", kind: "candidate_profiles", name: "Hello", body: "Hi {student}" });
  });

  it("creates an email template with a subject", async () => {
    const calls = serve(() => res({ ...row, id: "t2", name: "Offer" }, 201));
    render(<RecruiterTemplatesPanel />);
    await screen.findAllByText("Interview confirmation", { selector: "td" });
    fireEvent.change(screen.getByLabelText("Channel (required)"), { target: { value: "email" } });
    fireEvent.change(screen.getByLabelText("Kind (required)"), { target: { value: "offer_follow_up" } });
    fireEvent.change(screen.getByLabelText("Template name (required)"), { target: { value: "Offer" } });
    fireEvent.change(screen.getByLabelText("Subject (required)"), { target: { value: "Your offer from {company}" } });
    fireEvent.change(screen.getByLabelText("Message (required)"), { target: { value: "Dear {name}" } });
    fireEvent.click(screen.getByRole("button", { name: "Create template" }));
    await screen.findByText("Created Offer.");
    await waitFor(() => expect(calls.filter((c) => c.init?.method === "POST")).toHaveLength(1));
    expect(JSON.parse(String(calls.find((c) => c.init?.method === "POST")?.init?.body))).toEqual({
      channel: "email", kind: "offer_follow_up", name: "Offer", body: "Dear {name}", subject: "Your offer from {company}",
    });
  });
});
