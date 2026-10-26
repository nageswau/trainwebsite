"use client";

import { DragEvent, FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import LocalTime from "@/components/LocalTime";
import { formatSize } from "@/lib/agentDocuments";
import { uploadStoredFile } from "@/lib/uploadFile";

type AssignmentRow = { id: string; title: string; due: string; submission: string; score: string | null; feedback: string | null; submission_type?: string };

// nehn-024 (DEC-SCOPE-292 F9): the `assignment_submission` upload policy (nehn-003) -- checked here first so a student gets a named
// message before anything is uploaded; the server still sniffs every file. Types come from the extension because browsers often
// leave HEIC (and sometimes Word) untyped, which the server would refuse.
const MAX_BYTES = 5 * 1024 * 1024;
const MAX_FILES = 5;
const TYPES: Record<string, string> = {
  pdf: "application/pdf",
  doc: "application/msword",
  docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  png: "image/png",
  heic: "image/heic",
};
const ACCEPT = Object.keys(TYPES).map((ext) => `.${ext}`).join(",");
const HINTS: Record<string, string> = {
  file: "Attach at least one file.",
  text: "Write your answer below.",
  text_or_file: "Write an answer, attach files, or both.",
};

function typeOf(file: File) {
  return TYPES[file.name.split(".").pop()?.toLowerCase() ?? ""];
}

function detailMessage(detail: unknown) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item: { msg?: string }) => item.msg || "Invalid input").join("; ");
  return "Unable to submit.";
}

