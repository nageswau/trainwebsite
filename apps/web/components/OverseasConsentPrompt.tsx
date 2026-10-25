import OverseasConsentCard from "@/components/OverseasConsentCard";
import { serverApi } from "@/lib/api";
import { MY_CONSENTS_URL, type MyConsent } from "@/lib/overseasConsents";

/** ccrm-040 (DEC-SCOPE-276 CN2): reads the student's consents for the dashboard; a failed read shows nothing (the dashboard still works). */
export default async function OverseasConsentPrompt() {
  const data = await serverApi<{ items: MyConsent[] }>(MY_CONSENTS_URL).catch(() => null);
  return data ? <OverseasConsentCard items={data.items} /> : null;
}
