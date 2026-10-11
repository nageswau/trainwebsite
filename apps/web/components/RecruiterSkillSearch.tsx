"use client";

import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";

import { skillSearchHref } from "@/lib/recruiterDashboard";

// rec-032 (EVID-018 S2-§9, DB10): "Find Candidates by Skill" -- opens rec-013's search with the skills; its facets show the experience,
// location and availability breakdown.
export default function RecruiterSkillSearch() {
  const router = useRouter();
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const href = skillSearchHref(text);
    if (!href) {
      setError("Type at least one skill.");
      return;
    }
    setError("");
    router.push(href);
  };
  return (
    <div className="card" style={{ marginBottom: 16 }}>
      <h3 id="skill-search-title">Find Candidates by Skill</h3>
      <form className="form" onSubmit={submit} noValidate role="search" aria-labelledby="skill-search-title">
        <div className="field">
          <label htmlFor="dashboard-skill">Skill</label>
          <input
            id="dashboard-skill" value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Java, Spring Boot" maxLength={500}
            aria-invalid={error ? "true" : undefined} aria-describedby="dashboard-skill-hint" autoComplete="off"
          />
          <small id="dashboard-skill-hint" className="muted">Separate several skills with commas: candidates must have all of them.</small>
        </div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <div className="actions"><button className="btn" type="submit">Find candidates</button></div>
      </form>
    </div>
  );
}