// STU-004: "View assigned work, submit before due date." Previously a student had to
// copy an assignment's raw database reference out of the read-only table above and
// paste it into a disconnected generic form. This fetches the same data the table
// shows and lets a student submit directly against the specific assignment, with the
// correct ID wired automatically -- no manual reference entry.
export default function AssignmentSubmissionPanel({ section }: { section: "assignments" | "projects" }) {
  const router = useRouter();
  const [rows, setRows] = useState<AssignmentRow[] | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [busyLabel, setBusyLabel] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [fileError, setFileError] = useState("");
  const [message, setMessage] = useState<{ id: string; text: string; failed: boolean } | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch(`/api/v1/portal/it/student/${section}`)
      .then((res) => (res.ok ? res.json() : { rows: [] }))
      .then((data) => !cancelled && setRows(data.rows || []))
      .catch(() => !cancelled && setRows([]));
    return () => {
      cancelled = true;
    };
  }, [section]);

  function openRow(id: string) {
    setOpenId(id);
    setFiles([]);
    setFileError("");
  }

  function addFiles(picked: FileList | File[] | null) {
    const problems: string[] = [];
    const next = [...files];
    for (const file of Array.from(picked ?? [])) {
      if (!typeOf(file)) problems.push(`${file.name} is not an allowed type (PDF, Word, JPG, PNG or HEIC).`);
      else if (file.size > MAX_BYTES) problems.push(`${file.name} is larger than 5 MB.`);
      else if (file.size === 0) problems.push(`${file.name} is empty.`);
      else if (next.length >= MAX_FILES) problems.push(`You can attach up to ${MAX_FILES} files.`);
      else next.push(file);
    }
    setFiles(next);
    setFileError([...new Set(problems)].join(" "));
  }

  function drop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    addFiles(event.dataTransfer.files);
  }

  async function submit(event: FormEvent<HTMLFormElement>, assignmentId: string) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const answer = String(form.get("answer") || "");
    const fileUrl = String(form.get("file_url") || "");
    setBusyId(assignmentId);
    setMessage(null);
    const fileIds: string[] = [];
    for (const [index, file] of files.entries()) {
      setBusyLabel(`Uploading ${index + 1} of ${files.length}…`);
      try {
        fileIds.push(await uploadStoredFile(file.type ? file : new File([file], file.name, { type: typeOf(file) }), "assignment_submission"));
      } catch (error) {
        setBusyId(null);
        setMessage({ id: assignmentId, text: `${file.name}: ${error instanceof Error ? error.message : "Upload failed"}`, failed: true });
        return;
      }
    }
    setBusyLabel("Submitting…");
    const response = await fetch(`/api/v1/workflows/it/assignments/${assignmentId}/submissions`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ answer: answer || null, file_url: fileUrl || null, ...(fileIds.length ? { file_ids: fileIds } : {}) }),
    });
    const data = await response.json().catch(() => ({}));
    setBusyId(null);
    if (!response.ok) {
      setMessage({ id: assignmentId, text: detailMessage(data.detail), failed: true });
      return;
    }
    setMessage({
      id: assignmentId,
      text: data.is_late ? "Submitted -- this was after the due date and is marked late." : "Submitted on time.",
      failed: false,
    });
    setOpenId(null);
    setFiles([]);
    router.refresh();
  }

  if (rows === null) {
    return (
      <div className="action-card">
        <h3>Submit work</h3>
        <p className="muted">Loading your assignments…</p>
      </div>
    );
  }

  const pending = rows.filter((row) => row.submission === "not submitted");

  if (pending.length === 0) {
    return (
      <div className="action-card">
        <h3>Submit work</h3>
        <p className="muted">Nothing is currently pending submission.</p>
      </div>
    );
  }

  return (
    <div className="action-card">
      <h3>Submit work</h3>
      <div className="grid two" style={{ marginTop: 16 }}>
        {pending.map((row) => {
          const type = row.submission_type || "text_or_file";
          return (
            <div className="card" key={row.id}>
              <h4>{row.title}</h4>
              <p className="muted" style={{ fontSize: 13 }}>Due <LocalTime value={row.due} time label /></p>
              {openId === row.id ? (
                <form className="form" onSubmit={(event) => submit(event, row.id)}>
                  <p className="muted" style={{ margin: 0 }}>{HINTS[type] ?? HINTS.text_or_file}</p>
                  <div className="field">
                    <label htmlFor={`answer-${row.id}`}>{type === "file" ? "Note (optional)" : "Answer"}</label>
                    <textarea id={`answer-${row.id}`} name="answer" />
                  </div>
                  {type !== "text" && (
                    <>
                      <div className="field">
                        <span className="field-label">Files</span>
                        <div className="upload-drop" onDragOver={(event) => event.preventDefault()} onDrop={drop}>
                          <p>Drag files here, or</p>
                          <input id={`files-${row.id}`} className="visually-hidden" type="file" multiple accept={ACCEPT} onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
                          <label className="btn small secondary" htmlFor={`files-${row.id}`}>Choose files</label>
                          <input id={`camera-${row.id}`} className="visually-hidden" type="file" accept="image/*" capture="environment" onChange={(event) => { addFiles(event.target.files); event.target.value = ""; }} />
                          <label className="btn small secondary" htmlFor={`camera-${row.id}`}>Take a photo</label>
                        </div>
                        <p className="muted" style={{ fontSize: 13, margin: 0 }}>PDF, Word, JPG, PNG or HEIC · up to 5 MB each · up to {MAX_FILES} files</p>
                        {files.length > 0 && (
                          <ul className="upload-list">
                            {files.map((file, index) => (
                              <li key={`${file.name}-${index}`}>
                                <span>{file.name}</span>
                                <span className="muted">{formatSize(file.size)}</span>
                                <button type="button" className="btn small secondary" aria-label={`Remove ${file.name}`} disabled={busyId === row.id} onClick={() => setFiles(files.filter((_, i) => i !== index))}>Remove</button>
                              </li>
                            ))}
                          </ul>
                        )}
                        {fileError && <div className="form-error" role="alert">{fileError}</div>}
                      </div>
                      <div className="field">
                        <label htmlFor={`file-${row.id}`}>Link (optional)</label>
                        <input id={`file-${row.id}`} name="file_url" placeholder="https://" />
                      </div>
                    </>
                  )}
                  <button className="btn small" disabled={busyId === row.id}>
                    {busyId === row.id ? busyLabel : "Submit"}
                  </button>
                </form>
              ) : (
                <button className="btn small" onClick={() => openRow(row.id)}>
                  Submit this work
                </button>
              )}
              {message?.id === row.id && (
                <div className={message.failed ? "form-error" : "form-message"} role="status" aria-live="polite" style={{ marginTop: 8 }}>
                  {message.text}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
