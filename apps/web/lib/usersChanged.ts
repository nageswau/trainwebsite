// The Create user card and the Manage users panel are siblings on the admin Users page, and the panel only fetches its
// list on mount. The card announces a new account so the panel can refetch -- otherwise an account whose email failed
// (the one an admin most needs to Re-send to) is missing from the panel until a full reload.
export const USERS_CHANGED = "edusphere:users-changed";

export function announceUsersChanged(): void {
  window.dispatchEvent(new Event(USERS_CHANGED));
}
