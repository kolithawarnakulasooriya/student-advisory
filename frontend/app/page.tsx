"use client";
import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, get, Me, post } from "../lib/api";

const accounts = [
  "student-a",
  "student-b",
  "advisor-a",
  "advisor-b",
  "secretary",
  "manager",
  "platform-admin",
  "super-admin",
  "multi-role",
  "pending",
  "unverified",
  "revoked",
  "suspended",
];
const descriptions: Record<string, string> = {
  student:
    "Your place to prepare for advising. Profile setup, cited guidance, and academic plans arrive in later releases.",
  advisor:
    "Your advising workspace. Assigned student rosters and guidance tools arrive in a later release.",
  secretary:
    "Your enrollment workspace. Requests, invitations, and assignment tools arrive in Release 0.2.",
  manager:
    "Your department workspace. Staff approvals and assignment tools arrive in Release 0.2.",
  platform_admin:
    "Your delegated administration workspace. Scope and staff management arrive in Release 0.2.",
  super_admin:
    "Your administration workspace. Institution management and audited oversight arrive in a later release.",
};
const label = (value: string) =>
  value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());

export default function Home() {
  const [me, setMe] = useState<Me | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [registering, setRegistering] = useState(false);
  const [email, setEmail] = useState("student-a@advisory.test");
  const [name, setName] = useState("");
  const [challenge, setChallenge] = useState("");
  const currentScope = useRef<string | null>(null);
  const generation = useRef(0);
  const title = useRef<HTMLHeadingElement>(null);

  const fail = useCallback((reason: unknown) => {
    if (reason instanceof ApiError) {
      setError(reason.message);
      if (reason.status === 401) {
        generation.current++;
        currentScope.current = null;
        setMe(null);
        setChallenge("");
      }
    } else {
      setError(
        "Cannot connect to the service. Check your connection and retry.",
      );
    }
  }, []);

  const refresh = useCallback(
    async (scope?: string, initial = false) => {
      const version = ++generation.current;
      try {
        let result: Me;
        try {
          result = await get(
            "/api/v1/me",
            scope ? `?scope_id=${encodeURIComponent(scope)}` : "",
          );
        } catch (reason) {
          if (!(scope && reason instanceof ApiError && reason.status === 404))
            throw reason;
          if (version !== generation.current) return;
          // A scope may be revoked while this tab is open. Clear it before resolving current grants.
          setMe(null);
          currentScope.current = null;
          result = await get("/api/v1/me");
        }
        if (version !== generation.current) return;
        currentScope.current = result.active_scope ?? null;
        setMe(result);
        setError("");
      } catch (reason) {
        if (version !== generation.current) return;
        // Invalidate the previous view whenever current authorization cannot be verified.
        setMe(null);
        if (!(
          initial &&
          reason instanceof ApiError &&
          reason.code === "SESSION_REQUIRED"
        ))
          fail(reason);
      } finally {
        if (version === generation.current) setLoading(false);
      }
    },
    [fail],
  );

  useEffect(() => {
    const initial = setTimeout(() => {
      void refresh(undefined, true);
    }, 0);
    const requests = generation;
    const timer = setInterval(() => {
      void refresh(currentScope.current ?? undefined, true);
    }, 30000);
    const focus = () => {
      void refresh(currentScope.current ?? undefined, true);
    };
    window.addEventListener("focus", focus);
    return () => {
      clearTimeout(initial);
      clearInterval(timer);
      window.removeEventListener("focus", focus);
      requests.current++;
    };
  }, [refresh]);

  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await action();
    } catch (reason) {
      fail(reason);
    } finally {
      setBusy(false);
      title.current?.focus();
    }
  }
  function signIn(event: FormEvent) {
    event.preventDefault();
    void act(async () => {
      generation.current++;
      setMe(null);
      setChallenge("");
      currentScope.current = null;
      if (registering) {
        const result = await post("/api/v1/auth/register", {
          email,
          name,
        });
        setChallenge(result.simulator_challenge);
      } else {
        await post("/api/v1/auth/sign-in", { email });
      }
      await refresh();
    });
  }
  const roles =
    me?.active_grants
      .filter((g) => g.org_unit_id === me.active_scope)
      .map((g) => g.role) ?? [];

  return (
    <div className="shell">
      <header className="top">
        <Link className="brand" href="/" aria-label="Student Advisory home">
          <span className="brand-icon" aria-hidden="true">
            A
          </span>
          Student Advisory
        </Link>
        <span className="release">Foundation / 0.1</span>
      </header>
      <div className="dev-banner">
        <span className="dot" aria-hidden="true" />
        Synthetic local environment · Simulated identity and MFA · No real
        student records
      </div>
      <main id="main" aria-busy={loading || busy}>
        <div className="eyebrow">A CLEAR START</div>
        <h1 ref={title} tabIndex={-1}>
          {loading
            ? "Opening your workspace…"
            : me
              ? "Welcome, " + me.name
              : "Your advising journey starts here."}
        </h1>
        {error && (
          <div role="alert" aria-label="Account error" className="alert">
            <strong>Unable to continue.</strong> {error}{" "}
            <button
              className="text-button"
              disabled={busy}
              onClick={() => void refresh(currentScope.current ?? undefined)}
            >
              Retry connection
            </button>
          </div>
        )}
        {notice && (
          <p role="status" className="notice">
            {notice}
          </p>
        )}
        {loading ? (
          <p role="status">Checking your session…</p>
        ) : !me ? (
          <div className="auth-grid">
            <section className="card">
              <div className="eyebrow">
                {registering ? "NEW ACCOUNT" : "SIGN IN"}
              </div>
              <h2>
                {registering
                  ? "Create a synthetic account"
                  : "Open your workspace"}
              </h2>
              <p className="muted">
                Use a synthetic .test address. This local simulator does not
                send email.
              </p>
              <form onSubmit={signIn}>
                {registering && (
                  <label>
                    Display name
                    <input
                      autoComplete="name"
                      required
                      maxLength={100}
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </label>
                )}
                <label>
                  Synthetic email
                  <input
                    type="email"
                    autoComplete="email"
                    required
                    maxLength={254}
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                </label>
                <button disabled={busy} type="submit">
                  {busy
                    ? "Connecting…"
                    : registering
                      ? "Create account"
                      : "Sign in"}
                </button>
              </form>
              <button
                className="text-button"
                disabled={busy}
                onClick={() => {
                  setRegistering(!registering);
                  setError("");
                }}
              >
                {registering
                  ? "Back to sign in"
                  : "Create a new synthetic account"}
              </button>
            </section>
            <aside className="card soft">
              <div className="eyebrow">EXPLORE THE FOUNDATION</div>
              <h2>A workspace for every role.</h2>
              <p>
                Choose a test identity, then sign in. Staff accounts include an
                explicit simulated MFA step.
              </p>
              <label>
                Predefined synthetic account
                <select
                  value={
                    accounts.includes(email.split("@")[0])
                      ? email.split("@")[0]
                      : ""
                  }
                  onChange={(e) => {
                    setEmail(e.target.value + "@advisory.test");
                    setRegistering(false);
                  }}
                >
                  <option value="" disabled>
                    Choose an account
                  </option>
                  {accounts.map((a) => (
                    <option key={a} value={a}>
                      {label(a.replaceAll("-", " "))}
                    </option>
                  ))}
                </select>
              </label>
              <p className="small">
                Verification confirms a synthetic identity. Membership and roles
                require a separate approval workflow in Release 0.2.
              </p>
            </aside>
          </div>
        ) : (
          <>
            <div className="account-bar">
              <div>
                <strong>{me.email}</strong>
                <p className="small">
                  {me.verified
                    ? "Synthetic email verified"
                    : "Email verification required"}
                </p>
              </div>
              <button
                className="secondary"
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    await post("/api/v1/auth/logout");
                    generation.current++;
                    setMe(null);
                    setChallenge("");
                    currentScope.current = null;
                    setNotice("You have signed out.");
                  })
                }
              >
                Sign out
              </button>
            </div>
            {!me.verified ? (
              <section className="card">
                <h2>Verify your synthetic email</h2>
                <p>
                  The local simulator displays your verification challenge here
                  instead of sending an email.
                </p>
                {!challenge ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void act(async () => {
                        const result = await post(
                          "/api/v1/auth/simulator/challenge",
                        );
                        setChallenge(result.simulator_challenge);
                      })
                    }
                  >
                    Get simulated verification email
                  </button>
                ) : (
                  <>
                    <p className="small">Local verification challenge</p>
                    <output className="challenge">{challenge}</output>
                    <button
                      disabled={busy}
                      onClick={() =>
                        void act(async () => {
                          await post("/api/v1/auth/verify", { challenge });
                          setChallenge("");
                          await refresh();
                        })
                      }
                    >
                      Verify synthetic email
                    </button>
                    <button
                      className="text-button"
                      disabled={busy}
                      onClick={() => setChallenge("")}
                    >
                      Request a new challenge
                    </button>
                  </>
                )}
              </section>
            ) : me.mfa_required ? (
              <section className="card">
                <h2>Staff verification required</h2>
                <p>
                  Staff workspaces require MFA assurance. This development
                  action simulates a provider MFA response; it is not real MFA.
                </p>
                <button
                  disabled={busy}
                  onClick={() =>
                    void act(async () => {
                      await post("/api/v1/auth/simulator/step-up");
                      await refresh();
                    })
                  }
                >
                  Simulate staff MFA
                </button>
              </section>
            ) : me.membership_state !== "active" ? (
              <section className="card">
                <span className="badge">
                  {me.membership_state === "pending"
                    ? "Pending approval"
                    : "Awaiting membership"}
                </span>
                <h2>Your identity is ready. Membership is separate.</h2>
                <p>
                  {me.membership_state === "pending"
                    ? "Your synthetic membership is pending approval."
                    : "You do not have an active membership."}{" "}
                  Membership requests and approval tools arrive in Release 0.2.
                </p>
              </section>
            ) : (
              <>
                <section className="scope-bar" aria-label="Active scope">
                  <label>
                    Active department
                    <select
                      disabled={busy}
                      value={me.active_scope ?? ""}
                      onChange={(e) => {
                        const scope = e.target.value;
                        generation.current++;
                        setMe(null);
                        setChallenge("");
                        setLoading(true);
                        currentScope.current = scope;
                        void refresh(scope);
                      }}
                    >
                      {me.scopes.map((s) => (
                        <option key={s.id} value={s.id}>
                          {s.name}
                        </option>
                      ))}
                    </select>
                  </label>
                  <span className="badge">{roles.map(label).join(" · ")}</span>
                </section>
                <div className="workspace-grid">
                  {roles.map((role) => (
                    <section className="card" key={role}>
                      <div className="eyebrow">YOUR WORKSPACE</div>
                      <h2>{label(role)} workspace</h2>
                      <p>{descriptions[role]}</p>
                      <div className="ready">
                        <span className="dot" aria-hidden="true" />
                        Identity and scope ready
                      </div>
                    </section>
                  ))}
                  <section className="card soft">
                    <div className="eyebrow">AVAILABLE NOW</div>
                    <h2>A secure foundation</h2>
                    <ul>
                      <li>Verified synthetic identity</li>
                      <li>Server-validated department scope</li>
                      <li>Revocable browser session</li>
                    </ul>
                    <p className="small">
                      Only foundation capabilities are available in this
                      release.
                    </p>
                  </section>
                </div>
              </>
            )}
          </>
        )}
        <footer>
          Student Advisory <span>Local foundation · Release 0.1</span>
        </footer>
      </main>
    </div>
  );
}
