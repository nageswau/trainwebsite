"""upc-027 (DEC-SCOPE-167, spec OB1/OB4/OB7/OB8): the partner onboarding checklist, in source order and wording (EVID-020 §29,
L946-L968), and its three statuses ("Not Started -> In Progress -> Completed").

Constants only, with no app imports, so the model CHECK, the migration's parity test, the service and the schemas share one list."""

from typing import NamedTuple


class Item(NamedTuple):
    key: str
    label: str


ITEMS: tuple[Item, ...] = (
    Item("counselor_training", "Counselor training"),
    Item("application_team_training", "Application team training"),
    Item("product_training", "Product training"),
    Item("university_portal_access", "University portal access"),
    Item("application_process", "Application process"),
    Item("marketing_material", "Marketing material"),
    Item("course_database_updated", "Course database updated"),
    Item("commission_setup", "Commission setup"),
    Item("university_contact_setup", "University contact setup"),
    Item("first_student_campaign", "First student campaign"),
)
ITEM_KEYS: tuple[str, ...] = tuple(i.key for i in ITEMS)

STATUS_LABELS: dict[str, str] = {"not_started": "Not Started", "in_progress": "In Progress", "completed": "Completed"}
STATUSES: tuple[str, ...] = tuple(STATUS_LABELS)
COMPLETED = "completed"

AUTO_ITEM = "course_database_updated"  # OB7: completed while the university has an active course (upc-017)
ACTIVATION_STAGE = "partner_activated"  # OB8 / Q-27: all ten completed moves the university here (forward only)
NOTE_MAX = 500
