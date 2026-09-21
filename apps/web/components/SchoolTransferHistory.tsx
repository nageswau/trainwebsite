import { formatDate } from "@/components/SchoolChildOverview";
import { serverApi } from "@/lib/api";
import type { SchoolRef } from "@/lib/transfers";

// ENH-005 -- a student's approved school transfers, read from GET /school/students/{id}/transfer-history. That endpoint uses
// the same own-scope loader as the overview and timeline, so it renders correctly for whichever role is looking, and it
// returns no reason and no staff IDs. Like SchoolGradeHistory it reuses the Journey Timeline's `.jtl-*` rail, and states the
// outcome in text (badge + sentence), never by colour alone.
//
// It renders the whole card, and renders NOTHING for a student who has never transferred: an empty "Transfer history" card
// on every student page would be clutter for the common case. A failed load is different -- that stays visible.

export type TransferHistoryEntry = { id: string; decided_at: string; from_school: SchoolRef; to_school: SchoolRef };
type TransferHistory = { student: { id: string; full_name: string }; history: TransferHistoryEntry[] };

/** The student's transfers, or null when they could not be loaded (rendered as "unavailable"). */
export async function loadTransferHistory(studentId: string): Promise<TransferHistoryEntry[] | null> {
  try {
    return (await serverApi<TransferHistory>(`/api/v1/school/students/${studentId}/transfer-history`)).history;
  } catch {
    return null;
  }
}

const COLOR = "#1554d8";

export default function SchoolTransferHistory({ history }: { history: TransferHistoryEntry[] | null }) {
  if (history !== null && history.length === 0) return null;
  return (
    <div className="card">
      <h3>Transfer history</h3>
      {history === null ? (
        <p className="muted">Transfer history is unavailable right now.</p>
      ) : (
        <div className="jtl">
          {history.map((h) => (
            <div className="jtl-row" key={h.id}>
              <div className="jtl-rail">
                <span className="jtl-node" style={{ "--jtl-color": COLOR } as React.CSSProperties} />
              </div>
              <div className="jtl-body">
                <span className="jtl-date">{formatDate(h.decided_at, true)}</span>
                <span className="jtl-badge" style={{ "--jtl-color": COLOR } as React.CSSProperties}>Transferred</span>
                <h4 className="jtl-title">Moved from {h.from_school.name} to {h.to_school.name}</h4>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
