import { ApiError, serverApi } from "@/lib/api";
import type { Page } from "@/lib/apiErrors";
import type { BdmManagerOption } from "@/lib/bdm";
import { bdmManagerNav } from "@/lib/bdmNav";
import { type NavItem, SUPER_ADMIN_NAV } from "@/lib/navigation";
import type { User } from "@/lib/types";

// bdm-024 (DEC-SCOPE-111 §6): what the four performance pages share on the server -- the role's sidebar (super_admin keeps the admin
// navigation, as bdm-023), the manager options for super_admin's team filter, and reading one API response as data or an ApiError.
export const UNABLE = "Unable to load the performance figures.";

export async function shellFor(user: User): Promise<{ superAdmin: boolean; nav: NavItem[]; roleLabel: string }> {
  const superAdmin = user.role === "super_admin";
  return { superAdmin, nav: superAdmin ? SUPER_ADMIN_NAV : await bdmManagerNav(), roleLabel: superAdmin ? "Super Administrator" : "BDM Manager" };
}

export const managerOptions = (): Promise<BdmManagerOption[]> =>
  serverApi<Page<BdmManagerOption>>("/api/v1/admin/bdm-managers?limit=100").then((p) => p.items, () => []);

/** The response when it has the expected shape, otherwise an ApiError (a malformed body reads as a 500). */
export async function load<T>(path: string, guard: (value: unknown) => value is T): Promise<T | ApiError> {
  try {
    const value = await serverApi<unknown>(path);
    return guard(value) ? value : new ApiError(UNABLE, 500);
  } catch (e) {
    return e instanceof ApiError ? e : new ApiError(UNABLE, 500);
  }
}

/** Signed out or not a manager: the access card, not an inline error. */
export const isDenied = (e: ApiError): boolean => e.status === 401 || e.status === 403;

/** A refused period (422) or an unknown BDM (404) says why; anything else is the generic failure. A date the API can't parse (e.g.
 * 2026-02-30) comes back as FastAPI's list of errors, which reaches here as "[object Object]". */
export function failureText(e: ApiError): string {
  if (e.status === 404) return e.message;
  if (e.status === 422) return e.message.startsWith("[object") ? "Choose valid dates for the period." : e.message;
  return UNABLE;
}
