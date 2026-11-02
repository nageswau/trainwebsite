"use client";

import { useEffect, useId, useState } from "react";

import TrainerProfileForm from "./TrainerProfileForm";
import { trainerProfileApi } from "@/lib/faculty";

type Trainer = { id: string; name: string };

/** itc-019 (DEC-SCOPE-345, F6): the IT Admin edits any IT trainer's faculty profile from the Trainers page. */
export default function AdminFacultyProfiles() {
  const [trainers, setTrainers] = useState<Trainer[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [chosen, setChosen] = useState("");
  const id = useId();

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/admin/users?role=trainer&division=it")
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: Trainer[]) => !cancelled && setTrainers(data.map((t) => ({ id: t.id, name: t.name }))))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <section aria-labelledby={`${id}-title`} style={{ display: "grid", gap: 12, marginBottom: 16 }}>
      <div className="card" style={{ display: "grid", gap: 8 }}>
        <h3 id={`${id}-title`} style={{ margin: 0, fontSize: 18 }}>Faculty profiles</h3>
        <p className="muted" style={{ margin: 0, fontSize: 14 }}>Edit what students see about a trainer. Trainers can also edit their own profile.</p>
        {failed ? (
          <p className="form-error" role="alert" style={{ margin: 0 }}>Unable to load the trainers.</p>
        ) : trainers === null ? (
          <p className="muted" style={{ margin: 0 }}>Loading trainers…</p>
        ) : trainers.length === 0 ? (
          <p className="muted" style={{ margin: 0 }}>No IT trainers yet. Create a trainer user first.</p>
        ) : (
          <div className="field" style={{ margin: 0, maxWidth: "24rem" }}>
            <label htmlFor={`${id}-trainer`}>Trainer</label>
            <select id={`${id}-trainer`} value={chosen} onChange={(e) => setChosen(e.target.value)}>
              <option value="">Choose a trainer</option>
              {trainers.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
          </div>
        )}
      </div>
      {chosen && <TrainerProfileForm key={chosen} api={trainerProfileApi(chosen)} />}
    </section>
  );
}
