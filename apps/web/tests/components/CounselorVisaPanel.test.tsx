import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CounselorVisaPanel from "@/components/CounselorVisaPanel";
import { NOT_COMPLETED } from "@/lib/apiErrors";

vi.mock("next/navigation", () => ({ useRouter: () => ({ refresh: vi.fn() }) }));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const TIER_403 = "This school's Gold partnership does not include Visa support (requires Platinum or higher).";
const json = (status: number, body: unknown) => Promise.resolve({ ok: status < 400, status, json: async () => body });

/** Two assigned applications with no visa case yet; the visa POST gets `onPost`. */
function stubApi(onPost: () => Promise<unknown>) {
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string, init?: RequestInit) => {
      if (init?.method === "POST") return onPost();
      if (url.includes("/counselor/applications")) return json(200, { rows: [{ id: "app1", student: "Asha", university: "Test University" }, { id: "app2", student: "Ravi", university: "Test University" }] });
      if (url.includes("/visa-checklist")) return json(200, { exists: false, status: null, checklist: [] });
      return json(200, { exists: false, status: null, appointment_date: null, tracking_reference: null, disclaimer: "" });
    }),
  );
}

async function startCaseForAsha() {
  render(<CounselorVisaPanel />);
  const card = (await screen.findByRole("heading", { name: "Asha" })).closest(".card") as HTMLElement;
  fireEvent.change(await within(card).findByLabelText(/checklist items/i), { target: { value: "Passport" } });
  fireEvent.click(within(card).getByRole("button", { name: "Start visa case" }));
  return card;
}

// ENH-022: a partnership-tier 403 (or any failed save) is announced as an alert in the application's own card.
describe("CounselorVisaPanel save failures", () => {
  it("shows the tier 403 as an alert in that application's card only, keeping the checklist input", async () => {
    stubApi(() => json(403, { detail: TIER_403 }));
    const card = await startCaseForAsha();
    const alert = await within(card).findByRole("alert");
    expect(alert).toHaveTextContent(TIER_403);
    expect(screen.getAllByRole("alert")).toHaveLength(1);
    expect(within(card).getByLabelText(/checklist items/i)).toHaveValue("Passport");
  });

  it("recovers from a network failure", async () => {
    stubApi(() => Promise.reject(new TypeError("Failed to fetch")));
    const card = await startCaseForAsha();
    expect(await within(card).findByRole("alert")).toHaveTextContent(NOT_COMPLETED);
    expect(within(card).getByRole("button", { name: "Start visa case" })).toBeEnabled();
  });

  it("announces success politely", async () => {
    stubApi(() => json(201, { id: "v1", status: "checklist" }));
    const card = await startCaseForAsha();
    expect(await within(card).findByRole("status")).toHaveTextContent("Visa case started.");
  });
});
