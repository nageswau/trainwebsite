import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import { historyUrl, PIPELINE_URL, type PipelineParams, pipelineQuery, type PipelineView, type StageEvent } from "@/lib/bdmPipeline";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmPipeline.ts, which client components import.
/** The organization pages' first history page, read alongside the organization (the firstActivityPage pattern). Never rejects: a
 * failure is null and the section offers "Try again"; a malformed id isn't sent. */
export function firstStageHistory(id: string): Promise<Page<StageEvent> | null> {
  return isUuid(id) ? serverApi<Page<StageEvent>>(historyUrl(id)).catch(() => null) : Promise.resolve(null);
}

/** A hand-edited address (unknown stage, another module) is "invalid", shown with a reset link; anything else is the page's error. */
export async function readPipeline(params: PipelineParams): Promise<PipelineView | "invalid"> {
  try {
    return await serverApi<PipelineView>(`${PIPELINE_URL}?${pipelineQuery(params)}`);
  } catch (e) {
    if (e instanceof ApiError && e.status === 422) return "invalid";
    throw e;
  }
}
