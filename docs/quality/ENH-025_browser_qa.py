"""ENH-025 browser QA against the isolated enh025 stack (http://localhost:3025).

Setup (school, accounts, links) goes through the API, exactly as the e2e helpers do; every ENH-025 behaviour is
then exercised through the real UI in Chromium. Each check is recorded PASS/FAIL with evidence; console errors,
page errors and every HTTP >= 400 are captured. Output: results.json + screenshots in this directory.
"""

import base64
import json
import os
import time
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

# Run: QA_BASE_URL=http://localhost:3025 QA_OUT=<scratch dir> PYTHONIOENCODING=utf-8 python docs/quality/ENH-025_browser_qa.py
# (needs a seeded stack: python -m app.seed). Screenshots and results.json go to QA_OUT, never into the repo.
BASE = os.environ.get("QA_BASE_URL", "http://localhost:3025")
OUT = Path(os.environ.get("QA_OUT", "enh025-qa-output"))
OUT.mkdir(parents=True, exist_ok=True)
PASSWORD = "E2e-Welcome-Pass-1!"
INVITE_PASSWORD = "Sup3r-Secret-Pass!"
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")
U = int(time.time())

results: list[dict] = []
console_errors: list[str] = []
http_errors: list[str] = []


def record(check: str, ac: str, ok: bool, evidence: str, shot=None, page=None):
    if shot and page:
        page.screenshot(path=str(OUT / f"{shot}.png"), full_page=True)
    results.append({"check": check, "ac": ac, "result": "PASS" if ok else "FAIL", "evidence": evidence, "screenshot": f"{shot}.png" if shot else None})
    print(("PASS " if ok else "FAIL ") + check + " -- " + evidence)


def attempt(check: str, ac: str, shot: str, page, fn):
    try:
        evidence = fn()
        record(check, ac, True, evidence or "as expected", shot, page)
    except Exception as exc:  # noqa: BLE001 -- QA harness: record, never abort the run
        record(check, ac, False, f"{type(exc).__name__}: {str(exc).splitlines()[0][:300]}", shot, page)


def api_login(ctx, email, password):
    ctx.request.post(f"{BASE}/api/v1/auth/logout")
    r = ctx.request.post(f"{BASE}/api/v1/auth/login", data={"email": email, "password": password, "division": "overseas"})
    assert r.ok, f"login {email}: {r.status} {r.text()}"


def activate(ctx, token, password=PASSWORD):
    r = ctx.request.post(f"{BASE}/api/v1/auth/reset-password", data={"token": token, "new_password": password})
    assert r.ok, f"activate: {r.status} {r.text()}"


