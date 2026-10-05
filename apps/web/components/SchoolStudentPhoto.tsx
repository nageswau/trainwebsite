"use client";

import { ChangeEvent, useEffect, useState } from "react";
import { detailMessage } from "@/lib/schoolStudents";

const MAX_BYTES = 2 * 1024 * 1024;
const TYPES = ["image/jpeg", "image/png"];

function initials(name: string) {
  return name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]!.toUpperCase()).join("");
}

// ENH-025: the student photo. Served only through GET .../photo (scoped exactly like the rest of the record, never a
// public URL); a missing or broken image always falls back to initials, never an error. Coordinator-only controls
// when `canEdit`. The client-side type/size check is for fast feedback only -- the server re-validates.
export default function SchoolStudentPhoto({ studentId, name, hasPhoto, canEdit }: { studentId: string; name: string; hasPhoto: boolean; canEdit: boolean }) {
  const [present, setPresent] = useState(hasPhoto);
  const [broken, setBroken] = useState(false);
  // QA2-01: an <img> in the server HTML can fail before hydration, and then onError never runs (the user saw a
  // broken-image icon). So the server HTML carries the placeholder and the image is only created once this is live.
  const [live, setLive] = useState(false);
  useEffect(() => setLive(true), []);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);
  const url = `/api/v1/school/students/${studentId}/photo`;

  async function upload(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];
    if (!file) return;
    // QA2-05: the same wording the server uses for the same problem.
    if (!TYPES.includes(file.type)) {
      setMessage({ text: "Photo must be a JPEG or PNG image", failed: true });
      return;
    }
    if (file.size > MAX_BYTES) {
      setMessage({ text: "Photo must be at most 2 MB", failed: true });
      return;
    }
    setBusy("upload");
    setMessage(null);
    const body = new FormData();
    body.append("file", file);
    const response = await fetch(url, { method: "PUT", body }).catch(() => null);
    setBusy(null);
    input.value = "";
    if (!response?.ok) {
      const data = response ? await response.json().catch(() => ({})) : {};
      setMessage({ text: detailMessage(data.detail, "Upload failed; please try again."), failed: true });
      return;
    }
    setPresent(true);
    setBroken(false);
    setVersion((v) => v + 1);
    setMessage({ text: "Photo saved.", failed: false });
  }

  async function remove() {
    setBusy("remove");
    setMessage(null);
    const response = await fetch(url, { method: "DELETE" }).catch(() => null);
    setBusy(null);
    setConfirming(false);
    if (!response?.ok) {
      setMessage({ text: "Could not remove the photo; please try again.", failed: true });
      return;
    }
    setPresent(false);
    setMessage({ text: "Photo removed.", failed: false });
  }

  return (
    <div className="student-photo-block">
      {live && present && !broken ? (
        // eslint-disable-next-line @next/next/no-img-element -- an authenticated, uncacheable API image; next/image would proxy and cache it
        <img className="student-photo" src={`${url}?v=${version}`} alt={`Photo of ${name}`} width={96} height={96} onError={() => setBroken(true)} />
      ) : (
        <span className="student-photo" role="img" aria-label={`No photo for ${name}`}>{initials(name)}</span>
      )}
      {canEdit && (
        <div className="field" style={{ marginTop: 8 }}>
          <label htmlFor={`photo-${studentId}`}>{present ? "Replace photo" : "Upload a photo"} (JPEG or PNG, up to 2 MB)</label>
          <input id={`photo-${studentId}`} type="file" accept="image/jpeg,image/png" onChange={upload} disabled={busy !== null} />
          {busy === "upload" && <span className="muted" aria-live="polite">Uploading…</span>}
          {present && !confirming && (
            <button type="button" className="btn ghost small" onClick={() => setConfirming(true)} disabled={busy !== null}>Remove photo</button>
          )}
          {confirming && (
            <div style={{ display: "flex", gap: 8 }}>
              <button type="button" className="btn small" onClick={remove} disabled={busy !== null}>{busy === "remove" ? "Removing…" : "Confirm remove"}</button>
              <button type="button" className="btn secondary small" onClick={() => setConfirming(false)}>Cancel</button>
            </div>
          )}
        </div>
      )}
      {message && (message.failed ? <div className="form-error" role="alert">{message.text}</div> : <div className="form-message" role="status" aria-live="polite">{message.text}</div>)}
    </div>
  );
}
