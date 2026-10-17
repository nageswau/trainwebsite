# AGN-024 — Agent signup KYC documents (PAN, Aadhaar, business licence) — design

- **Feature ID:** AGN-024 (next free after AGN-023 on `origin/main` @ 4396b4eb)
- **Decision:** DEC-SCOPE-224 · **Migration:** `0164_agent_org_kyc` · **API contract:** §12EK · **RBAC:** §2.147
- **Branch / worktree:** `feature/agn-024` in `../agn-024`
- **Status:** design approved in chat 2026-10-17; built on `feature/agn-024`. Sections marked **As built** record where the build differs from the first draft (reconciled in Task 11).
- **Evidence:** owner request + owner answers K1–K8 given in a Claude Code session on 2026-10-17 (owner confirmation recorded here; DEC-SCOPE-224 will cite it)

## 1. Purpose

When a person picks **Education agent** on the overseas self-registration form, they must upload their PAN card, Aadhaar card and business licence. An Overseas Admin or Super Admin checks each document before approving the agency. An agency cannot become active until all three documents are verified.

## 2. Owner answers (2026-10-17)

| # | Question | Answer |
|---|---|---|
| K1 | Which documents are required at signup | All three (PAN, Aadhaar, business licence) are mandatory. Signup is refused without them. |
| K2 | Document numbers | PAN number (format `ABCDE1234F`) and business licence number in full. **Aadhaar: last 4 digits only.** The full Aadhaar number is never stored. |
| K3 | Verification model | Each document is marked Verified or Rejected, and a rejection needs a reason. **Approve is blocked until all three are Verified.** |
| K4 | Existing agencies | New signups only. Existing pending, active or rejected agencies are unaffected, and an existing pending one can still be approved as today. |
| K5 | Re-upload after rejection | A pending agent can open one **Registration status** page that shows each document's status and reason, with a re-upload button for rejected documents. The rest of the portal stays blocked. |
| K6 | Notifications | The agent is emailed when a document is rejected (with the reason and a link to the status page) and when the agency is approved. |
| K7 | Super Admin UI | Super Admin gets the same Agent Approvals screen as Overseas Admin (the API already allows Super Admin). |
| K8 | File rules | PDF, JPG or PNG, **at most 5 MB per file**. The type is decided from the file's bytes and image metadata is stripped (the same approach as AGN-009). |

## 3. Current state (verified on `origin/main` @ 4396b4eb)

- `apps/web/components/RegisterForm.tsx` posts **JSON** to `POST /api/v1/auth/register`. The `account_type` select (student / agent) appears only for `division="overseas"`. Agents get an optional "Agency name" field.
- `apps/api/app/api/auth.py` `register` creates a `User` with role `agent` and calls `ensure_agent_org(..., status="pending")`, which creates an `AgentOrg` and its Master `M001`. It then sets the role assignment to `approval_status="pending"`, writes an audit row and sets auth cookies.
- `rbac.agent_denial_reason` refuses every agent route while `org.status != "active"` and returns `PENDING_MESSAGE`.
- Approvals use `POST /overseas-admin/agent-orgs/{org_id}/approve|reject|suspend|reinstate` in `admin.py`, with role in `{overseas_admin, super_admin}`. Transitions are in `agent_orgs.TRANSITIONS` and `set_org_status`.
- The UI is `AgentApprovalPanel.tsx`, mounted in `WorkflowPanel.tsx` only for `overseas_admin` on `section === "agents"`.
- The upload pattern to reuse is `services/agent_documents.py`: `read_upload` (type from bytes, EXIF strip), `store` (server-generated key) and `discard`. `read_upload` uses the global `settings.max_upload_bytes`, which is 20 MB.
- The codebase has no PAN, Aadhaar, licence or KYC fields today.
- `/local-files` is an **unauthenticated** static mount in local storage mode. KYC files must never be served through it.

## 4. Design

