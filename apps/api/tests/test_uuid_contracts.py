import sqlalchemy as sa

from app.main import app
from app.models import Base


def test_every_application_primary_key_is_uuid_and_not_autoincrementing():
    for table in Base.metadata.sorted_tables:
        primary_columns = list(table.primary_key.columns)
        assert len(primary_columns) == 1, f"{table.name} must have one primary key"
        column = primary_columns[0]
        assert isinstance(column.type, sa.Uuid), f"{table.name}.{column.name} must be UUID"
        assert column.autoincrement is not True, f"{table.name}.{column.name} must not auto-increment"


def test_every_relationship_uses_uuid_columns():
    for table in Base.metadata.sorted_tables:
        for constraint in table.foreign_key_constraints:
            for element in constraint.elements:
                assert isinstance(element.parent.type, sa.Uuid)
                assert isinstance(element.column.type, sa.Uuid)


def test_teacher_action_routes_are_registered():
    registered = {(path, method.lower()) for path, operations in app.openapi()["paths"].items() for method in operations}
    expected = {
        ("/api/v1/workflows/it/trainer/attendance", "post"),
        ("/api/v1/workflows/it/attendance-corrections/{correction_id}", "patch"),
        ("/api/v1/workflows/it/trainer/assignments", "post"),
        ("/api/v1/workflows/it/trainer/submissions/{submission_id}", "patch"),
        ("/api/v1/workflows/it/trainer/assessments", "post"),
        ("/api/v1/workflows/it/trainer/assessments/{assessment_id}/questions", "post"),
        ("/api/v1/workflows/it/trainer/assessment-attempts/{attempt_id}", "patch"),
        ("/api/v1/workflows/it/trainer/materials", "post"),
        ("/api/v1/communications/it/live-sessions", "post"),
        ("/api/v1/communications/it/live-sessions/{session_id}/recording", "patch"),
        ("/api/v1/workflows/it/trainer/enrollments/{enrollment_id}/progress", "patch"),
        ("/api/v1/workflows/it/certificates/{enrollment_id}/issue", "post"),
    }
    missing = sorted(expected - registered)
    assert not missing, "Missing teacher routes:\n" + "\n".join(f"{method} {path}" for path, method in missing)
