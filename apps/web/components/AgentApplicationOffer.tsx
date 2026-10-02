"use client";

import { useState } from "react";
import AgentApplicationOfferForm from "./AgentApplicationOfferForm";
import { AgentApplicationDetail, OFFER_TYPE_LABELS } from "@/lib/agentApplications";
import { openDocument, statusLabel } from "@/lib/agentDocuments";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

type Props = {
  detail: AgentApplicationDetail;
  open: boolean; // the form is showing
  canOpen: boolean; // false while read-only or while another form of the detail is open
  onOpen: () => void;
  onCancel: () => void;
  onSaved: (d: AgentApplicationDetail, message: string) => void;
  onFailed: (message: string, status?: number) => void;
};

// AGN-010 (DEC-SCOPE-054): the application's offer -- the recorded offer (type in words, dates, conditions as written, the offer letter
// with its review status and a scoped download), or an empty state, plus the button that opens the form. Saving returns focus to the
// heading, cancelling to the button.
export default function AgentApplicationOffer({ detail, open, canOpen, onOpen, onCancel, onSaved, onFailed }: Props) {
  const offer = detail.offer;
  const focusAfter = useFocusAfterRender();
  const headingId = `offer-heading-${detail.id}`;
  const openId = `offer-open-${detail.id}`;
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);

  async function download(id: string) {
    setDownloading(true);
    setDownloadError(null);
    setDownloadError(await openDocument(id));
    setDownloading(false);
  }

  return (
    <section aria-labelledby={headingId}>
      <h5 id={headingId} tabIndex={-1}>
        Offer
      </h5>
      {open ? (
        <AgentApplicationOfferForm
          detail={detail}
          onSaved={(next, message) => {
            focusAfter(headingId);
            onSaved(next, message);
          }}
          onFailed={onFailed}
          onCancel={() => {
            focusAfter(openId);
            onCancel();
          }}
        />
      ) : (
        <>
          {offer ? (
            <dl className="card-stack">
              <dt>Type</dt>
              <dd>{OFFER_TYPE_LABELS[offer.type]}</dd>
              <dt>Offer date</dt>
              <dd>{offer.date}</dd>
              <dt>Deadline</dt>
              <dd>{offer.deadline ?? "—"}</dd>
              {offer.conditions && (
                <>
                  <dt>Conditions</dt>
                  <dd className="offer-conditions">{offer.conditions}</dd>
                </>
              )}
              <dt>Offer letter</dt>
              <dd>
                {offer.document ? (
                  <>
                    {offer.document.name} ({statusLabel(offer.document.verification_status)}){" "}
                    <button type="button" className="btn secondary small" aria-label={`Download ${offer.document.name}`} disabled={downloading} onClick={() => download(offer.document!.id)}>
                      {downloading ? "Preparing…" : "Download"}
                    </button>
                  </>
                ) : (
                  "Not attached"
                )}
              </dd>
            </dl>
          ) : (
            <p className="muted">No offer recorded yet.</p>
          )}
          {downloadError && (
            <p className="form-error" role="alert">
              {downloadError}
            </p>
          )}
          {canOpen && (
            <button id={openId} type="button" className="btn secondary small" onClick={onOpen}>
              {offer ? "Edit offer" : "Record offer"}
            </button>
          )}
        </>
      )}
    </section>
  );
}
