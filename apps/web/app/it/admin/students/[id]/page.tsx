import ItStudent360Page from "@/components/ItStudent360Page";

// itc-029 (DEC-SCOPE-358): the IT student 360 -- contact, lead history, courses, fees, risk, feedback, resume, HR stage, notes, notices.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ItStudent360Page portal="admin" id={id} />;
}
