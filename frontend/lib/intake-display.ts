// Render evidence as plain text with useful locators, without exposing parser internals.
export function factText(value: unknown): string {
  if (value == null || value === "") return "Unknown";
  if (Array.isArray(value)) {
    if (!value.length) return "None supplied";
    return value
      .map((course) => {
        if (typeof course !== "object" || !course || !("course_id" in course))
          return "Unknown course";
        const completion =
          course.completed === true
            ? "reported complete"
            : course.completed === false
              ? "not completed"
              : "completion unknown";
        return `${String(course.course_id)} (${completion}${course.grade ? `; grade ${String(course.grade)}` : ""})`;
      })
      .join("; ");
  }
  return String(value);
}

export function extractionText(value: unknown): string {
  if (
    typeof value !== "object" ||
    !value ||
    !("segments" in value) ||
    !Array.isArray(value.segments)
  )
    throw new Error(
      "The extracted document is unavailable. Refresh and retry.",
    );
  return value.segments
    .map((segment) => {
      if (
        typeof segment !== "object" ||
        !segment ||
        typeof segment.text !== "string"
      )
        throw new Error(
          "The extracted document is unavailable. Refresh and retry.",
        );
      const locator = [
        segment.page ? `Page ${String(segment.page)}` : "",
        segment.heading ? String(segment.heading) : "",
        segment.paragraph ? `Paragraph ${String(segment.paragraph)}` : "",
        segment.line ? `Line ${String(segment.line)}` : "",
        segment.table
          ? `Table ${String(segment.table)}, row ${String(segment.row)}`
          : "",
      ]
        .filter(Boolean)
        .join(" · ");
      return `${locator}\n${segment.text}`;
    })
    .join("\n\n");
}
