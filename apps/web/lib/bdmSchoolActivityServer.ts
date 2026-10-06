import { serverApi } from "@/lib/api";
import { type SchoolActivity, schoolActivityUrl } from "@/lib/bdmSchoolActivity";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmSchoolActivity.ts, which client components import.
/** The organization pages' School activity panel, read alongside the organization (the firstMou pattern). Never rejects: a failure
 * (including a non-School organization's 404, which the panel never shows) is null; a malformed id isn't sent. */
export function firstSchoolActivity(id: string): Promise<SchoolActivity | null> {
  return isUuid(id) ? serverApi<SchoolActivity>(schoolActivityUrl(id)).catch(() => null) : Promise.resolve(null);
}
