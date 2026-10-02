"use client";

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import AgentDocumentRequestForm from "./AgentDocumentRequestForm";
import AgentDocumentRequestsPanel from "./AgentDocumentRequestsPanel";
import AgentDocumentsPanel from "./AgentDocumentsPanel";
import AgentDocumentUploadForm from "./AgentDocumentUploadForm";
import { parseView } from "@/lib/agentDocuments";
import type { User } from "@/lib/types";

// AGN-009 (DEC-SCOPE-051): the agency Documents page -- upload and request forms, then the sidebar view in the URL (?view=pending |
// uploaded | additional). Staff see only their assigned students' documents (G4); a non-agency viewer (Super Admin) gets a note, as
// on the Applications page.
function Viewed({ reloadKey, user }: { reloadKey: number; user: User }) {
  const view = parseView(useSearchParams().get("view"));
  return view === "additional" ? <AgentDocumentRequestsPanel reloadKey={reloadKey} /> : <AgentDocumentsPanel key={view} view={view} reloadKey={reloadKey} user={user} />;
}

export default function AgentDocumentsSection({ user }: { user: User }) {
  const [reloadKey, setReloadKey] = useState(0);
  const member = user.role === "agent";
  const reload = () => setReloadKey((k) => k + 1);
  const intro = !member
    ? "Agency documents are managed by the agency's own Masters and Staff."
    : user.agent_member_role === "staff"
      ? "Documents of students assigned to you, with or without a login."
      : "Every document of your agency's students, with or without a login.";
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Workspace</div>
          <h2>Documents</h2>
          <p className="muted">{intro}</p>
        </div>
      </div>
      {member && (
        <div className="action-grid">
          <AgentDocumentUploadForm onUploaded={reload} />
          <AgentDocumentRequestForm onCreated={reload} />
          <Suspense fallback={<p className="muted">Loading documents…</p>}>
            <Viewed reloadKey={reloadKey} user={user} />
          </Suspense>
        </div>
      )}
    </div>
  );
}
