import Link from "next/link";

import { UNIVERSITIES_PATH } from "@/lib/universities";

// upc-003 (UM13): universities are added and edited in the Global University Master now, which replaced the old create-only panel here.
export default function UniversityMasterLink() {
  return (
    <div className="action-card">
      <h3>University Master</h3>
      <p className="muted">Add, edit, assign and publish universities in one place. New universities stay internal until published.</p>
      <Link className="btn small" href={UNIVERSITIES_PATH}>Open University Master</Link>
    </div>
  );
}
