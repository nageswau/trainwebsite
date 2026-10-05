import { DOCUMENT_TYPES, OTHER } from "@/lib/agentDocuments";

// AGN-009 (G3): the fixed document type list, plus the description "Other" needs -- shared by the upload and request forms. Ids are
// `<idPrefix>-type` / `<idPrefix>-label`; the description is submitted as `document_label`. AGN-010: the upload form passes
// UPLOAD_DOCUMENT_TYPES (adds "Offer letter"); the request form keeps the default list.
export default function AgentDocumentTypeField({
  idPrefix,
  value,
  onChange,
  types = DOCUMENT_TYPES,
}: {
  idPrefix: string;
  value: string;
  onChange: (type: string) => void;
  types?: readonly string[];
}) {
  return (
    <>
      <div className="field">
        <label htmlFor={`${idPrefix}-type`}>Document type</label>
        <select id={`${idPrefix}-type`} value={value} onChange={(e) => onChange(e.target.value)}>
          {types.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>
      {value === OTHER && (
        <div className="field">
          <label htmlFor={`${idPrefix}-label`}>Description</label>
          <input id={`${idPrefix}-label`} name="document_label" required minLength={2} maxLength={80} />
        </div>
      )}
    </>
  );
}
