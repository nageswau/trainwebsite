from app.core.rbac import has_permission


def test_super_admin():
    assert has_permission("super_admin", "anything:anywhere")


def test_student_cannot_admin():
    assert not has_permission("it_student", "users:write")


def test_it_admin_domain():
    assert has_permission("it_admin", "it:anything")
