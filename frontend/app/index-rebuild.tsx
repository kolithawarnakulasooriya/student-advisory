"use client";
import { useState } from "react";
import { staffApi as api, revision } from "../lib/staff-api";
import type { S, Purpose } from "./intake-workspace";
export default function IndexRebuild({
  institution,
  purpose,
  fail,
}: {
  institution: string;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [builds, setBuilds] = useState<S["BuildOut"][]>([]),
    [reason, setReason] = useState(""),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false);
  async function act(work: () => Promise<void>) {
    setBusy(true);
    try {
      await work();
    } catch (e) {
      setBuilds([]);
      await fail(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <details>
      <summary>Embedding rebuild and atomic activation</summary>
      <p>
        Prepare the currently published versions under the pinned runtime. The
        previous release stays active until every replacement build is ready.
        This does not publish source replacements.
      </p>
      <label>
        Embedding release reason
        <input
          value={reason}
          maxLength={1000}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <button
        disabled={busy || !reason}
        onClick={() =>
          void act(async () => {
            const rows: S["SourceOut"][] = [];
            let cursor: string | undefined;
            do {
              const { data } = await api.GET("/api/v1/sources", {
                params: { query: { purpose, cursor } },
              });
              if (!data) return;
              rows.push(
                ...data.items.filter((s) => s.institution_id === institution),
              );
              cursor = data.next_cursor ?? undefined;
            } while (cursor);
            const prepared: S["BuildOut"][] = [];
            for (const source of rows) {
              const { data: p } = await api.GET(
                "/api/v1/sources/{sid}/publication",
                { params: { path: { sid: source.id }, query: { purpose } } },
              );
              if (!p || p.status !== "published") continue;
              const current = p.builds.find((b) => b.id === p.build_id);
              if (!current) continue;
              const { data: b } = await api.POST(
                "/api/v1/sources/{sid}/index",
                {
                  params: { path: { sid: source.id } },
                  headers: revision(source.version),
                  body: {
                    source_version_id: current.source_version_id,
                    reason,
                  },
                },
              );
              if (b) prepared.push(b);
            }
            setBuilds(prepared);
            setStatus(
              `${prepared.length} builds prepared. Wait for the worker, then activate; the server requires all builds to be complete.`,
            );
          })
        }
      >
        Prepare published-version rebuild
      </button>
      <button
        disabled={busy || !reason || !builds.length}
        onClick={() =>
          void act(async () => {
            const { data } = await api.GET("/api/v1/knowledge/state", {
              params: { query: { institution_id: institution, purpose } },
            });
            if (!data) return;
            await api.POST("/api/v1/knowledge/rebuild/activate", {
              headers: revision(data.version),
              body: {
                institution_id: institution,
                build_ids: builds.map((b) => b.id),
                reason,
              },
            });
            setStatus("Complete embedding release activated atomically.");
            setBuilds([]);
          })
        }
      >
        Activate complete embedding rebuild
      </button>
      <p role="status">{busy ? "Saving…" : status}</p>
    </details>
  );
}
