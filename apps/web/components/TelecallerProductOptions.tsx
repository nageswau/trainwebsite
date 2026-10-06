import { GROUPS, GROUP_LABEL, type Product } from "@/lib/telecallerCatalogue";

// tel-002: the shared product picker's options, one <optgroup> per §3 group (IT Courses, Overseas Education, Other). Pass active
// products (lib/telecallerCatalogue.activeProducts); tel-003's lead form reuses it.
export default function TelecallerProductOptions({ products }: { products: Product[] }) {
  return GROUPS.map((group) => {
    const items = products.filter((p) => p.group === group);
    return items.length > 0 && (
      <optgroup key={group} label={GROUP_LABEL[group]}>
        {items.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </optgroup>
    );
  });
}
