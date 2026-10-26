# nehn-043 — Feedback tracker for the next review (design)

**Source:** `docs/delivery/CONSOLIDATED_REVIEW_ENHANCEMENT_BACKLOG.md` `nehn-043` (PDF action 25, §27 L812-828;
`MEETING_TRANSCRIPT_REQUEST`, `UNVERIFIED` backlog). Dependency: the backlog itself (on main). Decision: `DEC-SCOPE-288`. **Documentation only. No code.**

## Intent

Give the client one page to walk through at the next review: what was asked for, what is done, what is waiting, and what the
client has to supply or decide. Today that information is spread across the backlog, the decision register and git history.

## Acceptance criteria (from the backlog)

- AC1 Every PDF action item (1–25) appears, with a status.
- AC2 Every backlog item (`nehn-001` … `nehn-043`) appears, with a status.
- AC3 Each row names the client inputs it still needs.
- AC4 Columns: ID, area, item, type (enhancement / bug / client dependency), status, owner, target, client input needed.
- AC5 No credentials and no internal-only findings (security exposure detail, file paths, line numbers).

## Builder's defaults (owner pre-authorised recommended answers; `NEEDS_CONFIRMATION`)

- **F1 Format.** `docs/delivery/FEEDBACK_TRACKER.md` is the source of truth; `docs/delivery/FEEDBACK_TRACKER.csv` carries the same
  item rows for Excel. No `.xlsx` binary in the repo (not diffable); the CSV opens in Excel directly.
- **F2 Audience.** Client-facing plain language. Rows say *what* a security item fixes ("private files are no longer
  reachable without signing in"), never *how* it could be exploited. No source paths, line numbers or secrets.
- **F3 Status vocabulary.** `Done`, `Done — confirm defaults` (built using recommended answers the client has not yet
  confirmed), `Superseded` (delivered by other work, named in the row), `Partly done`, `Ready to start` (all dependencies met),
  `Waiting — dependency`, `Waiting — client input`, `Waiting — decision`.
- **F4 Status evidence.** A row is Done only when its merge is on `origin/main` (merge commit cited in the snapshot line).
  Status is a snapshot, refreshed by hand before each review.
- **F5 Target.** The backlog's §6.5 wave (0–4) plus a "next review" flag. No calendar dates: none are recorded
  (`NEEDS_CONFIRMATION`).
- **F6 Owner.** `Dev`, `Client`, or `Dev + Client`, as in the PDF's action-item table.
- **F7 Extra sections.** Client inputs (§7) and open decisions (§8) get their own tables with IDs `CI-nn` / `OD-nn`, so
  "pending items" are visible, and a "confirm at the review" list collects the recommended answers built into Done items.

## Non-goals

No code, no app page, no change to the backlog or the decision register beyond one DEC entry for this item. No new statuses
invented for items not yet analysed.

## Verification

A throwaway script (session scratchpad, not committed) checks AC1–AC5: all 43 IDs and 25 actions present, CSV header and row
count match the Markdown table, every CSV row equals its Markdown row, and a deny-list (`.py`, `.tsx`, `/local-files`,
`password`, `secret`, `token`, `L\d+`) finds nothing.
