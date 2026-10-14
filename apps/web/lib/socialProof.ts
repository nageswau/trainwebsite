// PUB-022 (DEC-SCOPE-210): the public social-proof strip's data -- GET /api/v1/public/social-proof.
import { formatDate } from "./formatDate";
import type { Testimonial } from "./types";

export type SocialProofDivision = "it" | "overseas" | "all";
export type RatingBadge = { source_name: string; rating: number; review_count: number; review_url: string | null; as_of: string };
export type SocialProof = { badge: RatingBadge | null; testimonials: Testimonial[] };

export const socialProofPath = (division: SocialProofDivision) => `/api/v1/public/social-proof?division=${division}`;

export function starsLabel(rating: number): string {
  return `Rated ${rating} out of 5`;
}

// "01 Oct 2026" -- a calendar date (no time), so it is formatted in UTC: the server and the browser then show the same day.
export function asOfLabel(isoDate: string): string {
  return /^\d{4}-\d{2}-\d{2}$/.test(isoDate) ? formatDate(`${isoDate}T00:00:00Z`, false, "UTC") : isoDate;
}

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  return (parts.slice(0, 2).map((p) => p[0]).join("") || "?").toUpperCase();
}
