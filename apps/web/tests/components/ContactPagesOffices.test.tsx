import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import Contact from "@/app/contact/page";
import ITContact from "@/app/it/contact/page";
import OverseasContact from "@/app/overseas/contact/page";
import { OFFICES } from "@/lib/offices";

// PUB-024: the header, footer and enquiry form are not under test; the offices block on each contact page is.
vi.mock("@/components/SiteHeader", () => ({ default: () => <header>site header</header> }));
vi.mock("@/components/Footer", () => ({ default: () => <footer>site footer</footer> }));
vi.mock("@/components/EnquiryForm", () => ({ default: () => <form aria-label="enquiry" /> }));

afterEach(cleanup);

const pages = [
  ["/contact", Contact],
  ["/it/contact", ITContact],
  ["/overseas/contact", OverseasContact],
] as const;

describe("contact pages show the three offices (PUB-024)", () => {
  it.each(pages)("%s lists every office with its address and directions link", (_path, Page) => {
    render(<Page />);
    const block = screen.getByRole("region", { name: "Our offices" });
    for (const office of OFFICES) {
      expect(within(block).getByRole("heading", { name: office.city })).toBeTruthy();
      expect(within(block).getByText(office.address)).toBeTruthy();
    }
    expect(within(block).getAllByRole("link", { name: /^Get directions/ })).toHaveLength(3);
  });

  it("the IT contact page no longer shows the address placeholder", () => {
    render(<ITContact />);
    expect(screen.queryByText(/after the client confirms the final office address/)).toBeNull();
  });
});
