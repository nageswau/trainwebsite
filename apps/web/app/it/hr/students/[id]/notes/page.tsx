import ItStudentNotesPage from "@/components/ItStudentNotesPage";

// itc-028 (DEC-SCOPE-351): an IT student's notes (internal by default, shared with the student only on request).
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ItStudentNotesPage portal="hr" id={id} />;
}
