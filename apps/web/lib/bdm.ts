// bdm-001 (DEC-SCOPE-052): BDM types, labels and endpoints shared by the BDM pages and the admin BDM page.
export type BdmType = "agent" | "school" | "college";
export type BdmManagerRef = { id: string; full_name: string; active: boolean };
export type BdmProfile = { bdm_type: BdmType; employee_id: string; designation: string | null; department: string | null; territory: string | null; reporting_manager: BdmManagerRef };
export type BdmMe = { id: string; full_name: string; email: string; phone: string | null; active: boolean; division: string; bdm_profile: BdmProfile };
export type BdmTeamRow = {
  id: string; full_name: string; email: string; phone: string | null; active: boolean; bdm_type: BdmType;
  employee_id: string; designation: string | null; department: string | null; territory: string | null;
};
export type BdmAdminRow = BdmTeamRow & { reporting_manager: BdmManagerRef; manager_active: boolean };
export type BdmManagerOption = { id: string; full_name: string };

export const BDM_TYPE_LABEL: Record<BdmType, string> = { agent: "Agent", school: "School", college: "College" };
// Display only -- the API decides (services/bdm.CREATOR_TYPES, D10).
const CREATOR_TYPES: Record<string, BdmType[]> = { super_admin: ["agent", "school", "college"], it_admin: ["college"], overseas_admin: ["agent", "school"] };
export const creatableTypes = (role: string): BdmType[] => CREATOR_TYPES[role] ?? [];
export const statusLabel = (active: boolean) => (active ? "Active" : "Inactive");

// Form readers shared by the create form and the row editor: trimmed text, and "" sent as null (clears an optional field).
export const formText = (form: FormData, name: string) => String(form.get(name) ?? "").trim();
export const formOptional = (form: FormData, name: string) => formText(form, name) || null;

export const BDMS_URL = "/api/v1/admin/bdms";
export const MANAGERS_URL = "/api/v1/admin/bdm-managers";
export const USERS_URL = "/api/v1/admin/users";
export const PAGE_SIZE = 50;
