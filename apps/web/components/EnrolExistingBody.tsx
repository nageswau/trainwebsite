import DualEnrolmentForm from "@/components/DualEnrolmentForm";
import { DIVISION_LABEL, OTHER_DIVISION, type StudentDivision } from "@/lib/dualEnrolment";

// ENH-033 (DEC-SCOPE-441): the page body shared by the counselor and telecaller "Enrol Existing" pages.
export default function EnrolExistingBody({ division }: { division: StudentDivision }) {
  const label = DIVISION_LABEL[division];
  const from = DIVISION_LABEL[OTHER_DIVISION[division]];
  return (
    <div className="portal-content">
      <div className="portal-title">
        <div>
          <div className="eyebrow">Students</div>
          <h2>Enrol an existing {from} student in {label}</h2>
          <p className="muted">
            The student keeps their {from} enrolment, login and Student ID, and can switch between the two portals. This gives {label} access
            only -- add programs or applications as usual afterwards.
          </p>
        </div>
      </div>
      <DualEnrolmentForm division={division} />
    </div>
  );
}
