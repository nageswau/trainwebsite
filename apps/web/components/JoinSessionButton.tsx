"use client";

import { formatDateTimeIn, viewerTimeZone } from "@/lib/formatDate";

// User-requested join-experience fix (2026-09-09, `docs/decisions/PENDING_ZOHO_LIVE_CLASSES.md`
// §1b items a/b/c): the raw join URL previously rendered as inert text in the generic
// `DataTable` and as a plain `<a>` in `LiveClassesPanel` -- neither gated on timing at all,
// so a student could "join" hours before or after a class with no feedback either way.
// This is a real `<button>` (not a link) so a click can be intercepted: too early (>15
// minutes before start -- the same figure `EVID-008` already gave) or after the session's
// end time each show a pop-up instead of opening anything, and a joining participant
// (never the host) confirms their own already-known identity before the real link opens.
//
// Honest limitation, also flagged in `PENDING_ZOHO_LIVE_CLASSES.md` §2 item 11: this only
// gates EduSphere's own button. Nothing here can stop someone who already has the raw
// Zoho/Google join URL from using it directly -- no provider-side lobby lock is confirmed
// to exist.

const EARLY_WINDOW_MINUTES = 15;

type SessionState = "too_early" | "joinable" | "ended";

function sessionState(startsAt: string, endsAt: string | null | undefined, now: number): SessionState {
  const start = new Date(startsAt).getTime();
  const end = endsAt ? new Date(endsAt).getTime() : start + 60 * 60 * 1000;
  if (Number.isNaN(start)) return "joinable"; // unparseable date -- never block on bad data
  if (!Number.isNaN(end) && now > end) return "ended";
  if (now < start - EARLY_WINDOW_MINUTES * 60 * 1000) return "too_early";
  return "joinable";
}

export default function JoinSessionButton({
  joinUrl,
  startsAt,
  endsAt,
  isHost,
  userName,
  userEmail,
  label = "Join class",
  className = "btn small",
}: {
  joinUrl: string | null | undefined;
  startsAt: string;
  endsAt?: string | null;
  isHost: boolean;
  userName?: string;
  userEmail?: string;
  label?: string;
  className?: string;
}) {
  if (!joinUrl) return <span className="muted" style={{ fontSize: 13 }}>Join link not yet available.</span>;

  function handleClick() {
    if (!joinUrl) return;
    // The host may legitimately need to join early to set up before students arrive --
    // the early/late window only applies to a joining participant, never the host.
    const state = isHost ? "joinable" : sessionState(startsAt, endsAt, Date.now());
    if (state === "too_early") {
      // window.alert() takes a plain string, so <LocalTime> cannot render here; the same helper gives the viewer's zone and its label.
      window.alert(`Too early to join -- this session starts at ${formatDateTimeIn(startsAt, viewerTimeZone(), true)}.`);
      return;
    }
    if (state === "ended") {
      window.alert("This session has ended.");
      return;
    }
    if (!isHost && userName && userEmail) {
      const confirmed = window.confirm(`Join as ${userName} (${userEmail})?`);
      if (!confirmed) return;
    }
    window.open(joinUrl, "_blank", "noreferrer");
  }

  return (
    <button type="button" className={className} onClick={handleClick}>
      {label}
    </button>
  );
}
