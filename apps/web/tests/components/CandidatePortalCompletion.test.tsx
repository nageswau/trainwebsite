import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import ContactDetailsCard from "@/components/ContactDetailsCard";
import DataTable from "@/components/DataTable";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import StudentCandidateDocumentsCard from "@/components/StudentCandidateDocumentsCard";
import { type DocumentRequest, documentCompletion } from "@/lib/candidateDocuments";
import { CANDIDATE_NAV } from "@/lib/candidatePortal";
import { PORTAL_NAV } from "@/lib/navigation";

// hrc-031 (DEC-SCOPE-412): the shared pieces both portals use -- every §11 section in both navs, the document completion (P5), the candidate's
// wording on the documents card (P4), the contact card (P10) and the notification filter over untyped notices (P8).
afterEach(cleanup);
beforeEach(() => {
  global.fetch = vi.fn();
});

const hrefs = (nav: { href: string }[]) => nav.map((item) => item.href);
const request = (status: DocumentRequest["status"]): DocumentRequest => ({
  id: status, document_type: "certificate", note: null, due_date: null, status, created_at: "2026-11-04T05:00:00Z", received_at: null, cancelled_at: null, document_id: null,
});
const notice = (id: string, title: string): NotificationItem => ({ id, title, body: `Body ${id}`, read: true, action_url: null, created_at: "2026-11-02T10:00:00Z" });

describe("the portal navs (hrc-031)", () => {
  it("gives a candidate every section", () => {
    expect(hrefs(CANDIDATE_NAV)).toEqual(
      ["profile", "jobs", "applications", "interviews", "results", "documents", "notifications", "privacy"].map((s) => `/it/careers/portal/${s}`),
    );
  });

  it("gives a student the new sections", () => {
    const links = hrefs(PORTAL_NAV["it/student"]);
    for (const section of ["results", "documents", "privacy", "job-applications", "interview-schedule", "notifications"]) expect(links).toContain(`/it/student/${section}`);
  });
});

describe("documentCompletion (P5)", () => {
  it("counts what was received out of what is still asked for, ignoring cancelled requests", () => {
    expect(documentCompletion([request("pending"), request("received"), request("cancelled")])).toBe("1 of 2 requested documents received");
  });

  it("is silent when nothing is asked for", () => {
    expect(documentCompletion([])).toBeNull();
    expect(documentCompletion([request("cancelled")])).toBeNull();
  });
});

describe("the documents card for a candidate (P4)", () => {
  const ok = (body: object) => new Response(JSON.stringify(body), { status: 200 });

  it("shows the completion and speaks of the recruitment team", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ available: true, requests: [request("pending")], documents: [] }));
    render(<StudentCandidateDocumentsCard candidate />);
    expect(await screen.findByText("0 of 1 requested documents received")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Documents the recruitment team asked for" })).toBeInTheDocument();
    expect(screen.queryByText(/placement/i)).toBeNull();
  });

  it("never asks a candidate to join the pool", async () => {
    vi.mocked(global.fetch).mockResolvedValue(ok({ available: false, requests: [], documents: [] }));
    render(<StudentCandidateDocumentsCard candidate />);
    expect(await screen.findByText(/aren't available/)).toBeInTheDocument();
    expect(screen.queryByText(/pool/)).toBeNull();
  });
});

describe("ContactDetailsCard (P10)", () => {
  it("shows the verified email, the mobile and where to change them", () => {
    render(<ContactDetailsCard email="a@example.com" verified mobile="+919876543210" changeHref="/it/careers/portal/profile" />);
    expect(screen.getByText("a@example.com")).toBeInTheDocument();
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("+919876543210")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Change your contact details" })).toHaveAttribute("href", "/it/careers/portal/profile");
  });

  it("shows an unverified email and a change waiting for its link", () => {
    render(<ContactDetailsCard email="a@example.com" verified={false} pendingEmail="b@example.com" mobile={null} changeHref="/x" />);
    expect(screen.getByText("Not verified")).toBeInTheDocument();
    expect(screen.getByText(/b@example.com/)).toBeInTheDocument();
    expect(screen.getByText("Not provided")).toBeInTheDocument();
  });
});

describe("browser QA fixes", () => {
  it("QA-01: the contact change reads as a button-styled link", () => {
    render(<ContactDetailsCard email="a@example.com" verified mobile={null} changeHref="/x" />);
    expect(screen.getByRole("link", { name: "Change your contact details" }).className).toContain("btn");
  });

  it("QA-04: a stacked table labels every cell, so nothing sits off a phone's screen", () => {
    const { container } = render(<DataTable columns={[{ key: "next_action", label: "Next action" }]} rows={[{ next_action: "Attend" }]} label="Mine" stack />);
    expect(container.querySelector("table")?.className).toBe("table compact stack"); // compact drops .table's 650 px minimum, which would keep the stacked rows off the screen
    expect(container.querySelector("td")?.getAttribute("data-label")).toBe("Next action");
  });

  it("QA-04: other tables are unchanged", () => {
    const { container } = render(<DataTable columns={[{ key: "a", label: "A" }]} rows={[{ a: "1" }]} label="Other" />);
    expect(container.querySelector("table")?.className).toBe("table");
    expect(container.querySelector("td")?.hasAttribute("data-label")).toBe(false);
  });
});

describe("SchoolNotificationList typeByTitle (P8)", () => {
  const notices = [notice("1", "Interview scheduled"), notice("2", "Interview result"), notice("3", "Interview scheduled")];

  it("filters untyped notices by their title", () => {
    render(<SchoolNotificationList notifications={notices} emptyText="none" typeByTitle />);
    const select = screen.getByLabelText("Type") as HTMLSelectElement;
    expect([...select.options].map((o) => o.textContent)).toEqual(["All", "Interview result", "Interview scheduled"]);
    fireEvent.change(select, { target: { value: "Interview result" } });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("Showing 1 of 3")).toBeInTheDocument();
  });

  it("leaves other portals as they were", () => {
    render(<SchoolNotificationList notifications={notices} emptyText="none" />);
    expect(screen.queryByLabelText("Type")).toBeNull();
  });
});
