import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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
  const mock = vi.fn((url: string, init?: RequestInit) => {
    if (init?.method === "POST") return onPost();
    if (url.startsWith("/api/v1/public/universities")) return json(200, [{ id: "u1", name: "Test University", city: "Testville" }]);
    if (url.startsWith("/api/v1/overseas-admin/school-applications")) return json(200, []);
    if (url.startsWith("/api/v1/lookups/schools?")) return json(200, { items: [{ id: "sch1", label: "Hill School", detail: "HILL0001" }], truncated: false });
    if (url.startsWith("/api/v1/lookups/school-students?")) return json(200, { items: [{ id: "s1", label: "Asha", detail: "Grade 5 · A3F9C21B" }], truncated: false });
    return json(404, {});
  });
  vi.stubGlobal("fetch", mock);
  return mock;
}

async function pickSchoolAndStudent() {
  fireEvent.focus(screen.getByRole("combobox", { name: "School" }));
  fireEvent.click(await screen.findByRole("option", { name: "Hill School — HILL0001" }));
  fireEvent.focus(await screen.findByRole("combobox", { name: "Student" }));
  fireEvent.click(await screen.findByRole("option", { name: "Asha — Grade 5 · A3F9C21B" }));
}

async function startApplication() {
  render(<AdminSchoolApplicationsPanel />);
  await pickSchoolAndStudent();
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

  it("searches students only within the chosen school and posts that student's id", async () => {
    const mock = stubApi(() => json(201, { id: "app1" }));
    await startApplication();
    expect(mock.mock.calls.some(([url]) => String(url) === "/api/v1/lookups/school-students?limit=20&school_id=sch1")).toBe(true);
    await waitFor(() => expect(mock.mock.calls.some(([url, init]) => url === "/api/v1/overseas-admin/school-students/s1/applications" && init?.method === "POST")).toBe(true));
  });

  it("offers no student search until a school is picked", () => {
    stubApi(() => json(201, {}));
    render(<AdminSchoolApplicationsPanel />);
    expect(screen.queryByRole("combobox", { name: "Student" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Start application" })).toBeNull();
  });
});
