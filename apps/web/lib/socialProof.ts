// PUB-022 (DEC-SCOPE-210): the public social-proof strip's data -- GET /api/v1/public/social-proof.
import type { Testimonial } from "./types";

export type SocialProofDivision = "it" | "overseas" | "all";
export type RatingBadge = { source_name: string; rating: number; review_count: number; review_url: string | null; as_of: string };
export type SocialProof = { badge: RatingBadge | null; testimonials: Testimonial[] };

export const socialProofPath = (division: SocialProofDivision) => `/api/v1/public/social-proof?division=${division}`;

export function starsLabel(rating: number): string {
  return `Rated ${rating} out of 5`;
}

// "1 Oct 2026" -- the date is a calendar date (no time zone), so it is formatted in UTC to avoid an off-by-one day.
export function asOfLabel(isoDate: string): string {
  const d = new Date(`${isoDate}T00:00:00Z`);
  return Number.isNaN(d.getTime()) ? isoDate : d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join("") || "?").toUpperCase();
}
