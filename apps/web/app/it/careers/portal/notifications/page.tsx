import CandidatePortalSection from "@/components/CandidatePortalSection";
import SchoolNotificationList, { type NotificationItem } from "@/components/SchoolNotificationList";
import SectionUnavailable from "@/components/SectionUnavailable";
import { serverApi } from "@/lib/api";

async function CandidateNotices() {
  let notices: NotificationItem[];
  try {
    notices = await serverApi<NotificationItem[]>("/api/v1/workflows/notifications");
  } catch {
    return <SectionUnavailable title="Notifications" />;
  }
  return <div className="card"><SchoolNotificationList notifications={notices} localTime readBeforeOpen typeByTitle emptyText="No notifications yet. Updates about your applications and interviews appear here." /></div>;
}

// hrc-031 (DEC-SCOPE-412 P8): the caller's own notices, filtered by type.
export default function CandidateNotificationsPage() {
  const header = { title: "Notifications", subtitle: "Your own notifications. Open one to go to the record it is about.", actions: [{ label: "Notification preferences", href: "/account/profile" }] };
  return <CandidatePortalSection header={header} lead={<CandidateNotices />} />;
}
