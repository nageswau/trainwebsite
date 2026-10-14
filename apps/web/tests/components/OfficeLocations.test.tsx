import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import OfficeLocations from "@/components/OfficeLocations";
import { OFFICES, mapsUrl } from "@/lib/offices";

afterEach(cleanup);

describe("OFFICES (PUB-024)", () => {
  it("lists the three owner-given offices in order with their tidied addresses", () => {
    expect(OFFICES.map((o) => o.city)).toEqual(["Bengaluru", "Hyderabad", "Tadepalligudem"]);
    expect(OFFICES[0].address).toBe("#57, B.B. Road, Allasandra Gate, G.K.V.K. Post, Yelahanka, Bengaluru – 560065");
    expect(OFFICES[1].address).toBe("Shop No. 1, Raja Rajeshwari Residency Apartments, Employees' Colony, Bapuji Nagar Road, Yapral, Hyderabad – 500087");
    expect(OFFICES[2].address).toBe("KK Plaza, 1st Floor, Opp. Sonovision, KN Road, Gollagudem Center, Tadepalligudem, West Godavari District, Andhra Pradesh – 534102");
  });
  it("builds an encoded Google Maps search URL from the address", () => {
    expect(mapsUrl("#57, B.B. Road")).toBe("https://www.google.com/maps/search/?api=1&query=%2357%2C%20B.B.%20Road");
  });
});

describe("OfficeLocations (PUB-024)", () => {
  it("renders one card per office with heading, address and a new-tab directions link", () => {
    render(<OfficeLocations />);
    const cards = screen.getAllByRole("article");
    expect(cards).toHaveLength(3);
    OFFICES.forEach((office, i) => {
      const card = within(cards[i]);
      expect(card.getByRole("heading", { name: office.city })).toBeTruthy();
      expect(cards[i].querySelector("address")?.textContent).toBe(office.address);
      const link = card.getByRole("link", { name: `Get directions to the ${office.city} office (opens in a new tab)` });
      expect(link.getAttribute("href")).toBe(mapsUrl(office.address));
      expect(link.getAttribute("target")).toBe("_blank");
      expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    });
  });
  it("uses the given heading level and title", () => {
    render(<OfficeLocations title="Visit us" headingLevel={3} />);
    expect(screen.getByRole("heading", { level: 3, name: "Visit us" })).toBeTruthy();
    expect(screen.getAllByRole("heading", { level: 4 })).toHaveLength(3);
  });
});
