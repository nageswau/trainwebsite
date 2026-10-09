import TargetsEditor from "@/components/TargetsEditor";
import { TEAM_TARGETS_URL, type TargetSheet } from "@/lib/bdmTargets";

// bdm-016 (spec §6): one BDM's month, on the shared targets editor (upc-021 reuses it for partnership managers).
export default function BdmTargetsEditor({ initial }: { initial: TargetSheet }) {
  return <TargetsEditor initial={initial} ownerId={initial.bdm.id} ownerField="bdm_user_id" saveUrl={TEAM_TARGETS_URL} />;
}
