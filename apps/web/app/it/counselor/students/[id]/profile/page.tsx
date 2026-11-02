import ItStudentProfilePage from "@/components/ItStudentProfilePage";

// itc-012 (DEC-SCOPE-345): an IT student's record, for their itc-003 counselor.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ItStudentProfilePage portal="counselor" id={id} />;
}
