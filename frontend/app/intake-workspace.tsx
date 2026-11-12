"use client";
import { useCallback, useEffect, useState } from "react";
import type { components } from "../lib/api-types";
import { ApiError, type Me } from "../lib/api";
import { staffApi as api } from "../lib/staff-api";
import ProfileWorkspace from "./profile-workspace";
import SourceWorkspace from "./source-workspace";
import SchemaWorkspace from "./schema-workspace";

export type S = components["schemas"];
export type Purpose =
  "administration" | "support_review" | "access_investigation";
export const pretty = (value: string) => value.replaceAll("_", " ");
export default function IntakeWorkspace({
  me,
  refreshMe,
}: {
  me: Me;
  refreshMe: () => Promise<void>;
}) {
  const scope = me.active_scope ?? undefined;
  const memberships = (me.student_memberships ?? []).filter((m) =>
    me.active_grants.some(
      (g) =>
        g.id === m.grant_id && g.org_unit_id === scope && g.role === "student",
    ),
  );
  const [tab, setTab] = useState("Profile");
  const [students, setStudents] = useState<S["StudentOut"][]>([]);
  const [mid, setMid] = useState(memberships[0]?.id ?? "");
  const [purpose, setPurpose] = useState<Purpose>("support_review");
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const global = (me.platform_grants?.length ?? 0) > 0;
  const staff =
    global ||
    me.capabilities.includes("student.read") ||
    me.active_grants.some(
      (g) => g.role === "advisor" && g.org_unit_id === scope,
    );
  const configure = global || me.capabilities.includes("profile.configure");
  const sourceManager = global || me.capabilities.includes("source.manage");
  const sourceReader = sourceManager || me.capabilities.includes("source.read");
  const fail = useCallback(
    async (e: unknown) => {
      setError(
        e instanceof Error
          ? e.message
          : "Unable to complete this action. Retry.",
      );
      if (e instanceof ApiError && [401, 403, 404].includes(e.status)) {
        setDenied(true);
        setStudents([]);
        await refreshMe();
      }
    },
    [refreshMe],
  );
  useEffect(() => {
    let active = true;
    async function load() {
      if (!scope || !staff) return;
      const rows: S["StudentOut"][] = [];
      let cursor: string | undefined;
      do {
        const { data } = await api.GET("/api/v1/students", {
          params: {
            query: { scope_id: scope, cursor, ...(global ? { purpose } : {}) },
          },
        });
        if (!active || !data) return;
        rows.push(...data.items);
        cursor = data.next_cursor ?? undefined;
      } while (cursor);
      setStudents(rows);
      setMid((old) =>
        rows.some((r) => r.id === old) ? old : (rows[0]?.id ?? ""),
      );
    }
    void load().catch(fail);
    return () => {
      active = false;
    };
  }, [scope, staff, global, purpose, fail]);
  if (
    !scope ||
    (!staff && !configure && !sourceReader && !memberships.length)
  )
    return null;
  const own = memberships.some((m) => m.id === mid);
  const selectedScope = me.scopes.find((s) => s.id === scope);
  return (
    <section
      className="card intake-workspace"
      aria-label="Student onboarding and documents"
    >
      <h2>Student onboarding and documents</h2>
      <p>
        Use synthetic academic information only. Do not enter SSNs, credentials,
        financial details, or unrelated health information.
      </p>
      {error && <p role="alert">{error}</p>}
      {global && (
        <label>
          Record access purpose
          <select
            value={purpose}
            onChange={(e) => setPurpose(e.target.value as Purpose)}
          >
            <option value="support_review">Support review</option>
            <option value="administration">Administration</option>
            <option value="access_investigation">Access investigation</option>
          </select>
        </label>
      )}
      {staff && (
        <label>
          Academic student
          <select value={mid} onChange={(e) => setMid(e.target.value)}>
            <option value="">Shared documents only</option>
            {students.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </label>
      )}
      {!staff && memberships.length > 1 && (
        <label>
          My student membership
          <select value={mid} onChange={(e) => setMid(e.target.value)}>
            {memberships.map((m) => (
              <option key={m.id} value={m.id}>
                {m.id}
              </option>
            ))}
          </select>
        </label>
      )}
      <nav aria-label="Academic workspace">
        <button
          aria-pressed={tab === "Profile"}
          onClick={() => setTab("Profile")}
        >
          Academic profile
        </button>
        <button
          aria-pressed={tab === "Documents"}
          onClick={() => setTab("Documents")}
        >
          Documents
        </button>
        {configure && (
          <button
            aria-pressed={tab === "Configuration"}
            onClick={() => setTab("Configuration")}
          >
            Onboarding configuration
          </button>
        )}
      </nav>
      {!denied &&
        tab === "Profile" &&
        (mid ? (
          <ProfileWorkspace
            key={`${mid}:${purpose}`}
            mid={mid}
            own={own}
            reviewer={
              !own &&
              me.active_grants.some(
                (g) => g.role === "advisor" && g.org_unit_id === scope,
              )
            }
            purpose={global ? purpose : undefined}
            fail={fail}
          />
        ) : (
          <p>Choose a student to review their profile.</p>
        ))}
      {!denied && tab === "Configuration" && configure && (
        <SchemaWorkspace
          key={`${scope}:${purpose}`}
          scope={scope}
          purpose={global ? purpose : undefined}
          fail={fail}
        />
      )}
      {!denied && tab === "Documents" && selectedScope && (
        <SourceWorkspace
          key={`${scope}:${mid}:${purpose}`}
          scope={selectedScope}
          mid={mid}
          canUpload={staff || sourceManager}
          shared={sourceManager}
          global={global}
          purpose={global ? purpose : undefined}
          fail={fail}
        />
      )}
    </section>
  );
}
