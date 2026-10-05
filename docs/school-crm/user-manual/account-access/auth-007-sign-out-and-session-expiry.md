# Sign out and session expiry

> Doc ID: DOC-SCH-AUTH-007 · Verified on 2026-10-06 against `main` @ `ce1f07c2` · Roles: all school roles

## Purpose
End your session safely, and understand what happens when a session ends by itself.

## Who Can Use This Feature
Any signed-in school user.

## Prerequisites
You are signed in.

## How to Access
Sidebar footer > **Sign out**.

## Steps

### Step 1 — Sign out
Click **Sign out** at the bottom of the sidebar. You are taken to the EduSphere home page.

### Step 2 — When your session has ended
If you return to a portal page after your session has ended, you see **Access unavailable — Not authenticated** with a
**Return to login** button. Click it and sign in again.

![Session ended](../../screenshots/account-access/23-session-expired.png)

## Fields
None.

## Expected Result
After **Sign out**, portal pages show "Access unavailable — Not authenticated" until you sign in again.

## Validation Messages
| Message | When |
|---|---|
| Access unavailable — Not authenticated | You are not signed in, or your session ended. |

## Common Errors
**Problem:** "Not authenticated" in the middle of your work.
**Cause:** A session lasts a limited time. *(From code: about 60 minutes after you sign in, whether or not you are
active. The documentation team confirmed the screen by removing the session, not by waiting 60 minutes.)*
**Resolution:** Click **Return to login** and sign in again. Unsaved changes on the page may be lost, so save long forms
regularly.

## Tips
- **On a phone or narrow window there is no Sign out button**: the menu (**Open menu**) shows Change password, My profile
  and your pages, but not Sign out. Close the browser, or widen the window to see the sidebar, to sign out.
- On a shared computer, always sign out and close the browser.

## Related Features
- [Sign in](auth-001-sign-in.md)
- ["Access unavailable" messages](auth-008-access-unavailable.md)
- [Find your way around](auth-009-find-your-way-around.md)
