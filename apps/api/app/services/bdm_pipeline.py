"""bdm-004 (DEC-SCOPE-070, spec §6.2): pipeline output, move / Lost / Revive rules, history and the pipeline view.

Functions only; nothing here commits -- the route owns the transaction (bdm-002's rule). Every check runs on the row locked by
`load_scoped(lock=True)`. Audit metadata and logs carry stage keys and flags only, never the note or reason text (spec §6.6)."""

from app.bdm_stages import AGENT_STATUS, LIVE, MANUAL, PIPELINES, VOLUME
from app.models import BdmOrganization

_LATER_STATE = {MANUAL: "upcoming", LIVE: "awaiting_handover", VOLUME: "not_tracked"}


def label_of(bdm_type: str, key: str) -> str:
    """A stage key's source label; a key no longer in the catalogue (history after a future change) is shown as stored."""
    return next((s.label for s in PIPELINES[bdm_type] if s.key == key), key)


def live_status(org: BdmOrganization) -> None:
    """S3: the live post-handover stage, read from the linked School (bdm-018) or Agent Organization (bdm-019). Nothing is linked
    yet, so live steps show "Awaiting handover"."""
    return None


def pipeline_out(org: BdmOrganization) -> dict:
    steps = PIPELINES[org.bdm_type]
    current = next(i for i, s in enumerate(steps) if s.key == org.pipeline_stage)

    def state(i: int, kind: str) -> str:
        return "done" if i < current else "current" if i == current else _LATER_STATE[kind]

    return {
        "stage": org.pipeline_stage,
        "stage_label": steps[current].label,
        "lost": {"at": org.lost_at, "reason": org.lost_reason} if org.lost_at else None,
        "agent_status": AGENT_STATUS[org.pipeline_stage] if org.bdm_type == "agent" else None,
        "steps": [{"key": s.key, "label": s.label, "kind": s.kind, "state": state(i, s.kind)} for i, s in enumerate(steps)],
    }
