"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

type ProgramOption = { id: string; title: string };
type TrainerOption = { id: string; name: string };

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to create batch.";
}

// ADM-003: "Create a batch, assign a trainer, set capacity (≤20/slot)." Replaces the
// generic "type the program/trainer's raw UUID" form with real pickers -- previously an
// admin had to already know both UUIDs by heart. Capacity is capped at 20 client-side to
// match the server's own enforced limit (DEC-WF-002 / ADM-003-AC02).
export default function AdminBatchCreatePanel() {
  const router = useRouter();
  const [programs, setPrograms] = useState<ProgramOption[]>([]);
  const [trainers, setTrainers] = useState<TrainerOption[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      fetch("/api/v1/admin/programs").then((res) => (res.ok ? res.json() : [])),
      fetch("/api/v1/admin/users?role=trainer&division=it").then((res) => (res.ok ? res.json() : [])),
    ])
      .then(([programData, trainerData]: [{ id: string; title: string }[], { id: string; name: string }[]]) => {
        if (cancelled) return;
        setPrograms(programData.map((p) => ({ id: p.id, title: p.title })));
        setTrainers(trainerData.map((t) => ({ id: t.id, name: t.name })));
      })
      .catch(() => {
        if (!cancelled) {
          setPrograms([]);
          setTrainers([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    setBusy(true);
    setMessage(null);
    const form = new FormData(formElement);
    const trainerId = String(form.get("trainer_id") || "");
    const response = await fetch("/api/v1/admin/batches", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        program_id: form.get("program_id"),
        trainer_id: trainerId || null,
        name: form.get("name"),
        start_date: form.get("start_date"),
        end_date: form.get("end_date"),
        schedule: form.get("schedule"),
        timezone: form.get("timezone") || "Asia/Kolkata",
        capacity: Number(form.get("capacity")),
        mode: form.get("mode") || "Online",
      }),
    });
    const data = await response.json().catch(() => ({}));
    setBusy(false);
    if (!response.ok) {
      setMessage({ text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({ text: `Batch "${data.name}" created.`, failed: false });
    formElement.reset();
    router.refresh();
  }

  return (
    <div className="action-card">
      <h3>Create batch</h3>
      <form className="form" onSubmit={submit}>
        <div className="field">
          <label htmlFor="batch-program">Program</label>
          <select id="batch-program" name="program_id" required>
            <option value="">Select program</option>
            {programs.map((p) => (
              <option key={p.id} value={p.id}>
                {p.title}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="batch-trainer">Trainer (optional)</label>
          <select id="batch-trainer" name="trainer_id">
            <option value="">Unassigned</option>
            {trainers.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label htmlFor="batch-name">Batch name</label>
          <input id="batch-name" name="name" required />
        </div>
        <div className="field">
          <label htmlFor="batch-start">Start date</label>
          <input id="batch-start" name="start_date" type="date" required />
        </div>
        <div className="field">
          <label htmlFor="batch-end">End date</label>
          <input id="batch-end" name="end_date" type="date" required />
        </div>
        <div className="field">
          <label htmlFor="batch-schedule">Fixed schedule</label>
          <input id="batch-schedule" name="schedule" required />
        </div>
        <div className="field">
          <label htmlFor="batch-capacity">Capacity (max 20)</label>
          <input id="batch-capacity" name="capacity" type="number" min="1" max="20" defaultValue={20} required />
        </div>
        <div className="field">
          <label htmlFor="batch-mode">Mode</label>
          <select id="batch-mode" name="mode" defaultValue="Online">
            <option value="Online">Online</option>
            <option value="Offline">Offline</option>
            <option value="Hybrid">Hybrid</option>
          </select>
        </div>
        <button className="btn" disabled={busy || !programs.length}>
          {busy ? "Creating…" : "Create batch"}
        </button>
        {!programs.length && <p className="muted" style={{ fontSize: 13 }}>Create a program before creating a batch.</p>}
      </form>
      {message && (
        <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
          {message.text}
        </div>
      )}
    </div>
  );
}
