// upc-009: the meeting detail and edit pages' read. A malformed id is answered like an unknown one ("Meeting not found"), as upc-010.
import { ApiError, serverApi } from "@/lib/api";
import { type Meeting, meetingUrl } from "@/lib/meetings";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export async function loadMeeting(id: string): Promise<Meeting> {
  if (!UUID.test(id)) throw new ApiError("Meeting not found", 404);
  return (await serverApi<{ meeting: Meeting }>(meetingUrl(id))).meeting;
}
