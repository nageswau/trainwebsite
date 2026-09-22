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

  it("shows a not-found message for an unknown code", async () => {
    stubFetch([json({ detail: "No school found with that School ID" }, 404)]);
    render(<AdminSchoolEditPanel />);
    fireEvent.change(screen.getByLabelText("School ID"), { target: { value: "ZZZZZZZZ" } });
    fireEvent.click(screen.getByRole("button", { name: "Look up" }));
    const outcome = await screen.findByText("No school found with that School ID");
    expect(outcome).toHaveClass("form-error");
  });
});