### 4.1 Data — migration `0164_agent_org_kyc`

New table `agent_org_kyc_documents`:

| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `org_id` | uuid FK → `agent_orgs.id` ON DELETE CASCADE | indexed |
| `doc_type` | varchar(32) | CHECK in (`pan`, `aadhaar`, `business_license`) |
| `doc_number` | varchar(64) | PAN: 10 characters, upper-cased. Aadhaar: exactly 4 digits. Licence: 3–64 characters. |
| `file_key` | varchar(255) | server-generated `agent-kyc/{uuid hex}` |
| `original_filename` | varchar(255) null | for display only; never part of a path |
| `content_type` | varchar(64) | `application/pdf`, `image/jpeg` or `image/png` |
| `file_size` | integer | |
| `status` | varchar(16) | CHECK in (`pending`, `verified`, `rejected`), default `pending` |
| `rejection_reason` | text null | required when status is `rejected`; 3–500 characters |
| `reviewed_by_user_id` | uuid FK → users null | |
| `reviewed_at` | timestamptz null | |
| `uploaded_by_user_id` | uuid FK → users | |
| `created_at` / `updated_at` | timestamptz | |

- UNIQUE (`org_id`, `doc_type`): there is one current document per type, and a re-upload replaces that row's file. Previous files are deleted from storage after the commit succeeds. History lives in the audit log, not in extra rows (YAGNI).
- New column `agent_orgs.kyc_required boolean NOT NULL DEFAULT false`. Every existing row stays `false` (K4). Self-registration sets it to `true`.

### 4.2 Signup — `POST /api/v1/auth/register`

- The endpoint accepts **either** `application/json` (unchanged, for students and the existing tests) **or** `multipart/form-data`. The multipart form carries the same fields as `RegistrationRequest` plus:
  - `pan_number`, `pan_file`
  - `aadhaar_last4`, `aadhaar_file`
  - `license_number`, `license_file`
- For `account_type=agent`, all six fields are required (K1). A JSON agent signup with no files returns **422** "PAN card, Aadhaar card and business licence are required". This means agent signup now always uses multipart.
- Validation runs in this order, and nothing is stored until every check passes:
  1. Field validation: PAN regex `^[A-Z]{5}[0-9]{4}[A-Z]$` after upper-casing; Aadhaar last 4 `^[0-9]{4}$`; licence `^[A-Za-z0-9/\-. ]{3,64}$`.
  2. Duplicate email → 409 (unchanged).
  3. Each file goes through `read_upload(file, max_bytes=5 MB)`. `read_upload` gains an optional `max_bytes` parameter; existing callers keep the default. The errors are 413 (too large), 415 (wrong type), 422 (empty file or unreadable image). Error messages name the document, for example "Aadhaar card: the file must be at most 5 MB".
- When validation passes:
  - Store the three files with prefix `agent-kyc/`.
  - Create the user, org (with `kyc_required=true`), Master, three `pending` document rows and the role assignment in **one transaction**.
  - If the commit fails, `discard` each stored key.
  - The audit row `auth.register` gains `kyc_documents: 3`. Document numbers are never written to audit metadata.
- The response is unchanged. On the web side, an agent is sent to `/overseas/agent/registration-status` instead of the dashboard.
- **As built (signup hardening):**
  - Multipart **or urlencoded** forms are accepted. A JSON agent signup returns 422 REQUIRED.
  - Before the body is parsed: **403** "Cross-site registration is not allowed" when `Origin` (else `Referer`) is present and is not the origin of `settings.frontend_url`; **411** without a valid `Content-Length`; **413** above `MAX_REGISTRATION_BYTES` (3 × 5 MB + 1 MB). A form post is a CORS-simple request, so the Origin check is the CSRF control.
  - 422 validation errors never echo the submitted input (password, PAN, licence number).
  - Number errors are 422; file errors are 413/415/422 with the document label as a prefix.
  - A concurrent signup that loses the email race on commit (`IntegrityError`) returns **409**, and the stored files are discarded.
  - OpenAPI no longer shows a request body for `/auth/register` (the body is read manually); the contract is in API §12EK.

