import { useState } from "react";

const API_URL = import.meta.env.VITE_API_URL || "/api";

async function csrfToken() {
  const response = await fetch(`${API_URL}/auth/csrf/`, {
    credentials: "include",
  });
  if (!response.ok) {
    throw new Error(`Could not start secure sign-in (${response.status}).`);
  }
  const result = await response.json();
  return result.csrfToken;
}

function destinationPath(destination) {
  return destination?.startsWith("/") && !destination.startsWith("//")
    ? destination
    : "/";
}

export function AuthPage({ destination } = {}) {
  const [mode, setMode] = useState(
    window.location.pathname.startsWith("/register") ? "register" : "login",
  );
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const nextPath = destinationPath(
    destination || new URLSearchParams(window.location.search).get("next"),
  );

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(
        `${API_URL}/auth/${mode === "register" ? "register" : "login"}/`,
        {
          method: "POST",
          credentials: "include",
          headers: {
            "Content-Type": "application/json",
            "X-CSRFToken": token,
          },
          body: JSON.stringify({ username, password }),
        },
      );
      const result = await response.json();
      if (!response.ok) {
        const detail = result.detail;
        throw new Error(
          Array.isArray(detail)
            ? detail.join(" ")
            : detail || Object.values(result)
                .flatMap((value) => Array.isArray(value) ? value : [value])
                .join(" "),
        );
      }
      window.location.assign(nextPath);
    } catch (requestError) {
      setError(requestError.message || "Sign-in failed. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-shell">
      <a className="brand auth-brand" href="/">
        <span className="brand-mark">R</span><span>Reportly</span>
      </a>
      <section className="auth-card">
        <p className="eyebrow">TEACHER WORKSPACE</p>
        <h1>{mode === "register" ? "Create a teacher account" : "Welcome back"}</h1>
        <p className="auth-description">
          {mode === "register"
            ? "Choose a username and password. Your account will have teacher access to this report-card workspace."
            : "Sign in to view and create student report cards."}
        </p>
        {error && <div className="notice error-notice" role="alert">{error}</div>}
        <form className="auth-form" onSubmit={submit}>
          <label className="field">
            <span>Username</span>
            <input
              autoComplete="username"
              maxLength={150}
              required
              value={username}
              onChange={(event) => setUsername(event.target.value)}
            />
          </label>
          <label className="field">
            <span>Password</span>
            <input
              autoComplete={mode === "register" ? "new-password" : "current-password"}
              required
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
          </label>
          {mode === "register" && (
            <p className="password-help">
              Use a password that is at least 8 characters and not commonly used.
            </p>
          )}
          <button className="generate-button auth-submit" disabled={busy}>
            {busy
              ? "Please wait…"
              : mode === "register"
                ? "Create account"
                : "Sign in"}
          </button>
        </form>
        <p className="auth-switch">
          {mode === "register" ? "Already have an account?" : "New teacher?"}{" "}
          <button
            type="button"
            onClick={() => {
              setMode((current) => current === "register" ? "login" : "register");
              setError("");
            }}
          >
            {mode === "register" ? "Sign in" : "Create an account"}
          </button>
        </p>
      </section>
    </main>
  );
}

export function SignOutButton() {
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function signOut() {
    setBusy(true);
    setError("");
    try {
      const token = await csrfToken();
      const response = await fetch(`${API_URL}/auth/logout/`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRFToken": token },
      });
      if (!response.ok) {
        throw new Error(`Sign-out failed (${response.status}).`);
      }
      window.location.assign("/login/");
    } catch (requestError) {
      setError(requestError.message);
      setBusy(false);
    }
  }

  return (
    <>
      <button className="signout-button" type="button" disabled={busy} onClick={signOut}>
        {busy ? "Signing out…" : "Sign out"}
      </button>
      {error && <span className="signout-error" role="alert">{error}</span>}
    </>
  );
}
