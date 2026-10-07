import CounselorLeadPage from "@/components/CounselorLeadPage";

// tel-018 (DEC-SCOPE-099): a lead handed to this counselor.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <CounselorLeadPage division="overseas" id={id} />;
}
