import StudentProfilePage from "@/components/StudentProfilePage";

// ccrm-007 (DEC-SCOPE-249): a student's structured profile, for the student's counselor.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <StudentProfilePage portal="counselor" id={id} />;
}
