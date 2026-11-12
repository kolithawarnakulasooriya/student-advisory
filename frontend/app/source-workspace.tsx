"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { extractionText } from "../lib/intake-display";
import { staffApi as api, revision } from "../lib/staff-api";
import { pretty, type S, type Purpose } from "./intake-workspace";
const emptyPage = { items: [], total: 0, next_cursor: null };
export default function SourceWorkspace({
  scope,
  mid,
  canUpload,
  shared,
  global,
  purpose,
  fail,
}: {
  scope: S["ScopeOut"];
  mid: string;
  canUpload: boolean;
  shared: boolean;
  global: boolean;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [page, setPage] = useState<S["Page_SourceOut_"]>(emptyPage);
  const [cursor, setCursor] = useState<string | undefined>();
  const [selected, setSelected] = useState<S["SourceOut"] | null>(null);
  const [visibility, setVisibility] =
    useState<S["SourceTarget"]["visibility"]>("student");
  const [metadata, setMetadata] = useState<S["SourceMetadata"]>({
    title: "",
    authority_rank: 0,
    document_class: "other",
  });
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [extracted, setExtracted] = useState("");
  const [history, setHistory] = useState<S["SourceOut"][]>([]);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const [fileKey, setFileKey] = useState(0);
  const alive = useRef(true);
  const requestSerial = useRef(0);
  const load = useCallback(async () => {
    const serial = ++requestSerial.current;
    const { data } = await api.GET("/api/v1/sources", {
      params: {
        query: {
          scope_id:
            global && visibility === "institution" ? undefined : scope.id,
          student_membership_id:
            visibility === "student" ? mid || undefined : undefined,
          cursor,
          purpose,
        },
      },
    });
    if (alive.current && serial === requestSerial.current && data)
      setPage(data);
  }, [scope.id, mid, cursor, purpose, global, visibility]);
  const handleError = useCallback(
    async (e: unknown) => {
      if (!alive.current) return;
      setError(
        e instanceof Error
          ? e.message
          : "Unable to complete document processing.",
      );
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) {
        setPage(emptyPage);
        setSelected(null);
        setExtracted("");
        setHistory([]);
        await fail(e);
      }
      if (e instanceof ApiError && e.status === 409) {
        setSelected(null);
        setExtracted("");
        setError("The document changed. Refresh and review it again.");
      }
    },
    [fail],
  );
  useEffect(() => {
    alive.current = true;
    const refresh = () => {
      if (!document.hidden) void load().catch(handleError);
    };
    refresh();
    const timer = setInterval(refresh, 3000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      alive.current = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
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
  function clear() {
    setSelected(null);
    setMetadata({ title: "", authority_rank: 0, document_class: "other" });
    setFile(null);
    setText("");
    setFileKey((k) => k + 1);
  }
  async function upload() {
    const target: S["SourceTarget"] = {
      institution_id: selected?.institution_id ?? scope.institution_id,
      org_unit_id: selected
        ? selected.org_unit_id
        : visibility === "institution"
          ? null
          : scope.id,
      student_membership_id: selected
        ? selected.student_membership_id
        : visibility === "student"
          ? mid || null
          : null,
      visibility: selected
        ? (selected.visibility as S["SourceTarget"]["visibility"])
        : visibility,
      metadata,
      source_id: selected?.id,
    };
    if (file) {
      const form = new FormData();
      form.append("target", JSON.stringify(target));
      form.append("file", file);
      await api.POST("/api/v1/sources/uploads", {
        body: {} as never,
        headers: revision(selected?.version ?? 0),
        bodySerializer: () => form,
      });
    } else {
      await api.POST("/api/v1/sources/text", {
        headers: revision(selected?.version ?? 0),
        body: { ...target, text },
      });
    }
    if (!alive.current) return;
    clear();
    await load();
    setStatus(
      "Document received. Processing begins when the worker is running.",
    );
  }
  return (
    <div>
      <h3>Documents</h3>
      <p>
        Extracted documents remain at needs review. They are not published or
        used for advising answers in this release.
      </p>
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => void action(load)}>Refresh documents</button>
        </p>
      )}
      <p role="status">{busy ? "Saving…" : status}</p>
      {canUpload && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action(upload);
          }}
        >
          <h4>
            {selected ? `Replace ${selected.metadata.title}` : "Add a document"}
          </h4>
          <fieldset disabled={busy}>
            <legend>Private document intake</legend>
            {!selected && (
              <label>
                Document scope
                <select
                  value={visibility}
                  onChange={(e) =>
                    setVisibility(
                      e.target.value as S["SourceTarget"]["visibility"],
                    )
                  }
                >
                  <option value="student">Selected student only</option>
                  {shared && (
                    <option
                      value={
                        scope.kind === "college" ? "college" : "department"
                      }
                    >
                      {scope.kind === "college" ? "College" : "Department"}{" "}
                      staff
                    </option>
                  )}
                  {global && (
                    <option value="institution">Institution staff</option>
                  )}
                </select>
              </label>
            )}
            <Metadata value={metadata} change={setMetadata} />
            <label>
              Document file
              <input
                key={fileKey}
                type="file"
                accept=".pdf,.docx,.txt,.md"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setText("");
                }}
              />
            </label>
            <p>
              PDF, DOCX, text or Markdown. Maximum 25 MiB and 200 PDF pages.
            </p>
            <label>
              Or paste document text
              <textarea
                disabled={!!file}
                maxLength={2000000}
                value={text}
                onChange={(e) => setText(e.target.value)}
              />
            </label>
            <button
              disabled={
                (!file && !text) ||
                (!selected && visibility === "student" && !mid)
              }
            >
              Submit document
            </button>
            {selected && (
              <>
                <button
                  type="button"
                  onClick={() =>
                    void action(async () => {
                      await api.PATCH("/api/v1/sources/{sid}/metadata", {
                        params: { path: { sid: selected.id } },
                        headers: revision(selected.version),
                        body: metadata,
                      });
                      if (alive.current) {
                        clear();
                        await load();
                        setStatus("Metadata saved as a new immutable version.");
                      }
                    })
                  }
                >
                  Save document metadata only
                </button>
                <button type="button" onClick={clear}>
                  Cancel document replacement
                </button>
              </>
            )}
          </fieldset>
        </form>
      )}
      <p role="status">{page.total} accessible documents</p>
      {page.items.map((s) => (
        <article className="source-card" key={s.id}>
          <h4>{s.metadata.title}</h4>
          <p>
            {s.filename} · revision {s.version} · {pretty(s.state)} · attempt{" "}
            {s.attempt}
          </p>
          {s.ocr && (
            <p>OCR was used. Review extraction against the original.</p>
          )}
          {s.error_code && (
            <p role="status">
              {pretty(s.error_code)}.{" "}
              {s.error_code === "SCANNER_UNAVAILABLE"
                ? "Ask the local operator to update scanner signatures, then retry."
                : "Resolve the issue and retry, or replace the file."}
            </p>
          )}
          {s.download_available && (
            <a
              href={`/api/v1/sources/${s.id}/versions/${s.source_version_id}/download${purpose ? `?purpose=${purpose}` : ""}`}
            >
              Download {s.filename}
            </a>
          )}
          {s.artifact_available && (
            <button
              onClick={() =>
                void action(async () => {
                  const { data } = await api.GET(
                    "/api/v1/sources/{sid}/versions/{vid}/extraction",
                    {
                      params: {
                        path: { sid: s.id, vid: s.source_version_id },
                        query: { purpose },
                      },
                    },
                  );
                  if (alive.current) setExtracted(extractionText(data));
                })
              }
            >
              Review extracted text for {s.metadata.title}
            </button>
          )}
          {canUpload && !s.archived && (
            <>
              <button
                disabled={busy}
                onClick={() => {
                  setSelected(s);
                  setMetadata(s.metadata);
                  setVisibility(
                    s.visibility as S["SourceTarget"]["visibility"],
                  );
                  setFile(null);
                  setText("");
                  setFileKey((k) => k + 1);
                }}
              >
                Replace or edit {s.metadata.title}
              </button>
              {["failed", "cancelled"].includes(s.state) && s.attempt < 3 && (
                <button
                  disabled={busy}
                  onClick={() =>
                    void action(async () => {
                      await api.POST("/api/v1/sources/{sid}/retry", {
                        params: { path: { sid: s.id } },
                        headers: revision(s.version),
                      });
                      if (alive.current) {
                        await load();
                        setStatus("Retry queued.");
                      }
                    })
                  }
                >
                  Retry {s.metadata.title}
                </button>
              )}
              <button
                disabled={busy}
                onClick={() =>
                  void action(async () => {
                    await api.POST("/api/v1/sources/{sid}/archive", {
                      params: { path: { sid: s.id } },
                      headers: revision(s.version),
                    });
                    if (alive.current) await load();
                  })
                }
              >
                Archive {s.metadata.title}
              </button>
            </>
          )}
          <button
            onClick={() =>
              void action(async () => {
                const rows: S["SourceOut"][] = [];
                let cursor: string | undefined;
                do {
                  const { data } = await api.GET(
                    "/api/v1/sources/{sid}/versions",
                    {
                      params: {
                        path: { sid: s.id },
                        query: { purpose, cursor },
                      },
                    },
                  );
                  if (!data || !alive.current) return;
                  rows.push(...data.items);
                  cursor = data.next_cursor ?? undefined;
                } while (cursor);
                setHistory(rows);
              })
            }
          >
            History for {s.metadata.title}
          </button>
        </article>
      ))}
      {page.next_cursor && (
        <button onClick={() => setCursor(page.next_cursor ?? undefined)}>
          Next documents page
        </button>
      )}
      {cursor && (
        <button onClick={() => setCursor(undefined)}>
          First documents page
        </button>
      )}
      {history.map((s) => (
        <p key={s.source_version_id}>
          Document revision {s.version}: {s.filename} · {pretty(s.state)}
        </p>
      ))}
      {extracted && (
        <details open>
          <summary>Extracted document text</summary>
          <pre className="extracted-text">{extracted}</pre>
        </details>
      )}
    </div>
  );
}
function Metadata({
  value,
  change,
}: {
  value: S["SourceMetadata"];
  change: (v: S["SourceMetadata"]) => void;
}) {
  return (
    <fieldset>
      <legend>Document metadata</legend>
      <label>
        Document title
        <input
          required
          maxLength={160}
          value={value.title}
          onChange={(e) => change({ ...value, title: e.target.value })}
        />
      </label>
      {(["program", "track"] as const).map((key) => (
        <label key={key}>
          {pretty(key)}
          <input
            maxLength={160}
            value={value[key] ?? ""}
            onChange={(e) =>
              change({ ...value, [key]: e.target.value || null })
            }
          />
        </label>
      ))}
      {(["catalog_start", "catalog_end"] as const).map((key) => (
        <label key={key}>
          {pretty(key)}
          <input
            type="number"
            min="1900"
            max="2200"
            value={value[key] ?? ""}
            onChange={(e) =>
              change({
                ...value,
                [key]: e.target.value ? Number(e.target.value) : null,
              })
            }
          />
        </label>
      ))}
      {(["effective_from", "effective_until"] as const).map((key) => (
        <label key={key}>
          {pretty(key)}
          <input
            type="date"
            value={value[key] ?? ""}
            onChange={(e) =>
              change({ ...value, [key]: e.target.value || null })
            }
          />
        </label>
      ))}
      <label>
        Document class
        <select
          value={value.document_class ?? "other"}
          onChange={(e) =>
            change({
              ...value,
              document_class: e.target
                .value as S["SourceMetadata"]["document_class"],
            })
          }
        >
          <option value="other">Other</option>
          <option value="student_evidence">Student evidence</option>
          <option value="catalog">Catalog</option>
          <option value="policy">Policy</option>
        </select>
      </label>
      <label>
        Authority rank (metadata pending review)
        <input
          type="number"
          min="0"
          max="100"
          value={value.authority_rank ?? 0}
          onChange={(e) =>
            change({ ...value, authority_rank: Number(e.target.value) })
          }
        />
      </label>
    </fieldset>
  );
}
