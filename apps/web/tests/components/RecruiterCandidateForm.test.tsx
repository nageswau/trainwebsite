import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateForm from "@/components/RecruiterCandidateForm";
import type { CandidateMatch } from "@/lib/recruiterCandidates";

// rec-009 (spec §6; AC2, AC3, Q-07): the candidate create form, its required check and the duplicate panel.
// QA-05: the new candidate replaces the form in history, so Back returns to the list rather than to a stale blank form.
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: push, push: vi.fn(), refresh: vi.fn() }) }));

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const sources = { items: [{ id: "s1", name: "Referral", active: true, sort_order: 1 }, { id: "s2", name: "Edusphere students", active: true, sort_order: 2 }], total: 2, limit: 100, offset: 0 };
const match: CandidateMatch = { id: "C9", candidate_code: "CAN-000009", name: "Rahul K", source_name: "LinkedIn", status: "placed", archived: false, matched_on: ["mobile"] };

let fetchMock: ReturnType<typeof vi.fn>;
let createReply: () => Response;
const posts = () => fetchMock.mock.calls.filter(([, init]) => init?.method === "POST");

beforeEach(() => {
  push.mockReset();
  createReply = () => res({ id: "NEW1", candidate_code: "CAN-000100" }, 201);
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res(sources));
    if (url.startsWith("/api/v1/recruiter/candidates/duplicate-check")) return Promise.resolve(res({ matches: [] }));
    if (init?.method === "POST" && url === "/api/v1/recruiter/candidates") return Promise.resolve(createReply());
    return Promise.resolve(res({}, 404));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const type = (label: RegExp, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } });

async function renderForm() {
  render(<RecruiterCandidateForm />);
  await screen.findByRole("option", { name: "Edusphere students" });
}

describe("RecruiterCandidateForm", () => {
  it("names the missing required fields and sends nothing", async () => {
    await renderForm();
    fireEvent.click(screen.getByRole("button", { name: "Add candidate" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Enter the name, source and a mobile number or an email.");
    expect(posts()).toHaveLength(0);
  });

  it("creates the candidate with the source detail and opens it", async () => {
    await renderForm();
    type(/^Name/, "Rahul");
    type(/^Mobile/, "98765 43210");
    type(/^Source \*/, "s2");
    type(/^Source detail/, "Edusphere Python Full Stack Course");
    fireEvent.click(screen.getByRole("button", { name: "Add candidate" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/recruiter/candidates/NEW1"));
    expect(JSON.parse(String(posts()[0][1].body))).toEqual({
      name: "Rahul", mobile: "98765 43210", source_id: "s2", source_detail: "Edusphere Python Full Stack Course", status: "available",
    });
  });

  it("shows the existing candidate when the API blocks a duplicate (Q-07), with a link to open them", async () => {
    createReply = () => res({ detail: { code: "duplicate_candidate", message: "This person is already a candidate", matches: [match] } }, 409);
    await renderForm();
    type(/^Name/, "Rahul");
    type(/^Mobile/, "98765 43210");
    type(/^Source \*/, "s1");
    fireEvent.click(screen.getByRole("button", { name: "Add candidate" }));
    const panel = await screen.findByRole("region", { name: /already a candidate/i });
    expect(within(panel).getByText(/CAN-000009/)).toBeInTheDocument();
    expect(within(panel).getByText(/same mobile/)).toBeInTheDocument();
    expect(within(panel).getByRole("link", { name: "Open CAN-000009" })).toHaveAttribute("href", "/recruiter/candidates/C9");
    expect(push).not.toHaveBeenCalled();
  });

  it("checks for a duplicate as soon as the mobile is entered", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res(sources));
      if (url.startsWith("/api/v1/recruiter/candidates/duplicate-check")) return Promise.resolve(res({ matches: [match] }));
      return Promise.resolve(res({}, 404));
    });
    await renderForm();
    type(/^Mobile/, "98765 43210");
    fireEvent.blur(screen.getByLabelText(/^Mobile/));
    expect(await screen.findByRole("region", { name: /already a candidate/i })).toBeInTheDocument();
    expect(String(fetchMock.mock.calls.find(([u]) => String(u).includes("duplicate-check"))?.[0])).toContain("mobile=98765+43210");
  });

  it("sends one request for a double click", async () => {
    let release: (r: Response) => void = () => undefined;
    fetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.startsWith("/api/v1/recruiter/catalogue/candidate-sources")) return Promise.resolve(res(sources));
      if (init?.method === "POST") return new Promise<Response>((resolve) => (release = resolve));
      return Promise.resolve(res({ matches: [] }));
    });
    await renderForm();
    type(/^Name/, "Rahul");
    type(/^Email/, "r@example.com");
    type(/^Source \*/, "s1");
    const button = screen.getByRole("button", { name: "Add candidate" });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(posts()).toHaveLength(1);
    release(res({ id: "NEW2" }, 201));
    await waitFor(() => expect(push).toHaveBeenCalledWith("/recruiter/candidates/NEW2"));
  });
});
