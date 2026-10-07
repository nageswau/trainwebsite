import { serverApi } from "@/lib/api";
import { BDM_MANAGER_NAV, BDM_MANAGER_NOTIFICATIONS_HREF, BDM_NAV, BDM_NOTIFICATIONS_HREF, withBadge, type NavItem } from "@/lib/navigation";

// bdm-010 (QA10-01): the BDM and BDM-manager sidebars with the unread count on Notifications (AGN-017's endpoint and badge). A page
// that can't read the count still renders, just without the badge -- the count is a hint, never a reason to fail a page.
export async function unread(): Promise<number | null> {
  try {
    const data = await serverApi<{ unread?: unknown }>("/api/v1/workflows/notifications/unread-count");
    return typeof data?.unread === "number" ? data.unread : null;
  } catch {
    return null;
  }
}

export const bdmNav = async (): Promise<NavItem[]> => withBadge(BDM_NAV, BDM_NOTIFICATIONS_HREF, await unread());
export const bdmManagerNav = async (): Promise<NavItem[]> => withBadge(BDM_MANAGER_NAV, BDM_MANAGER_NOTIFICATIONS_HREF, await unread());
