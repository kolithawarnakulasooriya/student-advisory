"use client";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";

export function SafeText({ text }: { text: string }) {
  return (
    <ReactMarkdown
      skipHtml
      rehypePlugins={[rehypeSanitize]}
      urlTransform={(url) => (/^(https?:\/\/|\/(?!\/))/.test(url) ? url : "")}
      components={{
        img: () => null,
        a: ({ href, children }) => (
          <a href={href} rel="noopener noreferrer" target="_blank">
            {children}
          </a>
        ),
      }}
    >
      {text}
    </ReactMarkdown>
  );
}
const records = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter(
        (v): v is Record<string, unknown> => !!v && typeof v === "object",
      )
    : [];
export function quoteText(payload: Record<string, unknown>): string {
  return records(payload.citations)
    .map((c) =>
      typeof c.quote === "string" ? c.quote : "[Evidence withdrawn]",
    )
    .join("\n\n");
}
export default function AdvisingAnswer({
  payload,
  onCitation,
}: {
  payload: Record<string, unknown>;
  onCitation: (id: string) => void;
}) {
  const citations = records(payload.citations),
    guidance = records(payload.guidance),
    checks = records(payload.rule_checks);
  return (
    <section
      className="advising-answer"
      aria-label="Validated assistant answer"
    >
      <h5>Assistant · validated response</h5>
      {payload.stale === true && (
        <p className="notice">
          Historical response: the profile, guidance, assignment, or knowledge
          context has changed. Ask again for a current response.
        </p>
      )}
      <p>
        {payload.status === "answered"
          ? "Published evidence for your question:"
          : payload.status === "needs_clarification"
            ? "Please review the missing or disputed profile facts, or ask a shorter question."
            : "The available evidence needs human review before a definitive answer can be given."}
      </p>
      {String(payload.reason_code ?? "").includes("POLICY") && (
        <p>
          Advisor preferences do not approve a policy waiver. Ask your advisor
          to review the applicable requirements.
        </p>
      )}
      {Array.isArray(payload.missing_fields) && (
        <p>
          Review:{" "}
          {payload.missing_fields
            .map(String)
            .map((s) => s.replaceAll("_", " "))
            .join(", ")}
        </p>
      )}
      {citations.map((c) => (
        <div key={String(c.id)}>
          <blockquote>
            {typeof c.quote === "string"
              ? c.quote
              : "This evidence has been withdrawn."}
          </blockquote>
          <button type="button" onClick={() => onCitation(String(c.id))}>
            View evidence: {String(c.title)}
          </button>
          <span> · {String(c.status)}</span>
        </div>
      ))}
      {!!guidance.length && (
        <div>
          <h6>Advisor guidance considered for this reply</h6>
          {guidance.map((g) => (
            <div key={String(g.id)}>
              <SafeText text={String(g.text)} />
              {g.preferences != null &&
                typeof g.preferences === "object" &&
                (g.preferences as Record<string, unknown>).max_courses !=
                  null && (
                  <p>
                    Planning preference: at most{" "}
                    {String(
                      (g.preferences as Record<string, unknown>).max_courses,
                    )}{" "}
                    courses. Official limits still apply.
                  </p>
                )}
            </div>
          ))}
        </div>
      )}
      {checks.map((r, i) => (
        <p key={i}>
          {String(r.course_id)} · {String(r.kind).replaceAll("_", " ")}:{" "}
          {String(r.result).replaceAll("_", " ")}
          {r.maximum != null ? ` (${String(r.maximum)})` : ""}. Student reports
          do not establish institutional eligibility.
        </p>
      ))}
    </section>
  );
}