### 4.3 Registration form — `RegisterForm.tsx`

- When "Education agent" is selected, a "Verification documents" group appears. It has three file inputs (`accept=".pdf,.jpg,.jpeg,.png"`), each paired with its number field: PAN number, Aadhaar (last 4 digits) and Business licence number.
- Helper text says "PDF, JPG or PNG, up to 5 MB each". Under the Aadhaar input it says "Only the last 4 digits are stored".
- The client checks size and extension for fast feedback only. The server stays authoritative.
- For agents the form submits `FormData`. Student submissions stay JSON.
- Accessibility: every input has a label; errors are linked with `aria-describedby`; the file-input error names the document; the layout works at 360 px width.

### 4.4 Agent registration status (pending agent)

- **API:** `GET /api/v1/agent/registration` returns `{org: {name, status, kyc_required}, documents: [{id, doc_type, doc_number_display, status, rejection_reason, original_filename, updated_at}]}`.
  - Allowed only for a user with role `agent` who is a Master of their org. It deliberately does **not** call `agent_denial_reason`, so pending and rejected agents can reach it.
  - `doc_number_display` masks the PAN as `ABCDE****F`. The Aadhaar shows as `XXXX XXXX 1234`. The licence is shown in full.
- **API:** `PUT /api/v1/agent/registration/documents/{doc_type}/file` takes multipart with `file` and an optional corrected number field. It replaces a **rejected** document only. Other cases return:
  - **409** for a pending or verified document, or when the org is not `pending`
  - **404** when the document does not belong to the caller's org
  - The status goes back to `pending`, the reason and reviewer fields are cleared, and audit `agent_kyc.reupload` is written.
  - **As built:** it is throttled to **20 re-uploads per agency per rolling 24 h** (`THROTTLE_WINDOW`, the AGN-009 audit-window pattern; first draft said 10 per hour), returning 429 with Retry-After.
- **Web:** a new page `/overseas/agent/registration-status` has three status cards (Pending review, Verified, Rejected with reason and a re-upload control) and an org status banner. **As built:** the status page has no portal navigation. The access cards for **both pending and rejected** agents link to it (`agent_denial_reason` gives a rejected org the same "pending approval" message, so a rejected agent can still open the page and see the outcome).
  - An active org redirects to the dashboard.
  - A rejected org shows "Registration rejected" with no upload controls.

### 4.5 Admin verification

- **API (router `/overseas-admin`, roles `{overseas_admin, super_admin}` via `_require_overseas_admin`):**
  - `GET /agent-orgs/{org_id}/kyc-documents` returns the list with full document numbers. Admins need these to compare against the image.
  - `GET /agent-orgs/{org_id}/kyc-documents/{doc_id}/file` **streams** the bytes through `storage.read_bytes`. It is never a presigned or `/local-files` URL, which avoids the public local mount.
    - Headers: `Content-Disposition: inline`, `Cache-Control: no-store`, `X-Content-Type-Options: nosniff`.
    - Writes audit `agent_kyc.view`.
  - `POST /agent-orgs/{org_id}/kyc-documents/{doc_id}/verify` writes audit `agent_kyc.verify`.
  - `POST /agent-orgs/{org_id}/kyc-documents/{doc_id}/reject` takes `{reason}` (3–500 characters) and writes audit `agent_kyc.reject`. It then emails the agent (§4.6).
  - Verify and reject are allowed only while the org is `pending`; otherwise they return 409. An admin may change a decision (verified ↔ rejected) while the org is pending.
- **Approval gate:** `set_org_status(..., "approve")` checks the gate when `org.kyc_required` is true. The gate applies to both pending → active and rejected → active.
  - If any of the three document types is missing or not `verified`, it raises **409** "All verification documents must be verified before approval".
  - Orgs with `kyc_required=false` approve exactly as today (K4).
  - Rejecting the org is never gated.
