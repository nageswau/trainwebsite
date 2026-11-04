"use client";

import { ROW_KINDS, emptyRow, parseRows, type FormRow, type RowKind } from "@/lib/recruiterCandidates";

// hrc-010 (DEC-SCOPE-383 P1): one editable list of profile rows -- education, employment or certifications. The value is the form's JSON
// text (so the hrc-003 stale guard compares strings); Add puts an empty row last and focuses nothing else; each Remove is named by row.
const FIELDSET = { display: "grid", gap: 8, border: "1px solid var(--border, #e5e7eb)", borderRadius: 8, padding: 12, margin: 0 } as const;
const GRID = { display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(12rem, 1fr))", alignItems: "start" } as const;

export default function CandidateRowsEditor({ kind, value, onChange, disabled, children }: {
  kind: RowKind; value: string; onChange: (value: string) => void; disabled?: boolean; children?: React.ReactNode;
}) {
  const { legend, noun, columns } = ROW_KINDS[kind];
  const rows = parseRows(value);
  const save = (next: FormRow[]) => onChange(JSON.stringify(next));
  const edit = (index: number, key: string, text: string) => save(rows.map((row, i) => (i === index ? { ...row, [key]: text } : row)));

  return (
    <fieldset style={FIELDSET}>
      <legend style={{ fontWeight: 600, padding: "0 4px" }}>{legend}</legend>
      {children}
      {rows.length === 0 && <p className="muted" style={{ margin: 0, fontSize: 13 }}>None added yet.</p>}
      {rows.map((row, index) => (
        <div key={index} role="group" aria-label={`${legend} ${index + 1}`} style={{ ...GRID, borderTop: index ? "1px solid var(--border, #e5e7eb)" : undefined, paddingTop: index ? 8 : 0 }}>
          {columns.map((column) => {
            const id = `cand-${kind}-${index}-${column.key}`;
            const { hint, options, required } = column;
            return (
              <div className="field" key={column.key}>
                <label htmlFor={id}>{column.label}{required ? " *" : ""}</label>
                {options ? (
                  <select id={id} value={row[column.key] ?? ""} disabled={disabled} onChange={(e) => edit(index, column.key, e.target.value)}>
                    <option value="">Not stated</option>
                    {options.map((o) => <option key={o.key} value={o.key}>{o.label}</option>)}
                  </select>
                ) : (
                  <input id={id} type={column.type} value={row[column.key] ?? ""} disabled={disabled} maxLength={column.max} min={column.min} max={column.numMax}
                    inputMode={column.type === "number" ? "numeric" : undefined} aria-describedby={hint ? `${id}-hint` : undefined}
                    aria-required={required || undefined} onChange={(e) => edit(index, column.key, e.target.value)} />
                )}
                {hint && <span id={`${id}-hint`} className="muted" style={{ fontSize: 13 }}>{hint}</span>}
              </div>
            );
          })}
          <div className="field" style={{ alignSelf: "end" }}>
            <button type="button" className="btn secondary small" disabled={disabled} onClick={() => save(rows.filter((_, i) => i !== index))}>
              Remove<span className="visually-hidden"> {noun} {index + 1}</span>
            </button>
          </div>
        </div>
      ))}
      <div>
        <button type="button" className="btn secondary small" disabled={disabled} onClick={() => save([...rows, emptyRow(kind)])}>+ Add {noun}</button>
      </div>
    </fieldset>
  );
}
