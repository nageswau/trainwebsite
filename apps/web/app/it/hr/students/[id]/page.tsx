import HrStudentPage from "@/components/HrStudentPage";

// nehn-017 (DEC-SCOPE-310): one student's training, read only.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <HrStudentPage id={id} />;
}