- The org list (`GET /agent-orgs`) items gain `kyc_required` and `kyc_summary: {verified, rejected, pending}`, so cards can show "2/3 verified" without extra calls.
- **Web (`AgentApprovalPanel.tsx`):**
  - Each Pending card with `kyc_required` gets a "Verification documents" section with three rows. Each row shows the type, the full number, a status chip, a **View** button (opens the streamed file in a new tab), **Verify**, and **Reject** (an inline reason field).
  - **Approve** is disabled with the hint "Verify all 3 documents first" until all are verified. The server enforces the same rule.
  - Cards for legacy orgs (`kyc_required=false`) show "No documents (registered before AGN-024)".
- **Super Admin access (K7):** `WorkflowPanel.tsx` `showAgentApproval` becomes `role in {overseas_admin, super_admin}`, and the Super Admin navigation gains an "Agent Approvals" link to the same route. Before building, check whether the route's section guard admits super_admin. If it doesn't, add it there.
  - **As built:** the guard was fine, but `services/portal.py` built the `agents` section payload for `overseas_admin` only, so Super Admin got an empty screen (found by e2e). The `agents` branch now serves `super_admin` too.

### 4.6 Emails (K6)

- **As built:** no new mailer functions. Both notices go through the existing `Notification` + `queue_deliveries` email outbox (ENH-014) for the org's active Masters:
  - document rejected (reason and a link to the status page);
  - agency approved (only for `kyc_required` orgs).
- They are queued **in the same transaction** as the action, delivered after commit, and a delivery failure never affects the action. When SMTP is not configured, the outbox's own handling applies.
- *First draft (superseded):* `send_agent_kyc_rejected_email` and `send_agent_approved_email` mailer functions called after commit.

### 4.7 Security, privacy, RBAC

- Only Overseas Admin and Super Admin can list, view, verify or reject. Agents see only their own org's documents, through the `/agent/registration` routes. Any other agent, staff member, student or role gets 403 on admin routes and 404 on a foreign document.
- Full Aadhaar numbers are never collected. PAN numbers are masked everywhere except the admin views. Document numbers are never put in logs or audit metadata.
- Storage keys are server-generated; the client filename is only for display. KYC files are never reachable via `/local-files`, a presigned URL or `/files/download`. The storage prefix `agent-kyc/` must be excluded from any generic download path. Tests will assert that `/files/download?key=agent-kyc/...` is refused.
- Audit actions: `agent_kyc.view`, `agent_kyc.verify`, `agent_kyc.reject`, `agent_kyc.reupload`, plus the existing `auth.register` and org approve actions.
- RBAC §2.147 adds the matrix rows. **As built:** no route-inventory matrix test covers the `/overseas-admin` or `/agent` prefixes, so there are no inventory rows to add. Access is pinned by `test_agn_024_admin.py`, `test_agn_024_agent.py` and `test_agn_024_portal.py`.

### 4.8 Out of scope / NEEDS_CONFIRMATION (not built in AGN-024)

- PAN uniqueness across agencies: not checked; two agencies may submit the same PAN.
- Online verification against NSDL or UIDAI: not included; verification is manual.
- Retention or deletion of KYC files for rejected agencies: not included; needs a retention decision.
- Rate limiting of the public `/auth/register` endpoint: none exists today. Multipart now allows up to about 15 MB per request. Recommend a follow-up (per-IP throttle or a Caddy `request_body` limit).
- Virus/malware scanning: none exists in the platform. Type-from-bytes plus EXIF stripping is the current control.
- Agent-added staff (non-Master) accounts do not upload KYC.
- Agencies created by BDM onboarding (bdm-019) or admin tooling keep `kyc_required=false` unless a later decision says otherwise.
- **As built, follow-ups and open points:**
  - `tests/doc-capture/s2-account-access.capture.ts` (agent registration screenshots) needs the KYC migration/fields; follow-up.
  - The admin KYC list returns the full PAN, but only file views are audited. `NEEDS_CONFIRMATION`: should the list be audited?
  - Deploy note: production `FRONTEND_URL` must equal the exact public origin (www vs apex), or agent signup returns 403 (Origin check).
  - Confirm the production reverse proxy's request-body limit admits about 16 MB (the signup body cap).

