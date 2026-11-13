"use client";
import { useEffect, useState } from "react";
import { staffApi as api } from "../lib/staff-api";
import type { S, Purpose } from "./intake-workspace";
export default function PublishedEvidence({
  mid,
  purpose,
  fail,
}: {
  mid: string;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [items, setItems] = useState<S["PublishedSourceOut"][]>([]);
  useEffect(() => {
    let active = true;
    const load = async () => {
      const rows: S["PublishedSourceOut"][] = [];
      let cursor: string | undefined;
      do {
        const { data } = await api.GET(
          "/api/v1/students/{mid}/published-sources",
          { params: { path: { mid }, query: { purpose, cursor } } },
        );
        if (!data || !active) return;
        rows.push(...data.items);
        cursor = data.next_cursor ?? undefined;
      } while (cursor);
      setItems(rows);
    };
    const refresh = () => {
      if (!document.hidden)
        void load().catch(async (e) => {
          setItems([]);
          await fail(e);
        });
    };
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [mid, purpose, fail]);
  return (
    <section aria-label="Published applicable evidence">
      <h4>Published applicable evidence</h4>
      <p>
        This list contains reviewed versions applicable to the current profile.
        Private staff replacements and intake history are excluded.
      </p>
      {!items.length && (
        <p>
          No applicable published sources yet. Complete your profile or request
          human help.
        </p>
      )}
      {items.map((item) => (
        <article key={item.source_id}>
          <h5>{item.title}</h5>
          <p>Published {new Date(item.published_at).toLocaleString()}</p>
          <a
            href={`/api/v1/sources/${item.source_id}/versions/${item.source_version_id}/download${purpose ? `?purpose=${purpose}` : ""}`}
          >
            Download published {item.title}
          </a>
        </article>
      ))}
    </section>
  );
}
