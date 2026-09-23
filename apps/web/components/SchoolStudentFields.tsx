import { GENDER_OPTIONS, listText, type SchoolStudent } from "@/lib/schoolStudents";

type TeacherOption = { id: string; name: string; active: boolean };

const LIST_INPUTS = [
  ["subjects", "Subjects"],
  ["career_interests", "Career interests"],
  ["preferred_countries", "Preferred countries"],
  ["preferred_courses", "Preferred courses"],
] as const;

// ENH-025: the grouped roster fields, shared by "Add one student" and "Edit" so both forms stay identical.
// In edit mode every input is pre-filled from `student`, so saving without touching a field keeps its value.
export default function SchoolStudentFields({ idPrefix, student, teachers, includeInactiveTeachers }: { idPrefix: string; student?: SchoolStudent; teachers: TeacherOption[]; includeInactiveTeachers: boolean }) {
  const id = (name: string) => `${idPrefix}-${name}`;
  const interest = student?.global_education_interest == null ? "" : student.global_education_interest ? "yes" : "no";
  const teacherOptions = includeInactiveTeachers ? teachers : teachers.filter((t) => t.active);
  return (
    <>
      <fieldset className="form-section">
        <legend>Identity</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={id("full-name")}>Full name</label>
            <input id={id("full-name")} name="full_name" defaultValue={student?.full_name} required />
          </div>
          <div className="field">
            <label htmlFor={id("dob")}>Date of birth</label>
            <input id={id("dob")} name="date_of_birth" type="date" defaultValue={student?.date_of_birth ?? ""} />
          </div>
          <div className="field">
            <label htmlFor={id("gender")}>Gender</label>
            <select id={id("gender")} name="gender" defaultValue={student?.gender ?? ""}>
              <option value="">Not recorded</option>
              {GENDER_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Class placement</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={id("grade")}>Grade/Class</label>
            <input id={id("grade")} name="grade_or_class" defaultValue={student?.grade_or_class ?? ""} maxLength={60} />
          </div>
          <div className="field">
            <label htmlFor={id("grade-level")}>Grade level (1-12, optional)</label>
            <input id={id("grade-level")} name="grade_level" type="number" min={1} max={12} step={1} defaultValue={student?.grade_level ?? ""} />
          </div>
          <div className="field">
            <label htmlFor={id("section")}>Section</label>
            <input id={id("section")} name="section" defaultValue={student?.section ?? ""} maxLength={20} />
          </div>
          <div className="field">
            <label htmlFor={id("roll")}>Roll number</label>
            <input id={id("roll")} name="roll_number" defaultValue={student?.roll_number ?? ""} maxLength={20} aria-describedby={id("roll-help")} />
            <span id={id("roll-help")} className="muted field-help">Unique within the grade, section and academic year.</span>
          </div>
          <div className="field">
            <label htmlFor={id("teacher")}>Assigned Teacher</label>
            {/* Edit includes inactive teachers so an already-assigned, since-deactivated Teacher still shows as the
                selected option -- otherwise the select would fall back to "Unassigned" and an unrelated save would clear it. */}
            {/* key: the teacher list loads after the form can open; an uncontrolled select never re-applies its
                defaultValue when options arrive later, so it remounts once they do (else a save would unassign). */}
            <select key={teacherOptions.map((t) => t.id).join(",")} id={id("teacher")} name="assigned_teacher_user_id" defaultValue={student?.assigned_teacher_user_id ?? ""}>
              <option value="">Unassigned</option>
              {teacherOptions.map((t) => <option key={t.id} value={t.id}>{t.name}{t.active ? "" : " (inactive)"}</option>)}
            </select>
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Contact</legend>
        <div className="form-grid">
          <div className="field">
            <label htmlFor={id("mobile")}>Student mobile</label>
            <input id={id("mobile")} name="student_mobile" type="tel" inputMode="tel" autoComplete="off" defaultValue={student?.student_mobile ?? ""} maxLength={20} />
          </div>
          <div className="field">
            <label htmlFor={id("city")}>City</label>
            <input id={id("city")} name="city" defaultValue={student?.city ?? ""} maxLength={120} />
          </div>
          <div className="field">
            <label htmlFor={id("parent-name")}>Parent&apos;s name</label>
            <input id={id("parent-name")} name="parent_name" placeholder="Only used if this parent has no account yet" />
          </div>
          <div className="field">
            <label htmlFor={id("parent-email")}>Parent&apos;s email</label>
            <input id={id("parent-email")} name="parent_email" type="email" defaultValue={student?.pending_parent_email ?? ""} placeholder="Sends an invite if they don't have an account yet" />
          </div>
        </div>
      </fieldset>

      <fieldset className="form-section">
        <legend>Studies &amp; interests</legend>
        <p id={id("list-help")} className="muted field-help">Separate multiple values with commas.</p>
        <div className="form-grid">
          {LIST_INPUTS.map(([name, label]) => (
            <div className="field" key={name}>
              <label htmlFor={id(name)}>{label}</label>
              <input id={id(name)} name={name} defaultValue={listText(student?.[name])} aria-describedby={id("list-help")} />
            </div>
          ))}
          <div className="field">
            <label htmlFor={id("global")}>Interested in studying abroad</label>
            <select id={id("global")} name="global_education_interest" defaultValue={interest}>
              <option value="">Not recorded</option>
              <option value="yes">Yes</option>
              <option value="no">No</option>
            </select>
          </div>
        </div>
      </fieldset>
    </>
  );
}
