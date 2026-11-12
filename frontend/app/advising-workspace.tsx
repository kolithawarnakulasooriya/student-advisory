"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import { staffApi as api, revision } from "../lib/staff-api";
import type { S, Purpose } from "./intake-workspace";
import AdvisingAnswer, { SafeText, quoteText } from "./advising-answer";
import PublishedEvidence from "./published-evidence";
import CaseWorkspace from "./case-workspace";
const pretty = (s: string) => s.replaceAll("_", " ");
export default function AdvisingWorkspace({
  mid,
  scope,
  own,
  reviewer,
  staff,
  purpose,
  fail,
}: {
  mid: string;
  scope: string;
  own: boolean;
  reviewer: boolean;
  staff: boolean;
  purpose?: Purpose;
  fail: (e: unknown) => Promise<void>;
}) {
  const [conversations, setConversations] = useState<S["ConversationOut"][]>(
      [],
    ),
    [cid, setCid] = useState("");
  const [conversation, setConversation] = useState<S["ConversationOut"] | null>(
    null,
  );
  const [messages, setMessages] = useState<S["MessageOut"][]>([]),
    [guidance, setGuidance] = useState<S["MessageOut"][]>([]);
  const [notes, setNotes] = useState<S["NoteOut"][]>([]),
    [drafts, setDrafts] = useState<S["DraftOut"][]>([]);
  const [question, setQuestion] = useState(""),
    [guidanceText, setGuidanceText] = useState(""),
    [note, setNote] = useState("");
  const [maximum, setMaximum] = useState(""),
    [priority, setPriority] = useState(""),
    [exception, setException] = useState(false);
  const [expiry, setExpiry] = useState(""),
    [supersedes, setSupersedes] = useState(""),
    [draftMessage, setDraftMessage] = useState("");
  const [draftText, setDraftText] = useState(""),
    [selectedDraft, setSelectedDraft] = useState(""),
    [draftReviewed, setDraftReviewed] = useState(false);
  const [tab, setTab] = useState("Conversation"),
    [citation, setCitation] = useState<S["CitationOut"] | null>(null);
  const [error, setError] = useState(""),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false);
  const alive = useRef(true),
    serial = useRef(0),
    activeConversation = useRef(cid);
  useEffect(() => {
    activeConversation.current = cid;
  }, [cid]);
  const handleError = useCallback(
    async (e: unknown) => {
      if (!alive.current) return;
      setError(e instanceof Error ? e.message : "Unable to load advising.");
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) {
        setMessages([]);
        setGuidance([]);
        setNotes([]);
        setDrafts([]);
        setCitation(null);
        setConversation(null);
        await fail(e);
      }
      if (e instanceof ApiError && e.status === 409) {
        setError(
          "This conversation changed. Refresh and review before submitting again.",
        );
        setDraftReviewed(false);
      }
    },
    [fail],
  );
  const loadConversations = useCallback(async () => {
    let cursor: string | undefined;
    const rows: S["ConversationOut"][] = [];
    do {
      const { data } = await api.GET("/api/v1/conversations", {
        params: { query: { student_membership_id: mid, purpose, cursor } },
      });
      if (!data || !alive.current) return;
      rows.push(...data.items);
      cursor = data.next_cursor ?? undefined;
    } while (cursor);
    setConversations(rows);
    setCid((old) =>
      rows.some((c) => c.id === old) ? old : (rows[0]?.id ?? ""),
    );
  }, [mid, purpose]);
  const load = useCallback(async () => {
    if (!cid) return;
    const stamp = ++serial.current;
    const { data: c } = await api.GET("/api/v1/conversations/{cid}", {
      params: { path: { cid }, query: { purpose } },
    });
    const rows: S["MessageOut"][] = [];
    let cursor: string | undefined;
    do {
      const { data } = await api.GET("/api/v1/conversations/{cid}/messages", {
        params: { path: { cid }, query: { purpose, cursor } },
      });
      if (!data || !alive.current) return;
      rows.push(...data.items);
      cursor = data.next_cursor ?? undefined;
    } while (cursor);
    const guides: S["MessageOut"][] = [];
    cursor = undefined;
    do {
      const response: { data?: S["Page_MessageOut_"] } = await api.GET(
        "/api/v1/conversations/{cid}/guidance",
        {
          params: { path: { cid }, query: { purpose, cursor } },
        },
      );
      const data: S["Page_MessageOut_"] | undefined = response.data;
      if (!data || !alive.current) return;
      guides.push(...data.items);
      cursor = data.next_cursor ?? undefined;
    } while (cursor);
    if (
      stamp !== serial.current ||
      !alive.current ||
      activeConversation.current !== cid
    )
      return;
    if (c) setConversation(c);
    setMessages(rows.sort((a, b) => a.created_at.localeCompare(b.created_at)));
    setGuidance(guides);
    if (staff && tab === "Staff notes") {
      const rows: S["NoteOut"][] = [];
      let cursor: string | undefined;
      do {
        const response: { data?: S["Page_NoteOut_"] } = await api.GET(
          "/api/v1/conversations/{cid}/notes",
          { params: { path: { cid }, query: { purpose, cursor } } },
        );
        if (
          !response.data ||
          !alive.current ||
          activeConversation.current !== cid
        )
          return;
        rows.push(...response.data.items);
        cursor = response.data.next_cursor ?? undefined;
      } while (cursor);
      setNotes(rows);
    }
    if (reviewer && tab === "Drafts") {
      const rows: S["DraftOut"][] = [];
      let cursor: string | undefined;
      do {
        const response: { data?: S["Page_DraftOut_"] } = await api.GET(
          "/api/v1/conversations/{cid}/advisor-drafts",
          { params: { path: { cid }, query: { purpose, cursor } } },
        );
        if (
          !response.data ||
          !alive.current ||
          activeConversation.current !== cid
        )
          return;
        rows.push(...response.data.items);
        cursor = response.data.next_cursor ?? undefined;
      } while (cursor);
      setDrafts(rows);
    }
  }, [cid, purpose, staff, reviewer, tab]);
  useEffect(() => {
    alive.current = true;
    const initial = setTimeout(
      () => void loadConversations().catch(handleError),
      0,
    );
    return () => {
      clearTimeout(initial);
      alive.current = false;
    };
  }, [loadConversations, handleError]);
  useEffect(() => {
    if (!cid) return;
    let active = true;
    const refresh = () => {
      if (active && !document.hidden) void load().catch(handleError);
    };
    refresh();
    const timer = setInterval(refresh, 2500);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      active = false;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [cid, load, handleError]);
  function selectConversation(value: string) {
    activeConversation.current = value;
    setCid(value);
    setMessages([]);
    setGuidance([]);
    setNotes([]);
    setDrafts([]);
    setCitation(null);
    setConversation(null);
    setQuestion("");
    setSelectedDraft("");
    setDraftText("");
    setDraftReviewed(false);
    setError("");
  }
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
  async function viewCitation(id: string) {
    await action(async () => {
      const { data } = await api.GET("/api/v1/citations/{eid}", {
        params: { path: { eid: id }, query: { purpose } },
      });
      if (data && alive.current) setCitation(data);
    });
  }
  const timeline = [...messages, ...guidance].sort((a, b) =>
    a.created_at.localeCompare(b.created_at),
  );
  return (
    <section aria-label="Cited advising chat">
      <h3>Cited advising chat</h3>
      <p>
        Replies quote reviewed, published sources. Advisor guidance is human
        input; staff notes and unpublished drafts stay separate.
      </p>
      {error && (
        <p role="alert">
          {error}{" "}
          <button onClick={() => void action(load)}>Refresh advising</button>
        </p>
      )}
      <p role="status" aria-live="polite">
        {busy ? "Saving…" : status}
      </p>
      <label>
        Advising conversation
        <select
          value={cid}
          onChange={(e) => selectConversation(e.target.value)}
        >
          <option value="">Choose a conversation</option>
          {conversations.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </label>
      {own && (
        <button
          disabled={busy}
          onClick={() =>
            void action(async () => {
              const { data } = await api.POST("/api/v1/conversations", {
                body: {
                  student_membership_id: mid,
                  title: "Academic advising",
                },
              });
              if (data && alive.current) {
                await loadConversations();
                setCid(data.id);
                setStatus("Conversation created.");
              }
            })
          }
        >
          Start advising conversation
        </button>
      )}
      {!cid && !own && (
        <p>The student can start a conversation to receive guidance.</p>
      )}
      {cid && (
        <>
          <nav aria-label="Conversation tools">
            <button
              aria-pressed={tab === "Conversation"}
              onClick={() => setTab("Conversation")}
            >
              Conversation
            </button>
            {reviewer && (
              <button
                aria-pressed={tab === "Guidance"}
                onClick={() => setTab("Guidance")}
              >
                Visible advisor guidance
              </button>
            )}
            {staff && (
              <button
                aria-pressed={tab === "Staff notes"}
                onClick={() => setTab("Staff notes")}
              >
                Staff-only notes
              </button>
            )}
            {reviewer && (
              <button
                aria-pressed={tab === "Drafts"}
                onClick={() => setTab("Drafts")}
              >
                Private AI drafts
              </button>
            )}
          </nav>
          {(tab === "Conversation" || tab === "Guidance") && (
            <div role="log" aria-label="Conversation messages">
              {timeline.map((m) => (
                <article className="chat-message" key={m.id}>
                  <h4>
                    {m.type === "student_question" ? "Student" : "Advisor"} ·{" "}
                    {m.author_name}
                  </h4>
                  <time dateTime={m.created_at}>
                    {new Date(m.created_at).toLocaleString()}
                  </time>
                  <SafeText text={m.text} />
                  {m.type === "student_visible_guidance" && (
                    <p>
                      {m.active
                        ? "Active advisor guidance"
                        : "Expired or superseded guidance"}
                      {m.effective_until
                        ? ` · until ${new Date(m.effective_until).toLocaleString()}`
                        : ""}
                    </p>
                  )}
                  {(m.answers ?? []).map((a) => (
                    <AdvisingAnswer
                      key={a.id}
                      payload={a.payload}
                      onCitation={(id) => void viewCitation(id)}
                    />
                  ))}
                  {(m.jobs ?? []).map((j) => (
                    <div key={j.id}>
                      {["queued", "running"].includes(j.state) ? (
                        <p role="status">
                          Preparing and validating your response…
                        </p>
                      ) : ["failed", "cancelled", "blocked"].includes(
                          j.state,
                        ) ? (
                        <p role="status">
                          Response {j.state}:{" "}
                          {pretty(j.error_code ?? "validation needs review")}.{" "}
                          {own && j.attempt < 3 && (
                            <button
                              disabled={busy}
                              onClick={() =>
                                void action(async () => {
                                  await api.POST("/api/v1/jobs/{jid}/retry", {
                                    params: { path: { jid: j.id } },
                                    headers: revision(j.version),
                                  });
                                  await load();
                                  setStatus("Question retry queued.");
                                })
                              }
                            >
                              Retry question
                            </button>
                          )}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </article>
              ))}
            </div>
          )}
          {tab === "Conversation" && own && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!conversation) return;
                void action(async () => {
                  await api.POST("/api/v1/conversations/{cid}/messages", {
                    params: { path: { cid } },
                    headers: revision(conversation.version),
                    body: { text: question, type: "student_question" },
                  });
                  if (alive.current) {
                    setQuestion("");
                    await load();
                    setStatus(
                      "Question received. The response is queued for validation.",
                    );
                  }
                });
              }}
            >
              <label>
                Your academic question
                <textarea
                  required
                  maxLength={4000}
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                />
              </label>
              <button disabled={busy || !conversation}>Ask a question</button>
            </form>
          )}
          {tab === "Guidance" && reviewer && (
            <form
              onSubmit={(e) => {
                e.preventDefault();
                if (!conversation) return;
                void action(async () => {
                  await api.POST("/api/v1/conversations/{cid}/guidance", {
                    params: { path: { cid } },
                    headers: revision(conversation.version),
                    body: {
                      type: "student_visible_guidance",
                      text: guidanceText,
                      effective_until: expiry
                        ? new Date(expiry).toISOString()
                        : null,
                      supersedes_id: supersedes || null,
                      preferences: {
                        max_courses: maximum ? Number(maximum) : null,
                        prioritize_courses: priority
                          .split(",")
                          .map((s) => s.trim())
                          .filter(Boolean),
                        requested_exception: exception,
                      },
                    },
                  });
                  if (alive.current) {
                    setGuidanceText("");
                    await load();
                    setStatus(
                      "Advisor guidance saved. No assistant response was requested.",
                    );
                  }
                });
              }}
            >
              <h4>Student-visible advisor guidance</h4>
              <label>
                Visible guidance text
                <textarea
                  required
                  maxLength={2000}
                  value={guidanceText}
                  onChange={(e) => setGuidanceText(e.target.value)}
                />
              </label>
              <label>
                Preferred maximum courses
                <input
                  type="number"
                  min="1"
                  max="20"
                  value={maximum}
                  onChange={(e) => setMaximum(e.target.value)}
                />
              </label>
              <label>
                Prioritize courses (comma separated)
                <input
                  value={priority}
                  onChange={(e) => setPriority(e.target.value)}
                />
              </label>
              <label>
                Guidance expires
                <input
                  type="datetime-local"
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                />
              </label>
              <label>
                Supersede existing guidance
                <select
                  value={supersedes}
                  onChange={(e) => setSupersedes(e.target.value)}
                >
                  <option value="">Add new guidance</option>
                  {guidance
                    .filter((g) => g.active)
                    .map((g) => (
                      <option key={g.id} value={g.id}>
                        {g.text.slice(0, 80)}
                      </option>
                    ))}
                </select>
              </label>
              <label>
                <input
                  type="checkbox"
                  checked={exception}
                  onChange={(e) => setException(e.target.checked)}
                />
                This requests human review of a policy exception; it does not
                approve a waiver.
              </label>
              <button disabled={busy || !conversation}>
                Post advisor guidance
              </button>
            </form>
          )}
          {tab === "Staff notes" && staff && (
            <section aria-label="Staff-only notes">
              <h4>Staff-only notes</h4>
              <p>
                These notes are excluded from student views, student prompts,
                and AI drafts.
              </p>
              {notes.map((n) => (
                <article key={n.id}>
                  <time dateTime={n.created_at}>
                    {new Date(n.created_at).toLocaleString()}
                  </time>
                  <SafeText text={n.text} />
                </article>
              ))}
              {reviewer && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void action(async () => {
                      await api.POST("/api/v1/conversations/{cid}/notes", {
                        params: { path: { cid } },
                        body: { type: "staff_only_note", text: note },
                      });
                      if (alive.current) {
                        setNote("");
                        await load();
                        setStatus("Private staff note saved.");
                      }
                    });
                  }}
                >
                  <label>
                    Private staff note
                    <textarea
                      required
                      maxLength={4000}
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </label>
                  <button disabled={busy}>Save staff-only note</button>
                </form>
              )}
            </section>
          )}
          {tab === "Drafts" && reviewer && (
            <section aria-label="Private advisor drafts">
              <h4>Private AI drafts</h4>
              <p>
                Drafts use student-visible evidence and guidance. Review and
                edit a draft before publishing it as your own guidance.
              </p>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!conversation) return;
                  void action(async () => {
                    await api.POST(
                      "/api/v1/conversations/{cid}/advisor-drafts",
                      {
                        params: { path: { cid } },
                        headers: revision(conversation.version),
                        body: { message_id: draftMessage },
                      },
                    );
                    setStatus(
                      "Private draft requested. It will appear after validation.",
                    );
                  });
                }}
              >
                <label>
                  Student question for draft
                  <select
                    required
                    value={draftMessage}
                    onChange={(e) => setDraftMessage(e.target.value)}
                  >
                    <option value="">Choose a question</option>
                    {messages.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.text.slice(0, 100)}
                      </option>
                    ))}
                  </select>
                </label>
                <button disabled={busy || !conversation}>
                  Request private draft
                </button>
              </form>
              {drafts.map((d) => (
                <article key={d.id}>
                  <AdvisingAnswer
                    payload={d.payload}
                    onCitation={(id) => void viewCitation(id)}
                  />
                  <button
                    onClick={() => {
                      setSelectedDraft(d.id);
                      setDraftText(quoteText(d.payload));
                      setDraftReviewed(false);
                    }}
                  >
                    Review this draft for publication
                  </button>
                </article>
              ))}
              {selectedDraft && (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!conversation) return;
                    void action(async () => {
                      await api.POST("/api/v1/advisor-drafts/{did}/publish", {
                        params: { path: { did: selectedDraft } },
                        headers: revision(conversation.version),
                        body: { text: draftText, reviewed: true },
                      });
                      if (alive.current) {
                        setSelectedDraft("");
                        setDraftText("");
                        setDraftReviewed(false);
                        await load();
                        setStatus(
                          "Draft published as advisor-authored guidance.",
                        );
                      }
                    });
                  }}
                >
                  <label>
                    Guidance to publish
                    <textarea
                      required
                      maxLength={2000}
                      value={draftText}
                      onChange={(e) => {
                        setDraftText(e.target.value);
                        setDraftReviewed(false);
                      }}
                    />
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={draftReviewed}
                      onChange={(e) => setDraftReviewed(e.target.checked)}
                    />
                    I reviewed the evidence and take responsibility for this
                    advisor guidance.
                  </label>
                  <button disabled={!draftReviewed || busy}>
                    Publish reviewed advisor draft
                  </button>
                </form>
              )}
            </section>
          )}
        </>
      )}
      {citation && (
        <aside className="evidence-drawer" aria-label="Evidence drawer">
          <h4>{citation.title}</h4>
          <p>
            {pretty(citation.status)}
            {citation.published_at
              ? ` · published ${new Date(citation.published_at).toLocaleString()}`
              : ""}
          </p>
          <p>
            {Object.entries(citation.locator)
              .filter(([k]) => !["start", "end"].includes(k))
              .map(([k, v]) => `${pretty(k)} ${String(v)}`)
              .join(" · ")}
          </p>
          <blockquote>
            {citation.text ??
              "The source has been withdrawn; its excerpt is not available here."}
          </blockquote>
          <button onClick={() => setCitation(null)}>Close evidence</button>
        </aside>
      )}
      <PublishedEvidence mid={mid} purpose={purpose} fail={fail} />
      <CaseWorkspace
        mid={mid}
        cid={cid || undefined}
        scope={scope}
        staff={staff}
        purpose={purpose}
        fail={fail}
      />
    </section>
  );
}
