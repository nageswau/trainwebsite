// ccrm-038 (DEC-SCOPE-274 CA4-CA7): the overseas counselor's read-only iCal feed. The API shows the feed URL only in the answer to a
// create/regenerate; afterwards it says only whether a feed is active.
export const CALENDAR_FEED_API = "/api/v1/counselor/calendar-feed";
export const CALENDAR_HOME = "/overseas/counselor/calendar";

export type CalendarFeedStatus = { active: boolean; created_at: string | null; url: string | null };

export const REGENERATE_PROMPT = "Create a new calendar link? The current link stops working at once, so calendars subscribed to it stop updating.";
export const REVOKE_PROMPT = "Turn off the calendar feed? The link stops working at once and subscribed calendars stop updating.";
