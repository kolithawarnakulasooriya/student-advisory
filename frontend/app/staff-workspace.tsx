"use client";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { components, paths } from "../lib/api-types";
import type { Me } from "../lib/api";
import { ApiError, post } from "../lib/api";
import { staffApi as api, revision } from "../lib/staff-api";

type S = components["schemas"];
type Tab =
  "Requests" | "Invitations" | "Memberships" | "Students" | "Audit" | "Users";
type Purpose = NonNullable<
  NonNullable<paths["/api/v1/users"]["get"]["parameters"]["query"]>["purpose"]
>;
const secretaryCaps = [
  "student.invite",
  "student.approve",
  "student.manage",
  "assignment.manage",
];
const platformCaps = [
  ...secretaryCaps,
  "org.read",
  "profile.configure",
  "source.manage",
  "source.read",
  "advisor.invite",
  "advisor.approve",
  "advisor.manage",
  "manager.invite",
  "manager.manage",
  "secretary.manage",
  "membership.read",
  "student.read",
  "staff.read",
  "audit.read",
  "history.read",
];
const blankPage = { items: [], total: 0, next_cursor: null };
const pretty = (text: string) => text.replaceAll("_", " ");

// Reference selectors follow bounded server pages without dropping later options.
async function selectorPages<T>(
  load: (cursor?: string) => Promise<{
    data?: { items: T[]; next_cursor: string | null };
  }>,
): Promise<T[]> {
  const items: T[] = [];
  let cursor: string | undefined;
  do {
    const response = await load(cursor);
    if (!response.data) throw new Error("Unable to load workflow options.");
    items.push(...response.data.items);
    cursor = response.data.next_cursor ?? undefined;
  } while (cursor);
  return items;
}

