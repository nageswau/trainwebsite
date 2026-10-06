import { TelecallerLeadPage } from "@/components/TelecallerLeadPages";

// tel-008 (D5): one lead in the manager's scope.
export default async function TeamLeadPage({ params }: { params: Promise<{ id: string }> }) {
  return <TelecallerLeadPage id={(await params).id} manager />;
}
