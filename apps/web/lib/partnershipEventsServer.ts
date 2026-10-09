// upc-011: the event detail and edit pages' read. A malformed id is answered like an unknown one ("Event not found"), as upc-009/010.
import { ApiError, serverApi } from "@/lib/api";
import { eventUrl, type PartnershipEvent } from "@/lib/partnershipCalendar";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function loadEvent(id: string): Promise<PartnershipEvent> {
  if (!UUID.test(id)) throw new ApiError("Event not found", 404);
  return (await serverApi<{ event: PartnershipEvent }>(eventUrl(id))).event;
}
