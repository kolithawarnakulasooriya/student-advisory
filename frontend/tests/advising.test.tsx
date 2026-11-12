import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import AdvisingAnswer, { SafeText } from "../app/advising-answer";
describe("Verified evidence presentation", () => {
  it("renders source quotes, stale context and authorized evidence actions", () => {
    const view = vi.fn();
    render(
      <AdvisingAnswer
        onCitation={view}
        payload={{
          status: "answered",
          stale: true,
          citations: [
            {
              id: "synthetic-e1",
              title: "Synthetic catalog",
              quote: "SYN102 requires SYN101.",
              status: "published",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("SYN102 requires SYN101.")).toBeVisible();
    expect(screen.getByText(/Historical response/)).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "View evidence: Synthetic catalog" }),
    );
    expect(view).toHaveBeenCalledWith("synthetic-e1");
  });
  it("does not render source HTML, images or unsafe URLs", () => {
    const { container } = render(
      <SafeText
        text={
          "<script>window.privateData()</script>\n\n[unsafe](javascript:alert(1))\n\n![tracker](https://example.invalid/track)"
        }
      />,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect((container.querySelector("a")?.getAttribute("href") ?? "")).not.toMatch(
      /^javascript:/,
    );
  });
  it("keeps withdrawn evidence redacted", () => {
    render(
      <AdvisingAnswer
        onCitation={() => {}}
        payload={{
          status: "answered",
          citations: [
            {
              id: "e1",
              title: "Withdrawn synthetic source",
              quote: null,
              status: "withdrawn",
            },
          ],
        }}
      />,
    );
    expect(screen.getByText("This evidence has been withdrawn.")).toBeVisible();
  });
});
