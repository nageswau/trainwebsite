import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { SocialProofView } from "@/components/SocialProofStrip";
import { asOfLabel, initials, socialProofPath } from "@/lib/socialProof";
import type { SocialProof } from "@/lib/socialProof";

afterEach(cleanup);

const badge = { source_name: "Google", rating: 4.8, review_count: 1234, review_url: "https://g.page/r/example", as_of: "2026-10-01" };
const story = (over: Partial<SocialProof["testimonials"][number]> = {}) => ({
  id: "t1", division: "it", person_name: "Asha Rao", headline: "Placed", quote: "Great mentors.", rating: 5, context: "Python Full-Stack", photo_url: null, ...over,
});

describe("SocialProofView (PUB-022)", () => {
  it("renders nothing without data or with nothing published", () => {
    expect(render(<SocialProofView data={null} />).container.innerHTML).toBe("");
    cleanup();
    expect(render(<SocialProofView data={{ badge: null, testimonials: [] }} />).container.innerHTML).toBe("");
  });

  it("renders the badge on its own", () => {
    render(<SocialProofView data={{ badge, testimonials: [] }} />);
    expect(screen.getByText(/on Google/).textContent).toMatch(/4\.8 on Google · 1,234 reviews · as of 01 Oct 2026/);
    expect(screen.getByRole("img", { name: "Rated 4.8 out of 5" })).toBeTruthy();
    const link = screen.getByRole("link", { name: /Read reviews/ });
    expect(link.getAttribute("href")).toBe("https://g.page/r/example");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(screen.queryByRole("figure")).toBeNull();
  });

  it("renders cards without a badge, with initials when there is no photo", () => {
    const { container } = render(<SocialProofView data={{ badge: null, testimonials: [story()] }} />);
    expect(screen.queryByText(/on Google/)).toBeNull();
    expect(screen.getByText(/Great mentors\./)).toBeTruthy();
    expect(screen.getByText("Asha Rao")).toBeTruthy();
    expect(screen.getByText(/Python Full-Stack/)).toBeTruthy();
    expect(screen.getByRole("img", { name: "Rated 5 out of 5" })).toBeTruthy();
    expect(container.querySelector(".social-proof-initials")?.textContent).toBe("AR");
  });

  it("shows the photo with an accessible name when there is one", () => {
    render(<SocialProofView data={{ badge: null, testimonials: [story({ photo_url: "/api/v1/public/testimonials/t1/photo" })] }} />);
    expect(screen.getByRole("img", { name: "Photo of Asha Rao" }).getAttribute("src")).toBe("/api/v1/public/testimonials/t1/photo");
  });

  it("omits the review link when there is no URL", () => {
    render(<SocialProofView data={{ badge: { ...badge, review_url: null }, testimonials: [] }} />);
    expect(screen.queryByRole("link")).toBeNull();
  });
});

describe("socialProof helpers", () => {
  it("formats dates and initials", () => {
    expect(asOfLabel("2026-10-01")).toBe("01 Oct 2026");
    expect(asOfLabel("not-a-date")).toBe("not-a-date");
    expect(initials("  sneha   p kumar ")).toBe("SP");
    expect(socialProofPath("it")).toBe("/api/v1/public/social-proof?division=it");
  });
});
