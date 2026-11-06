// hrc-032 (DEC-SCOPE-412 N8-N10): the Delivery exceptions page. The API decides who may read it (a `notifications.retry` holder) and what a row
// says: never a notice's body or an email's subject.
import type { Page } from "@/lib/apiErrors";

export const EXCEPTIONS_URL = "/api/v1/recruiter/notification-exceptions";
export const EXCEPTIONS_PATH = "/recruiter/notification-exceptions";
export const PAGE_SIZE = 50;
export const CHANNELS = [
  { key: "email", label: "Email" },
  { key: "whatsapp", label: "WhatsApp" },
  { key: "sms", label: "SMS" },
] as const;

export type ExceptionRow = {
  source: "delivery" | "email"; id: string; type: string; type_label: string; recipient: string; channel: string;
  error: string | null; attempts: number; failed_at: string;
};
export type ExceptionPage = Page<ExceptionRow> & { types: { key: string; label: string }[] };
export type ExceptionFilters = { type: string; channel: string; offset: number };

const text = (value: unknown): string => (typeof value === "string" ? value : "");

export function parseFilters(params: Record<string, string | string[] | undefined>): ExceptionFilters {
  const channel = text(params.channel);
  const offset = text(params.offset);
  return { type: text(params.type), channel: CHANNELS.some((c) => c.key === channel) ? channel : "", offset: /^\d+$/.test(offset) ? Number(offset) : 0 };
}

function query({ type, channel, offset }: ExceptionFilters): URLSearchParams {
  const params = new URLSearchParams();
  if (type) params.set("type", type);
  if (channel) params.set("channel", channel);
  if (offset) params.set("offset", String(offset));
  return params;
}

export function listUrl(filters: ExceptionFilters): string {
  const params = query(filters);
  params.set("limit", String(PAGE_SIZE));
  return `${EXCEPTIONS_URL}?${params}`;
}

export function pageHref(filters: ExceptionFilters): string {
  const params = query(filters).toString();
  return params ? `${EXCEPTIONS_PATH}?${params}` : EXCEPTIONS_PATH;
}

export const retryUrl = (row: Pick<ExceptionRow, "source" | "id">) => `${EXCEPTIONS_URL}/${row.source}/${encodeURIComponent(row.id)}/retry`;
export const channelLabel = (key: string) => CHANNELS.find((c) => c.key === key)?.label ?? key;
