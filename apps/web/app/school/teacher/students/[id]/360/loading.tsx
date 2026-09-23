import { Student360Loading } from "@/components/Student360Route";
import { SCHOOL_NAV } from "@/lib/navigation";

export default function Loading() {
  return <Student360Loading nav={SCHOOL_NAV.teacher} roleLabel="Teacher" />;
}
