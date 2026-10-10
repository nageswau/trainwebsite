import MapHoverPanel from "@/components/MapHoverPanel";
import { colourOf, countLabel, countryHref, type MapCountry, type MapFilters } from "@/lib/partnershipMap";
import { SHAPES, VIEW_BOX } from "@/lib/worldMapShapes";

// upc-025 (MP11-MP14): the inline SVG world map, rendered on the server so the ~230 KB of shapes never reach the client bundle. Each
// country with a matching university is an SVG link to its university list -- in the tab order, opened by Enter or a click, named with
// its four counts -- and a small country also gets a marker. Countries with none are decorative. The hover/focus panel reads the counts
// from the link's data attributes.
export default function PartnershipWorldMap({ countries, filters }: { countries: MapCountry[]; filters: MapFilters }) {
  const drawn = countries.filter((c) => c.iso2 && SHAPES[c.iso2]);
  const linked = new Set(drawn.map((c) => c.iso2));
  return (
    <MapHoverPanel>
      <svg className="world-map" viewBox={VIEW_BOX} role="group" aria-label="World map of university partnerships">
        <g aria-hidden="true">
          {Object.entries(SHAPES).filter(([iso2]) => !linked.has(iso2)).map(([iso2, shape]) => (
            <path key={iso2} d={shape.d} className="map-country map-none" />
          ))}
        </g>
        {drawn.map((c) => {
          const shape = SHAPES[c.iso2 as string];
          return (
            <a key={c.iso2} href={countryHref(filters, c.iso2 as string)} aria-label={countLabel(c)} className={`map-link map-${colourOf(c)}`}
              data-name={c.name} data-partner={c.partner} data-in-progress={c.in_progress} data-target={c.target} data-lost={c.lost}>
              <path d={shape.d} className="map-country" />
              {shape.small && <circle cx={shape.x} cy={shape.y} r={7} className="map-marker" />}
            </a>
          );
        })}
      </svg>
    </MapHoverPanel>
  );
}
