"use client";

import { type ChangeEvent, type KeyboardEvent, useEffect, useId, useRef, useState } from "react";

import { type LookupPage, optionText, type PickOption } from "@/lib/lookups";

// ENH-031 (DEC-SCOPE-039): an accessible searchable dropdown (WAI-ARIA 1.2 combobox) that only ever submits a picked value.
// Load-once mode filters `options` in the browser; server mode calls `search` (debounced; a reply for an older query is
// dropped). The chosen id travels in a hidden input under `name`, so the host form's FormData and its API are unchanged.
// Validity uses the constraint API: an unpicked required field, or text that is not a pick, blocks the form's submit and
// shows a field error. Status text uses aria-live (not role="status"): host pages already query their own status region.

export type Noun = "student" | "application" | "school" | "candidate" | "manager" | "BDM" | "organization" | "telecaller" | "counsellor" | "head" | "skill" | "recruiter";
const PLURAL: Record<Noun, string> = { student: "students", application: "applications", school: "schools", candidate: "candidates", manager: "managers", BDM: "BDMs", organization: "organizations", telecaller: "telecallers", counsellor: "counsellors", head: "heads", skill: "skills", recruiter: "recruiters" };
export const MAX_RENDERED = 50;
export const DEBOUNCE_MS = 250;

type Props = {
  label: string;
  noun: Noun;
  id?: string;
  name?: string;
  required?: boolean;
  disabled?: boolean;
  options?: PickOption[];
  search?: (q: string, signal: AbortSignal) => Promise<LookupPage>;
  minChars?: number;
  onChange?: (option: PickOption | null) => void;
  /** bdm-001 QA-02: an editor's current value, already picked (shown, submitted and valid without typing). */
  initial?: PickOption | null;
};

export function filterOptions(options: PickOption[], text: string): LookupPage {
  const needle = text.trim().toLowerCase();
  const matches = needle ? options.filter((option) => optionText(option).toLowerCase().includes(needle)) : options;
  return { items: matches.slice(0, MAX_RENDERED), truncated: matches.length > MAX_RENDERED };
}

