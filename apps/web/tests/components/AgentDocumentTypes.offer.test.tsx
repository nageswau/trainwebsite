import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import AgentDocumentRequestForm from "@/components/AgentDocumentRequestForm";
import AgentDocumentUploadForm from "@/components/AgentDocumentUploadForm";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Offer letter document type (AGN-010)", () => {
  it("is an upload type that makes the application required", () => {
    render(<AgentDocumentUploadForm onUploaded={vi.fn()} />);
    const type = screen.getByLabelText("Document type");
    expect(within(type).getByRole("option", { name: "Offer letter" })).toBeInTheDocument();
    expect(screen.getByLabelText("Application (optional)")).not.toBeRequired();
    fireEvent.change(type, { target: { value: "Offer letter" } });
    expect(screen.getByLabelText("Application (required for an offer letter)")).toBeRequired();
  });

  it("is never requested from a student", () => {
    render(<AgentDocumentRequestForm onCreated={vi.fn()} />);
    expect(within(screen.getByLabelText("Document type")).queryByRole("option", { name: "Offer letter" })).toBeNull();
  });
});
