import { readFileSync } from "node:fs";
import path from "node:path";

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import CertificationDetails from "@/components/CertificationDetails";

// ENH-024 -- docs/superpowers/specs/2026-09-28-enh-024-skill-india-certification-design.md §6.

afterEach(cleanup);

describe("CertificationDetails", () => {
  it("renders nothing for an entry that is not Skill India", () => {
    const { container } = render(<CertificationDetails entry={{ certification_type: null, certification_status: null, certificate_number: null, issued_on: null }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the badge, status as text, certificate number and issue date", () => {
    render(<CertificationDetails entry={{ certification_type: "skill_india", certification_status: "certified", certificate_number: "SI-2026-0001", issued_on: "2026-05-01" }} />);
    expect(screen.getByText("Skill India")).toHaveClass("badge");
    expect(screen.getByText("Certified")).toHaveClass("status");
    expect(screen.getByText("Certified")).not.toHaveClass("pending");
    expect(screen.getByText("Certificate no. SI-2026-0001")).toBeInTheDocument();
    expect(screen.getByText(/^Issued /)).toBeInTheDocument();
  });

  it("marks a not-yet-certified status as pending, still in words", () => {
    render(<CertificationDetails entry={{ certification_type: "skill_india", certification_status: "in_progress", certificate_number: null, issued_on: null }} />);
    expect(screen.getByText("In progress")).toHaveClass("status", "pending");
    expect(screen.queryByText(/Certificate no\./)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Issued /)).not.toBeInTheDocument();
  });

  it("is safe inside client components (imports no server-only module)", () => {
    // clientBoundary.test.ts only checks a client file's direct imports; PortfolioPanel ("use client") imports this file,
    // so a server-only import here would break `next build` without that test noticing.
    const source = readFileSync(path.resolve(__dirname, "../../components/CertificationDetails.tsx"), "utf8");
    expect(source).not.toMatch(/@\/components\/SchoolChildOverview|@\/lib\/api["']|next\/headers/);
  });
});
