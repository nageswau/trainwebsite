import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import RecruiterCandidateOwnership from "@/components/RecruiterCandidateOwnership";
import type { CandidateOwnership } from "@/lib/recruiterCandidates";

// hrc-012 (DEC-SCOPE-382): the Ownership card -- primary recruiter, placement officer and (when shared ownership is on, or some remain)
// collaborators; Change ownership for the primary recruiter and managers (`can_assign`). Only changed keys are sent.
const asha = { id: "u1", full_name: "Asha", active: true };
const ravi = { id: "u2", full_name: "Ravi", active: false };
const base: CandidateOwnership = { owner: asha, placement_officer: null, collaborators: [], shared_ownership: false, can_assign: true };
const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (String(url).includes("/assignees")) return Promise.resolve(res([{ id: "u3", full_name: "Kiran", role: "placement_team" }]));
    if (init?.method === "PUT") return Promise.resolve(res({ id: "c1", ownership: { ...base, owner: { id: "u3", full_name: "Kiran", active: true } } }));
    return Promise.resolve(res({}));
  });
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("RecruiterCandidateOwnership", () => {
  it("shows the owners, marks an inactive one, and hides collaborators while sharing is off and none exist", () => {
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={{ ...base, placement_officer: ravi }} onSaved={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Ownership" })).toBeInTheDocument();
    expect(screen.getByText("Asha")).toBeInTheDocument();
    expect(screen.getByText("Ravi (inactive)")).toBeInTheDocument();
    expect(screen.queryByText("Collaborators")).toBeNull();
  });

  it("says Unassigned and offers no change to someone who cannot assign", () => {
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={{ ...base, owner: null, can_assign: false }} onSaved={vi.fn()} />);
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Change ownership" })).toBeNull();
  });

  it("lists collaborators when sharing is on", () => {
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={{ ...base, shared_ownership: true, collaborators: [ravi] }} onSaved={vi.fn()} />);
    expect(screen.getByText("Collaborators")).toBeInTheDocument();
    expect(screen.getByText("Ravi (inactive)")).toBeInTheDocument();
  });

  it("sends only the new primary recruiter and reports success", async () => {
    const onSaved = vi.fn();
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={base} onSaved={onSaved} />);
    fireEvent.click(screen.getByRole("button", { name: "Change ownership" }));
    const input = screen.getByRole("combobox", { name: "Primary recruiter" });
    fireEvent.change(input, { target: { value: "Kir" } });
    fireEvent.click(await screen.findByRole("option", { name: /Kiran/ }));
    fireEvent.click(screen.getByRole("button", { name: "Save ownership" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(put[0]).toBe("/api/v1/recruiter/candidates/c1/ownership");
    expect(JSON.parse(put[1].body)).toEqual({ owner_user_id: "u3" });
    expect(screen.getByRole("status")).toHaveTextContent("Ownership updated.");
  });

  it("clears the placement officer, and Escape cancels", async () => {
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={{ ...base, placement_officer: ravi }} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Change ownership" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove placement officer" }));
    fireEvent.click(screen.getByRole("button", { name: "Save ownership" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true));
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(put[1].body)).toEqual({ placement_officer_user_id: null });
  });

  it("removes a collaborator and shows the server's refusal in an alert", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(res({ detail: "Shared ownership is switched off" }, 422)));
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={{ ...base, shared_ownership: true, collaborators: [ravi] }} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Change ownership" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove Ravi" }));
    fireEvent.click(screen.getByRole("button", { name: "Save ownership" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Shared ownership is switched off");
    const put = fetchMock.mock.calls.find(([, init]) => init?.method === "PUT")!;
    expect(JSON.parse(put[1].body)).toEqual({ collaborator_user_ids: [] });
  });

  it("closes without a request when nothing changed", () => {
    render(<RecruiterCandidateOwnership candidateId="c1" ownership={base} onSaved={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Change ownership" }));
    fireEvent.keyDown(screen.getByRole("group", { name: "Change ownership" }), { key: "Escape" });
    expect(screen.queryByRole("group", { name: "Change ownership" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Change ownership" }));
    fireEvent.click(screen.getByRole("button", { name: "Save ownership" }));
    expect(fetchMock.mock.calls.some(([, init]) => init?.method === "PUT")).toBe(false);
    expect(screen.queryByRole("group", { name: "Change ownership" })).toBeNull();
  });
});
