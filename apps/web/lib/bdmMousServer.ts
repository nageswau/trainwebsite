import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { MOUS_URL, type MouRow, type MousParams, mousQuery, type OrgMou, orgMouUrl } from "@/lib/bdmMous";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmMous.ts, which client components import.
/** The organization pages' MoU card, read alongside the organization (the firstStageHistory pattern). Never rejects: a failure is
 * null and the card offers "Try again"; a malformed id isn't sent. */
export function firstMou(id: string): Promise<OrgMou | null> {
  return isUuid(id) ? serverApi<OrgMou>(orgMouUrl(id)).catch(() => null) : Promise.resolve(null);
}

/** A hand-edited address (an unknown status) is "invalid", shown with a reset link; anything else is the page's error. */
export async function readMous(params: MousParams): Promise<Page<MouRow> | "invalid"> {
  try {
    return await serverApi<Page<MouRow>>(`${MOUS_URL}?${mousQuery(params)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) return "invalid";
    throw e;
  }
}
