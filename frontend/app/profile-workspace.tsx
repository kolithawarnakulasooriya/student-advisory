"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { factText } from "../lib/intake-display";
import { staffApi as api, revision } from "../lib/staff-api";
import { pretty, type S, type Purpose } from "./intake-workspace";

type Facts = Record<string, S["FactInput"]>;
type Course = { course_id: string; grade?: string; completed?: boolean | null };
export default function ProfileWorkspace({
  mid,
  own,
  reviewer,
  purpose,
  fail,
}: {
  mid: string;
  own: boolean;
  reviewer: boolean;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [profile, setProfile] = useState<S["ProfileOut"] | null>(null);
  const [schema, setSchema] = useState<S["SchemaOut"] | null>(null);
  const [facts, setFacts] = useState<Facts>({});
  const [reviewing, setReviewing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [field, setField] = useState("");
  const [decision, setDecision] = useState<"confirmed" | "disputed">(
    "confirmed",
  );
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState<S["ProfileOut"][]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  const load = useCallback(async () => {
    const { data } = await api.GET("/api/v1/students/{mid}/profile", {
      params: { path: { mid }, query: { purpose } },
    });
    if (!data || !alive.current) return;
    setProfile(data);
    setSchema(data.schema);
    setFacts(
      Object.fromEntries(
        Object.entries(data.facts).map(([key, f]) => [
          key,
          {
            value: f.value,
            effective_term: f.effective_term,
            last_confirmed: f.last_confirmed,
          },
        ]),
      ),
    );
    setReviewing(false);
    setConfirmed(false);
  }, [mid, purpose]);
  const handleError = useCallback(
    async (e: unknown) => {
      if (!alive.current) return;
      setError(e instanceof Error ? e.message : "Unable to load the profile.");
      if (e instanceof ApiError && [401, 403, 404, 409].includes(e.status)) {
        setProfile(null);
        setFacts({});
        setSchema(null);
        setHistory([]);
        setReviewing(false);
        setConfirmed(false);
        if (e.status === 409)
          setError("The profile changed. Refresh and review it again.");
        else await fail(e);
      }
    },
    [fail],
  );
  useEffect(() => {
    alive.current = true;
    void load().catch(handleError);
    return () => {
      alive.current = false;
    };
  }, [load, handleError]);
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await work();
    } catch (e) {
      await handleError(e);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function change(key: string, value: unknown) {
    setFacts((old) => ({ ...old, [key]: { ...old[key], value } }));
    setConfirmed(false);
  }
  async function save(complete: boolean) {
    if (!profile || !schema) return;
    const keys = new Set(schema.definition.fields.map((q) => q.key));
    await api.PATCH("/api/v1/students/{mid}/profile", {
      params: { path: { mid } },
      headers: revision(profile.version),
      body: {
        schema_id: schema.id,
        status: complete ? "complete" : "draft",
        catalog_confirmed: confirmed,
        facts: Object.fromEntries(
          Object.entries(facts).filter(([key]) => keys.has(key)),
        ),
      },
    });
    if (!alive.current) return;
    await load();
    setStatus(
      complete
        ? "Profile setup complete."
        : "Draft saved. You can return later.",
    );
  }
  return (
    <div>
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => void action(load)}>Refresh profile</button>
        </p>
      )}
      <p role="status">{busy ? "Saving…" : status}</p>
      {!profile && !error && <p role="status">Loading profile…</p>}
      {profile && (
        <>
          <h3>Academic profile · {pretty(profile.status)}</h3>
          <p>
            Revision {profile.version}. College and department come from the
            approved membership. Student-entered facts are self-reported.
          </p>
          {profile.missing_fields.length > 0 && (
            <p>
              Missing facts: {profile.missing_fields.map(pretty).join(", ")}
            </p>
          )}
          {profile.schema_update_available && (
            <p className="notice">
              A newer department schema is available. Your historical version is
              retained.{" "}
              {own && (
                <button
                  onClick={() =>
                    void action(async () => {
                      const { data } = await api.GET(
                        "/api/v1/departments/{oid}/onboarding-schemas",
                        { params: { path: { oid: profile.org_unit_id } } },
                      );
                      if (!alive.current) return;
                      const next = data?.schemas.find(
                        (s) => s.id === data.active_schema_id,
                      );
                      if (next) {
                        setSchema(next);
                        setConfirmed(false);
                        setReviewing(false);
                        setStatus(
                          "Review the new questions and save to adopt the schema.",
                        );
                      }
                    })
                  }
                >
                  Review new schema
                </button>
              )}
            </p>
          )}
          {!schema && (
            <p>
              The department manager must configure onboarding before setup can
              begin.
            </p>
          )}
          {schema && !reviewing && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(() => save(false));
              }}
            >
              <fieldset disabled={!own || busy}>
                <legend>Academic facts</legend>
                {schema.definition.fields.map((q) => (
                  <div className="academic-field" key={q.key}>
                    {q.kind === "courses" ? (
                      <Courses
                        label={q.label}
                        value={
                          Array.isArray(facts[q.key]?.value)
                            ? (facts[q.key].value as Course[])
                            : []
                        }
                        onChange={(v) => change(q.key, v)}
                      />
                    ) : (
                      <label>
                        {q.label}
                        {q.required ? " (required to complete)" : ""}
                        {q.kind === "choice" || q.key.endsWith("_term") ? (
                          <select
                            value={String(facts[q.key]?.value ?? "")}
                            onChange={(e) => change(q.key, e.target.value)}
                          >
                            <option value="">Unknown / not supplied</option>
                            {(q.key.endsWith("_term")
                              ? schema.definition.terms
                              : (q.choices ?? [])
                            ).map((c) => (
                              <option key={c}>{c}</option>
                            ))}
                          </select>
                        ) : q.kind === "number" ? (
                          <input
                            type="number"
                            min="0"
                            max="1000"
                            value={String(facts[q.key]?.value ?? "")}
                            onChange={(e) =>
                              change(
                                q.key,
                                e.target.value === ""
                                  ? null
                                  : Number(e.target.value),
                              )
                            }
                          />
                        ) : (
                          <textarea
                            maxLength={4000}
                            value={String(facts[q.key]?.value ?? "")}
                            onChange={(e) => change(q.key, e.target.value)}
                          />
                        )}
                      </label>
                    )}
                    <details>
                      <summary>
                        Provenance and effective term for {q.label}
                      </summary>
                      <p>
                        {profile.facts[q.key]
                          ? `Student entered · self reported · recorded ${profile.facts[q.key].recorded_at}`
                          : "No fact supplied. Completion is unknown."}
                      </p>
                      <label>
                        Effective term for {q.label}
                        <select
                          value={facts[q.key]?.effective_term ?? ""}
                          onChange={(e) =>
                            setFacts((old) => ({
                              ...old,
                              [q.key]: {
                                ...old[q.key],
                                value: old[q.key]?.value ?? null,
                                effective_term: e.target.value || null,
                              },
                            }))
                          }
                        >
                          <option value="">Unknown</option>
                          {schema.definition.terms.map((t) => (
                            <option key={t}>{t}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Last confirmed date for {q.label}
                        <input
                          type="date"
                          value={facts[q.key]?.last_confirmed ?? ""}
                          onChange={(e) =>
                            setFacts((old) => ({
                              ...old,
                              [q.key]: {
                                ...old[q.key],
                                value: old[q.key]?.value ?? null,
                                last_confirmed: e.target.value || null,
                              },
                            }))
                          }
                        />
                      </label>
                    </details>
                  </div>
                ))}
              </fieldset>
              {own && (
                <>
                  <button disabled={busy}>Save profile draft</button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => setReviewing(true)}
                  >
                    Review profile
                  </button>
                </>
              )}
            </form>
          )}
          {reviewing && (
            <div>
              <h3>Review your profile</h3>
              <dl>
                {schema?.definition.fields.map((q) => (
                  <div key={q.key}>
                    <dt>{q.label}</dt>
                    <dd>
                      {facts[q.key]?.value == null || facts[q.key]?.value === ""
                        ? "Unknown"
                        : factText(facts[q.key].value)}
                    </dd>
                  </div>
                ))}
              </dl>
              <label>
                <input
                  type="checkbox"
                  checked={confirmed}
                  onChange={(e) => setConfirmed(e.target.checked)}
                />
                I reviewed my facts and confirmed my catalog year.
              </label>
              <button
                disabled={!confirmed || busy}
                onClick={() => void action(() => save(true))}
              >
                Confirm and complete profile
              </button>
              <button onClick={() => setReviewing(false)}>
                Back to edit profile
              </button>
            </div>
          )}
          <h3>Advisor confirmations and disputes</h3>
          <p>
            Advisor review is separate from institutional verification and
            cannot approve a waiver.
          </p>
          {profile.reviews.length ? (
            profile.reviews.map((r, i) => (
              <p key={i}>
                {pretty(r.field)}: {r.decision} — {r.reason}
              </p>
            ))
          ) : (
            <p>No advisor reviews.</p>
          )}
          {reviewer && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(async () => {
                  await api.POST("/api/v1/students/{mid}/profile/reviews", {
                    params: { path: { mid } },
                    headers: revision(profile.version),
                    body: { field, decision, reason },
                  });
                  if (!alive.current) return;
                  await load();
                  setReason("");
                  setStatus("Advisor review recorded.");
                });
              }}
            >
              <label>
                Fact to review
                <select
                  required
                  value={field}
                  onChange={(e) => setField(e.target.value)}
                >
                  <option value="">Choose a fact</option>
                  {Object.keys(profile.facts).map((key) => (
                    <option key={key} value={key}>
                      {pretty(key)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Review decision
                <select
                  value={decision}
                  onChange={(e) =>
                    setDecision(e.target.value as "confirmed" | "disputed")
                  }
                >
                  <option value="confirmed">Confirm</option>
                  <option value="disputed">Dispute</option>
                </select>
              </label>
              <label>
                Review reason
                <textarea
                  required
                  maxLength={1000}
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <button disabled={busy}>Record advisor review</button>
            </form>
          )}
          <button
            onClick={() =>
              void action(async () => {
                const rows: S["ProfileOut"][] = [];
                let cursor: string | undefined;
                do {
                  const { data } = await api.GET(
                    "/api/v1/students/{mid}/profile/history",
                    { params: { path: { mid }, query: { purpose, cursor } } },
                  );
                  if (!data || !alive.current) return;
                  rows.push(...data.items);
                  cursor = data.next_cursor ?? undefined;
                } while (cursor);
                setHistory(rows);
              })
            }
          >
            Show profile history
          </button>
          {history.map((p) => (
            <details key={p.version}>
              <summary>
                Profile revision {p.version} · {pretty(p.status)}
              </summary>
              <dl>
                {Object.entries(p.facts).map(([key, f]) => (
                  <div key={key}>
                    <dt>{pretty(key)}</dt>
                    <dd>
                      {factText(f.value)} · {f.verification}
                    </dd>
                  </div>
                ))}
              </dl>
            </details>
          ))}
        </>
      )}
    </div>
  );
}
function Courses({
  label,
  value,
  onChange,
}: {
  label: string;
  value: Course[];
  onChange: (v: Course[]) => void;
}) {
  return (
    <fieldset>
      <legend>{label}</legend>
      <p>
        Missing completion remains unknown. Enter grades only if needed for a
        prerequisite.
      </p>
      {value.map((c, i) => (
        <div key={i}>
          <label>
            {label} course {i + 1}
            <input
              maxLength={100}
              value={c.course_id}
              onChange={(e) =>
                onChange(
                  value.map((x, n) =>
                    n === i ? { ...x, course_id: e.target.value } : x,
                  ),
                )
              }
            />
          </label>
          <label>
            Completion for {label} course {i + 1}
            <select
              value={
                c.completed == null ? "unknown" : c.completed ? "yes" : "no"
              }
              onChange={(e) =>
                onChange(
                  value.map((x, n) =>
                    n === i
                      ? {
                          ...x,
                          completed:
                            e.target.value === "unknown"
                              ? null
                              : e.target.value === "yes",
                        }
                      : x,
                  ),
                )
              }
            >
              <option value="unknown">Unknown</option>
              <option value="yes">Reported complete</option>
              <option value="no">Not complete</option>
            </select>
          </label>
          <label>
            Grade for {label} course {i + 1} (only if needed)
            <input
              maxLength={20}
              value={c.grade ?? ""}
              onChange={(e) =>
                onChange(
                  value.map((x, n) =>
                    n === i ? { ...x, grade: e.target.value || undefined } : x,
                  ),
                )
              }
            />
          </label>
          <button
            type="button"
            onClick={() => onChange(value.filter((_, n) => n !== i))}
          >
            Remove {label} course {i + 1}
          </button>
        </div>
      ))}
      <button
        type="button"
        onClick={() => onChange([...value, { course_id: "", completed: null }])}
      >
        Add {label} course
      </button>
    </fieldset>
  );
}
