// tel-012 (DEC-SCOPE-083): the call-script, message-template and brochure library -- types, labels, endpoints and the placeholder rule.
// Labels and the placeholder check are display only; the API decides (services/telecaller_content.py).
import { CATALOGUE_PAGE_SIZE, getPage } from "@/lib/telecallerCatalogue";

export type ProductRef = { id: string; name: string; group: string; active: boolean };
export type ScriptStep = { title: string; notes: string | null };
export type Script = { id: string; product: ProductRef; name: string; steps: ScriptStep[]; active: boolean };
export type Channel = "whatsapp" | "email";
export type Template = {
  id: string; channel: Channel; kind: string; name: string; product: ProductRef | null; asset: { id: string; name: string; active: boolean } | null;
  subject: string | null; body: string; active: boolean;
};
export type AssetKind = "brochure" | "fee";
export type Asset = { id: string; name: string; kind: AssetKind; product: ProductRef | null; file_name: string; size_bytes: number; active: boolean; uploaded_at: string };
export type AssetLink = { url: string; expires_at: string };
export type Preview = { subject: string | null; body: string; brochure_link: AssetLink | null };

export const SCRIPTS_URL = "/api/v1/telecaller/scripts";
export const TEMPLATES_URL = "/api/v1/telecaller/templates";
export const ASSETS_URL = "/api/v1/telecaller/assets";

// EVID-019 §11 / §12, in source order (app/tel_content_kinds.py).
export const WHATSAPP_KINDS = ["welcome", "course_details", "brochure", "fee_details", "counselling_appointment", "reminder", "follow_up", "overseas_destination", "document_request"] as const;
export const EMAIL_KINDS = ["course_brochure", "fee_proposal", "counselling_confirmation", "overseas_information", "university_information", "follow_up", "appointment_confirmation"] as const;
export const KIND_LABEL: Record<string, string> = {
  welcome: "Welcome message", course_details: "Course details", brochure: "Brochure", fee_details: "Fee details",
  counselling_appointment: "Counselling appointment", reminder: "Reminder", follow_up: "Follow-up", overseas_destination: "Overseas destination information",
  document_request: "Document request", course_brochure: "Course brochure", fee_proposal: "Fee proposal", counselling_confirmation: "Counselling confirmation",
  overseas_information: "Overseas information", university_information: "University information", appointment_confirmation: "Appointment confirmation",
};
export const kindsFor = (channel: Channel): readonly string[] => (channel === "whatsapp" ? WHATSAPP_KINDS : EMAIL_KINDS);
export const CHANNEL_LABEL: Record<Channel, string> = { whatsapp: "WhatsApp", email: "Email" };
export const BODY_LIMIT: Record<Channel, number> = { whatsapp: 1000, email: 5000 };
export const ASSET_KIND_LABEL: Record<AssetKind, string> = { brochure: "Brochure", fee: "Fee sheet" };

export const PLACEHOLDERS = ["name", "product", "brochure_link", "appointment_time"];
export const PLACEHOLDER_HINT = "Placeholders: {name}, {product}, {brochure_link} (needs a brochure), {appointment_time}.";

/** The server's rule (AC3): every {…} on one line must be one of the four placeholders, spelled exactly. */
export function unknownPlaceholders(text: string): string[] {
  return [...text.matchAll(/\{([^{}\n]*)\}/g)].filter((m) => !PLACEHOLDERS.includes(m[1])).map((m) => m[0]);
}

export function formatBytes(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${Math.round(size / 1024)} KB`;
  return `${Math.round((size / (1024 * 1024)) * 10) / 10} MB`;
}

/** The brochure picker: every active brochure, page after page (tel-002 QA-01: a picker must not stop at the first page). */
export async function activeAssets(signal?: AbortSignal): Promise<Asset[]> {
  const items: Asset[] = [];
  for (;;) {
    const page = await getPage<Asset>(`${ASSETS_URL}?active=true&limit=${CATALOGUE_PAGE_SIZE}&offset=${items.length}`, signal);
    items.push(...page.items);
    if (page.items.length === 0 || items.length >= page.total) return items;
  }
}
