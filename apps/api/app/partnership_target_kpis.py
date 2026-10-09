"""upc-021 (DEC-SCOPE-146, spec TG1/TG10): the §21 monthly target KPIs, in source order (EVID-020 §21, L703-L715), each with the written
definition of its actual (backlog Appendix B T1-T7). Meetings (T3 = D7) waits for upc-009, so it is not tracked yet: a target can be set,
the actual says "Not tracked", never 0.

Constants only, with no app imports, so the model CHECK, the migration's parity test, the service and the schemas share one list."""

from typing import NamedTuple


class Kpi(NamedTuple):
    key: str
    label: str
    definition: str
    tracked: bool = True


KPIS: tuple[Kpi, ...] = (
    Kpi("new_universities", "New universities identified", "Universities first assigned to the manager as primary this month"),
    Kpi("contacted", "Contacted", "Universities that first reached Initial Contact or a later stage this month"),
    Kpi("meetings", "Meetings", "Meetings completed this month — counted once Meetings (upc-009) is available", tracked=False),
    Kpi("proposals", "Proposals", "Universities moved into Proposal Sent this month"),
    Kpi("negotiations", "Negotiations", "Universities moved into Commercial Discussion this month"),
    Kpi("mous", "MoUs", "Agreements that reached Signed this month"),
    Kpi("new_active", "New active universities", "Universities moved into Partner Activated this month"),
)
KPI_KEYS: tuple[str, ...] = tuple(k.key for k in KPIS)
TARGET_MAX = 100_000  # TG4: the tel-022 / bdm-016 bound