export default function SearchableSelect({ label, noun, id, name, required = false, disabled = false, options, search, minChars = 0, onChange, initial = null }: Props) {
  const autoId = useId();
  const inputId = id ?? `combo-${autoId}`;
  // aria-controls/aria-describedby are space-separated id lists, so the ids they point at must not contain spaces
  // (ActionForm ids are "<spec title>-<field>", e.g. "Create visa case-application_id").
  const baseId = inputId.replace(/\s+/g, "-");
  const listId = `${baseId}-list`;
  const statusId = `${baseId}-status`;
  const errorId = `${baseId}-error`;
  const inputRef = useRef<HTMLInputElement>(null);
  // Hosts often pass inline functions; refs keep a re-render from restarting the search or firing stale callbacks.
  const searchRef = useRef(search);
  searchRef.current = search;
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;
  const serverMode = search !== undefined;

  const [text, setText] = useState(() => (initial ? optionText(initial) : ""));
  const [selected, setSelected] = useState<PickOption | null>(initial);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const [remote, setRemote] = useState<LookupPage | null>(null);
  const [loadState, setLoadState] = useState<"idle" | "loading" | "failed">("idle");
  const [retries, setRetries] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const query = selected ? "" : text.trim();
  const tooShort = serverMode && query.length < minChars;
  const page: LookupPage | null = serverMode ? (tooShort ? null : remote) : filterOptions(options ?? [], query);
  const items = page?.items ?? [];
  const invalidMessage = `Choose ${noun === "application" ? "an" : "a"} ${noun} from the list.`;
  const invalid = !selected && (required || text.trim() !== "");

  useEffect(() => {
    inputRef.current?.setCustomValidity(invalid ? invalidMessage : "");
  }, [invalid, invalidMessage]);

  useEffect(() => {
    if (!serverMode || !open || tooShort) return;
    const controller = new AbortController();
    const timer = setTimeout(() => {
      setLoadState("loading");
      searchRef.current!(query, controller.signal)
        .then((result) => {
          if (controller.signal.aborted) return;
          setRemote(result);
          setLoadState("idle");
        })
        .catch(() => {
          if (!controller.signal.aborted) setLoadState("failed");
        });
    }, DEBOUNCE_MS);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [serverMode, open, tooShort, query, retries]);

  useEffect(() => {
    const form = inputRef.current?.form;
    if (!form) return;
    const onReset = () => {
      setText("");
      setSelected(null);
      setError(null);
      setOpen(false);
      onChangeRef.current?.(null);
    };
    form.addEventListener("reset", onReset);
    return () => form.removeEventListener("reset", onReset);
  }, []);

  function pick(option: PickOption) {
    setSelected(option);
    setText(optionText(option));
    setOpen(false);
    setActive(-1);
    setError(null);
    onChangeRef.current?.(option);
  }

  function edit(event: ChangeEvent<HTMLInputElement>) {
    setText(event.target.value);
    // The previous search's results no longer match the text; never let one be picked for the new text.
    if (serverMode) setRemote(null);
    setOpen(true);
    setActive(-1);
    setError(null);
    if (selected) {
      setSelected(null);
      onChangeRef.current?.(null);
    }
  }

  function keyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setOpen(true);
      setActive((index) => Math.min(index + 1, items.length - 1));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => Math.max(index - 1, 0));
    } else if (event.key === "Enter" && open && items[active]) {
      event.preventDefault();
      pick(items[active]);
    } else if (event.key === "Escape" && open) {
      event.preventDefault();
      setOpen(false);
      setActive(-1);
    }
  }

  let status = "";
  if (open && !selected) {
    if (tooShort) status = `Type at least ${minChars} characters.`;
    else if (serverMode && loadState === "loading") status = "Loading…";
    else if (serverMode && loadState === "failed") status = `Could not load the ${PLURAL[noun]}.`;
    else if (page && items.length === 0) status = `No matching ${PLURAL[noun]}.`;
    else if (page?.truncated) status = "Keep typing to narrow the list.";
  }
  const showList = open && items.length > 0;

  return (
    <div className="field combo">
      <label htmlFor={inputId}>{label}</label>
      {/* The input and its list share a positioned box, so the list opens directly under the input (.field is a grid). */}
      <div className="combo-control">
      <input
        ref={inputRef}
        id={inputId}
        type="text"
        role="combobox"
        autoComplete="off"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList && active >= 0 ? `${listId}-${active}` : undefined}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${errorId} ${statusId}` : statusId}
        value={text}
        disabled={disabled}
        onChange={edit}
        onKeyDown={keyDown}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          setOpen(false);
          setActive(-1);
        }}
        onInvalid={(event) => {
          event.preventDefault();
          setError(invalidMessage);
          event.currentTarget.focus();
        }}
      />
      {name && <input type="hidden" name={name} value={selected?.id ?? ""} />}
      <ul id={listId} role="listbox" aria-label={label} className="combo-list" hidden={!showList}>
        {items.map((option, index) => (
          <li
            key={option.id}
            id={`${listId}-${index}`}
            role="option"
            aria-selected={index === active}
            data-value={option.id}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => pick(option)}
          >
            {optionText(option)}
          </li>
        ))}
      </ul>
      </div>
      {error && <p id={errorId} className="form-error">{error}</p>}
      <p id={statusId} aria-live="polite" className="muted combo-status">{status}</p>
      {serverMode && loadState === "failed" && (
        <button
          type="button"
          className="btn ghost small"
          onClick={() => {
            setOpen(true);
            setRetries((count) => count + 1);
            inputRef.current?.focus();
          }}
        >
          Retry
        </button>
      )}
    </div>
  );
}
