import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolEditPanel from "@/components/AdminSchoolEditPanel";

const json = (body: unknown, status: number) => new Response(JSON.stringify(body), { status });

function stubFetch(responses: Response[]) {
  const mock = vi.fn();
  responses.forEach((r) => mock.mockResolvedValueOnce(r));
  vi.stubGlobal("fetch", mock);
  return mock;
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("AdminSchoolEditPanel", () => {
  it("looks up a school by code, then patches the fields the admin changes", async () => {
    stubFetch([
      json({ id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School", branch: null, board: null }, 200),
      json({ id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School", branch: "North Campus", board: "CBSE" }, 200),
    ]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Branch");

    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "North Campus" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/updated/i);
  });

  it("sends an explicit null for a cleared field and omits the fields that did not change", async () => {
    const loaded = {
      id: "11111111-1111-1111-1111-111111111111", school_code: "ABCD1234", name: "Test School",
      branch: "North Campus", address: "1 Main Street", contact_number: "0123456789",
      email: "school@example.local", website: "https://example.local", grades_available: "1-12",
      board: "CBSE", partnership_date: "2026-01-01", mou_reference: "MOU-1",
      edusphere_bdm: "A Manager", monthly_visit_schedule: "First Monday", vice_principal_name: "A Deputy",
    };
    const mock = stubFetch([json(loaded, 200), json({ ...loaded, branch: null }, 200)]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ABCD1234" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    await screen.findByLabelText("Branch");

    fireEvent.change(screen.getByLabelText("Branch"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await screen.findByText(/updated/i);

    const body = JSON.parse(mock.mock.calls[1][1].body);
    // The cleared field is sent as an explicit null (never omitted -- otherwise it can never
    // be cleared), and nothing else is sent, so `changed_fields` stays accurate.
    expect(body).toEqual({ branch: null });
  });

  it("shows a not-found message for an unknown code", async () => {
    stubFetch([json({ detail: "No school found with that School ID" }, 404)]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ZZZZZZZZ" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    const outcome = await screen.findByText("No school found with that School ID");
    expect(outcome).toHaveClass("form-error");
  });
});
