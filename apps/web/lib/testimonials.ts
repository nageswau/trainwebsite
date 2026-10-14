// PUB-022 (DEC-SCOPE-210): the CMS testimonial + rating badge endpoints (spec §4.2).
export type Division = "it" | "overseas";

export type ManagedTestimonial = {
  id: string;
  division: Division;
  person_name: string;
  headline: string;
  quote: string;
  rating: number;
  context: string | null;
  photo_url: string | null;
  published: boolean;
  featured: boolean;
  display_order: number;
  consent_confirmed: boolean;
  consent_at: string | null;
  has_photo: boolean;
  updated_at: string | null;
};

export type TestimonialDraft = {
  division: Division;
  person_name: string;
  headline: string;
  quote: string;
  rating: number;
  context: string;
  display_order: string;
  featured: boolean;
  consent_confirmed: boolean;
  published: boolean;
};

export type BadgeDraft = { source_name: string; rating: string; review_count: string; review_url: string; as_of: string; published: boolean };

export const MANAGE_URL = "/api/v1/cms/manage/testimonials";
export const TESTIMONIALS_URL = "/api/v1/cms/testimonials";
export const BADGE_URL = "/api/v1/cms/rating-badge";
export const testimonialUrl = (id: string) => `${TESTIMONIALS_URL}/${id}`;
export const photoUrl = (id: string) => `${TESTIMONIALS_URL}/${id}/photo`;
export const CONSENT_TEXT = "I confirm this person agreed to public use of their name, words and photo.";

export function emptyDraft(division: Division): TestimonialDraft {
  return { division, person_name: "", headline: "", quote: "", rating: 5, context: "", display_order: "0", featured: false, consent_confirmed: false, published: false };
}

export function draftFrom(t: ManagedTestimonial): TestimonialDraft {
  return {
    division: t.division,
    person_name: t.person_name,
    headline: t.headline,
    quote: t.quote,
    rating: t.rating,
    context: t.context ?? "",
    display_order: String(t.display_order),
    featured: t.featured,
    consent_confirmed: t.consent_confirmed,
    published: t.published,
  };
}

// Consent first, then publish: the server applies them in that order, and unticking consent unpublishes (SP9).
export function draftBody(d: TestimonialDraft, creating: boolean): Record<string, unknown> {
  const body: Record<string, unknown> = {
    person_name: d.person_name.trim(),
    headline: d.headline.trim(),
    quote: d.quote.trim(),
    rating: d.rating,
    context: d.context.trim() || null,
    display_order: Number.parseInt(d.display_order, 10) || 0,
    featured: d.featured,
    consent_confirmed: d.consent_confirmed,
    published: d.consent_confirmed && d.published,
  };
  if (creating) body.division = d.division;
  return body;
}

export function badgeDraftFrom(b: { source_name: string; rating: number; review_count: number; review_url: string | null; as_of: string; published: boolean } | null): BadgeDraft {
  if (!b) return { source_name: "Google", rating: "", review_count: "", review_url: "", as_of: "", published: false };
  return { source_name: b.source_name, rating: String(b.rating), review_count: String(b.review_count), review_url: b.review_url ?? "", as_of: b.as_of, published: b.published };
}

export function badgeBody(d: BadgeDraft): Record<string, unknown> {
  return {
    source_name: d.source_name.trim(),
    rating: Number(d.rating),
    review_count: Number.parseInt(d.review_count, 10),
    review_url: d.review_url.trim() || null,
    as_of: d.as_of,
    published: d.published,
  };
}
