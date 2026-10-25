import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import OverseasStudentJourney from "@/components/OverseasStudentJourney";
import type { StudentJourney } from "@/lib/overseasStudent360";

const KEYS = ["lead", "counselling", "applying", "offer", "visa", "enrolled"];
const LABELS = ["Lead", "Counselling", "Applying", "Offer", "Visa", "Enrolled"];

function journey(stage: string, extra: Partial<StudentJourney> = {}): StudentJourney {
  const at = KEYS.indexOf(stage);
  return {
    stage, label: LABELS[at], note: null, application: null,
    steps: KEYS.map((key, i) => ({ key, label: LABELS[i], state: i < at ? "done" : i === at ? "current" : "upcoming" })),
    ...extra,
  };
}

afterEach(cleanup);

describe("OverseasStudentJourney (ccrm-017)", () => {
  it("shows six steps with the current one marked and every state as text", () => {
    render(<OverseasStudentJourney journey={journey("offer", { application: { id: "a1", application_code: "APP-000012", university: "Alpha Uni" } })} />);
    const list = screen.getByRole("list", { name: "Student journey" });
    const items = within(list).getAllByRole("listitem");
    expect(items.map((i) => i.querySelector(".jny-name")?.textContent)).toEqual(LABELS);
    expect(items[3]).toHaveAttribute("aria-current", "step");
    expect(items[3]).toHaveTextContent("Current");
    expect(items[0]).toHaveTextContent("Done");
    expect(items[5]).toHaveTextContent("Not yet");
    expect(screen.getByText(/APP-000012/)).toHaveTextContent("Furthest application: APP-000012 · Alpha Uni");
  });

  it("shows the note and no application line when there is none", () => {
    render(<OverseasStudentJourney journey={journey("counselling", { note: "All applications closed" })} />);
    expect(screen.getByText("All applications closed")).toBeInTheDocument();
    expect(screen.queryByText(/Furthest application/)).not.toBeInTheDocument();
  });
});
