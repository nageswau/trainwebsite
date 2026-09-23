import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AdminSchoolApplicationsPanel from "@/components/AdminSchoolApplicationsPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TIER_403 = "This school's Silver partnership does not include Application support (requires Gold or higher).";
const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });

/** The panel's reads succeed; the application POST gets `onPost`. */
function stubApi(onPost: () => Promise<unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return onPost();
      if (url.startsWith("/api/v1/public/universities")) return json(200, [{ id: "u1", name: "Test University", city: "Testville" }]);
      if (url.startsWith("/api/v1/overseas-admin/school-applications")) return json(200, []);
      return json(200, { id: "s1", full_name: "Asha", student_code: "A3F9C21B", school_name: "Hill School" });
    }),
  );
}

async function startApplication() {
  render(<AdminSchoolApplicationsPanel />);
  fireEvent.change(screen.getByLabelText("Student ID"), { target: { value: "a3f9c21b" } });
  fireEvent.click(screen.getByRole("button", { name: "Look up" }));
  await screen.findByText("Asha — Hill School");
  await screen.findByRole("option", { name: "Test University (Testville)" });
  fireEvent.change(screen.getByLabelText("University"), { target: { value: "u1" } });
  fireEvent.change(screen.getByLabelText("Intake"), { target: { value: "Fall 2027" } });
  fireEvent.click(screen.getByRole("button", { name: "Start application" }));
}

// ENH-022: a partnership-tier 403 (or any failed save) is announced as an alert under the form.
describe("AdminSchoolApplicationsPanel save failures", () => {
  it("shows the tier 403 as an alert and keeps the resolved student and intake", async () => {
    stubApi(() => json(403, { detail: TIER_403 }));
    await startApplication();
    expect(await screen.findByRole("alert")).toHaveTextContent(TIER_403);
    expect(screen.getByLabelText("Intake")).toHaveValue("Fall 2027");
  });

  it("recovers from a network failure", async () => {
    stubApi(() => Promise.reject(new TypeError("Failed to fetch")));
    await startApplication();
    expect(await screen.findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(screen.getByRole("button", { name: "Start application" })).toBeEnabled();
  });

  it("announces success politely", async () => {
    stubApi(() => json(201, { id: "app1" }));
    await startApplication();
    expect(await screen.findByRole("status")).toHaveTextContent("Application started for Asha.");
  });
});
