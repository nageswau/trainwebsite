import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import BdmLeadForm from "@/components/BdmLeadForm";
import { NOT_COMPLETED } from "@/lib/apiErrors";
import type { Lead } from "@/lib/bdmLeads";

const res = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
const saved: Lead = {
  id: "l1", name: "Asha Nair", email: "asha@example.com", phone: null, interest: "B.Tech", status: "new", bdm: { id: "b1", full_name: "Asha" },
  converted: false, created_at: "2026-10-05T04:00:00Z",
};
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function fill() {
  fireEvent.change(screen.getByLabelText("Student name (required)"), { target: { value: " Asha Nair " } });
  fireEvent.change(screen.getByLabelText("Email (required)"), { target: { value: "asha@example.com" } });
  fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "+91 90000 11111" } });
  fireEvent.change(screen.getByLabelText("Interest (required)"), { target: { value: "B.Tech" } });
}
const sentBodies = (fetchMock: ReturnType<typeof vi.fn>) =>
  fetchMock.mock.calls.map((call) => JSON.parse(String((call as unknown as [string, RequestInit])[1].body)));

describe("BdmLeadForm (bdm-017 spec §6)", () => {
  it("labels every field, marks student data as not autofilled and focuses the name on open", async () => {
    render(<BdmLeadForm organizationId="o1" onSaved={vi.fn()} onCancel={vi.fn()} />);
    expect(screen.getByRole("form", { name: "Add lead" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email (required)")).toHaveAttribute("type", "email");
    expect(screen.getByLabelText("Phone")).toHaveAttribute("type", "tel");
    expect(screen.getByLabelText("Email (required)")).toHaveAttribute("autocomplete", "off");
    await waitFor(() => expect(screen.getByLabelText("Student name (required)")).toHaveFocus());
  });

  it("asks for the required fields before sending", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    render(<BdmLeadForm organizationId="o1" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Check the highlighted fields.");
    expect(screen.getByLabelText("Email (required)")).toHaveAccessibleDescription("Enter the student's email.");
    await waitFor(() => expect(screen.getByLabelText("Student name (required)")).toHaveFocus());
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("posts the lead to the organization and hands back the saved one", async () => {
    const fetchMock = vi.fn(() => Promise.resolve(res(saved, 201)));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmLeadForm organizationId="o1" onSaved={onSaved} onCancel={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect((fetchMock.mock.calls[0] as unknown as [string])[0]).toBe("/api/v1/bdm/organizations/o1/leads");
    expect(sentBodies(fetchMock)[0]).toEqual({ name: "Asha Nair", email: "asha@example.com", phone: "+91 90000 11111", interest: "B.Tech", note: null });
  });

  it("puts a 422 on its field", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: [{ loc: ["body", "email"], msg: "Value error, Enter a valid email address" }] }, 422))));
    render(<BdmLeadForm organizationId="o1" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    await waitFor(() => expect(screen.getByLabelText("Email (required)")).toHaveAccessibleDescription("Enter a valid email address"));
    expect(screen.getByLabelText("Email (required)")).toHaveAttribute("aria-invalid", "true");
  });

  it("a possible duplicate shows the matching lead and saves only when confirmed", async () => {
    const duplicate = { detail: { message: "This student is already a lead of this organization", code: "possible_duplicate",
      matches: [{ id: "l0", name: "Asha N", created_at: "2026-10-01T04:00:00Z" }], total: 1 } };
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(res(duplicate, 409))
      .mockResolvedValueOnce(res(saved, 201));
    vi.stubGlobal("fetch", fetchMock);
    const onSaved = vi.fn();
    render(<BdmLeadForm organizationId="o1" onSaved={onSaved} onCancel={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    const group = await screen.findByRole("group", { name: "Possible duplicate" });
    expect(group).toHaveTextContent("This student is already a lead of this organization");
    expect(group).toHaveTextContent("Asha N");
    fireEvent.click(screen.getByRole("button", { name: "Save anyway" }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(sentBodies(fetchMock)[1]).toMatchObject({ acknowledge_duplicate: true, email: "asha@example.com" });
  });

  it("a network drop keeps the entry and says so", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("offline"))));
    render(<BdmLeadForm organizationId="o1" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByLabelText("Email (required)")).toHaveValue("asha@example.com");
  });

  it("a refusal (403 / 409 cap / 422 archived) shows the server's words", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(res({ detail: "You've added 200 leads today" }, 409))));
    render(<BdmLeadForm organizationId="o1" onSaved={vi.fn()} onCancel={vi.fn()} />);
    fill();
    fireEvent.click(screen.getByRole("button", { name: "Save lead" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("You've added 200 leads today");
  });

  it("Cancel calls back", () => {
    const onCancel = vi.fn();
    render(<BdmLeadForm organizationId="o1" onSaved={vi.fn()} onCancel={onCancel} />);
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalled();
  });
});
