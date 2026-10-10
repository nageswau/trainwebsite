import { ApiError, serverApi } from "@/lib/api";
import { isUuid } from "@/lib/bdmTravel";
import { type UniversityView, universityViewUrl } from "@/lib/universityView";

/** upc-030 QA-01: a view link is a UUID; anything else is "University not found" before the API is asked (it would answer 422, whose
 * list-shaped detail has no sentence to show). The loadUniversity idiom. */
export async function loadUniversityView(id: string): Promise<UniversityView> {
  if (!isUuid(id)) throw new ApiError("University not found", 404);
  return serverApi<UniversityView>(universityViewUrl(id));
}
