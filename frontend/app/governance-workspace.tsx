"use client";
import { useCallback, useEffect, useState } from "react";
import { staffApi as api, revision } from "../lib/staff-api";
import IndexRebuild from "./index-rebuild";
import type { S, Purpose } from "./intake-workspace";
export default function GovernanceWorkspace({
  scope,
  global,
  department,
  purpose,
  fail,
}: {
  scope: S["ScopeOut"];
  global: boolean;
  department: boolean;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [kind, setKind] = useState<"rules" | "preferences" | "prompt">(
      department ? "rules" : "prompt",
    ),
    [items, setItems] = useState<S["GovernanceOut"][]>([]),
    [version, setVersion] = useState(0);
  const [course, setCourse] = useState(""),
    [requires, setRequires] = useState(""),
    [maximum, setMaximum] = useState(""),
    [ruleKind, setRuleKind] = useState<"prerequisite" | "course_limit">(
      "prerequisite",
    );
  const [source, setSource] = useState(""),
    [sources, setSources] = useState<S["SourceOut"][]>([]),
    [excerpts, setExcerpts] = useState<S["IndexedExcerptOut"][]>([]),
    [evidence, setEvidence] = useState("");
  const [rules, setRules] = useState<S["Rule"][]>([]),
    [advisor, setAdvisor] = useState(""),
    [program, setProgram] = useState(""),
    [term, setTerm] = useState(""),
    [style, setStyle] = useState<"concise" | "expanded">("concise");
  const [clarifications, setClarifications] = useState<
    NonNullable<S["GovernanceDefinition"]["clarification_fields"]>
  >([]);
  const [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState(""),
    [job, setJob] = useState<S["JobOut"] | null>(null);
  const load = useCallback(async () => {
    const { data: state } = await api.GET("/api/v1/knowledge/state", {
      params: { query: { institution_id: scope.institution_id, purpose } },
    });
    if (state) setVersion(state.version);
    let cursor: string | undefined;
    const rows: S["GovernanceOut"][] = [];
    do {
      const { data } = await api.GET("/api/v1/knowledge/governance", {
        params: {
          query: {
            institution_id: scope.institution_id,
            scope_id: kind === "prompt" ? undefined : scope.id,
            purpose,
            cursor,
          },
        },
      });
      if (!data) return;
      rows.push(...data.items);
      cursor = data.next_cursor ?? undefined;
    } while (cursor);
    setItems(
      rows
        .filter((g) => g.kind === kind)
        .sort((a, b) => b.created_at.localeCompare(a.created_at)),
    );
  }, [scope.id, scope.institution_id, kind, purpose]);
  useEffect(() => {
    let active = true;
    const refresh = () => {
      if (active && !document.hidden) void load().catch(fail);
    };
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [load, fail]);
  useEffect(() => {
    let active = true;
    void (async () => {
      const rows: S["SourceOut"][] = [];
      let cursor: string | undefined;
      do {
        const { data } = await api.GET("/api/v1/sources", {
          params: { query: { scope_id: scope.id, purpose, cursor } },
        });
        if (!data || !active) return;
        rows.push(...data.items);
        cursor = data.next_cursor ?? undefined;
      } while (cursor);
      setSources(rows);
    })().catch(fail);
    return () => {
      active = false;
    };
  }, [scope.id, purpose, fail]);
  useEffect(() => {
    let active = true;
    if (source)
      void (async () => {
        const rows: S["IndexedExcerptOut"][] = [];
        let cursor: string | undefined;
        do {
          const { data } = await api.GET(
            "/api/v1/sources/{sid}/indexed-excerpts",
            { params: { path: { sid: source }, query: { purpose, cursor } } },
          );
          if (!data || !active) return;
          rows.push(...data.items.filter((e) => e.published));
          cursor = data.next_cursor ?? undefined;
        } while (cursor);
        setExcerpts(rows);
      })().catch(fail);
    return () => {
      active = false;
    };
  }, [source, purpose, fail]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.state)) return;
    let active = true;
    const timer = setInterval(() => {
      if (!document.hidden)
        void api
          .GET("/api/v1/jobs/{jid}", {
            params: { path: { jid: job.id }, query: { purpose } },
          })
          .then(({ data }) => {
            if (active && data) {
              setJob(data);
              if (!["queued", "running"].includes(data.state))
                void load().catch(fail);
            }
          })
          .catch(fail);
    }, 2500);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job, load, fail, purpose]);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setStatus("");
    try {
      await work();
      await load();
    } catch (e) {
      setItems([]);
      setExcerpts([]);
      await fail(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Evidence rules and releases">
      <h3>Evidence rules and releases</h3>
      <p>
        Rules require published evidence. Evaluate before activation. Reevaluate
        a previous version to roll back. Access and citation controls remain
        server enforced.
      </p>
      <label>
        Release kind
        <select
          value={kind}
          onChange={(e) => {
            setKind(e.target.value as typeof kind);
            setRules([]);
          }}
        >
          {department && (
            <>
              <option value="rules">Department academic rules</option>
              <option value="preferences">Department terminology</option>
            </>
          )}
          {global && <option value="prompt">Global prompt style</option>}
        </select>
      </label>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void act(async () => {
            const terminology: S["GovernanceDefinition"]["terminology"] = {};
            if (advisor) terminology.advisor = advisor;
            if (program) terminology.program = program;
            if (term) terminology.term = term;
            await api.POST("/api/v1/knowledge/governance", {
              headers: revision(version),
              body: {
                institution_id: scope.institution_id,
                org_unit_id: kind === "prompt" ? null : scope.id,
                kind,
                definition: {
                  rules: kind === "rules" ? rules : [],
                  terminology: kind === "preferences" ? terminology : {},
                  clarification_fields:
                    kind === "preferences" ? clarifications : [],
                  style,
                },
              },
            });
            setStatus("Immutable release saved. Evaluate before activation.");
          });
        }}
      >
        {kind === "rules" && (
          <fieldset disabled={busy}>
            <legend>Reviewed rule</legend>
            <label>
              Course or rule identifier
              <input
                value={course}
                maxLength={40}
                onChange={(e) => setCourse(e.target.value)}
              />
            </label>
            <label>
              Rule type
              <select
                value={ruleKind}
                onChange={(e) => setRuleKind(e.target.value as typeof ruleKind)}
              >
                <option value="prerequisite">Prerequisite</option>
                <option value="course_limit">Maximum course count</option>
              </select>
            </label>
            {ruleKind === "prerequisite" ? (
              <label>
                Required courses, comma separated
                <input
                  value={requires}
                  onChange={(e) => setRequires(e.target.value)}
                />
              </label>
            ) : (
              <label>
                Maximum courses
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={maximum}
                  onChange={(e) => setMaximum(e.target.value)}
                />
              </label>
            )}
            <label>
              Published source
              <select
                value={source}
                onChange={(e) => {
                  setSource(e.target.value);
                  setExcerpts([]);
                  setEvidence("");
                }}
              >
                <option value="">Choose reviewed evidence</option>
                {sources.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.metadata.title}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Supporting excerpt
              <select
                value={evidence}
                onChange={(e) => setEvidence(e.target.value)}
              >
                <option value="">Choose an excerpt</option>
                {excerpts.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.text.slice(0, 140)}
                  </option>
                ))}
              </select>
            </label>
            {excerpts.find((e) => e.id === evidence) && (
              <blockquote>
                {excerpts.find((e) => e.id === evidence)?.text}
              </blockquote>
            )}
            <button
              type="button"
              disabled={
                !course ||
                !evidence ||
                (ruleKind === "prerequisite" ? !requires : !maximum)
              }
              onClick={() => {
                setRules([
                  ...rules,
                  {
                    course_id: course,
                    kind: ruleKind,
                    requires:
                      ruleKind === "prerequisite"
                        ? requires
                            .split(",")
                            .map((s) => s.trim())
                            .filter(Boolean)
                        : [],
                    maximum:
                      ruleKind === "course_limit" ? Number(maximum) : null,
                    evidence_id: evidence,
                  },
                ]);
                setCourse("");
              }}
            >
              Add reviewed rule
            </button>
            {rules.map((r, i) => (
              <p key={i}>
                {r.course_id}:{" "}
                {r.kind === "prerequisite" ? r.requires?.join(", ") : r.maximum}
                <button
                  type="button"
                  onClick={() => setRules(rules.filter((_, j) => i !== j))}
                >
                  Remove {r.course_id}
                </button>
              </p>
            ))}
          </fieldset>
        )}
        {kind === "preferences" && (
          <>
            <label>
              Advisor label
              <input
                maxLength={200}
                value={advisor}
                onChange={(e) => setAdvisor(e.target.value)}
              />
            </label>
            <label>
              Program label
              <input
                maxLength={200}
                value={program}
                onChange={(e) => setProgram(e.target.value)}
              />
            </label>
            <label>
              Term label
              <input
                maxLength={200}
                value={term}
                onChange={(e) => setTerm(e.target.value)}
              />
            </label>
          </>
        )}
        <label>
          Answer style
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value as typeof style)}
          >
            <option value="concise">Concise</option>
            <option value="expanded">Expanded</option>
          </select>
        </label>
        <button disabled={busy}>Save release draft</button>
      </form>
      {kind === "preferences" && (
        <fieldset>
          <legend>Facts to clarify before answering</legend>
          {(
            [
              "program",
              "catalog_year",
              "completed_courses",
              "current_term",
            ] as const
          ).map((k) => (
            <label key={k}>
              <input
                type="checkbox"
                checked={clarifications.includes(k)}
                onChange={(e) =>
                  setClarifications(
                    e.target.checked
                      ? [...clarifications, k]
                      : clarifications.filter((v) => v !== k),
                  )
                }
              />
              {k.replaceAll("_", " ")}
            </label>
          ))}
        </fieldset>
      )}
      {global && (
        <IndexRebuild
          institution={scope.institution_id}
          purpose={purpose}
          fail={fail}
        />
      )}
      <label>
        Activation or rollback reason
        <input
          value={reason}
          maxLength={1000}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {job && (
        <p role="status">
          Evaluation {job.state}
          {job.error_code ? `: ${job.error_code}` : ""}
        </p>
      )}
      {items.map((g) => (
        <article key={g.id}>
          <h4>
            {g.kind} release · {g.active ? "active" : "inactive"}
          </h4>
          <p>
            {new Date(g.created_at).toLocaleString()} ·{" "}
            {g.evaluation_passed
              ? "Passing recorded evaluation"
              : "Passing evaluation required"}
          </p>
          <details>
            <summary>Review settings</summary>
            <pre>{JSON.stringify(g.definition, null, 2)}</pre>
          </details>
          <button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                const { data } = await api.POST(
                  "/api/v1/knowledge/governance/{gid}/evaluate",
                  { params: { path: { gid: g.id } }, headers: revision(0) },
                );
                if (data) setJob(data);
                setStatus("Evaluation queued.");
              })
            }
          >
            Evaluate release
          </button>
          <button
            disabled={
              busy || !reason || !g.evaluation_passed || !g.evaluation_id
            }
            onClick={() =>
              void act(async () => {
                if (!g.evaluation_id) return;
                await api.POST("/api/v1/knowledge/governance/{gid}/activate", {
                  params: { path: { gid: g.id } },
                  headers: revision(version),
                  body: { evaluation_id: g.evaluation_id, reason },
                });
                setStatus("Evaluated release activated.");
              })
            }
          >
            Activate evaluated version
          </button>
        </article>
      ))}
      <p role="status">{busy ? "Saving…" : status}</p>
    </section>
  );
}
