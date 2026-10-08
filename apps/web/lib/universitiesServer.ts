// upc-003 (QA-01): the detail and edit pages' read. A malformed id is answered like an unknown one ("University not found"), instead of
// the API's 422 list reaching the access-unavailable card as "[object Object]".
import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { StageEvent } from "@/lib/bdmPipeline";
import { stageHistoryUrl } from "@/lib/partnershipPipeline";
import { type University, UNIVERSITIES_URL } from "@/lib/universities";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function loadUniversity(id: string): Promise<University> {
  if (!UUID.test(id)) throw new ApiError("University not found", 404);
  return (await serverApi<{ university: University }>(`${UNIVERSITIES_URL}/${id}`)).university;
}

/** upc-007: the first stage-history page, read alongside the university (bdm-004's firstStageHistory). Never rejects: a failure is null
 * and the section offers "Try again". Call after loadUniversity has accepted the id. */
export function firstStageHistory(id: string): Promise<Page<StageEvent> | null> {
  return serverApi<Page<StageEvent>>(stageHistoryUrl(id)).catch(() => null);
}
