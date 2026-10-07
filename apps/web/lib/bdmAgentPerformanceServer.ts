import { serverApi } from "@/lib/api";
import { type AgentPerformance, agentPerformanceUrl } from "@/lib/bdmAgentPerformance";
import { isUuid } from "@/lib/bdmTravel";

// Server-only (serverApi reads next/headers): kept out of lib/bdmAgentPerformance.ts, which the client component imports.
/** bdm-022: the organization pages' Agent performance panel, read alongside the organization (the firstMou pattern). Never rejects:
 * a failure (including a non-Agent organization's 404, which the panel never shows) is null; a malformed id isn't sent. */
export function firstAgentPerformance(id: string): Promise<AgentPerformance | null> {
  return isUuid(id) ? serverApi<AgentPerformance>(agentPerformanceUrl(id)).catch(() => null) : Promise.resolve(null);
}
