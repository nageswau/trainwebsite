// upc-010: the visit detail and edit pages' read. A malformed id is answered like an unknown one ("Visit not found"), as upc-003 QA-01.
import { ApiError, serverApi } from "@/lib/api";
import { type Visit, visitUrl } from "@/lib/visits";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function loadVisit(id: string): Promise<Visit> {
  if (!UUID.test(id)) throw new ApiError("Visit not found", 404);
  return (await serverApi<{ visit: Visit }>(visitUrl(id))).visit;
}
