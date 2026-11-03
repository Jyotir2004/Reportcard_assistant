import { useEffect, useState } from "react";
import Assistant from "./Assistant.jsx";
import ManualReport from "./ManualReport.jsx";
import { AuthPage, SignOutButton } from "./Auth.jsx";

const API_URL = import.meta.env.VITE_API_URL || "/api";

async function fetchPage(url) {
  const response = await fetch(url, { credentials: "include" });
  if (!response.ok) {
    throw new Error(`Request failed (${response.status}). Please try again.`);
  }
  return response.json();
}

function formatMarks(value) {
  return Number(value || 0).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function Dashboard() {
  const [reportCards, setReportCards] = useState([]);
  const [reportCount, setReportCount] = useState(0);
  const [totalReportCount, setTotalReportCount] = useState(0);
  const [studentCount, setStudentCount] = useState(0);
  const [averageTotal, setAverageTotal] = useState(0);
  const [topStudent, setTopStudent] = useState(null);
  const [page, setPage] = useState(1);
  const [pageCount, setPageCount] = useState(1);
  const [search, setSearch] = useState("");
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      fetchPage(`${API_URL}/students/?page_size=1`),
      fetchPage(`${API_URL}/report-cards/summary/`),
    ])
      .then(([studentPage, summary]) => {
        if (!active) return;
        setStudentCount(studentPage.count);
        setTotalReportCount(summary.total_reports);
        setAverageTotal(summary.average_total_marks || 0);
        setTopStudent(summary.top_student);
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const params = new URLSearchParams({ page, page_size: "25" });
    if (search.trim()) params.set("search", search.trim());
    setLoading(true);
    fetchPage(`${API_URL}/report-cards/?${params}`)
      .then((result) => {
        if (!active) return;
        const cards = result.results || [];
        setReportCards(cards);
        setReportCount(result.count);
        setPageCount(Math.max(1, Math.ceil(result.count / 25)));
        if (page === 1) setTopStudent(cards[0]?.student || null);
        setError("");
      })
      .catch((requestError) => {
        if (active) setError(requestError.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [page, search]);

  const selectedCard =
    reportCards.find((card) => String(card.student.id) === selectedId) ||
    reportCards[0] ||
    null;

  async function generateReportCards() {
    setError("");
    try {
      const response = await fetch(`${API_URL}/report-cards/generate/`, {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRFToken": getCookie("csrftoken") },
      });
      if (!response.ok) {
        throw new Error(
          response.status === 403
            ? "Only a signed-in staff user can generate report cards. Sign in through Django Admin first."
            : `Report generation failed (${response.status}).`,
        );
      }
      setPage(1);
      const params = new URLSearchParams({ page: "1", page_size: "25" });
      if (search.trim()) params.set("search", search.trim());
      const result = await fetchPage(`${API_URL}/report-cards/?${params}`);
      const cards = result.results || [];
      setReportCards(cards);
      setReportCount(result.count);
      setPageCount(Math.max(1, Math.ceil(result.count / 25)));
      setTopStudent(cards[0]?.student || null);
      const summary = await fetchPage(`${API_URL}/report-cards/summary/`);
      setTotalReportCount(summary.total_reports);
      setAverageTotal(summary.average_total_marks || 0);
      setTopStudent(summary.top_student);
    } catch (requestError) {
      setError(requestError.message);
    }
  }

  async function generateTeacherSummary() {
    if (!selectedCard) return;
    setSummaryLoading(true);
    setSummaryError("");
    try {
      const response = await fetch(
        `${API_URL}/report-cards/${selectedCard.id}/teacher-summary/`,
        {
          method: "POST",
          credentials: "include",
          headers: { "X-CSRFToken": getCookie("csrftoken") },
        },
      );
      const result = await response.json();
      if (!response.ok) {
        throw new Error(
          response.status === 403
            ? "Sign in through the Admin portal as a staff user to generate teacher feedback."
            : result.detail || `AI feedback generation failed (${response.status}).`,
        );
      }
      setReportCards((cards) =>
        cards.map((card) =>
          card.id === selectedCard.id
            ? {
                ...card,
                teacher_summary: result.summary,
                summary_generated_at: result.generated_at,
              }
            : card,
        ),
      );
    } catch (requestError) {
      setSummaryError(requestError.message);
    } finally {
      setSummaryLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" aria-label="Report card home">
          <span className="brand-mark">R</span>
          <span>Reportly</span>
        </a>
        <a className="admin-link" href="/admin/">
          Admin portal <span aria-hidden="true">↗</span>
        </a>
        <nav className="workflow-nav" aria-label="Report creation methods">
          <a className="admin-link" href="/manual/">Manual report</a>
          <a className="admin-link" href="/assistant/">AI Report Assistant</a>
          <SignOutButton />
        </nav>
      </header>

      <section className="intro">
        <div>
          <p className="eyebrow">ACADEMIC OVERVIEW</p>
          <h1>Student report cards</h1>
          <p className="subtitle">
            Performance at a glance, with scores and rankings in one place.
          </p>
        </div>
        <div className="create-actions">
          <a className="generate-button" href="/manual/">Create report manually</a>
          <a className="secondary-button" href="/assistant/">Create with AI assistant</a>
          <button className="secondary-button" onClick={generateReportCards}>
            <span aria-hidden="true">↻</span> Generate stored reports
          </button>
        </div>
      </section>

      {error && <div className="notice error-notice" role="alert">{error}</div>}

      <section className="stats-grid" aria-label="Class statistics">
        <article className="stat-card">
          <span className="stat-icon blue">▣</span>
          <div><p>Total students</p><strong>{loading ? "—" : studentCount}</strong></div>
          <span className="stat-caption">in the directory</span>
        </article>
        <article className="stat-card">
          <span className="stat-icon green">↗</span>
          <div><p>Reports generated</p><strong>{loading ? "—" : totalReportCount}</strong></div>
          <span className="stat-caption">ready to view</span>
        </article>
        <article className="stat-card">
          <span className="stat-icon violet">★</span>
          <div><p>Class average</p><strong>{loading ? "—" : formatMarks(averageTotal)}</strong></div>
          <span className="stat-caption">total marks</span>
        </article>
        <article className="stat-card highlight-stat">
          <span className="stat-icon amber">♛</span>
          <div><p>Top student</p><strong>{loading ? "—" : topStudent?.name || "—"}</strong></div>
          <span className="stat-caption">{topStudent?.roll_number || "No report yet"}</span>
        </article>
      </section>

      <section className="content-grid">
        <article className="panel directory-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">CLASS DIRECTORY</p>
              <h2>Report cards</h2>
            </div>
            <span className="result-count">{reportCount} records</span>
          </div>
          <label className="search-box">
            <span aria-hidden="true">⌕</span>
            <input
              type="search"
              placeholder="Search by name or roll number"
              value={search}
              onChange={(event) => {
                setPage(1);
                setSearch(event.target.value);
              }}
            />
          </label>

          {loading ? (
            <p className="empty-state">Loading report cards…</p>
          ) : reportCards.length ? (
            <div className="table-wrap">
              <table>
                <thead><tr><th>Student</th><th>Total marks</th><th>Rank</th></tr></thead>
                <tbody>
                  {reportCards.map((card) => (
                    <tr
                      key={card.id}
                      className={selectedCard?.id === card.id ? "selected-row" : ""}
                      onClick={() => setSelectedId(String(card.student.id))}
                      tabIndex={0}
                      onKeyDown={(event) => {
                        if (event.key === "Enter") setSelectedId(String(card.student.id));
                      }}
                    >
                      <td><span className="avatar">{card.student.name.charAt(0).toUpperCase()}</span><span className="student-name">{card.student.name}<small>{card.student.roll_number}</small></span></td>
                      <td className="score">{formatMarks(card.total_marks)}</td>
                      <td><span className={`rank-badge ${card.rank === 1 ? "first-rank" : ""}`}>#{card.rank}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="empty-state">
              {reportCount ? "No students match your search." : "No report cards generated yet."}
            </div>
          )}
          {pageCount > 1 && (
            <nav className="pagination" aria-label="Report card pages">
              <button disabled={page === 1} onClick={() => setPage(page - 1)}>Previous</button>
              <span>Page {page} of {pageCount}</span>
              <button disabled={page === pageCount} onClick={() => setPage(page + 1)}>Next</button>
            </nav>
          )}
        </article>

        <article className="panel detail-panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">STUDENT PROFILE</p>
              <h2>Report details</h2>
            </div>
            {selectedCard && <span className="rank-badge first-rank">Rank #{selectedCard.rank}</span>}
          </div>
          {selectedCard ? (
            <>
              <div className="profile">
                <span className="profile-avatar">{selectedCard.student.name.charAt(0).toUpperCase()}</span>
                <div>
                  <h3>{selectedCard.student.name}</h3>
                  <p>{selectedCard.student.roll_number}{selectedCard.student.department_name ? ` · ${selectedCard.student.department_name}` : ""}</p>
                </div>
              </div>
              <div className="total-score">
                <span>Total marks</span>
                <strong>{formatMarks(selectedCard.total_marks)}</strong>
                <small>Overall aggregate score</small>
              </div>
              <div className="subject-heading"><h3>Subject breakdown</h3><span>{selectedCard.subject_marks.length} subjects</span></div>
              <div className="subject-list">
                {selectedCard.subject_marks.map((mark) => {
                  const percentage = Number(mark.maximum_marks)
                    ? Math.min((Number(mark.marks) / Number(mark.maximum_marks)) * 100, 100)
                    : 0;
                  return (
                    <div className="subject-item" key={mark.id}>
                      <div className="subject-topline"><span>{mark.subject_name}</span><strong>{formatMarks(mark.marks)} <small>/ {formatMarks(mark.maximum_marks)}</small></strong></div>
                      <div className="progress-track"><span style={{ width: `${percentage}%` }} /></div>
                    </div>
                  );
                })}
              </div>
              <div className="teacher-summary">
                <div className="subject-heading">
                  <h3>Teacher feedback</h3>
                  {selectedCard.summary_generated_at && (
                    <span>
                      Updated {new Date(selectedCard.summary_generated_at).toLocaleDateString()}
                    </span>
                  )}
                </div>
                {selectedCard.teacher_summary ? (
                  <p>{selectedCard.teacher_summary}</p>
                ) : (
                  <p>Generate constructive feedback for this report card.</p>
                )}
                {summaryError && <p className="summary-error" role="alert">{summaryError}</p>}
                <button
                  className="summary-button"
                  onClick={generateTeacherSummary}
                  disabled={summaryLoading}
                >
                  {summaryLoading ? "Generating feedback…" : "Generate AI teacher note"}
                </button>
              </div>
              <p className="generated-date">Generated {new Date(selectedCard.generated_at).toLocaleString()}</p>
            </>
          ) : (
            <div className="empty-state">Choose a generated report card to see details.</div>
          )}
        </article>
      </section>
      <footer>Student Report Card System <span>•</span> Performance, clearly presented</footer>
    </main>
  );
}

function getCookie(name) {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith(`${name}=`))
    ?.split("=")
    .slice(1)
    .join("=") || "";
}

function AuthGate() {
  const [status, setStatus] = useState("checking");
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    fetch(`${API_URL}/auth/me/`, { credentials: "include" })
      .then(async (response) => {
        if (!response.ok) {
          throw new Error(`Authentication check failed (${response.status}).`);
        }
        return response.json();
      })
      .then((result) => {
        if (active) setStatus(result.authenticated ? "authenticated" : "anonymous");
      })
      .catch((requestError) => {
        if (active) {
          setError(requestError.message);
          setStatus("error");
        }
      });
    return () => { active = false; };
  }, []);

  if (status === "checking") {
    return <main className="auth-shell"><p className="empty-state">Checking sign-in…</p></main>;
  }
  if (status === "error") {
    return <main className="auth-shell"><div className="notice error-notice" role="alert">{error}</div></main>;
  }
  if (status === "anonymous") {
    const destination = `${window.location.pathname}${window.location.search}`;
    return <AuthPage destination={destination} />;
  }

  if (window.location.pathname.startsWith("/assistant")) return <Assistant />;
  if (window.location.pathname.startsWith("/manual")) return <ManualReport />;
  return <Dashboard />;
}

export default function App() {
  if (window.location.pathname.startsWith("/login") || window.location.pathname.startsWith("/register")) {
    return <AuthPage />;
  }
  return <AuthGate />;
}
