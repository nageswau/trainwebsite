import type { ReactNode } from "react";
import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import OverseasProgress from "@/components/OverseasProgress";
import PortalPage from "@/components/PortalPage";
import PortalSection from "@/components/PortalSection";
import { ApiError, serverApi } from "@/lib/api";
import { PORTAL_NAV } from "@/lib/navigation";
import { MY_PROGRESS_URL, type Progress } from "@/lib/overseasProgress";
import { elements } from "@/tests/helpers/elementTree";

// nehn-033 (DEC-SCOPE-332): the overseas student's Progress page -- a stepper per application (state always as text), the documents
// still to upload (each linking to upload) and the next actions; an inline status card when the read fails.
vi.mock("next/navigation", () => ({ notFound: () => { throw new Error("notFound"); }, redirect: vi.fn() }));
vi.mock("@/lib/api", async () => ({ ...(await vi.importActual<typeof import("@/lib/api")>("@/lib/api")), serverApi: vi.fn() }));
const api = vi.mocked(serverApi);

const KEYS = ["submitted", "under_review", "university_selected", "offer_processing", "offer", "documentation", "visa_processing", "visa_decision", "final"];
const LABELS = ["Application submitted", "Application under review", "University selected", "Offer processing", "Conditional offer", "Documentation", "Visa processing", "Visa decision", "Final outcome"];

function body(extra: Partial<Progress> = {}): Progress {
  return {
    applications: [
      {
        id: "a1", application_code: "APP-000012", university: "Alpha Uni", intake: "Sep 2027", closed: false, note: "On hold",
        current: { key: "offer", label: "Conditional offer" },
        steps: KEYS.map((key, i) => ({ key, label: LABELS[i], state: i < 4 ? "done" : i === 4 ? "current" : "upcoming" })),
      },
    ],
    missing_documents: [
      { name: "Passport", source: "Visa checklist", application_code: "APP-000012", university: "Alpha Uni", status_label: "Not uploaded", due_date: null, overdue: false, upload_url: "/overseas/student/documents" },
      { name: "SOP", source: "Document request", application_code: null, university: null, status_label: "Requested", due_date: "2026-11-02", overdue: true, upload_url: "/overseas/student/documents" },
    ],
    next_actions: [
      { text: "Upload 2 missing documents", href: "/overseas/student/documents" },
      { text: "Pay the deposit for Alpha Uni", href: null },
    ],
    ...extra,
  };
}

async function show(data: Progress | Error) {
  api.mockImplementation(() => (data instanceof Error ? Promise.reject(data) : Promise.resolve(data)));
  render(await OverseasProgress());
}

beforeEach(() => {
  api.mockReset();
});
afterEach(cleanup);

describe("OverseasProgress (nehn-033)", () => {
  it("reads the student's own progress", async () => {
    await show(body());
    expect(api).toHaveBeenCalledWith(MY_PROGRESS_URL);
    expect(MY_PROGRESS_URL).toBe("/api/v1/overseas/me/progress");
  });

  it("shows each application's steps with the current one marked and every state as text (AC1)", async () => {
    await show(body());
    const list = screen.getByRole("list", { name: "Progress of Alpha Uni (APP-000012)" }); // QA-03: unique per application
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(9);
    expect(items[4]).toHaveAttribute("aria-current", "step");
    expect(items[4]).toHaveTextContent("Conditional offer");
    expect(items[4]).toHaveTextContent("Current");
    expect(items[0]).toHaveTextContent("Done");
    expect(items[8]).toHaveTextContent("Not yet");
    expect(screen.getByText(/Current step: Conditional offer/)).toBeInTheDocument();
    expect(screen.getByText("On hold")).toBeInTheDocument();
  });

  it("names a closed application's final outcome (AC2)", async () => {
    const closed = body().applications[0];
    await show(
      body({
        applications: [{ ...closed, closed: true, note: null, current: { key: "visa_decision", label: "Visa decision: Rejected" }, steps: closed.steps.map((s, i) => ({ ...s, state: i < 7 ? "done" : i === 7 ? "stopped" : "stopped", label: i === 7 ? "Visa decision: Rejected" : i === 8 ? "Final outcome: Visa rejected" : s.label })) }],
      }),
    );
    expect(screen.getByText(/Current step: Visa decision: Rejected/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Alpha Uni Closed" })).toBeInTheDocument(); // QA-02: the badge is a separate word
    const items = within(screen.getByRole("list", { name: "Progress of Alpha Uni (APP-000012)" })).getAllByRole("listitem");
    expect(items[8]).toHaveTextContent("Final outcome: Visa rejected");
    expect(items[8]).toHaveTextContent("Stopped");
    expect(items[8]).not.toHaveAttribute("aria-current");
  });

  it("lists every missing document with a link to upload it (AC3)", async () => {
    await show(body());
    const list = screen.getByRole("list", { name: "Missing documents" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("Passport");
    expect(items[0]).toHaveTextContent("Visa checklist · Alpha Uni (APP-000012) · Not uploaded");
    expect(within(items[0]).getByRole("link", { name: "Upload Passport" })).toHaveAttribute("href", "/overseas/student/documents");
    expect(items[1]).toHaveTextContent(/Due \d{2} Nov 2026 Overdue/); // QA-02
    expect(within(items[0]).getByRole("link", { name: "Upload Passport" })).toHaveClass("btn"); // QA-04: reads as an action
  });

  it("lists the next actions, linking the ones that have a page", async () => {
    await show(body());
    const items = within(screen.getByRole("list", { name: "Next actions" })).getAllByRole("listitem");
    expect(within(items[0]).getByRole("link", { name: "Upload 2 missing documents" })).toHaveAttribute("href", "/overseas/student/documents");
    expect(within(items[1]).queryByRole("link")).toBeNull();
  });

  it("says when nothing is missing and nothing is due", async () => {
    await show(body({ missing_documents: [], next_actions: [] }));
    expect(screen.getByText("No documents are missing.")).toBeInTheDocument();
    expect(screen.getByText("Nothing to do right now. Your counselor will update you.")).toBeInTheDocument();
  });

  it("points a student without applications to Applications", async () => {
    await show({ applications: [], missing_documents: [], next_actions: [] });
    expect(screen.getByText(/You have no applications yet/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Apply to a university" })).toHaveAttribute("href", "/overseas/student/applications");
  });

  it("shows an inline status when the read fails", async () => {
    await show(new ApiError("boom", 500));
    expect(screen.getByRole("status")).toHaveTextContent("Your progress could not be loaded. Refresh the page to try again.");
  });
});

describe("Progress in the overseas student's portal", () => {
  it("is the nav entry right after Dashboard", () => {
    expect(PORTAL_NAV["overseas/student"].slice(0, 2)).toEqual([
      { label: "Dashboard", href: "/overseas/student/dashboard" },
      { label: "Progress", href: "/overseas/student/progress" },
    ]);
  });

  it("mounts the page under the section header without an empty table", async () => {
    api.mockImplementation((path: string) => Promise.resolve(path === "/api/v1/auth/me" ? { id: "u1", role: "overseas_student", full_name: "S", email: "s@x" } : { title: "Progress", subtitle: "", columns: [], rows: [], metrics: [] }));
    const tree = elements(await PortalPage({ division: "overseas", role: "student", section: "progress" }));
    const section = tree.find((el) => el.type === PortalSection);
    expect(section?.props.table).toBe(false);
    expect(elements(section?.props.lead as ReactNode).some((el) => el.type === OverseasProgress)).toBe(true);
  });
});
