import HrReviewQueuePage from "@/components/HrReviewQueuePage";

// itc-027 (DEC-SCOPE-353): HR's resume-review queue (a static route wins over [section]).
export default async function Page({ searchParams }: { searchParams: Promise<Record<string, string | string[] | undefined>> }) {
  return <HrReviewQueuePage searchParams={await searchParams} />;
}
