import { TelecallerLeadPage } from "@/components/TelecallerLeadPages";

// tel-008 (AC2-AC4): one of the telecaller's leads.
export default async function MyLeadPage({ params }: { params: Promise<{ id: string }> }) {
  return <TelecallerLeadPage id={(await params).id} manager={false} />;
}