export default function StaffWorkspace({
  me,
  refreshMe,
  invitation,
  clearInvitation,
}: {
  me: Me;
  refreshMe: () => Promise<void>;
  invitation: string;
  clearInvitation: () => void;
}) {
  const scope = me.active_scope ?? undefined;
  const caps = me.capabilities;
  const isGlobal = (me.platform_grants?.length ?? 0) > 0;
  const [tab, setTab] = useState<Tab>(
    caps.includes("roster.read") && !caps.includes("student.approve")
      ? "Students"
      : "Requests",
  );
  const [purpose, setPurpose] = useState<Purpose>("administration");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [advisors, setAdvisors] = useState<S["AdvisorOut"][]>([]);
  const [advisor, setAdvisor] = useState("");
  const [options, setOptions] = useState<{ id: string; name: string }[]>([]);
  const [requestScope, setRequestScope] = useState("");
  const [role, setRole] = useState<"student" | "advisor" | "manager">(
    "student",
  );
  const [justification, setJustification] = useState("");
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] =
    useState<S["InviteInput"]["role"]>("student");
  const [selectedCaps, setSelectedCaps] = useState<string[]>([]);
  const [capacity, setCapacity] = useState("");
  const [ceiling, setCeiling] = useState<"student" | "advisor" | "manager">(
    "advisor",
  );
  const [emailSearch, setEmailSearch] = useState("");
  const [requests, setRequests] = useState<S["Page_RequestOut_"]>(blankPage);
  const [invites, setInvites] = useState<S["Page_InviteOut_"]>(blankPage);
  const [members, setMembers] = useState<S["Page_MemberOut_"]>(blankPage);
  const [students, setStudents] = useState<S["Page_StudentOut_"]>(blankPage);
  const [events, setEvents] = useState<S["Page_AuditOut_"]>(blankPage);
  const [users, setUsers] = useState<S["Page_UserOut_"]>(blankPage);
  const [platformGrants, setPlatformGrants] = useState<S["PlatformOut"][]>([]);
  const [historyUser, setHistoryUser] = useState("");
  const serial = useRef(0);
  const can = (cap: string) => caps.includes(cap);
  const hasInvites =
    caps.some((c) => c.endsWith(".invite")) || can("secretary.manage");
  const hasAdvisors = [
    "assignment.manage",
    "student.approve",
    "student.invite",
  ].some((c) => caps.includes(c));
  const tabs: Tab[] = [
    "Requests",
    ...(hasInvites ? ["Invitations" as const] : []),
    ...(can("membership.read") ? ["Memberships" as const] : []),
    ...(can("student.read") || can("roster.read") ? ["Students" as const] : []),
    ...(can("audit.own") ? ["Audit" as const] : []),
    ...(can("staff.read") || isGlobal ? ["Users" as const] : []),
  ];

  const load = useCallback(
    async (cursor?: string) => {
      const version = ++serial.current;
      const query = { scope_id: scope, purpose, cursor, limit: 10 };
      try {
        if (tab === "Requests") {
          const result = await api.GET("/api/v1/membership-requests", {
            params: {
              query: { ...query, scope_id: isGlobal ? undefined : scope },
            },
          });
          if (version === serial.current && result.data)
            setRequests(result.data);
        } else if (tab === "Invitations" && scope) {
          const result = await api.GET("/api/v1/invitations", {
            params: { query: { ...query, scope_id: scope } },
          });
          if (version === serial.current && result.data)
            setInvites(result.data);
        } else if (tab === "Memberships" && scope) {
          const result = await api.GET("/api/v1/memberships", {
            params: { query: { ...query, scope_id: scope } },
          });
          if (version === serial.current && result.data)
            setMembers(result.data);
        } else if (tab === "Students" && scope) {
          const result = await api.GET("/api/v1/students", {
            params: { query: { ...query, scope_id: scope } },
          });
          if (version === serial.current && result.data)
            setStudents(result.data);
        } else if (tab === "Audit") {
          const result = historyUser
            ? await api.GET("/api/v1/users/{uid}/history", {
                params: { path: { uid: historyUser }, query },
              })
            : await api.GET("/api/v1/audit-events", { params: { query } });
          if (version === serial.current && result.data) setEvents(result.data);
        } else if (tab === "Users") {
          const result = await api.GET("/api/v1/users", {
            params: {
              query: {
                ...query,
                scope_id: isGlobal ? undefined : scope,
                email: emailSearch || undefined,
              },
            },
          });
          if (version === serial.current && result.data) setUsers(result.data);
          if (isGlobal) {
            const grants = await selectorPages((cursor) =>
              api.GET("/api/v1/platform-grants", {
                params: { query: { purpose, limit: 100, cursor } },
              }),
            );
            if (version === serial.current) setPlatformGrants(grants);
          }
        }
      } catch (e) {
        if (version === serial.current) {
          setError(
            e instanceof Error ? e.message : "Unable to load workflow data.",
          );
          if (e instanceof ApiError && e.status === 401) await refreshMe();
        }
      }
    },
    [scope, purpose, tab, isGlobal, emailSearch, historyUser, refreshMe],
  );

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      void load();
      void selectorPages((cursor) =>
        api.GET("/api/v1/membership-options", {
          params: { query: { limit: 100, cursor } },
        }),
      )
        .then((items) => {
          if (active) {
            setOptions(items);
            setRequestScope((old) =>
              items.some((o) => o.id === old) ? old : (items[0]?.id ?? ""),
            );
          }
        })
        .catch(() => {});
      if (hasAdvisors && scope)
        void selectorPages((cursor) =>
          api.GET("/api/v1/eligible-advisors", {
            params: { query: { scope_id: scope, purpose, limit: 100, cursor } },
          }),
        )
          .then((items) => {
            if (active) setAdvisors(items);
          })
          .catch((e) => {
            if (active)
              setError(
                e instanceof Error ? e.message : "Unable to load advisors.",
              );
          });
    }, 0);
    return () => {
      clearTimeout(timer);
      active = false;
    };
  }, [scope, purpose, hasAdvisors, load]);

  async function act(operation: () => Promise<unknown>, needsReason = true) {
    if (needsReason && !reason.trim()) {
      setError("Enter a reason for this action.");
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await operation();
      setStatus("Saved. Permissions and state were checked by the server.");
      await refreshMe();
      await load();
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "Unable to complete the action.",
      );
      if (e instanceof ApiError && e.status === 401) await refreshMe();
    } finally {
      setBusy(false);
    }
  }
  function requestMembership(event: FormEvent) {
    event.preventDefault();
    void act(
      () =>
        api.POST("/api/v1/membership-requests", {
          body: {
            org_unit_id: requestScope,
            requested_role: role,
            justification,
          },
        }),
      false,
    );
  }
  const advisorSelector = (
    <label>
      Primary advisor
      <select value={advisor} onChange={(e) => setAdvisor(e.target.value)}>
        <option value="">Choose an eligible advisor</option>
        {advisors.map((a) => (
          <option key={a.id} value={a.id}>
            {a.name} ({a.assigned_count}
            {a.capacity ? `/${a.capacity}` : " assigned"})
          </option>
        ))}
      </select>
    </label>
  );
  function grantState(
    member: S["MemberOut"],
    state: "active" | "suspended" | "revoked",
  ) {
    return act(() =>
      api.PATCH("/api/v1/memberships/{gid}", {
        params: { path: { gid: member.id } },
        headers: revision(member.version),
        body: { status: state, reason, advisor_grant_id: advisor || null },
      }),
    );
  }
  const page =
    tab === "Requests"
      ? requests
      : tab === "Invitations"
        ? invites
        : tab === "Memberships"
          ? members
          : tab === "Students"
            ? students
            : tab === "Users"
              ? users
              : events;

  return (
    <section
      className="operations"
      aria-label="Membership and staff workflows"
      aria-busy={busy}
    >
      <div className="section-title">
        <div>
          <div className="eyebrow">RELEASE 0.2</div>
          <h2>Membership and staff workflows</h2>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => {
            setError("");
            void load();
          }}
        >
          Refresh workflow
        </button>
      </div>
      {error && (
        <div className="alert" role="alert" aria-label="Workflow error">
          {error}
          <button
            className="text-button"
            disabled={busy}
            onClick={() =>
              void act(async () => {
                await post("/api/v1/auth/simulator/step-up");
              }, false)
            }
          >
            Refresh synthetic authentication
          </button>
        </div>
      )}
      {status && (
        <p className="notice" role="status">
          {status}
        </p>
      )}
      {invitation && (
        <section className="card">
          <h3>Accept your invitation</h3>
          <p>
            Your verified identity must match the invited email. No privileges
            activate until the server confirms acceptance.
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void act(async () => {
                await api.POST("/api/v1/invitations/accept", {
                  body: { token: invitation },
                });
                clearInvitation();
              }, false)
            }
          >
            Accept invitation
          </button>
          <button
            className="text-button"
            disabled={busy}
            onClick={clearInvitation}
          >
            Dismiss invitation
          </button>
        </section>
      )}
      {isGlobal && (
        <label>
          Purpose for global oversight
          <select
            value={purpose}
            onChange={(e) => setPurpose(e.target.value as Purpose)}
          >
            <option value="administration">Staff administration</option>
            <option value="support_review">Support review</option>
            <option value="access_investigation">Access investigation</option>
          </select>
        </label>
      )}
      <nav className="workflow-tabs" aria-label="Workflow views">
        {tabs.map((t) => (
          <button
            key={t}
            className={t === tab ? "" : "secondary"}
            disabled={busy}
            aria-current={t === tab ? "page" : undefined}
            onClick={() => {
              serial.current++;
              setTab(t);
              setError("");
              setHistoryUser("");
            }}
          >
            {t}
          </button>
        ))}
      </nav>
      <p className="small">
        Showing {page.items.length} of {page.total} authorized items.
      </p>
      {tab === "Requests" && (
        <>
          <details className="card">
            <summary>Request a membership</summary>
            <form onSubmit={requestMembership}>
              <label>
                Requested department
                <select
                  required
                  value={requestScope}
                  onChange={(e) => setRequestScope(e.target.value)}
                >
                  {options.map((o) => (
                    <option key={o.id} value={o.id}>
                      {o.name}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                Requested role
                <select
                  value={role}
                  onChange={(e) => setRole(e.target.value as typeof role)}
                >
                  <option value="student">Student</option>
                  <option value="advisor">Advisor</option>
                  <option value="manager">Manager</option>
                </select>
              </label>
              <label>
                Justification
                <textarea
                  required
                  maxLength={1000}
                  value={justification}
                  onChange={(e) => setJustification(e.target.value)}
                />
              </label>
              <button disabled={busy || !requestScope}>
                Submit membership request
              </button>
            </form>
          </details>
          {hasAdvisors && advisorSelector}
          {requests.items.map((r) => (
            <article className="workflow-row" key={r.id}>
              <div>
                <h3>
                  {r.name} · {pretty(r.requested_role)}
                </h3>
                <p className="small">
                  {r.email} · {r.status}
                </p>
                <p>{r.justification}</p>
                {r.decision_reason && <p>Decision: {r.decision_reason}</p>}
              </div>
              {r.status === "pending" &&
                r.user_id !== me.user_id &&
                can(r.requested_role + ".approve") && (
                  <div className="actions">
                    <button
                      disabled={
                        busy || (r.requested_role === "student" && !advisor)
                      }
                      onClick={() =>
                        void act(() =>
                          api.POST(
                            "/api/v1/membership-requests/{rid}/approve",
                            {
                              params: { path: { rid: r.id } },
                              headers: revision(r.version),
                              body: {
                                reason,
                                advisor_grant_id: advisor || null,
                              },
                            },
                          ),
                        )
                      }
                    >
                      Approve {pretty(r.requested_role)}
                    </button>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          api.POST("/api/v1/membership-requests/{rid}/reject", {
                            params: { path: { rid: r.id } },
                            headers: revision(r.version),
                            body: { reason },
                          }),
                        )
                      }
                    >
                      Reject request
                    </button>
                  </div>
                )}
            </article>
          ))}
        </>
      )}
      {tab === "Invitations" && scope && (
        <>
          <form
            className="card"
            onSubmit={(event) => {
              event.preventDefault();
              void act(
                () =>
                  api.POST("/api/v1/invitations", {
                    body: {
                      email: inviteEmail,
                      org_unit_id: scope,
                      role: inviteRole,
                      advisor_grant_id: advisor || null,
                      capabilities:
                        inviteRole === "secretary" ? selectedCaps : [],
                    },
                  }),
                false,
              );
            }}
          >
            <h3>Invite a synthetic user</h3>
            <label>
              Invitation email
              <input
                type="email"
                required
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
              />
            </label>
            <label>
              Invitation role
              <select
                value={inviteRole}
                onChange={(e) => {
                  setInviteRole(e.target.value as typeof inviteRole);
                  setSelectedCaps([]);
                }}
              >
                {["student", "advisor", "secretary", "manager"]
                  .filter((r) =>
                    can(r === "secretary" ? "secretary.manage" : r + ".invite"),
                  )
                  .map((r) => (
                    <option key={r} value={r}>
                      {pretty(r)}
                    </option>
                  ))}
              </select>
            </label>
            {inviteRole === "student" && advisorSelector}
            {inviteRole === "secretary" && (
              <fieldset>
                <legend>Explicit secretary delegation</legend>
                {secretaryCaps.map((c) => (
                  <label className="check" key={c}>
                    <input
                      type="checkbox"
                      checked={selectedCaps.includes(c)}
                      onChange={(e) =>
                        setSelectedCaps((old) =>
                          e.target.checked
                            ? [...old, c]
                            : old.filter((x) => x !== c),
                        )
                      }
                    />
                    {c}
                  </label>
                ))}
              </fieldset>
            )}
            <button disabled={busy || (inviteRole === "student" && !advisor)}>
              Send local invitation
            </button>
            <p className="small">
              Delivery appears in the{" "}
              <a href="http://localhost:8025" target="_blank" rel="noreferrer">
                local Mailpit inbox
              </a>
              . No external email is sent.
            </p>
          </form>
          {invites.items.map((i) => (
            <article className="workflow-row" key={i.id}>
              <div>
                <h3>{i.email}</h3>
                <p>
                  {i.role} · {i.status} · Expires{" "}
                  {new Date(i.expires_at).toLocaleString()}
                </p>
              </div>
              {["pending", "expired"].includes(i.status) && (
                <div className="actions">
                  <button
                    disabled={busy}
                    onClick={() =>
                      void act(() =>
                        api.POST("/api/v1/invitations/{iid}/resend", {
                          params: { path: { iid: i.id } },
                          headers: revision(i.version),
                          body: { reason },
                        }),
                      )
                    }
                  >
                    Resend invitation
                  </button>
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() =>
                      void act(() =>
                        api.POST("/api/v1/invitations/{iid}/revoke", {
                          params: { path: { iid: i.id } },
                          headers: revision(i.version),
                          body: { reason },
                        }),
                      )
                    }
                  >
                    Revoke invitation
                  </button>
                </div>
              )}
            </article>
          ))}
        </>
      )}
      {tab === "Memberships" && (
        <>
          {hasAdvisors && advisorSelector}
          <p className="small">
            Enrollment metadata only. Secretary permissions do not include
            student records.
          </p>
          {members.items.map((m) => (
            <article className="workflow-row" key={m.id}>
              <div>
                <h3>
                  {m.name} · {pretty(m.role)}
                </h3>
                <p className="small">
                  {m.email} · {m.status}
                  {m.account_state !== "active"
                    ? ` · account ${m.account_state}`
                    : ""}
                </p>
                {m.role === "student" && (
                  <p>
                    Primary advisor: {m.advisor_name ?? "Reassignment required"}
                  </p>
                )}
              </div>
              <div className="actions">
                {m.student_membership_id &&
                  m.status === "active" &&
                  can("assignment.manage") && (
                    <button
                      disabled={busy || !advisor}
                      onClick={() =>
                        void act(async () => {
                          // Enrollment projections expose relationship version through the dedicated assignment read.
                          const result = await api.GET(
                            "/api/v1/assignment-state/{mid}",
                            {
                              params: {
                                path: { mid: m.student_membership_id! },
                                query: { purpose },
                              },
                            },
                          );
                          if (result.data)
                            await api.PUT("/api/v1/students/{mid}/advisor", {
                              params: {
                                path: { mid: m.student_membership_id! },
                              },
                              headers: revision(result.data.version),
                              body: { advisor_grant_id: advisor, reason },
                            });
                        })
                      }
                    >
                      Assign selected advisor
                    </button>
                  )}
                {m.user_id !== me.user_id &&
                  can(
                    m.role === "secretary"
                      ? "secretary.manage"
                      : m.role === "platform_admin"
                        ? "platform.manage"
                        : m.role + ".manage",
                  ) && (
                    <>
                      {m.status === "active" && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => void grantState(m, "suspended")}
                        >
                          Suspend membership
                        </button>
                      )}
                      {m.status === "suspended" && (
                        <button
                          disabled={
                            busy ||
                            (m.role === "student" &&
                              (!advisor || !can("assignment.manage")))
                          }
                          onClick={() => void grantState(m, "active")}
                        >
                          Reactivate membership
                        </button>
                      )}
                      {["active", "suspended"].includes(m.status) && (
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() => void grantState(m, "revoked")}
                        >
                          Revoke membership
                        </button>
                      )}
                      {["secretary", "platform_admin", "advisor"].includes(
                        m.role,
                      ) && (
                        <details
                          name="delegation-editor"
                          onToggle={(event) => {
                            if (event.currentTarget.open) {
                              setSelectedCaps(m.capabilities);
                              setCapacity(
                                m.capacity === null ? "" : String(m.capacity),
                              );
                              setCeiling(m.ceiling as typeof ceiling);
                            }
                          }}
                        >
                          <summary>Change delegation or capacity</summary>
                          {m.role !== "advisor" && (
                            <fieldset>
                              <legend>Explicit capabilities</legend>
                              {(m.role === "secretary"
                                ? secretaryCaps
                                : platformCaps
                              ).map((c) => (
                                <label className="check" key={c}>
                                  <input
                                    type="checkbox"
                                    checked={selectedCaps.includes(c)}
                                    onChange={(e) =>
                                      setSelectedCaps((old) =>
                                        e.target.checked
                                          ? [...old, c]
                                          : old.filter((x) => x !== c),
                                      )
                                    }
                                  />
                                  {c}
                                </label>
                              ))}
                            </fieldset>
                          )}
                          {m.role === "platform_admin" && (
                            <label>
                              Appointment ceiling
                              <select
                                value={ceiling}
                                onChange={(e) =>
                                  setCeiling(e.target.value as typeof ceiling)
                                }
                              >
                                <option value="student">Student</option>
                                <option value="advisor">Advisor</option>
                                <option value="manager">Manager</option>
                              </select>
                            </label>
                          )}
                          {m.role === "advisor" && (
                            <label>
                              Advisor capacity (blank means no configured limit)
                              <input
                                type="number"
                                min="1"
                                value={capacity}
                                onChange={(e) => setCapacity(e.target.value)}
                              />
                            </label>
                          )}
                          <button
                            disabled={busy}
                            onClick={() =>
                              void act(() =>
                                api.PATCH("/api/v1/role-grants/{gid}", {
                                  params: { path: { gid: m.id } },
                                  headers: revision(m.version),
                                  body: {
                                    reason,
                                    capabilities:
                                      m.role === "advisor" ? [] : selectedCaps,
                                    ceiling:
                                      m.role === "platform_admin"
                                        ? ceiling
                                        : "advisor",
                                    capacity:
                                      m.role === "advisor" && capacity
                                        ? Number(capacity)
                                        : null,
                                  },
                                }),
                              )
                            }
                          >
                            Save delegation
                          </button>
                        </details>
                      )}
                    </>
                  )}
                {can("history.read") && (
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => {
                      setHistoryUser(m.user_id);
                      setTab("Audit");
                    }}
                  >
                    View scoped history
                  </button>
                )}
              </div>
            </article>
          ))}
        </>
      )}
      {tab === "Students" &&
        students.items.map((s) => (
          <article className="workflow-row" key={s.id}>
            <div>
              <h3>{s.name}</h3>
              <p className="small">{s.email}</p>
              <p>
                Primary advisor: {s.advisor_name ?? "Reassignment required"}
              </p>
              <p className="small">
                Authorized student summary. Review academic facts and documents in the academic workspace below.
              </p>
            </div>
          </article>
        ))}
      {tab === "Audit" && (
        <>
          {historyUser && (
            <p className="notice">
              Scoped user/advisor timeline
              <button
                className="text-button"
                onClick={() => setHistoryUser("")}
              >
                Return to audit
              </button>
            </p>
          )}
          {events.items.map((e) => (
            <article className="workflow-row" key={e.id}>
              <div>
                <h3>{e.action}</h3>
                <p>
                  {e.result} · {e.reason_code}
                </p>
                <p className="small">
                  {new Date(e.occurred_at).toLocaleString()} · {e.object_type}
                  {e.object_id ? ` · ${e.object_id}` : ""}
                </p>
              </div>
            </article>
          ))}
        </>
      )}
      {tab === "Users" && (
        <>
          <label>
            Search exact verified email
            <input
              type="email"
              value={emailSearch}
              onChange={(e) => setEmailSearch(e.target.value)}
            />
          </label>
          {users.items.map((u) => (
            <article className="workflow-row" key={u.id}>
              <div>
                <h3>{u.name}</h3>
                <p>
                  {u.email} · {u.status}
                </p>
              </div>
              <div className="actions">
                {can("history.read") && (
                  <button
                    className="secondary"
                    disabled={busy}
                    onClick={() => {
                      setHistoryUser(u.id);
                      setTab("Audit");
                    }}
                  >
                    View user history
                  </button>
                )}
                {isGlobal && u.id !== me.user_id && (
                  <>
                    <button
                      className="secondary"
                      disabled={busy}
                      onClick={() =>
                        void act(() =>
                          api.POST("/api/v1/users/{uid}/state", {
                            params: { path: { uid: u.id } },
                            headers: revision(u.grant_epoch),
                            body: {
                              status:
                                u.status === "active" ? "suspended" : "active",
                              reason,
                              approved_grant_ids: [],
                            },
                          }),
                        )
                      }
                    >
                      {u.status === "active"
                        ? "Suspend account"
                        : "Reactivate account only"}
                    </button>
                    {u.verified &&
                      u.status === "active" &&
                      !platformGrants.some(
                        (g) => g.user_id === u.id && g.status !== "revoked",
                      ) && (
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act(() =>
                              api.POST("/api/v1/platform-grants", {
                                body: { user_id: u.id, reason },
                              }),
                            )
                          }
                        >
                          Appoint platform super admin
                        </button>
                      )}
                    {u.verified && u.status === "active" && scope && (
                      <details>
                        <summary>Appoint scoped platform admin</summary>
                        <fieldset>
                          <legend>Delegated administration capabilities</legend>
                          {platformCaps.map((c) => (
                            <label className="check" key={c}>
                              <input
                                type="checkbox"
                                checked={selectedCaps.includes(c)}
                                onChange={(e) =>
                                  setSelectedCaps((old) =>
                                    e.target.checked
                                      ? [...old, c]
                                      : old.filter((x) => x !== c),
                                  )
                                }
                              />
                              {c}
                            </label>
                          ))}
                        </fieldset>
                        <label>
                          Appointment ceiling
                          <select
                            value={ceiling}
                            onChange={(e) =>
                              setCeiling(e.target.value as typeof ceiling)
                            }
                          >
                            <option value="student">Student</option>
                            <option value="advisor">Advisor</option>
                            <option value="manager">Manager</option>
                          </select>
                        </label>
                        <button
                          disabled={busy}
                          onClick={() =>
                            void act(() =>
                              api.POST("/api/v1/role-grants", {
                                body: {
                                  user_id: u.id,
                                  org_unit_id: scope,
                                  role: "platform_admin",
                                  reason,
                                  capabilities: selectedCaps,
                                  ceiling,
                                },
                              }),
                            )
                          }
                        >
                          Appoint delegated admin
                        </button>
                      </details>
                    )}
                  </>
                )}
              </div>
            </article>
          ))}
          {isGlobal && (
            <section className="card">
              <h3>Platform super-admin grants</h3>
              {platformGrants.map((g) => (
                <div className="workflow-row" key={g.id}>
                  <p>
                    {g.user_id} · {g.status}
                  </p>
                  <div className="actions">
                    {g.status !== "revoked" && (
                      <>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            void act(() =>
                              api.POST("/api/v1/platform-grants/{gid}/state", {
                                params: { path: { gid: g.id } },
                                headers: revision(g.version),
                                body: {
                                  status:
                                    g.status === "active"
                                      ? "suspended"
                                      : "active",
                                  reason,
                                },
                              }),
                            )
                          }
                        >
                          {g.status === "active"
                            ? "Suspend platform grant"
                            : "Reactivate platform grant"}
                        </button>
                        <button
                          className="secondary"
                          disabled={busy}
                          onClick={() =>
                            void act(() =>
                              api.POST("/api/v1/platform-grants/{gid}/state", {
                                params: { path: { gid: g.id } },
                                headers: revision(g.version),
                                body: { status: "revoked", reason },
                              }),
                            )
                          }
                        >
                          Revoke platform grant
                        </button>
                      </>
                    )}
                  </div>
                </div>
              ))}
            </section>
          )}
        </>
      )}
      {page.items.length === 0 && (
        <p className="empty" role="status">
          No authorized items in this view.
        </p>
      )}
      {page.next_cursor && (
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void load(page.next_cursor!)}
        >
          Next page
        </button>
      )}
      {caps.some(
        (c) =>
          c.endsWith(".approve") ||
          c.endsWith(".manage") ||
          c.endsWith(".invite"),
      ) && (
        <label>
          Reason for staff action
          <textarea
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="State the operational reason; do not paste student record content."
          />
        </label>
      )}
    </section>
  );
}
