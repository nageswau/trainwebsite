"use client";

import { useState } from "react";

import TelecallerImportHistory from "@/components/TelecallerImportHistory";
import TelecallerLeadImportPanel from "@/components/TelecallerLeadImportPanel";

// tel-006: the upload panel and the history it refreshes after each import.
export default function TelecallerLeadImports() {
  const [version, setVersion] = useState(0);
  return (
    <>
      <TelecallerLeadImportPanel onImported={() => setVersion((v) => v + 1)} />
      <TelecallerImportHistory version={version} />
    </>
  );
}