def accept_invite(ctx, token):
    page = ctx.new_page()
    page.goto(f"{BASE}/school/invite/{token}/accept")
    page.fill("#invite-password", INVITE_PASSWORD)
    page.click('button:has-text("Accept and set up login")')
    page.wait_for_load_state("networkidle")
    page.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})

        def on_console(msg):
            if msg.type == "error":
                console_errors.append(f"{msg.text[:300]} @ {msg.location.get('url', '')}")

        def on_response(resp):
            if resp.status >= 400:
                http_errors.append(f"{resp.status} {resp.request.method} {resp.url.replace(BASE, '')}")

        ctx.on("console", on_console)
        ctx.on("response", on_response)
        ctx.on("page", lambda pg: pg.on("pageerror", lambda e: console_errors.append(f"pageerror: {e}")))

        # ---------------------------------------------------------------- setup (API)
        emails = {r: f"enh025-qa-{r}-{U}@example.local" for r in ("coord", "teacher", "parent", "counselor")}
        api_login(ctx, "overseasadmin@edusphere.local", "Demo@123")
        school = ctx.request.post(f"{BASE}/api/v1/overseas-admin/schools", data={"name": f"QA ENH-025 School {U}", "coordinator_full_name": "QA Coordinator", "coordinator_email": emails["coord"]}).json()
        activate(ctx, school["development_welcome_token"])
        school_id = school.get("id") or school.get("school", {}).get("id")
        staff = ctx.request.post(f"{BASE}/api/v1/overseas-admin/school-staff", data={"role": "career_counselor", "full_name": "QA Counsellor", "email": emails["counselor"], "school_ids": [school_id]}).json()
        activate(ctx, staff["development_welcome_token"])

        api_login(ctx, emails["coord"], PASSWORD)
        tokens = {}
        for role, key, name in (("school_teacher", "teacher", "QA Teacher"), ("school_parent", "parent", "QA Parent")):
            tokens[key] = ctx.request.post(f"{BASE}/api/v1/school/team/invites", data={"role": role, "full_name": name, "email": emails[key]}).json()["development_invite_token"]
        for key in ("teacher", "parent"):
            ctx.request.post(f"{BASE}/api/v1/auth/logout")
            accept_invite(ctx, tokens[key])
        api_login(ctx, emails["coord"], PASSWORD)

        page = ctx.new_page()

        # ---------------------------------------------------------------- coordinator: create with new fields
        def create_with_fields():
            page.goto(f"{BASE}/school/coordinator/students")
            page.wait_for_load_state("networkidle")
            # Visual: the submit button keeps its natural width (the busy-state grid must not stretch it).
            width = page.get_by_role("button", name="Add student").bounding_box()["width"]
            assert width < 300, f"Add student button stretched to {width:.0f}px"
            page.fill("#new-full-name", "Asha Rao")
            page.select_option("#new-teacher", label="QA Teacher")
            page.fill("#new-grade", "Grade 8-A")
            page.fill("#new-grade-level", "8")
            page.fill("#new-section", "A")
            page.fill("#new-roll", "7")
            page.select_option("#new-gender", "female")
            page.fill("#new-mobile", "+91 98765 43210")
            page.fill("#new-city", "Pune")
            page.fill("#new-subjects", "Maths, Physics")
            page.fill("#new-parent-email", emails["parent"])
            page.click('button:has-text("Add student")')
            expect(page.get_by_text("Asha Rao added to the roster.")).to_be_visible()
            row = page.locator("tr", has_text="Asha Rao")
            expect(row.get_by_role("cell", name="A", exact=True)).to_be_visible()
            expect(row.get_by_role("cell", name="7", exact=True)).to_be_visible()
            return "created with section/roll/gender/mobile/city/subjects; row shows Section A, Roll 7; parent linked"

        attempt("Coordinator creates a student with the new fields", "AC1", "01-create", page, create_with_fields)
        href = page.locator("tr", has_text="Asha Rao").get_by_role("link", name="Timeline").get_attribute("href")
        sid = href.split("/")[-1]

        def edit_prefilled_and_keyboard():
            page.locator("tr", has_text="Asha Rao").get_by_role("button", name="Edit").click()
            expect(page.locator("#edit-heading")).to_be_focused()
            for legend in ("Identity", "Class placement", "Contact", "Studies & interests"):
                expect(page.get_by_role("group", name=legend).first).to_be_visible()
            assert page.input_value("#edit-city") == "Pune" and page.input_value("#edit-section") == "A"
            # Visual: a help text under one field must not stretch its neighbour's input in the same grid row.
            hs, hr = page.locator("#edit-section").bounding_box()["height"], page.locator("#edit-roll").bounding_box()["height"]
            assert abs(hs - hr) < 1, f"section input {hs}px tall vs roll input {hr}px"
            assert page.input_value("#edit-teacher") != "", "teacher select lost its value"
            page.keyboard.press("Tab")
            focused = page.evaluate("document.activeElement.id")
            assert focused == "edit-full-name", f"Tab from heading went to {focused!r}"
            page.fill("#edit-career_interests", "Engineering, Design")
            page.select_option("#edit-global", "yes")
            page.click('button:has-text("Save changes")')
            expect(page.get_by_text("Student updated.")).to_be_visible()
            expect(page.locator("tr", has_text="Asha Rao").get_by_role("button", name="Edit")).to_be_focused()
            return "grouped legends, prefilled values (teacher kept), heading focused, Tab → Full name, save → roster message, focus back on Edit"

        attempt("Coordinator edits: grouped, prefilled, keyboard focus", "AC1/AC11", "02-edit", page, edit_prefilled_and_keyboard)

        def untouched_save_keeps_values():
            page.locator("tr", has_text="Asha Rao").get_by_role("button", name="Edit").click()
            page.click('button:has-text("Save changes")')
            expect(page.get_by_text("Student updated.")).to_be_visible()
            s = ctx.request.get(f"{BASE}/api/v1/school/students/{sid}").json()
            assert s["city"] == "Pune" and s["subjects"] == ["Maths", "Physics"] and s["career_interests"] == ["Engineering", "Design"] and s["assigned_teacher_user_id"], s
            return "saving without touching anything left city, subjects, career interests and teacher intact"

        attempt("Saving the edit form untouched keeps every value", "AC7", "03-untouched-save", page, untouched_save_keeps_values)

        def roll_clash():
            page.fill("#new-full-name", "Clash Kid")
            page.fill("#new-grade-level", "8")
            page.fill("#new-section", "a")
            page.fill("#new-roll", "7")
            page.click('button:has-text("Add student")')
            alert = page.locator(".action-card", has_text="Add one student").get_by_role("alert")
            expect(alert).to_have_text("roll_number '7' is already used in this grade and section for this academic year")
            return "409 shown as an alert inside the Add card (section 'a' treated as 'A')"

        attempt("Roll-number clash is reported in the form", "AC5", "04-roll-clash", page, roll_clash)

        def bad_mobile():
            page.fill("#new-full-name", "Bad Mobile Kid")
            page.fill("#new-roll", "")
            page.fill("#new-mobile", "12ab")
            page.click('button:has-text("Add student")')
            alert = page.locator(".action-card", has_text="Add one student").get_by_role("alert")
            expect(alert).to_contain_text("student_mobile")
            assert "12ab" not in alert.inner_text()
            return f"422 shown: {alert.inner_text()!r} (value not echoed)"

        attempt("Invalid field is rejected with a field-named message", "AC2", "05-bad-mobile", page, bad_mobile)

        # ---------------------------------------------------------------- coordinator: student page + photo
        def profile_and_photo():
            page.goto(f"{BASE}/school/coordinator/students/{sid}")
            page.wait_for_load_state("networkidle")
            expect(page.get_by_text("Female")).to_be_visible()
            expect(page.get_by_text("Maths, Physics")).to_be_visible()
            expect(page.get_by_role("img", name="No photo for Asha Rao")).to_be_visible()
            page.set_input_files(f"#photo-{sid}", files=[{"name": "asha.png", "mimeType": "image/png", "buffer": PNG}])
            expect(page.get_by_text("Photo saved.")).to_be_visible()
            img = page.get_by_role("img", name="Photo of Asha Rao")
            expect(img).to_be_visible()
            page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=img.element_handle())
            return "profile shows Female / Maths, Physics; placeholder before upload; uploaded PNG rendered (naturalWidth > 0)"

        attempt("Coordinator sees the profile and uploads a photo", "AC1/AC8", "06-photo-upload", page, profile_and_photo)

        def photo_headers_and_key():
            r = ctx.request.get(f"{BASE}/api/v1/school/students/{sid}/photo")
            h = r.headers
            assert r.status == 200 and h.get("content-type") == "image/png", (r.status, h.get("content-type"))
            assert h.get("cache-control") == "private, no-store" and h.get("x-content-type-options") == "nosniff", h
            assert h.get("content-security-policy") == "default-src 'none'; sandbox", h.get("content-security-policy")
            body = ctx.request.get(f"{BASE}/api/v1/school/students/{sid}").text()
            assert "photo_key" not in body and "school-student-photos" not in body
            return "image/png, private no-store, nosniff, sandbox CSP; student JSON has has_photo only, no key"

        attempt("Photo response headers and no key leak", "AC8/AC12", "07-photo-headers", page, photo_headers_and_key)

        def client_side_reject():
            page.set_input_files(f"#photo-{sid}", files=[{"name": "x.gif", "mimeType": "image/gif", "buffer": b"GIF89a"}])
            # Scoped: Next.js renders its own role="alert" route announcer on every page.
            expect(page.locator(".student-photo-block").get_by_role("alert")).to_contain_text("JPEG or PNG")
            return "GIF rejected in the browser before any upload"

        attempt("Wrong photo type rejected before upload", "AC12", "08-photo-reject", page, client_side_reject)

        def remove_confirm_and_reupload():
            page.get_by_role("button", name="Remove photo").click()
            page.get_by_role("button", name="Cancel").click()
            expect(page.get_by_role("img", name="Photo of Asha Rao")).to_be_visible()
            page.get_by_role("button", name="Remove photo").click()
            page.get_by_role("button", name="Confirm remove").click()
            expect(page.get_by_role("img", name="No photo for Asha Rao")).to_be_visible()
            page.set_input_files(f"#photo-{sid}", files=[{"name": "asha.png", "mimeType": "image/png", "buffer": PNG}])
            expect(page.get_by_text("Photo saved.")).to_be_visible()
            return "Cancel keeps it; Confirm remove → initials placeholder; re-uploaded for the reader checks"

        attempt("Photo removal needs confirmation", "AC8", "09-photo-remove", page, remove_confirm_and_reupload)

        # ---------------------------------------------------------------- bulk upload
        def bulk_upload():
            page.goto(f"{BASE}/school/coordinator/students/bulk-upload")
            page.wait_for_load_state("networkidle")
            page.get_by_text("Column reference").click()
            expect(page.get_by_role("cell", name="global_education_interest")).to_be_visible()
            expect(page.get_by_text("Photos can't be uploaded in the CSV")).to_be_visible()
            csv = "full_name,grade_level,section,roll_number,gender,city,subjects,global_education_interest\nBulk Kid,6,B,3,Male,Nashik,Maths;Art,no\nBad Kid,6,B,4,robot,,,\n"
            page.set_input_files("#roster-file", files=[{"name": "r.csv", "mimeType": "text/csv", "buffer": csv.encode()}])
            page.click('button:has-text("Upload roster")')
            expect(page.get_by_text("1 of 2 rows accepted, 1 rejected")).to_be_visible()
            expect(page.get_by_role("cell", name="gender must be one of: female, male, other, prefer_not_to_say")).to_be_visible()
            page.goto(f"{BASE}/school/coordinator/students")
            row = page.locator("tr", has_text="Bulk Kid")
            expect(row.get_by_role("cell", name="B", exact=True)).to_be_visible()
            return "column reference visible incl. photo note; 1 accepted / 1 rejected with gender message; roster shows section B"

        attempt("Bulk upload with the new columns", "AC1/AC2/AC6", "10-bulk", page, bulk_upload)

        # ---------------------------------------------------------------- teacher
        api_login(ctx, emails["teacher"], INVITE_PASSWORD)

        def teacher_view():
            page.goto(f"{BASE}/school/teacher/students/{sid}")
            page.wait_for_load_state("networkidle")
            expect(page.get_by_text("Pune")).to_be_visible()
            img = page.get_by_role("img", name="Photo of Asha Rao")
            page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=img.element_handle())
            assert page.locator("input[type=file]").count() == 0
            return "assigned teacher sees profile + photo; no upload control"

        attempt("Teacher (assigned) reads profile and photo", "AC8", "11-teacher", page, teacher_view)

        def teacher_unassigned():
            bulk_id = [s for s in ctx.request.get(f"{BASE}/api/v1/school/students").json() if s["full_name"] == "Bulk Kid"]
            assert bulk_id == [], "an unassigned student appeared in the teacher's list"
            r = ctx.request.get(f"{BASE}/api/v1/school/students/{sid}/photo")
            assert r.status == 200
            return "unassigned students absent from the teacher's list (scope unchanged)"

        attempt("Teacher scope unchanged for unassigned students", "AC8", None, page, teacher_unassigned)

        # ---------------------------------------------------------------- parent
        api_login(ctx, emails["parent"], INVITE_PASSWORD)

        def parent_view():
            page.goto(f"{BASE}/school/parent/children/{sid}")
            page.wait_for_load_state("networkidle")
            expect(page.get_by_text("A / 7")).to_be_visible()
            img = page.get_by_role("img", name="Photo of Asha Rao")
            page.wait_for_function("(el) => el.complete && el.naturalWidth > 0", arg=img.element_handle())
            return "linked parent sees photo and 'Section / Roll number: A / 7'"

        attempt("Parent (linked) sees photo, section and roll", "AC8", "12-parent", page, parent_view)

        # ---------------------------------------------------------------- counsellor
        api_login(ctx, emails["counselor"], PASSWORD)

        def counselor_prefs():
            page.goto(f"{BASE}/school/career-counselor/dashboard")
            page.wait_for_load_state("networkidle")
            page.select_option("#prefs-student", value=sid)
            expect(page.locator("#prefs-career_interests")).to_have_value("Engineering, Design")
            # Visual: the busy-state fieldset must keep .form's 16px spacing between fields.
            above = page.locator("#prefs-career_interests").bounding_box()
            below = page.locator("label[for=prefs-preferred_countries]").bounding_box()
            gap = below["y"] - (above["y"] + above["height"])
            assert gap >= 12, f"only {gap:.1f}px between career interests and the next field"
            page.fill("#prefs-preferred_countries", "Germany, Canada")
            page.click('button:has-text("Save preferences")')
            expect(page.get_by_text("Career preferences saved.")).to_be_visible()
            assert ctx.request.get(f"{BASE}/api/v1/school/students/{sid}/photo").status == 403
            return "loads coordinator's career interests, saves countries; counsellor gets 403 on the photo"

        attempt("Counsellor records career preferences", "AC9", "13-counselor", page, counselor_prefs)

        api_login(ctx, emails["coord"], PASSWORD)

        def coordinator_sees_counselor_edit():
            page.goto(f"{BASE}/school/coordinator/students/{sid}")
            expect(page.get_by_text("Germany, Canada")).to_be_visible()
            return "coordinator's profile shows the counsellor's preferred countries"

        attempt("Counsellor edit visible to the coordinator", "AC9", "14-coord-sees-prefs", page, coordinator_sees_counselor_edit)

        # ---------------------------------------------------------------- unauthenticated photo
        def unauth_photo():
            anon = browser.new_context()
            r = anon.request.get(f"{BASE}/api/v1/school/students/{sid}/photo")
            anon.close()
            assert r.status in (401, 403), r.status
            return f"no session → {r.status}"

        attempt("Photo requires a session", "AC12", None, page, unauth_photo)

        # ---------------------------------------------------------------- phone width
        mobile = browser.new_context(viewport={"width": 375, "height": 800}, storage_state=ctx.storage_state())
        mobile.on("console", on_console)
        mobile.on("response", on_response)
        mp = mobile.new_page()

        def phone_roster_form():
            mp.goto(f"{BASE}/school/coordinator/students")
            mp.wait_for_load_state("networkidle")
            mp.locator("tr", has_text="Asha Rao").get_by_role("button", name="Edit").click()
            a, b = mp.locator("#edit-section").bounding_box(), mp.locator("#edit-roll").bounding_box()
            assert b["y"] > a["y"], "section and roll are side by side at 375px"
            width = mp.evaluate("document.documentElement.scrollWidth")
            assert width <= 375, f"page scrollWidth {width}"
            return f"fields stacked; document scrollWidth {width}px ≤ 375"

        attempt("Roster edit form at 375px", "AC11", "15-phone-roster", mp, phone_roster_form)

        def phone_student_page():
            mp.goto(f"{BASE}/school/coordinator/students/{sid}")
            mp.wait_for_load_state("networkidle")
            width = mp.evaluate("document.documentElement.scrollWidth")
            assert width <= 375, f"page scrollWidth {width}"
            photo, dl = mp.locator(".student-photo").first.bounding_box(), mp.locator(".student-profile dl").bounding_box()
            assert dl["y"] >= photo["y"] + photo["height"] - 1, "profile list not stacked under the photo"
            return f"photo above profile list; scrollWidth {width}px"

        attempt("Student profile at 375px", "AC11", "16-phone-profile", mp, phone_student_page)
        mobile.close()

        browser.close()

    expected_4xx = {"409 POST /api/v1/school/students", "422 POST /api/v1/school/students", "403 GET /api/v1/school/students/" + sid + "/photo"}
    unexpected = [e for e in http_errors if e not in expected_4xx and not e.startswith("401 POST /api/v1/auth/logout")]
    (OUT / "results.json").write_text(json.dumps({"base": BASE, "student_id": sid, "results": results, "console_errors": console_errors, "http_errors": http_errors, "unexpected_http_errors": unexpected}, indent=2), encoding="utf-8")
    print(f"\n{sum(r['result'] == 'PASS' for r in results)}/{len(results)} checks passed")
    print(f"console errors: {len(console_errors)}")
    for e in console_errors:
        print("  " + e)
    print(f"HTTP >= 400: {len(http_errors)} (unexpected: {len(unexpected)})")
    for e in http_errors:
        print("  " + e + ("" if e not in unexpected else "   <-- unexpected"))


if __name__ == "__main__":
    main()
