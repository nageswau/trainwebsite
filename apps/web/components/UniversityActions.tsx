"use client";
import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { sendJson } from "@/lib/apiErrors";
import { plural } from "@/lib/plural";
import { type University, universityUrl } from "@/lib/universities";

// upc-003 (UM5, UM6, UM10): the catalogue and lifecycle actions the API allows this user (`permissions`). Deactivation asks first, and
// names the applications that keep pointing at the university; the server re-checks the count and wants `confirm`.
type Action = "publish" | "unpublish" | "deactivate" | "reactivate";

export default function UniversityActions({ university: u }: { university: University }) {
  const router = useRouter();
  const sending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: Action, body: unknown = {}) {
    if (sending.current) return;
    sending.current = true;
    setBusy(true);
    setError(null);
    const outcome = await sendJson(universityUrl(u.id, action), "POST", body);
    sending.current = false;
    setBusy(false);
    setConfirming(false);
    if (outcome.ok) router.refresh();
    else setError(outcome.message);
  }

  const { can_publish, can_deactivate } = u.permissions;
  if (!can_publish && !can_deactivate) return null;
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {error && <p role="alert" className="notice" style={{ margin: 0 }}>{error}</p>}
      {confirming ? (
        <div role="group" aria-label="Confirm deactivation" style={{ display: "grid", gap: 8 }}>
          <p style={{ margin: 0 }}>
            Deactivating hides {u.name} from the public catalogue and makes it read-only.
            {u.application_count > 0 && ` Its ${plural(u.application_count, "application")} keep working.`}
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <button className="btn small" type="button" disabled={busy} onClick={() => run("deactivate", { confirm: true })}>Yes, deactivate</button>
            <button className="btn secondary small" type="button" disabled={busy} onClick={() => setConfirming(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          {u.active && can_publish && (u.catalogue_visible
            ? <button className="btn secondary small" type="button" disabled={busy} onClick={() => run("unpublish")}>Remove from catalogue</button>
            : <button className="btn small" type="button" disabled={busy} onClick={() => run("publish")}>Publish to catalogue</button>)}
          {can_deactivate && (u.active
            ? <button className="btn secondary small" type="button" disabled={busy} onClick={() => setConfirming(true)}>Deactivate</button>
            : <button className="btn small" type="button" disabled={busy} onClick={() => run("reactivate")}>Reactivate</button>)}
        </div>
      )}
    </div>
  );
}
