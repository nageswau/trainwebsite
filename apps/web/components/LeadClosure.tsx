import type { LeadClosureFields } from "@/lib/leadStages";

// ccrm-006 (DEC-SCOPE-264): how a closed lead closed -- the surviving lead of a Duplicate, or the loss reason and who it was lost to.
export default function LeadClosure({ lead }: { lead: LeadClosureFields }) {
  const text = lead.duplicate_of
    ? `Duplicate of ${lead.duplicate_of.lead_code}`
    : lead.lost_reason
      ? `Lost reason: ${lead.lost_reason.name}${lead.lost_to ? ` · Lost to: ${lead.lost_to}` : ""}`
      : null;
  return text ? <p className="muted" style={{ margin: "4px 0 0", fontSize: 13, overflowWrap: "anywhere" }}>{text}</p> : null;
}
