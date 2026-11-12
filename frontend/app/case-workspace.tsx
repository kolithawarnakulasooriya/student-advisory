"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { staffApi as api, revision } from "../lib/staff-api";
import type { S, Purpose } from "./intake-workspace";
import { SafeText } from "./advising-answer";
export default function CaseWorkspace({
  mid,
  cid,
  scope,
  staff,
  purpose,
  fail,
}: {
  mid?: string;
  cid?: string;
  scope: string;
  staff: boolean;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [cases, setCases] = useState<S["CaseOut"][]>([]),
    [reason, setReason] = useState("Please review my academic question.");
  const [status, setStatus] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState(""),
    [history, setHistory] = useState<S["CaseEventOut"][]>([]);
  const [disposition, setDisposition] =
      useState<S["CaseTransition"]["status"]>("in_progress"),
    [reply, setReply] = useState("");
  const alive = useRef(true);
  const load = useCallback(async () => {
    let cursor: string | undefined;
    const rows: S["CaseOut"][] = [];
    do {
      const { data } = await api.GET("/api/v1/cases", {
        params: {
          query: {
            scope_id: scope,
            student_membership_id: mid,
            purpose,
            cursor,
          },
        },
      });
      if (!data || !alive.current) return;
      rows.push(...data.items);
      cursor = data.next_cursor ?? undefined;
    } while (cursor);
    setCases(rows);
  }, [scope, mid, purpose]);
  useEffect(() => {
    alive.current = true;
    const refresh = () => {
      if (!document.hidden) void load().catch(fail);
    };
    refresh();
    const timer = setInterval(refresh, 5000);
    return () => {
      alive.current = false;
      clearInterval(timer);
    };
  }, [load, fail]);
  async function action(work: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await work();
    } catch (e) {
      if (alive.current)
        setError(e instanceof Error ? e.message : "Unable to update the case.");
      await fail(e);
    } finally {
      if (alive.current) setBusy(false);
    }
  }
  return (
    <section aria-label="Human advisor help">
      <h4>Ask a human advisor</h4>
      <p>
        Your request is recorded even when the model is unavailable. Cases go to
        the current advisor or the department manager queue. No response time is
        promised.
      </p>
      {error && <p role="alert">{error}</p>}
      <p role="status">{status}</p>
      {mid && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void action(async () => {
              await api.POST("/api/v1/cases", {
                body: {
                  student_membership_id: mid,
                  conversation_id: cid ?? null,
                  reason,
                },
              });
              if (alive.current) {
                await load();
                setStatus(
                  "Your advisor request was received. Track its status below.",
                );
              }
            });
          }}
        >
          <label>
            Reason for advisor help
            <textarea
              required
              maxLength={1000}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <button disabled={busy}>Request human help</button>
        </form>
      )}
      {cases.map((c) => (
        <article className="case-card" key={c.id}>
          <h5>Advisor case · {c.status.replaceAll("_", " ")}</h5>
          <SafeText text={c.reason} />
          <p>
            {c.route === "advisor"
              ? "Routed to the current advisor"
              : "Waiting in the manager assignment queue"}
          </p>
          <button
            onClick={() =>
              void action(async () => {
                const rows: S["CaseEventOut"][] = [];
                let cursor: string | undefined;
                do {
                  const { data } = await api.GET(
                    "/api/v1/cases/{case_id}/history",
                    {
                      params: {
                        path: { case_id: c.id },
                        query: { purpose, cursor },
                      },
                    },
                  );
                  if (!data || !alive.current) return;
                  rows.push(...data.items);
                  cursor = data.next_cursor ?? undefined;
                } while (cursor);
                setSelected(c.id);
                setHistory(rows);
              })
            }
          >
            Show case history
          </button>
          {staff && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void action(async () => {
                  await api.PATCH("/api/v1/cases/{case_id}", {
                    params: { path: { case_id: c.id } },
                    headers: revision(c.version),
                    body: { status: disposition, text: reply },
                  });
                  if (alive.current) {
                    setReply("");
                    await load();
                    setStatus("Case status updated.");
                  }
                });
              }}
            >
              <label>
                Case status
                <select
                  value={disposition}
                  onChange={(e) =>
                    setDisposition(
                      e.target.value as S["CaseTransition"]["status"],
                    )
                  }
                >
                  <option value="assigned">Assigned</option>
                  <option value="in_progress">In progress</option>
                  <option value="waiting_for_student">
                    Waiting for student
                  </option>
                  <option value="resolved">Resolved</option>
                  <option value="cancelled">Cancelled</option>
                  <option value="open">Reopen</option>
                </select>
              </label>
              <label>
                Student-visible case update
                <textarea
                  required
                  maxLength={1000}
                  value={reply}
                  onChange={(e) => setReply(e.target.value)}
                />
              </label>
              <button disabled={busy}>Update case</button>
            </form>
          )}
          {!staff && (
            <button
              disabled={busy}
              onClick={() =>
                void action(async () => {
                  await api.PATCH("/api/v1/cases/{case_id}", {
                    params: { path: { case_id: c.id } },
                    headers: revision(c.version),
                    body: {
                      status: ["resolved", "cancelled"].includes(c.status)
                        ? "open"
                        : "cancelled",
                      text: "Student requested a case status change.",
                    },
                  });
                  await load();
                })
              }
            >
              {["resolved", "cancelled"].includes(c.status)
                ? "Reopen case"
                : "Cancel case"}
            </button>
          )}
          {selected === c.id &&
            history.map((h) => (
              <p key={h.id}>
                {h.status.replaceAll("_", " ")} · {h.text}
              </p>
            ))}
        </article>
      ))}
    </section>
  );
}
