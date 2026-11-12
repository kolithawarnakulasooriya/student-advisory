"use client";
import { useCallback, useEffect, useState } from "react";
import { staffApi as api, revision } from "../lib/staff-api";
import type { S, Purpose } from "./intake-workspace";
export default function PublicationCard({
  source,
  purpose,
  fail,
}: {
  source: S["SourceOut"];
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [publication, setPublication] = useState<S["PublicationOut"] | null>(
      null,
    ),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [status, setStatus] = useState("");
  const [excerpts, setExcerpts] = useState<S["IndexedExcerptOut"][]>([]);
  const load = useCallback(async () => {
    const { data } = await api.GET("/api/v1/sources/{sid}/publication", {
      params: { path: { sid: source.id }, query: { purpose } },
    });
    if (data) setPublication(data);
  }, [source.id, purpose]);
  useEffect(() => {
    let active = true;
    const refresh = () => {
      if (active && !document.hidden) void load().catch(fail);
    };
    refresh();
    const timer = setInterval(refresh, 4000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [load, fail]);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    setStatus("");
    try {
      await work();
      await load();
    } catch (e) {
      setPublication(null);
      setExcerpts([]);
      await fail(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label={`Publication for ${source.metadata.title}`}>
      <h5>Evidence publication</h5>
      <p>
        {publication?.status ?? "Loading publication…"} · publication revision{" "}
        {publication?.version ?? 0}
      </p>
      <label>
        Review or publication reason
        <input
          required
          maxLength={1000}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <p>
        Confirm scope, catalog, effective dates, authority and extracted text
        before indexing. Publication makes only this reviewed version available
        to applicable students.
      </p>
      <button
        disabled={
          busy || !reason || !source.artifact_available || source.archived
        }
        onClick={() =>
          void act(async () => {
            await api.POST("/api/v1/sources/{sid}/index", {
              params: { path: { sid: source.id } },
              headers: revision(source.version),
              body: { source_version_id: source.source_version_id, reason },
            });
            setStatus("Reviewed metadata saved; indexing queued.");
          })
        }
      >
        Review metadata and index
      </button>
      {publication?.builds.map((b) => (
        <div key={b.id}>
          <p>
            Source revision{" "}
            {b.source_version_id === source.source_version_id
              ? "current"
              : "historical"}{" "}
            · {b.state} · {b.chunk_count} excerpts
            {b.error_code ? ` · ${b.error_code}` : ""}
          </p>
          {b.state === "ready" && (
            <button
              disabled={busy || !reason || source.archived}
              onClick={() =>
                void act(async () => {
                  await api.POST("/api/v1/sources/{sid}/publish", {
                    params: { path: { sid: source.id } },
                    headers: revision(publication.version),
                    body: { build_id: b.id, reason },
                  });
                  setStatus("Reviewed evidence published.");
                })
              }
            >
              Publish reviewed build
            </button>
          )}
        </div>
      ))}
      {publication?.status === "published" && (
        <button
          disabled={busy || !reason}
          onClick={() =>
            void act(async () => {
              await api.POST("/api/v1/sources/{sid}/withdraw", {
                params: { path: { sid: source.id } },
                headers: revision(publication.version),
                body: { reason },
              });
              setStatus("Evidence withdrawn from new answers.");
            })
          }
        >
          Withdraw evidence
        </button>
      )}
      <button
        disabled={busy}
        onClick={() =>
          void act(async () => {
            let cursor: string | undefined;
            const rows: S["IndexedExcerptOut"][] = [];
            do {
              const { data } = await api.GET(
                "/api/v1/sources/{sid}/indexed-excerpts",
                {
                  params: {
                    path: { sid: source.id },
                    query: { purpose, cursor },
                  },
                },
              );
              if (!data) return;
              rows.push(...data.items);
              cursor = data.next_cursor ?? undefined;
            } while (cursor);
            setExcerpts(rows);
          })
        }
      >
        Inspect indexed excerpts
      </button>
      {excerpts.map((e) => (
        <details key={e.id}>
          <summary>
            {e.title} · excerpt {e.ordinal + 1} ·{" "}
            {e.published ? "published" : "not published"}
          </summary>
          <blockquote>{e.text}</blockquote>
          <p>
            Evidence reference for reviewed rules: <code>{e.id}</code>
          </p>
          <p>{JSON.stringify(e.locator)}</p>
        </details>
      ))}
      <p role="status">{busy ? "Saving…" : status}</p>
    </section>
  );
}
