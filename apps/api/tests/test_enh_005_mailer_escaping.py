from app.services.mailer import _parent_notification_html

# ENH-005 security review S1 (docs/superpowers/specs/2026-09-21-enh-005-student-school-transfer-design.md §6.1):
# the parent notification email is built from coordinator-, admin- and invite-controlled text.
HOSTILE = dict(
    recipient_name="<b>P</b>",
    school_name="S<script>x</script>",
    title='"><img src=x onerror=1>',
    body="a & <i>b</i>",
    action_url='/school/x"><a href=evil>',
)


def test_every_interpolated_value_is_escaped():
    html = _parent_notification_html(**HOSTILE)
    # The template has its own logo <img>, so the hostile one is matched by its payload, not by the tag name.
    for live in ("<b>P</b>", "<script>", "<img src=x", "<i>b</i>", '"><a href=evil>'):
        assert live not in html
    assert "&lt;img src=x" in html
    assert "&lt;b&gt;P&lt;/b&gt;" in html
    assert "a &amp; &lt;i&gt;b&lt;/i&gt;" in html


def test_ordinary_text_renders_unchanged():
    html = _parent_notification_html(recipient_name="Asha", school_name="Sunrise", title="Result published", body="Maths is ready.", action_url="/school/parent/children/1")
    assert "Result published" in html
    assert "Maths is ready." in html
    assert 'href="/school/parent/children/1"' in html
