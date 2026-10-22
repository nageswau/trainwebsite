import StudentNotesPage from "@/components/StudentNotesPage";

// ccrm-010 (DEC-SCOPE-241): a student's internal notes, for the Overseas Admin.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <StudentNotesPage portal="admin" id={id} />;
}
