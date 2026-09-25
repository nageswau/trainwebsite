"use client";

import { useId, useState } from "react";

import type { UnsentText } from "@/lib/activityFeedback";

// ENH-018 QA-018-03: the activity already had feedback (another device or tab saved it first), so what this coordinator typed
// was not saved. Stored feedback stays immutable; their text is shown read-only, in memory only, with a way to copy it.
export default function UnsentFeedbackNote({ unsent, onDismiss }: { unsent: UnsentText; onDismiss: () => void }) {
  const id = useId();
  const [copied, setCopied] = useState<"yes" | "failed" | null>(null);
  const lines = [
    unsent.trainer_name && `Trainer / Counsellor: ${unsent.trainer_name}`,
    `Feedback: ${unsent.feedback}`,
    unsent.suggestions && `Suggestions: ${unsent.suggestions}`,
  ].filter(Boolean);

  async function copy() {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      setCopied("yes");
    } catch {
      setCopied("failed");
    }
  }

  return (
    <div className="action-card" role="group" aria-label="Your unsent text">
      <p className="field-hint">Feedback for this activity was already saved, so the text below was not. Copy it if you need it.</p>
      {unsent.trainer_name && <p style={{ margin: 0 }}>{`Trainer / Counsellor: ${unsent.trainer_name}`}</p>}
      <div className="field">
        <label htmlFor={`${id}-feedback`}>Your unsent feedback</label>
        <textarea id={`${id}-feedback`} readOnly value={unsent.feedback} />
      </div>
      {unsent.suggestions && (
        <div className="field">
          <label htmlFor={`${id}-suggestions`}>Your unsent suggestions</label>
          <textarea id={`${id}-suggestions`} readOnly value={unsent.suggestions} />
        </div>
      )}
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
        <button type="button" className="btn small" onClick={() => void copy()}>Copy text</button>
        <button type="button" className="btn secondary small" onClick={onDismiss}>Dismiss</button>
        <span role="status">{copied === "yes" ? "Copied." : copied === "failed" ? "Could not copy; select the text and copy it." : ""}</span>
      </div>
    </div>
  );
}