## 5. Testing

**Backend (pytest, lite set for this feature):**
- Multipart agent signup with three valid files → 201; the org is pending with `kyc_required`; three pending rows; files exist in storage.
- Each of the six agent fields missing → 422 and nothing created. JSON agent signup → 422. A JSON student signup is unchanged.
- Bad PAN or Aadhaar format → 422. A 5 MB + 1 byte file → 413. A `.exe` renamed to `.pdf` → 415. A failure on the third file leaves no user, org or stored files.
- Approve with 0, 1 or 2 verified → 409. All 3 verified → 200 and the approval email is sent. A legacy org with `kyc_required=false` → approves as today. Reject org → never gated.
- Verify or reject by `overseas_admin` and `super_admin` → 200. By `agent`, `overseas_counselor`, `it_admin` or a student → 403. On a non-pending org → 409. Reject without a reason → 422.
- File view streams bytes with `no-store`, writes audit, and is refused for non-admins. `/files/download?key=agent-kyc/...` is refused.
- `/agent/registration` is reachable while pending. Re-upload works for a rejected document only (409 otherwise), and another org's document → 404. Re-upload resets the status. The throttle returns 429.
- Masking: Aadhaar shows only the last 4, and the PAN is masked in the agent view.
- Access for the new routes is pinned by `test_agn_024_admin.py`, `test_agn_024_agent.py` and `test_agn_024_portal.py` (no route-inventory matrix covers these prefixes). Migration upgrade and downgrade both work.

**Web:** unit tests for the RegisterForm agent branch (fields shown and `FormData` built) and the panel's Approve-disabled state.

**E2E (Playwright, one spec):** agent signs up with three files → admin rejects the Aadhaar with a reason → agent re-uploads on the status page → admin verifies all three → Approve is enabled → agent reaches the dashboard. Add a Super Admin variant of the approval step and a 360 px responsive check of the signup form.

## 6. Traceability and docs to update

- `docs/decisions/PRODUCT_DECISION_REGISTER.md` gets DEC-SCOPE-224 (K1–K8).
- `docs/delivery/AGENT_CRM_BACKLOG.md` gets ang-024 / AGN-024 with acceptance criteria AC01–AC10, mapped from §4.2–§4.7.
- `docs/architecture/API_CONTRACT.md` gets §12EK. `docs/architecture/RBAC_MATRIX.md` gets §2.147.
- Tests and code as in §5, plus release evidence (e2e run output and screenshots) under the usual QA evidence folder.

## 7. Acceptance criteria (draft for the backlog item)

- **AC01:** An agent signup without all three documents and numbers is refused, and nothing is created.
- **AC02:** Files are PDF, JPG or PNG up to 5 MB; the type comes from the bytes and image metadata is stripped.
- **AC03:** Only the last 4 Aadhaar digits are stored. The PAN is validated and masked outside admin views.
- **AC04:** Overseas Admin and Super Admin can view, verify and reject each document; rejection needs a reason.
- **AC05:** Approve is refused (both in the API and the UI) until all three documents are verified, for `kyc_required` orgs only.
- **AC06:** Legacy orgs approve unchanged.
- **AC07:** A pending agent sees the status page and can re-upload rejected documents only.
- **AC08:** Emails go out on document rejection and on approval; a mail failure never blocks the action.
- **AC09:** No other role or agency can reach KYC files or data; every view and decision is audited.
- **AC10:** Super Admin sees the Agent Approvals screen.
