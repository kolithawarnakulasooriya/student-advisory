"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import type { components } from "../lib/api-types";
import { ApiError, type Me } from "../lib/api";
import { staffApi as api, revision } from "../lib/staff-api";

type S = components["schemas"];
type Org = S["OrganizationOut"];
type OrgPage = S["Page_OrganizationOut_"];
const empty = { items: [], total: 0, next_cursor: null };
async function allPages<T>(
  get: (
    cursor?: string,
  ) => Promise<{ data?: { items: T[]; next_cursor: string | null } }>,
) {
  const rows: T[] = [];
  let cursor: string | undefined;
  do {
    const response = await get(cursor);
    if (!response.data)
      throw new Error("Organization options are unavailable.");
    rows.push(...response.data.items);
    cursor = response.data.next_cursor ?? undefined;
  } while (cursor);
  return rows;
}

export default function OrganizationWorkspace({
  me,
  refreshMe,
}: {
  me: Me;
  refreshMe: () => Promise<void>;
}) {
  const isSuper = me.platform_grants.length > 0;
  const [institutions, setInstitutions] = useState<S["InstitutionOut"][]>([]);
  const [institution, setInstitution] = useState("");
  const [colleges, setColleges] = useState<Org[]>([]);
  const [page, setPage] = useState<OrgPage>(empty);
  const [grants, setGrants] = useState<S["Page_OrganizationGrantOut_"]>(empty);
  const [history, setHistory] = useState<S["Page_AuditOut_"]>(empty);
  const [historyOrg, setHistoryOrg] = useState<Org | null>(null);
  const [purpose, setPurpose] = useState<
    "administration" | "support_review" | "access_investigation"
  >("administration");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [reason, setReason] = useState("");
  const [editing, setEditing] = useState<Org | null>(null);
  const [kind, setKind] = useState<"college" | "department">(
    isSuper ||
      me.organization_grants.some((g) => g.scope_kind === "institution")
      ? "college"
      : "department",
  );
  const [parent, setParent] = useState("");
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [timezone, setTimezone] = useState("America/Chicago");
  const [email, setEmail] = useState("");
  const [target, setTarget] = useState<S["UserOut"] | null>(null);
  const [selected, setSelected] = useState<Org | null>(null);
  const [grantScope, setGrantScope] = useState<"institution" | "college">(
    "college",
  );
  const [expiry, setExpiry] = useState("");
  const serial = useRef(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const query = { purpose };
  const canCreateCollege =
    isSuper ||
    me.organization_grants.some(
      (g) => g.institution_id === institution && g.scope_kind === "institution",
    );

  const effectiveKind = canCreateCollege ? kind : "department";

  const fail = useCallback(
    async (e: unknown) => {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to load organization administration.",
      );
      if (e instanceof ApiError && (e.status === 401 || e.status === 403))
        await refreshMe();
    },
    [refreshMe],
  );

  const load = useCallback(
    async (cursor?: string) => {
      if (!institution) return;
      const generation = ++serial.current;
      setLoading(true);
      try {
        const result = await api.GET("/api/v1/admin/org-units", {
          params: {
            query: { institution_id: institution, purpose, limit: 10, cursor },
          },
        });
        if (generation === serial.current && result.data) setPage(result.data);
      } catch (e) {
        if (generation === serial.current) {
          setPage(empty);
          await fail(e);
        }
      } finally {
        if (generation === serial.current) setLoading(false);
      }
    },
    [institution, purpose, fail],
  );

  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      void allPages((cursor) =>
        api.GET("/api/v1/admin/institutions", {
          params: { query: { purpose, limit: 100, cursor } },
        }),
      )
        .then((items) => {
          if (active) {
            setInstitutions(items);
            setInstitution((old) =>
              items.some((i) => i.id === old) ? old : (items[0]?.id ?? ""),
            );
            if (!items.length) setLoading(false);
          }
        })
        .catch((e) => {
          if (active) {
            setLoading(false);
            void fail(e);
          }
        });
    }, 0);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [purpose, fail]);

  useEffect(() => {
    let active = true;
    const requests = serial;
    const timer = setTimeout(() => {
      void load();
      if (institution)
        void allPages((cursor) =>
          api.GET("/api/v1/admin/org-units", {
            params: {
              query: {
                institution_id: institution,
                purpose,
                kind: "college",
                limit: 100,
                cursor,
              },
            },
          }),
        )
          .then((items) => {
            if (active) setColleges(items.filter((i) => i.status === "active"));
          })
          .catch((e) => {
            if (active) void fail(e);
          });
      void api
        .GET("/api/v1/organization-admin-grants", {
          params: { query: { purpose, limit: 10 } },
        })
        .then((r) => {
          if (active && r.data) setGrants(r.data);
        })
        .catch((e) => {
          if (active) void fail(e);
        });
    }, 0);
    return () => {
      active = false;
      requests.current++;
      clearTimeout(timer);
    };
  }, [institution, purpose, load, fail]);

  async function act(operation: () => Promise<unknown>) {
    if (!reason.trim()) {
      setError("Enter a reason for the organization change.");
      return;
    }
    setBusy(true);
    setError("");
    setStatus("");
    try {
      await operation();
      setStatus("Organization change saved.");
      await refreshMe();
    } catch (e) {
      await fail(e);
      if (e instanceof ApiError && e.status === 409) {
        setEditing(null);
        await load();
      }
    } finally {
      setBusy(false);
      heading.current?.focus();
    }
  }
  function resetForm() {
    setEditing(null);
    setName("");
    setCode("");
    setTimezone("America/Chicago");
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      const metadata = { name, code, timezone, reason };
      if (editing)
        await api.PATCH("/api/v1/admin/org-units/{oid}", {
          params: { path: { oid: editing.id } },
          headers: revision(editing.version),
          body: metadata,
        });
      else
        await api.POST("/api/v1/admin/org-units", {
          body: {
            ...metadata,
            institution_id: institution,
            kind: effectiveKind,
            parent_id: effectiveKind === "department" ? parent : null,
          },
        });
    });
  }
  async function showHistory(org: Org, cursor?: string) {
    const generation = serial.current;
    try {
      const r = await api.GET("/api/v1/admin/org-units/{oid}/history", {
        params: {
          path: { oid: org.id },
          query: { purpose, limit: 10, cursor },
        },
      });
      if (r.data && generation === serial.current) {
        setHistoryOrg(org);
        setHistory(r.data);
      }
    } catch (e) {
      if (generation === serial.current) await fail(e);
    }
  }
  function selectInstitution(id: string) {
    serial.current++;
    setInstitution(id);
    setKind(
      isSuper ||
        me.organization_grants.some(
          (g) => g.institution_id === id && g.scope_kind === "institution",
        )
        ? "college"
        : "department",
    );
    setPage(empty);
    setColleges([]);
    setSelected(null);
    setHistoryOrg(null);
    setHistory(empty);
    setTarget(null);
    resetForm();
    setParent("");
  }

  return (
    <section
      id="organization-administration"
      tabIndex={-1}
      className="organization-workspace"
      aria-label="Organization administration"
      aria-busy={busy || loading}
    >
      <div className="workflow-heading">
        <div>
          <div className="eyebrow">ORGANIZATIONS</div>
          <h2 ref={heading} tabIndex={-1}>
            College and department administration
          </h2>
        </div>
        <button
          className="secondary"
          disabled={busy}
          onClick={() => void refreshMe()}
        >
          Refresh organizations
        </button>
      </div>
      <p>
        Manage organization details within your explicit administrative scope.
        Memberships and student records use separate permissions.
      </p>
      {error && (
        <div role="alert" aria-label="Organization error" className="alert">
          {error}
        </div>
      )}
      {status && (
        <p role="status" className="notice">
          {status}
        </p>
      )}
      <div className="org-controls">
        <label>
          Administration purpose
          <select
            value={purpose}
            disabled={busy}
            onChange={(e) => {
              setPurpose(e.target.value as typeof purpose);
              setPage(empty);
              setHistoryOrg(null);
            }}
          >
            <option value="administration">Administration</option>
            <option value="support_review">Support review</option>
            <option value="access_investigation">Access investigation</option>
          </select>
        </label>
        <label>
          Organization institution
          <select
            value={institution}
            disabled={busy}
            onChange={(e) => selectInstitution(e.target.value)}
          >
            {institutions.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Reason for organization action
          <textarea
            required
            maxLength={500}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Describe the organization change; omit student record content."
          />
        </label>
      </div>
      {!me.recent_auth && (
        <p className="notice">
          Recent authentication is required. Use the staff verification control
          before changing organizations.
        </p>
      )}
      {institution && (
        <details className="card" open={!!editing}>
          <summary>
            {editing ? "Edit organization" : "Create a college or department"}
          </summary>
          <form onSubmit={submit} className="org-form">
            {!editing && (
              <>
                <label>
                  Organization type
                  <select
                    value={effectiveKind}
                    onChange={(e) => setKind(e.target.value as typeof kind)}
                  >
                    {canCreateCollege && (
                      <option value="college">College</option>
                    )}
                    <option value="department">Department</option>
                  </select>
                </label>
                {effectiveKind === "department" && (
                  <label>
                    Parent college
                    <select
                      required
                      value={parent}
                      onChange={(e) => setParent(e.target.value)}
                    >
                      <option value="">Choose an active college</option>
                      {colleges.map((c) => (
                        <option key={c.id} value={c.id}>
                          {c.name}
                        </option>
                      ))}
                    </select>
                  </label>
                )}
              </>
            )}
            <label>
              Organization name
              <input
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label>
              Organization code
              <input
                required
                maxLength={80}
                value={code}
                onChange={(e) => setCode(e.target.value)}
              />
            </label>
            <label>
              Organization timezone
              <input
                required
                maxLength={100}
                value={timezone}
                onChange={(e) => setTimezone(e.target.value)}
                list="organization-timezones"
              />
              <datalist id="organization-timezones">
                <option value="America/Chicago" />
                <option value="UTC" />
                <option value="Asia/Colombo" />
              </datalist>
            </label>
            <div className="row-actions">
              <button disabled={busy || !me.recent_auth}>
                {editing ? "Save organization" : "Create organization"}
              </button>
              {editing && (
                <button type="button" className="secondary" onClick={resetForm}>
                  Cancel editing
                </button>
              )}
            </div>
          </form>
        </details>
      )}
      {loading ? (
        <p role="status">Loading authorized organizations…</p>
      ) : (
        <p>
          Showing {page.items.length} of {page.total} authorized organizations.
        </p>
      )}
      <div className="workflow-list">
        {page.items.map((org) => (
          <article key={org.id}>
            <div>
              <h3>{org.name}</h3>
              <p>
                {org.code} · {org.kind} · {org.status} · {org.timezone}
              </p>
              {org.kind === "department" && (
                <p>
                  Membership requests:{" "}
                  {org.enrollment_enabled ? "open" : "closed"}
                </p>
              )}
            </div>
            <div className="row-actions">
              <button
                className="secondary"
                disabled={busy}
                onClick={() => {
                  setEditing(org);
                  setName(org.name);
                  setCode(org.code);
                  setTimezone(org.timezone);
                }}
              >
                Edit organization
              </button>
              {org.kind === "department" && org.status === "active" && (
                <button
                  disabled={busy || !me.recent_auth}
                  onClick={() =>
                    void act(() =>
                      api.PUT("/api/v1/admin/org-units/{oid}/enrollment", {
                        params: { path: { oid: org.id } },
                        headers: revision(org.version),
                        body: { enabled: !org.enrollment_enabled, reason },
                      }),
                    )
                  }
                >
                  {org.enrollment_enabled
                    ? "Close membership requests"
                    : "Open membership requests"}
                </button>
              )}
              <button
                className="secondary"
                disabled={busy || !me.recent_auth}
                onClick={() =>
                  void act(() =>
                    org.status === "active"
                      ? api.POST("/api/v1/admin/org-units/{oid}/archive", {
                          params: { path: { oid: org.id } },
                          headers: revision(org.version),
                          body: { reason },
                        })
                      : api.POST("/api/v1/admin/org-units/{oid}/restore", {
                          params: { path: { oid: org.id } },
                          headers: revision(org.version),
                          body: { reason },
                        }),
                  )
                }
              >
                {org.status === "active"
                  ? "Archive organization"
                  : "Restore organization"}
              </button>
              <button
                className="text-button"
                onClick={() => void showHistory(org)}
              >
                Organization history
              </button>
              {isSuper &&
                org.kind === "department" &&
                org.status === "active" && (
                  <button
                    className="secondary"
                    onClick={() => {
                      setSelected(org);
                      setTarget(null);
                    }}
                  >
                    Appoint department manager
                  </button>
                )}
            </div>
          </article>
        ))}
      </div>
      {!loading && !page.total && (
        <p className="notice">
          No organizations in your administrative scope. Institution
          administrators can create a college first.
        </p>
      )}
      {page.next_cursor && (
        <button
          className="secondary"
          onClick={() => void load(page.next_cursor!)}
        >
          Next organizations page
        </button>
      )}
      {historyOrg && (
        <section className="card" aria-label="Organization history">
          <h3>History: {historyOrg.name}</h3>
          {history.items.map((e) => (
            <p key={e.id}>
              {e.action} · {e.reason ?? e.reason_code} ·{" "}
              {new Date(e.occurred_at).toLocaleString()}
            </p>
          ))}
          {history.next_cursor && (
            <button
              onClick={() => void showHistory(historyOrg, history.next_cursor!)}
            >
              Next organization history page
            </button>
          )}
          <button
            className="text-button"
            onClick={() => {
              setHistoryOrg(null);
              setHistory(empty);
            }}
          >
            Close organization history
          </button>
        </section>
      )}
      {isSuper && (
        <section
          className="card"
          aria-label="Organization delegation and appointments"
        >
          <h3>
            {selected
              ? `Appoint manager: ${selected.name}`
              : "Delegate organization administration"}
          </h3>
          <p>
            Organization delegation grants metadata management only. Manager
            appointment is a separate action.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setError("");
              setTarget(null);
              void api
                .GET("/api/v1/users", {
                  params: { query: { email, purpose, limit: 10 } },
                })
                .then((r) => {
                  const user = r.data?.items.find(
                    (u) =>
                      u.email === email && u.verified && u.status === "active",
                  );
                  if (user) setTarget(user);
                  else
                    setError("No verified active synthetic account matched.");
                })
                .catch(fail);
            }}
          >
            <label>
              Appointment email
              <input
                required
                type="email"
                value={email}
                onChange={(e) => {
                  setEmail(e.target.value);
                  setTarget(null);
                }}
              />
            </label>
            <button className="secondary" disabled={busy}>
              Find appointment account
            </button>
          </form>
          {target && (
            <p role="status">
              Selected account: {target.name} · {target.email}
            </p>
          )}
          {selected ? (
            <div className="row-actions">
              <button
                disabled={!target || busy || !me.recent_auth}
                onClick={() =>
                  void act(() =>
                    api.POST("/api/v1/role-grants", {
                      body: {
                        user_id: target!.id,
                        org_unit_id: selected.id,
                        role: "manager",
                        ceiling: "advisor",
                        reason,
                      },
                    }),
                  )
                }
              >
                Confirm manager appointment
              </button>
              <button
                className="secondary"
                onClick={() => {
                  setSelected(null);
                  setTarget(null);
                }}
              >
                Cancel manager appointment
              </button>
            </div>
          ) : (
            <>
              <label>
                Delegation scope
                <select
                  value={grantScope}
                  onChange={(e) =>
                    setGrantScope(e.target.value as typeof grantScope)
                  }
                >
                  <option value="college">
                    One college and its department metadata
                  </option>
                  <option value="institution">
                    This institution and its organization metadata
                  </option>
                </select>
              </label>
              {grantScope === "college" && (
                <label>
                  Delegated college
                  <select
                    value={parent}
                    onChange={(e) => setParent(e.target.value)}
                  >
                    <option value="">Choose a college</option>
                    {colleges.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label>
                Delegation expiry (optional)
                <input
                  type="datetime-local"
                  value={expiry}
                  onChange={(e) => setExpiry(e.target.value)}
                />
              </label>
              <button
                disabled={
                  !target ||
                  busy ||
                  !me.recent_auth ||
                  (grantScope === "college" && !parent)
                }
                onClick={() =>
                  void act(() =>
                    api.POST("/api/v1/organization-admin-grants", {
                      body: {
                        user_id: target!.id,
                        institution_id: institution,
                        scope_kind: grantScope,
                        root_org_unit_id:
                          grantScope === "college" ? parent : null,
                        valid_until: expiry
                          ? new Date(expiry).toISOString()
                          : null,
                        reason,
                      },
                    }),
                  )
                }
              >
                Delegate organization management
              </button>
            </>
          )}
        </section>
      )}
      <section aria-label="Organization administration grants">
        <h3>
          {isSuper
            ? "Organization administration grants"
            : "Your organization administration grants"}
        </h3>
        {grants.items.map((g) => (
          <article className="org-grant" key={g.id}>
            <p>
              {g.scope_kind} · {g.status} · account {g.user_id}
              {g.valid_until
                ? ` · expires ${new Date(g.valid_until).toLocaleString()}`
                : ""}
            </p>
            {isSuper && g.status !== "revoked" && (
              <div className="row-actions">
                {(g.status === "active"
                  ? (["suspended", "revoked"] as const)
                  : (["active", "revoked"] as const)
                ).map((state) => (
                  <button
                    key={state}
                    className="secondary"
                    disabled={busy || !me.recent_auth}
                    onClick={() =>
                      void act(() =>
                        api.POST(
                          "/api/v1/organization-admin-grants/{gid}/state",
                          {
                            params: { path: { gid: g.id } },
                            headers: revision(g.version),
                            body: { status: state, reason },
                          },
                        ),
                      )
                    }
                  >
                    {state === "active"
                      ? "Reactivate"
                      : state === "suspended"
                        ? "Suspend"
                        : "Revoke"}{" "}
                    organization grant
                  </button>
                ))}
              </div>
            )}
          </article>
        ))}
        {grants.next_cursor && (
          <button
            className="secondary"
            onClick={() =>
              void api
                .GET("/api/v1/organization-admin-grants", {
                  params: {
                    query: { ...query, limit: 10, cursor: grants.next_cursor! },
                  },
                })
                .then((r) => {
                  if (r.data) setGrants(r.data);
                })
                .catch(fail)
            }
          >
            Next organization grants page
          </button>
        )}
      </section>
    </section>
  );
}
