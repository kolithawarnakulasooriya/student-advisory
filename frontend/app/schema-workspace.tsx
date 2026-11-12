"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { staffApi as api, revision } from "../lib/staff-api";
import type { S, Purpose } from "./intake-workspace";
const blank: S["Definition"] = {
  fields: [
    {
      key: "program",
      label: "Program",
      kind: "choice",
      required: true,
      choices: ["Synthetic Program"],
    },
    {
      key: "catalog_year",
      label: "Catalog year",
      kind: "choice",
      required: true,
      choices: ["2026"],
    },
  ],
  terms: ["2026 Fall", "2027 Spring"],
  program_tracks: {},
};
const split = (s: string) =>
  s
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
export default function SchemaWorkspace({
  scope,
  purpose,
  fail,
}: {
  scope: string;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [config, setConfig] = useState<S["ConfigOut"] | null>(null);
  const [definition, setDefinition] = useState<S["Definition"]>(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const alive = useRef(true);
  const load = useCallback(async () => {
    const { data } = await api.GET(
      "/api/v1/departments/{oid}/onboarding-schemas",
      { params: { path: { oid: scope }, query: { purpose } } },
    );
    if (data && alive.current) {
      setConfig(data);
      setDefinition(
        data.schemas.find((s) => s.id === data.active_schema_id)?.definition ??
          blank,
      );
    }
  }, [scope, purpose]);
  useEffect(() => {
    alive.current = true;
    void load().catch(fail);
    return () => {
      alive.current = false;
    };
  }, [load, fail]);
  async function action(work: () => Promise<void>) {
    setError("");
    setStatus("");
    setBusy(true);
    try {
      await work();
    } catch (e) {
      if (!alive.current) return;
      setError(
        e instanceof ApiError && e.status === 409
          ? "The configuration changed. Refresh and review it again."
          : e instanceof Error
            ? e.message
            : "Unable to save.",
      );
      if (e instanceof ApiError && [401, 403, 404].includes(e.status))
        await fail(e);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  function question(i: number, patch: Partial<S["Question"]>) {
    setDefinition((d) => ({
      ...d,
      fields: d.fields.map((q, n) => (n === i ? { ...q, ...patch } : q)),
    }));
  }
  return (
    <div>
      <h3>Department onboarding configuration</h3>
      <p>
        Required program and catalog choices constrain profile completion.
        Existing profiles retain their schema until explicitly updated.
      </p>
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => void action(load)}>
            Refresh configuration
          </button>
        </p>
      )}
      <p role="status">{busy ? "Saving…" : status}</p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void action(async () => {
            await api.POST("/api/v1/departments/{oid}/onboarding-schemas", {
              params: { path: { oid: scope } },
              headers: revision(config?.version ?? 0),
              body: { definition, activate: true },
            });
            if (alive.current) {
              await load();
              setStatus("Department schema saved and activated.");
            }
          });
        }}
      >
        <fieldset disabled={busy}>
          <legend>Versioned academic questions</legend>
          <CommaList
            key={`terms:${config?.version}`}
            label="Allowed terms (comma separated)"
            required
            values={definition.terms}
            change={(terms) => setDefinition((d) => ({ ...d, terms }))}
          />
          {definition.fields.map((q, i) => (
            <fieldset key={`${i}:${config?.version}`}>
              <legend>Question {i + 1}</legend>
              <label>
                Question key
                <input
                  required
                  pattern="[a-z][a-z0-9_]*"
                  maxLength={60}
                  disabled={["program", "catalog_year"].includes(q.key)}
                  value={q.key}
                  onChange={(e) => question(i, { key: e.target.value })}
                />
              </label>
              <label>
                Question label
                <input
                  required
                  maxLength={160}
                  value={q.label}
                  onChange={(e) => question(i, { label: e.target.value })}
                />
              </label>
              <label>
                Question type
                <select
                  value={q.kind}
                  onChange={(e) =>
                    question(i, {
                      kind: e.target.value as S["Question"]["kind"],
                    })
                  }
                >
                  <option value="text">Text</option>
                  <option value="choice">Choice</option>
                  <option value="courses">Course history</option>
                  <option value="number">Number</option>
                </select>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={q.required ?? false}
                  disabled={["program", "catalog_year"].includes(q.key)}
                  onChange={(e) => question(i, { required: e.target.checked })}
                />
                Required to complete
              </label>
              {q.kind === "choice" && (
                <CommaList
                  label="Allowed choices (comma separated)"
                  required
                  values={q.choices ?? []}
                  change={(choices) => question(i, { choices })}
                />
              )}
              {!["program", "catalog_year"].includes(q.key) && (
                <button
                  type="button"
                  onClick={() =>
                    setDefinition((d) => ({
                      ...d,
                      fields: d.fields.filter((_, n) => n !== i),
                    }))
                  }
                >
                  Remove question {i + 1}
                </button>
              )}
            </fieldset>
          ))}
          <button
            type="button"
            onClick={() =>
              setDefinition((d) => ({
                ...d,
                fields: [
                  ...d.fields,
                  {
                    key: `question_${Date.now()}`,
                    label: "Academic question",
                    kind: "text",
                    required: false,
                    choices: [],
                  },
                ],
              }))
            }
          >
            Add academic question
          </button>
          {(
            definition.fields.find((q) => q.key === "program")?.choices ?? []
          ).map((program) => (
            <CommaList
              key={`${program}:${config?.version}`}
              label={`Tracks for ${program} (comma separated)`}
              values={definition.program_tracks?.[program] ?? []}
              change={(tracks) =>
                setDefinition((d) => ({
                  ...d,
                  program_tracks: { ...d.program_tracks, [program]: tracks },
                }))
              }
            />
          ))}
          <button>Save and activate onboarding schema</button>
        </fieldset>
      </form>
      <h4>Schema history</h4>
      {config?.schemas.map((s) => (
        <p key={s.id}>
          Schema revision {s.version}
          {s.id === config.active_schema_id ? (
            " · active"
          ) : (
            <button
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  await api.POST(
                    "/api/v1/departments/{oid}/onboarding-schemas/{sid}/activate",
                    {
                      params: { path: { oid: scope, sid: s.id } },
                      headers: revision(config.version),
                    },
                  );
                  if (alive.current) {
                    await load();
                    setStatus("Schema activated.");
                  }
                })
              }
            >
              Activate schema revision {s.version}
            </button>
          )}
        </p>
      ))}
    </div>
  );
}

function CommaList({
  label,
  values,
  change,
  required = false,
}: {
  label: string;
  values: string[];
  change: (values: string[]) => void;
  required?: boolean;
}) {
  const [raw, setRaw] = useState(values.join(", "));
  return (
    <label>
      {label}
      <input
        required={required}
        value={raw}
        onChange={(e) => {
          setRaw(e.target.value);
          change(split(e.target.value));
        }}
      />
    </label>
  );
}
