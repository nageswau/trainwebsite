"use client";
import { useRef, useState } from "react";

import RecruiterCatalogueSearch from "@/components/RecruiterCatalogueSearch";
import RecruiterCatalogueValueRow from "@/components/RecruiterCatalogueValueRow";
import TelecallerContentList from "@/components/TelecallerContentList";
import { sendJson } from "@/lib/apiErrors";
import { CATALOGUE_URL, VALUE_TABS, type CatalogueValue, type ValueKind } from "@/lib/recruiterCatalogue";
import { formText } from "@/lib/telecaller";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";
import { useUrlList } from "@/lib/useUrlList";
import { toneClass, type Feedback } from "@/lib/welcomeLink";

const FEEDBACK_ID = "rec-value-create-feedback";
const NAME_ID = "rec-value-name";

// rec-002: one recruiter managed list (lead sources, industries, ...) -- an add form and the list with search, pager and loading /
// error+Retry / empty states. The manager sees inactive values too; the API decides who may write.
export default function RecruiterCatalogueValuesPanel({ kind }: { kind: ValueKind }) {
  const { label, noun } = VALUE_TABS[kind];
  const url = `${CATALOGUE_URL}/${kind}`;
  const list = useUrlList<CatalogueValue>(url, "q");
  const [busy, setBusy] = useState(false);
  const [feedback, setFeedback] = useState<Feedback | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const inFlight = useRef(false); // `busy` disables the button only after a re-render; a double click must not POST twice
  const focus = useFocusAfterRender();
  const title = noun[0].toUpperCase() + noun.slice(1);

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (inFlight.current) return;
    inFlight.current = true;
    const formEl = event.currentTarget;
    const name = formText(new FormData(formEl), "name");
    setBusy(true);
    const outcome = await sendJson(url, "POST", { name });
    inFlight.current = false;
    setBusy(false);
    if (outcome.ok) {
      setFeedback({ text: `Added ${name}.`, tone: "success" });
      formEl.reset();
      list.reload();
    } else {
      setFeedback({ text: outcome.message, tone: "error" });
    }
    focus(FEEDBACK_ID);
  }

  return (
    <>
      <form className="action-card form" onSubmit={create} aria-describedby={FEEDBACK_ID}>
        <h3>Add {noun}</h3>
        <div className="field"><label htmlFor={NAME_ID}>{title} name (required)</label><input id={NAME_ID} name="name" required maxLength={120} disabled={busy} /></div>
        <button className="btn" disabled={busy}>{busy ? "Adding…" : `Add ${noun}`}</button>
        <div id={FEEDBACK_ID} tabIndex={-1} className={feedback ? toneClass[feedback.tone] : undefined} role="status" aria-live="polite" style={{ marginTop: 8, overflowWrap: "anywhere" }}>
          {feedback?.text}
        </div>
      </form>
      <TelecallerContentList
        title={label}
        noun={label.toLowerCase()}
        list={list}
        notice={notice}
        filter={<RecruiterCatalogueSearch list={list} label={`Search ${label.toLowerCase()}`} />}
        createTargetId={NAME_ID}
        createLabel={`Add ${noun}`}
        headers={["Name", "Status"]}
      >
        {(items) => items.map((row) => <RecruiterCatalogueValueRow key={row.id} row={row} url={url} noun={title} onChanged={(text) => { setNotice(text); list.reload(); }} />)}
      </TelecallerContentList>
    </>
  );
}
