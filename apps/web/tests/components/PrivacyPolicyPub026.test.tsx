import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import PrivacyPolicy from "@/app/privacy/page";
import sitemap from "@/app/sitemap";
import Footer from "@/components/Footer";
import { OFFICES } from "@/lib/offices";
import { PENDING_FACTS } from "@/lib/privacyPolicy";

// PUB-026 (DEC-SCOPE-442): the public privacy policy that ads and lead forms link to.
vi.mock("@/components/SiteHeader", () => ({ default: () => <header>site header</header> }));

afterEach(cleanup);

describe("privacy policy page (PUB-026)", () => {
  it("has every section, each reachable from the on-page contents", () => {
    render(<PrivacyPolicy />);
    expect(screen.getByRole("heading", { level: 1, name: "Privacy Policy" })).toBeTruthy();
    const toc = screen.getByRole("navigation", { name: "On this page" });
    const links = within(toc).getAllByRole("link");
    expect(links).toHaveLength(11);
    for (const link of links) {
      const id = link.getAttribute("href")!.slice(1);
      expect(document.getElementById(id), id).toBeTruthy();
    }
  });

  it("names the offices and the processors the product really uses", () => {
    render(<PrivacyPolicy />);
    for (const office of OFFICES) expect(screen.getByText(office.address)).toBeTruthy();
    for (const provider of ["DigitalOcean", "Zoho Mail", "Twilio", "Razorpay", "Google Analytics"]) {
      expect(screen.getAllByText(new RegExp(provider)).length, provider).toBeGreaterThan(0);
    }
    expect(screen.getByText(/We do not sell your personal data/)).toBeTruthy();
  });

  it("points account holders to self-service export and deletion", () => {
    render(<PrivacyPolicy />);
    expect(screen.getByRole("link", { name: "Privacy & your data" }).getAttribute("href")).toBe("/account/privacy");
  });

  it("gives the owner's privacy contact, grievance officer and lead retention (2026-11-16)", () => {
    render(<PrivacyPolicy />);
    expect(screen.getByRole("link", { name: "info@edusphere.org.uk" }).getAttribute("href")).toBe("mailto:info@edusphere.org.uk");
    expect(screen.getByText(/Joseph/)).toBeTruthy();
    expect(screen.getByText(/24 months after our last contact with you/)).toBeTruthy();
    expect(screen.queryByText(/UK representative/)).toBeNull();
  });

  it("shows each unconfirmed fact as a visible placeholder, never a guess", () => {
    render(<PrivacyPolicy />);
    const marks = document.querySelectorAll("mark.pending");
    expect(marks.length).toBe(PENDING_FACTS.length);
    if (PENDING_FACTS.length) expect(screen.getByRole("note", { name: "Details still to be confirmed" })).toBeTruthy();
    else expect(screen.queryByRole("note", { name: "Details still to be confirmed" })).toBeNull();
  });

  it("is linked from the footer and listed in the sitemap", () => {
    render(<Footer />);
    const privacyLinks = screen.getAllByRole("link", { name: "Privacy Policy" });
    expect(privacyLinks.length).toBeGreaterThan(0);
    for (const link of privacyLinks) expect(link.getAttribute("href")).toBe("/privacy");
    expect(screen.queryByText(/should be reviewed before production launch/)).toBeNull();
    expect(sitemap().some((entry) => entry.url.endsWith("/privacy"))).toBe(true);
  });
});
