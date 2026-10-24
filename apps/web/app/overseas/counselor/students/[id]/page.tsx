import OverseasStudent360Page from "@/components/OverseasStudent360Page";
import { studentTab } from "@/lib/overseasStudent360";

// ccrm-009 (DEC-SCOPE-253): the student 360, for the student's counselor.
export default async function Page({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ tab?: string | string[] }> }) {
  const [{ id }, { tab }] = await Promise.all([params, searchParams]);
  return <OverseasStudent360Page portal="counselor" id={id} tab={studentTab(tab)} />;
}
