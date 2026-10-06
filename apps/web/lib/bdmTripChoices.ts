import { serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { TripRow } from "@/lib/bdmTravel";

/** bdm-011: the BDM's open trips for the appointment form's Trip choice, read once by a server page. A failure never blocks the
 * appointment page -- the form just says the trips couldn't be loaded (the link can be made later). */
export async function linkableTrips(): Promise<{ trips: TripRow[]; tripsUnavailable: boolean }> {
  try {
    return { trips: (await serverApi<Page<TripRow>>("/api/v1/bdm/trips?linkable=true&limit=100")).items, tripsUnavailable: false };
  } catch {
    return { trips: [], tripsUnavailable: true };
  }
}
