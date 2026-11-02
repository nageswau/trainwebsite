import ItStudentProfilePage from "@/components/ItStudentProfilePage";

// itc-012 (DEC-SCOPE-345): an IT student's record, for the IT Admin.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ItStudentProfilePage portal="admin" id={id} />;
}
