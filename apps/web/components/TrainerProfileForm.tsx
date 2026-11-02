"use client";

import { type FormEvent, useCallback, useEffect, useId, useState } from "react";

import FacultyCard from "./FacultyCard";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { type ContactRoute, OWN_PROFILE_API, type OwnProfile, parseExpertise, profileBody, studentPreview } from "@/lib/faculty";

type Notice = { text: string; failed: boolean } | null;
const VISIBILITY = [["show_photo", "photo"], ["show_bio", "bio"], ["show_office_hours", "office hours"], ["show_email", "email"], ["show_phone", "phone"]] as const;
const ROUTES: [ContactRoute, string][] = [["in_app", "In the app (the Questions page)"], ["email", "Email"], ["phone", "Phone"]];

/** itc-019 (DEC-SCOPE-346): a trainer's faculty profile -- what students see and which details stay private. `api` is the trainer's
 *  own route by default; the IT Admin passes `/it/trainers/{id}/profile`. The preview applies the same rules the API applies. */
export default function TrainerProfileForm({ api = OWN_PROFILE_API }: { api?: string }) {
  const [profile, setProfile] = useState<OwnProfile | null>(null);
  const [expertise, setExpertise] = useState("");
  const [loadFailed, setLoadFailed] = useState(false);
  const [reload, setReload] = useState(0);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Notice>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [fileKey, setFileKey] = useState(0);
  const id = useId();

  const accept = useCallback((data: OwnProfile) => {
    setProfile(data);
    setExpertise(data.expertise.join(", "));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setLoadFailed(false);
    setProfile(null);
    void sendRequest(api, { method: "GET" }).then((outcome) => {
      if (cancelled) return;
      if (outcome.ok && typeof outcome.data.trainer_id === "string") accept(outcome.data as unknown as OwnProfile);
      else setLoadFailed(true);
    });
    return () => {
      cancelled = true;
    };
  }, [api, reload, accept]);

  if (loadFailed)
    return (
      <div className="card" role="alert" style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
        <p className="form-error" style={{ margin: 0 }}>Unable to load the profile.</p>
        <button type="button" className="btn secondary small" onClick={() => setReload((n) => n + 1)}>Try again</button>
      </div>
    );
  if (!profile) return <p className="muted" aria-live="polite">Loading the profile…</p>;

  const set = <K extends keyof OwnProfile>(key: K, value: OwnProfile[K]) => setProfile({ ...profile, [key]: value });
  const draft = { ...profile, expertise: parseExpertise(expertise) };

  async function run(request: Promise<Awaited<ReturnType<typeof sendRequest>>>, success: string, onDone?: () => void) {
    setBusy(true);
    setNotice(null);
    const outcome = await request;
    setBusy(false);
    if (!outcome.ok) return setNotice({ text: outcome.message, failed: true });
    accept(outcome.data as unknown as OwnProfile);
    onDone?.();
    setNotice({ text: success, failed: false });
  }

  function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void run(sendJson(api, "PUT", profileBody(draft)), "Profile saved.");
  }

  function upload() {
    if (!photo) return setNotice({ text: "Choose a photo first.", failed: true });
    const body = new FormData();
    body.append("file", photo);
    void run(sendRequest(`${api}/photo`, { method: "PUT", body }), "Photo saved.", () => {
      setPhoto(null);
      setFileKey((n) => n + 1);
    });
  }

  return (
    <div style={{ display: "grid", gap: 16, gridTemplateColumns: "repeat(auto-fit, minmax(min(22rem, 100%), 1fr))", alignItems: "start" }}>
      <form className="card" onSubmit={save} noValidate style={{ display: "grid", gap: 14 }} aria-label={`Faculty profile of ${profile.name}`}>
        <h3 style={{ margin: 0, fontSize: 18 }}>{profile.name}</h3>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-designation`}>Designation</label>
          <input id={`${id}-designation`} maxLength={120} value={profile.designation ?? ""} placeholder="e.g. Senior Python Trainer" onChange={(e) => set("designation", e.target.value)} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-expertise`}>Expertise</label>
          <input id={`${id}-expertise`} aria-describedby={`${id}-expertise-hint`} value={expertise} placeholder="Python, Django, SQL" onChange={(e) => setExpertise(e.target.value)} />
          <small id={`${id}-expertise-hint`} className="field-help muted">Separate topics with commas (up to 12, each up to 60 characters).</small>
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-hours`}>Office hours</label>
          <input id={`${id}-hours`} maxLength={160} value={profile.office_hours ?? ""} placeholder="e.g. Mon–Fri 6–7 pm" onChange={(e) => set("office_hours", e.target.value)} />
        </div>
        <div className="field" style={{ margin: 0 }}>
          <label htmlFor={`${id}-bio`}>Bio</label>
          <textarea id={`${id}-bio`} maxLength={2000} rows={4} value={profile.bio ?? ""} onChange={(e) => set("bio", e.target.value)} />
        </div>
        <fieldset style={{ display: "grid", gap: 6, border: "1px solid var(--border, #e5e7eb)", borderRadius: 10, padding: 12 }}>
          <legend style={{ fontWeight: 800, padding: "0 6px" }}>What students can see</legend>
          <p className="muted" style={{ margin: 0, fontSize: 13 }}>Your name, designation and expertise are always shown. Email and phone come from your account{profile.account_email || profile.account_phone ? ` (${[profile.account_email, profile.account_phone].filter(Boolean).join(", ")})` : ""}.</p>
          {VISIBILITY.map(([key, label]) => (
            <label key={key} style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input type="checkbox" checked={profile[key]} onChange={(e) => set(key, e.target.checked)} />
              {`Show my ${label} to students`}
            </label>
          ))}
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-route`}>How students should contact you</label>
            <select id={`${id}-route`} value={profile.contact_route} onChange={(e) => set("contact_route", e.target.value as ContactRoute)}>
              {ROUTES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}
            </select>
          </div>
        </fieldset>
        <fieldset style={{ display: "grid", gap: 8, border: "1px solid var(--border, #e5e7eb)", borderRadius: 10, padding: 12 }}>
          <legend style={{ fontWeight: 800, padding: "0 6px" }}>Photo</legend>
          {profile.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element -- a short-lived signed link from the API
            <img src={profile.photo_url} alt={`Current photo of ${profile.name}`} width={96} height={96} style={{ width: 96, height: 96, borderRadius: "50%", objectFit: "cover" }} />
          ) : (
            <p className="muted" style={{ margin: 0, fontSize: 13 }}>No photo. Students see your initials.</p>
          )}
          <label htmlFor={`${id}-photo`}>PNG, JPEG or WebP, up to 2 MB, at least 120 × 120 px</label>
          <input key={fileKey} id={`${id}-photo`} type="file" accept="image/png,image/jpeg,image/webp" disabled={busy} onChange={(e) => setPhoto(e.target.files?.[0] ?? null)} />
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button type="button" className="btn secondary small" disabled={busy || !photo} onClick={upload}>Upload photo</button>
            {profile.photo_url && (
              <button type="button" className="btn secondary small" disabled={busy} onClick={() => void run(sendRequest(`${api}/photo`, { method: "DELETE" }), "Photo removed.")}>Remove photo</button>
            )}
          </div>
        </fieldset>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
          <button type="submit" className="btn" disabled={busy}>{busy ? "Saving…" : "Save profile"}</button>
          <span aria-live="polite">
            {notice && <span className={notice.failed ? "form-error" : "muted"} role={notice.failed ? "alert" : "status"}>{notice.text}</span>}
          </span>
        </div>
      </form>
      <section className="card" aria-labelledby={`${id}-preview`} style={{ display: "grid", gap: 10 }}>
        <h3 id={`${id}-preview`} style={{ margin: 0, fontSize: 18 }}>What students see</h3>
        <p className="muted" style={{ margin: 0, fontSize: 13 }}>Unsaved changes show here; save to publish them.</p>
        <FacultyCard faculty={studentPreview(draft)} />
      </section>
    </div>
  );
}
