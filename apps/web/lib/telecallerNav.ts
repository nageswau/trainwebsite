import { unread } from "@/lib/bdmNav";
import { TELECALLER_NAV, TELECALLER_NOTIFICATIONS_HREF, withBadge, type NavItem } from "@/lib/navigation";

// tel-020: the telecaller sidebar with the unread count on Notifications (bdm-010's badge; a page that can't read the count still renders).
export const telecallerNav = async (): Promise<NavItem[]> => withBadge(TELECALLER_NAV, TELECALLER_NOTIFICATIONS_HREF, await unread());
