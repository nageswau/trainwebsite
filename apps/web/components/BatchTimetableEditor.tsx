"use client";

import { type FormEvent, useCallback, useEffect, useId, useState } from "react";

import TimetableCalendar from "@/components/TimetableCalendar";
import { sendJson, sendRequest } from "@/lib/apiErrors";
import { DAYS, EMPTY_SLOT, type Slot, slotBody, type SlotInput, slotInput, slotsUrl } from "@/lib/timetable";

type BatchOption = { id: string; name: string; program: string };

/** itc-020 (DEC-SCOPE-344): the IT Admin's Timetable page -- pick a batch, keep its weekly slots, and see (and cancel) the classes they
 *  produce. Every rule (overlaps, rooms, links) is the API's; its refusal is shown next to the form. */
export default function AdminTimetablePanel() {
  const [batches, setBatches] = useState<BatchOption[] | null>(null);
  const [batchId, setBatchId] = useState("");
  const [loadError, setLoadError] = useState("");
  const [refreshKey, setRefreshKey] = useState(0);
  const id = useId();

  function choose(value: string) {
    setBatchId(value);
    const url = new URL(window.location.href);
    if (value) url.searchParams.set("batch", value);
    else url.searchParams.delete("batch");
    window.history.replaceState(window.history.state, "", url);
  }

  useEffect(() => {
    let cancelled = false;
    void sendRequest("/api/v1/admin/batches", { method: "GET" }).then((outcome) => {
      if (cancelled) return;
      const rows = outcome.ok && Array.isArray(outcome.data) ? (outcome.data as BatchOption[]) : null;
      if (!rows) return setLoadError(outcome.ok ? "Unable to load batches." : outcome.message);
      setBatches(rows);
      const chosen = new URLSearchParams(window.location.search).get("batch"); // browser QA-04: a refresh keeps the chosen batch
      if (chosen && rows.some((b) => b.id === chosen)) setBatchId(chosen);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div style={{ display: "grid", gap: 16 }}>
      <section className="card" aria-labelledby={`${id}-slots`} style={{ display: "grid", gap: 12 }}>
        <h3 id={`${id}-slots`} style={{ margin: 0, fontSize: 18 }}>Weekly slots</h3>
        <div className="field" style={{ margin: 0, maxWidth: 420 }}>
          <label htmlFor={`${id}-batch`}>Batch</label>
          <select id={`${id}-batch`} value={batchId} disabled={!batches} onChange={(e) => choose(e.target.value)}>
            <option value="">{batches ? "Choose a batch" : "Loading batches…"}</option>
            {batches?.map((b) => <option key={b.id} value={b.id}>{b.name} — {b.program}</option>)}
          </select>
        </div>
        {loadError && <p className="form-error" role="alert" style={{ margin: 0 }}>{loadError}</p>}
        {batches && !batches.length && <p className="muted" style={{ margin: 0 }}>No batches yet. Create one under Batches first.</p>}
        {batchId && <BatchTimetableEditor key={batchId} batchId={batchId} onChanged={() => setRefreshKey((n) => n + 1)} />}
      </section>
      <TimetableCalendar batchId={batchId || undefined} refreshKey={refreshKey} />
    </div>
  );
}

function BatchTimetableEditor({ batchId, onChanged }: { batchId: string; onChanged: () => void }) {
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [listError, setListError] = useState("");
  const [form, setForm] = useState<SlotInput>(EMPTY_SLOT);
  const [editing, setEditing] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const id = useId();

  const load = useCallback(async () => {
    const outcome = await sendRequest(slotsUrl(batchId), { method: "GET" });
    const items = outcome.ok && Array.isArray(outcome.data.items) ? (outcome.data.items as Slot[]) : null;
    if (!items) return setListError(outcome.ok ? "Unable to load the slots." : outcome.message);
    setListError("");
    setSlots(items);
  }, [batchId]);

  useEffect(() => {
    void load();
  }, [load]);

  function reset() {
    setForm(EMPTY_SLOT);
    setEditing(null);
    setError("");
  }

  async function save(event: FormEvent) {
    event.preventDefault();
    if (form.end_time <= form.start_time) return setError("The class must end after it starts.");
    if (form.mode === "offline" && !form.room.trim()) return setError("An in-person class needs a room.");
    if (form.meeting_url.trim() && !/^https?:\/\/\S+$/.test(form.meeting_url.trim())) return setError("The class link must start with https:// (or http://) and have no spaces."); // QA-02
    setBusy(true);
    setError("");
    setMessage("");
    const outcome = await sendJson(editing ? `${slotsUrl(batchId)}/${editing}` : slotsUrl(batchId), editing ? "PUT" : "POST", slotBody(form));
    setBusy(false);
    if (!outcome.ok) return setError(outcome.message);
    setMessage(editing ? "Slot updated." : "Slot added.");
    reset();
    await load();
    onChanged();
  }

  async function remove(slot: Slot) {
    setBusy(true);
    setMessage("");
    const outcome = await sendRequest(`${slotsUrl(batchId)}/${slot.id}`, { method: "DELETE" });
    setBusy(false);
    setConfirmDelete(null);
    if (!outcome.ok) return setListError(outcome.message);
    if (editing === slot.id) reset();
    setMessage("Slot removed.");
    await load();
    onChanged();
  }

  const set = <K extends keyof SlotInput>(key: K, value: SlotInput[K]) => setForm((f) => ({ ...f, [key]: value }));
  return (
    <div style={{ display: "grid", gap: 12 }}>
      {listError && <p className="form-error" role="alert" style={{ margin: 0 }}>{listError}</p>}
      {!slots && !listError && <p className="muted" style={{ margin: 0 }}>Loading slots…</p>}
      {slots && !slots.length && <p className="muted" style={{ margin: 0 }}>No weekly slots yet. Add the first one below.</p>}
      {slots && slots.length > 0 && (
        <div style={{ overflowX: "auto" }}>
          <table className="table compact stack">
            <caption className="sr-only">Weekly slots of this batch</caption>
            <thead>
              <tr><th scope="col">Day</th><th scope="col">Time</th><th scope="col">Where</th><th scope="col">Topic</th><th scope="col"><span className="sr-only">Actions</span></th></tr>
            </thead>
            <tbody>
              {slots.map((slot) => (
                <tr key={slot.id}>
                  <td data-label="Day">{slot.day}</td>
                  <td data-label="Time">{slot.start_time}–{slot.end_time}</td>
                  <td data-label="Where" style={{ overflowWrap: "anywhere" }}>{slot.mode === "offline" ? `In person · ${slot.room}` : slot.meeting_url ? "Online · link set" : "Online · no link yet"}</td>
                  <td data-label="Topic" style={{ overflowWrap: "anywhere" }}>{slot.topic || <span className="muted">—</span>}</td>
                  <td data-label="Actions">
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {confirmDelete === slot.id ? (
                        <>
                          <button type="button" className="btn small" disabled={busy} onClick={() => void remove(slot)}>Confirm remove</button>
                          <button type="button" className="btn secondary small" disabled={busy} onClick={() => setConfirmDelete(null)}>Keep</button>
                        </>
                      ) : (
                        <>
                          <button type="button" className="btn secondary small" disabled={busy} aria-label={`Edit ${slot.day} ${slot.start_time}`}
                            onClick={() => { setEditing(slot.id); setForm(slotInput(slot)); setError(""); setMessage(""); }}>Edit</button>
                          <button type="button" className="btn secondary small" disabled={busy} aria-label={`Remove ${slot.day} ${slot.start_time}`}
                            onClick={() => setConfirmDelete(slot.id)}>Remove</button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <form onSubmit={save} noValidate className="action-card" style={{ display: "grid", gap: 10 }} aria-labelledby={`${id}-form`}>
        <h4 id={`${id}-form`} style={{ margin: 0, fontSize: 15 }}>{editing ? "Edit slot" : "Add a weekly slot"}</h4>
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))" }}>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-day`}>Day</label>
            <select id={`${id}-day`} value={form.weekday} disabled={busy} onChange={(e) => set("weekday", Number(e.target.value))}>
              {DAYS.map((day, i) => <option key={day} value={i}>{day}</option>)}
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-start`}>Starts (IST)</label>
            <input id={`${id}-start`} type="time" required value={form.start_time} disabled={busy} onChange={(e) => set("start_time", e.target.value)} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-end`}>Ends (IST)</label>
            <input id={`${id}-end`} type="time" required value={form.end_time} disabled={busy} onChange={(e) => set("end_time", e.target.value)} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-mode`}>Mode</label>
            <select id={`${id}-mode`} value={form.mode} disabled={busy} onChange={(e) => set("mode", e.target.value as SlotInput["mode"])}>
              <option value="online">Online</option>
              <option value="offline">In person</option>
            </select>
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-room`}>Room{form.mode === "offline" ? " (required)" : " (optional)"}</label>
            <input id={`${id}-room`} maxLength={120} value={form.room} disabled={busy} onChange={(e) => set("room", e.target.value)} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-link`}>Class link (optional)</label>
            <input id={`${id}-link`} type="url" inputMode="url" maxLength={500} placeholder="https://" value={form.meeting_url} disabled={busy} onChange={(e) => set("meeting_url", e.target.value)} />
          </div>
          <div className="field" style={{ margin: 0 }}>
            <label htmlFor={`${id}-topic`}>Topic (optional)</label>
            <input id={`${id}-topic`} maxLength={160} value={form.topic} disabled={busy} onChange={(e) => set("topic", e.target.value)} />
          </div>
        </div>
        {error && <p className="form-error" role="alert" style={{ margin: 0, fontSize: 13 }}>{error}</p>}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
          <button type="submit" className="btn small" disabled={busy}>{busy ? "Saving…" : editing ? "Save slot" : "Add slot"}</button>
          {editing && <button type="button" className="btn secondary small" disabled={busy} onClick={reset}>Cancel edit</button>}
          <span role="status" className="muted" style={{ fontSize: 13 }}>{message}</span>
        </div>
      </form>
    </div>
  );
}
