import { unread } from "@/lib/bdmNav";
import {
  TELECALLER_MANAGER_NAV, TELECALLER_MANAGER_NOTIFICATIONS_HREF, TELECALLER_NAV, TELECALLER_NOTIFICATIONS_HREF, withBadge, type NavItem,
} from "@/lib/navigation";

// tel-020: the telecaller sidebar with the unread count on Notifications (bdm-010's badge; a page that can't read the count still renders).
export const telecallerNav = async (): Promise<NavItem[]> => withBadge(TELECALLER_NAV, TELECALLER_NOTIFICATIONS_HREF, await unread());

// itc-009: the manager's sidebar on its Notifications page, with the same unread count.
export const telecallerManagerNav = async (): Promise<NavItem[]> =>
  withBadge(TELECALLER_MANAGER_NAV, TELECALLER_MANAGER_NOTIFICATIONS_HREF, await unread());
