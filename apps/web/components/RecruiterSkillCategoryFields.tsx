"use client";
import { useState } from "react";

import type { SkillCategory, SkillRef } from "@/lib/recruiterSkills";

// rec-006 (S5): a skill's primary category and its other categories (tags), shared by the create and edit forms. Only active categories
// are offered, except the skill's current ones (a since-deactivated category may be kept); the primary is never offered as a tag.
export default function RecruiterSkillCategoryFields({ idPrefix, categories, current, disabled }: {
  idPrefix: string;
  categories: SkillCategory[];
  current?: { category: SkillRef; tags: SkillRef[] };
  disabled: boolean;
}) {
  const [primary, setPrimary] = useState(current?.category.id ?? "");
  const kept = current ? [current.category, ...current.tags] : [];
  const offered = [...categories.filter((c) => c.active), ...kept.filter((k) => !categories.some((c) => c.id === k.id && c.active))];
  const choices = offered.filter((c, i) => offered.findIndex((x) => x.id === c.id) === i);
  const tagIds = new Set(current?.tags.map((t) => t.id));
  return (
    <>
      <div className="field">
        <label htmlFor={`${idPrefix}-category`}>Category (required)</label>
        <select id={`${idPrefix}-category`} name="category_id" value={primary} onChange={(e) => setPrimary(e.target.value)} required disabled={disabled}>
          <option value="" disabled>Choose a category</option>
          {choices.map((c) => <option key={c.id} value={c.id}>{c.name}{c.active ? "" : " (inactive)"}</option>)}
        </select>
      </div>
      <fieldset className="field" role="group" aria-label="Other categories" disabled={disabled} style={{ border: 0, padding: 0, margin: 0 }}>
        <legend className="muted" style={{ fontSize: 13 }}>Other categories (optional)</legend>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "4px 12px" }}>
          {choices.filter((c) => c.id !== primary).map((c) => (
            <label key={c.id} style={{ display: "inline-flex", gap: 4, alignItems: "center" }}>
              <input type="checkbox" name="tag_category_ids" value={c.id} defaultChecked={tagIds.has(c.id)} />
              {c.name}{c.active ? "" : " (inactive)"}
            </label>
          ))}
        </div>
      </fieldset>
    </>
  );
}
