"use client";

import { useEffect, useState } from "react";
import type { LiveSessionInfo } from "@/lib/types";
import JoinSessionButton from "./JoinSessionButton";

const PROVIDER_LABEL: Record<string, string> = {
  zoho_meeting: "Zoho Meeting",
  google_meet: "Google Meet",
  manual: "Meeting link",
};

function formatWhen(iso: string) {
  try {
    return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return iso;
  }
}

// STU-003/TRN-003: "Student joins from dashboard at session time" / "Trainer views/joins
// upcoming session." The backend already scopes GET /communications/it/live-sessions to
// the caller's own batches (enrolled, for a student; assigned, for a trainer) and returns
// host_url only to trainer/admin roles -- this only renders it, preferring the host link
// when present (transparently correct for both roles, since a student's host_url is
// always null). Previously this data existed only as an unclickable text string inside a
// generic panel; this is the actual "join" UI. `upcomingOnly` scopes it to a dashboard
// widget (soonest-first, sessions not yet concluded) rather than the full session history.
export default function LiveClassesPanel({ title = "Live classes", upcomingOnly = false, userName, userEmail }: { title?: string; upcomingOnly?: boolean; userName?: string; userEmail?: string }) {
  const [sessions, setSessions] = useState<LiveSessionInfo[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/communications/it/live-sessions")
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => !cancelled && setSessions(data))
      .catch(() => !cancelled && setSessions([]));
    return () => {
      cancelled = true;
    };
  }, []);

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
          return (
          <div className="card" key={session.id}>
            <span className="badge">{session.batch}</span>
            <h4 style={{ marginTop: 10 }}>{session.title}</h4>
            <p className="muted" style={{ fontSize: 13 }}>{formatWhen(session.starts_at)}</p>
            <p className="muted" style={{ fontSize: 13 }}>{PROVIDER_LABEL[session.provider] || session.provider}</p>
            <JoinSessionButton
              joinUrl={joinUrl}
              startsAt={session.starts_at}
              endsAt={session.ends_at}
              isHost={Boolean(session.host_url)}
              userName={userName}
              userEmail={userEmail}
              label="Join class"
            />
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
