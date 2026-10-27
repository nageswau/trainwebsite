"use client";

import { useEffect, useState } from "react";
import type { LiveSessionInfo } from "@/lib/types";
import JoinSessionButton from "./JoinSessionButton";
import LocalTime from "@/components/LocalTime";
import { paymentLock, type PaymentLock } from "@/lib/studentAccess";
import LockedFeatureCard from "./LockedFeatureCard";

const PROVIDER_LABEL: Record<string, string> = {
  zoho_meeting: "Zoho Meeting",
  google_meet: "Google Meet",
  manual: "Meeting link",
};

// STU-003/TRN-003: "Student joins from dashboard at session time" / "Trainer views/joins
// upcoming session." The backend already scopes GET /communications/it/live-sessions to
// the caller's own batches (enrolled, for a student; assigned, for a trainer) and returns
// host_url only to trainer/admin roles -- this only renders it, preferring the host link
// when present (transparently correct for both roles, since a student's host_url is
// always null). Previously this data existed only as an unclickable text string inside a
// generic panel; this is the actual "join" UI. `upcomingOnly` scopes it to a dashboard
// widget (soonest-first, sessions not yet concluded) rather than the full session history.
// nehn-018 (DEC-SCOPE-303): `lock` -- the page already knows live classes are locked, so nothing is fetched (QA18-02).
export default function LiveClassesPanel({ title = "Live classes", upcomingOnly = false, userName, userEmail, lock: knownLock = null }: { title?: string; upcomingOnly?: boolean; userName?: string; userEmail?: string; lock?: PaymentLock | null }) {
  const [sessions, setSessions] = useState<LiveSessionInfo[] | null>(null);
  const [lock, setLock] = useState<PaymentLock | null>(knownLock);

  useEffect(() => {
    if (knownLock) return;
    let cancelled = false;
    fetch("/api/v1/communications/it/live-sessions")
      .then(async (res) => {
        if (res.ok) return res.json();
        // nehn-018 (DEC-SCOPE-303): a student whose payment state does not unlock live classes gets the lock, not an empty list.
        const found = paymentLock((await res.json().catch(() => ({}))).detail);
        if (found && !cancelled) setLock(found);
        return [];
      })
      .then((data) => !cancelled && setSessions(data))
      .catch(() => !cancelled && setSessions([]));
    return () => {
      cancelled = true;
    };
  }, [knownLock]);

  if (lock) return <LockedFeatureCard lock={lock} />;

  if (sessions === null) {
    return (
      <div className="action-card">
        <h3>{title}</h3>
        <p className="muted">Loading your scheduled sessions…</p>
      </div>
    );
  }

  const visible = upcomingOnly
    ? sessions
        .filter((session) => new Date(session.ends_at || session.starts_at).getTime() >= Date.now())
        .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
    : sessions;

  if (visible.length === 0) {
    return (
      <div className="action-card">
        <h3>{title}</h3>
        <p className="muted">{upcomingOnly ? "No upcoming sessions are scheduled across your batches." : "No live classes have been scheduled for your batch yet."}</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>{title}</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {visible.map((session) => {
          const joinUrl = session.host_url || session.meeting_url;
          const cancelled = session.status === "cancelled";
          return (
          <div className="card" key={session.id}>
            <span className="badge">{session.batch}</span>
            {/* nehn-029: a cancelled class says so with the trainer's reason, and offers nothing to join. */}
            {cancelled && <span className="status error" style={{ marginLeft: 8 }}>Cancelled</span>}
            <h4 style={{ marginTop: 10 }}>{session.title}</h4>
            <p className="muted" style={{ fontSize: 13 }}><LocalTime value={session.starts_at} time label /></p>
            <p className="muted" style={{ fontSize: 13 }}>{PROVIDER_LABEL[session.provider] || session.provider}</p>
            {cancelled ? <p style={{ fontSize: 13 }}><strong>Reason:</strong> {session.cancel_reason || "Not given"}</p> : <JoinSessionButton
              joinUrl={joinUrl}
              startsAt={session.starts_at}
              endsAt={session.ends_at}
              isHost={Boolean(session.host_url)}
              userName={userName}
              userEmail={userEmail}
              label="Join class"
            />}
            <p className="muted" style={{ fontSize: 13, marginTop: 8 }}>
              {session.recording_url ? (
                <a href={session.recording_url} target="_blank" rel="noreferrer">Watch recording</a>
              ) : (
                "Recording not available for this session."
              )}
            </p>
          </div>
          );
        })}
      </div>
    </div>
  );
}
