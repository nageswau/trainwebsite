"use client";
import { useState } from "react";

import AdminSchoolCreatePanel from "@/components/AdminSchoolCreatePanel";
import AdminSchoolOnboardingRequests from "@/components/AdminSchoolOnboardingRequests";
import type { OnboardingItem } from "@/lib/bdmOnboarding";
import { useFocusAfterRender } from "@/lib/useFocusAfterRender";

// bdm-018 (spec §6): the onboarding queue and the SCH-003 create form share the chosen request -- choosing one prefills the form,
// creating clears it and reloads the queue, and a request resolved in the queue (linked or rejected) stops being the form's.
export default function AdminSchoolOnboarding() {
  const [request, setRequest] = useState<OnboardingItem | null>(null);
  const [version, setVersion] = useState(0);
  const focus = useFocusAfterRender();
  return (
    <>
      <AdminSchoolOnboardingRequests
        selectedId={request?.id ?? null}
        version={version}
        onUse={(item) => {
          setRequest(item);
          focus("school-name");
        }}
        onResolved={(id) => setRequest((current) => (current?.id === id ? null : current))}
      />
      <AdminSchoolCreatePanel
        request={request}
        onClear={() => setRequest(null)}
        onCreated={() => {
          setRequest(null);
          setVersion((v) => v + 1);
        }}
      />
    </>
  );
}
