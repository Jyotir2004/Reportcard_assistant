import { useState } from "react";
import { SignOutButton } from "./Auth.jsx";

const API_URL = import.meta.env.VITE_API_URL || "/api";

export function resolvePdfUrl(pdfUrl) {
  if (!pdfUrl) return "";
  if (pdfUrl.startsWith("http://") || pdfUrl.startsWith("https://")) {
    return pdfUrl;
  }
  const clean = pdfUrl.startsWith("/") ? pdfUrl : "/" + pdfUrl;
  if (clean.startsWith("/api/")) {
    return clean;
  }
  return `${API_URL}${clean}`;
}

const DEFAULT_GRADES = [
  { grade: "A", min_percentage: "90", max_percentage: "100" },
  { grade: "B", min_percentage: "80", max_percentage: "89.99" },
  { grade: "C", min_percentage: "70", max_percentage: "79.99" },
  { grade: "D", min_percentage: "60", max_percentage: "69.99" },
  { grade: "E", min_percentage: "50", max_percentage: "59.99" },
  { grade: "F", min_percentage: "0", max_percentage: "49.99" },
];

function csrfToken() {
  return document.cookie
    .split("; ")
    .find((cookie) => cookie.startsWith("csrftoken="))
    ?.split("=")
    .slice(1)
    .join("=") || "";
}

async function postJson(path, payload) {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify(payload),
  });
  const body = response.headers.get("content-type")?.includes("application/json")
    ? await response.json()
    : {};
  if (!response.ok) {
    if (response.status === 403) {
      throw new Error("Please sign in as a staff user through the Admin portal to generate a report.");
    }
    const message = Object.values(body)
      .flatMap((value) => Array.isArray(value) ? value : [value])
      .map((value) => typeof value === "string" ? value : JSON.stringify(value))
      .join(" ");
    throw new Error(message || `Request failed (${response.status}).`);
  }
  return body;
}

function Field({ label, value, onChange, required = false, ...props }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input
        {...props}
        required={required}
        value={value || ""}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function SubjectResults({ results }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr><th>Subject</th><th>Marks</th><th>Percent</th><th>Grade</th><th>Status</th></tr>
        </thead>
        <tbody>
          {results.map((result) => (
            <tr key={result.subject}>
              <td>{result.subject}</td>
              <td>{result.marks} / {result.maximum_marks}</td>
              <td>{result.percentage}%</td>
              <td>{result.grade}</td>
              <td>{result.passed ? "Pass" : "Needs support"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ManualReport({ embedded = false }) {
  const [details, setDetails] = useState({
    name: "",
    roll_number: "",
    class_name: "",
    section: "",
    academic_year: "",
    examination_name: "",
  });
  const [marks, setMarks] = useState([
    { subject: "", marks: "", maximum_marks: "100" },
  ]);
  const [grades, setGrades] = useState(DEFAULT_GRADES);
  const [policy, setPolicy] = useState({
    name: "School grading policy",
    minimum_passing_percentage: "40",
    subject_passing_percentage: "33",
    require_subject_pass: false,
    weighted_subjects_text: "{}",
  });
  const [rankRequested, setRankRequested] = useState(true);
  const [teacherRemarks, setTeacherRemarks] = useState("");
  const [preview, setPreview] = useState(null);
  const [previewPayload, setPreviewPayload] = useState(null);
  const [issued, setIssued] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  function updateDetail(field, value) {
    setDetails((previous) => ({ ...previous, [field]: value }));
  }

  function updateMark(index, field, value) {
    setMarks((previous) => previous.map((mark, row) =>
      row === index ? { ...mark, [field]: value } : mark,
    ));
  }

  function updateGrade(index, field, value) {
    setGrades((previous) => previous.map((grade, row) =>
      row === index ? { ...grade, [field]: value } : grade,
    ));
  }

  function buildPayload() {
    let weightedSubjects;
    try {
      weightedSubjects = JSON.parse(policy.weighted_subjects_text || "{}");
    } catch {
      throw new Error("Subject weights must be valid JSON, for example {\"Mathematics\": 2}.");
    }
    return {
      details,
      marks,
      rank_requested: rankRequested,
      teacher_remarks: teacherRemarks,
      policy: {
        name: policy.name,
        grade_boundaries: grades,
        minimum_passing_percentage: policy.minimum_passing_percentage,
        require_subject_pass: policy.require_subject_pass,
        subject_passing_percentage: policy.subject_passing_percentage,
        weighted_subjects: weightedSubjects,
      },
    };
  }

  async function createPreview(event) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = buildPayload();
      const result = await postJson("/manual/report-cards/preview/", payload);
      setPreviewPayload(payload);
      setPreview(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  async function issueReport() {
    if (!previewPayload) return;
    setBusy(true);
    setError("");
    try {
      const result = await postJson("/manual/report-cards/issue/", previewPayload);
      setIssued(result);
    } catch (requestError) {
      setError(requestError.message);
    } finally {
      setBusy(false);
    }
  }

  const panelContent = (
    <section className={`assistant-panel ${embedded ? "manual-embedded-panel" : ""}`}>
      {error && <div className="notice error-notice manual-error" role="alert">{error}</div>}
      {!issued && !preview && (
          <form className="workflow-form" onSubmit={createPreview}>
            <h2>Student details</h2>
            <div className="form-grid">
              <Field label="Student name" required value={details.name} onChange={(value) => updateDetail("name", value)} />
              <Field label="Roll number" required value={details.roll_number} onChange={(value) => updateDetail("roll_number", value)} />
              <Field label="Class" required value={details.class_name} onChange={(value) => updateDetail("class_name", value)} />
              <Field label="Section" value={details.section} onChange={(value) => updateDetail("section", value)} />
              <Field label="Academic year" required placeholder="2026-2027" value={details.academic_year} onChange={(value) => updateDetail("academic_year", value)} />
              <Field label="Examination name" required value={details.examination_name} onChange={(value) => updateDetail("examination_name", value)} />
            </div>

            <h3>Subject marks</h3>
            <div className="marks-editor">
              {marks.map((mark, index) => (
                <div className="mark-input-row" key={index}>
                  <Field label="Subject" required value={mark.subject} onChange={(value) => updateMark(index, "subject", value)} />
                  <Field label="Marks obtained" required type="number" min="0" step="0.01" value={mark.marks} onChange={(value) => updateMark(index, "marks", value)} />
                  <Field label="Maximum marks" required type="number" min="0.01" step="0.01" value={mark.maximum_marks} onChange={(value) => updateMark(index, "maximum_marks", value)} />
                  <button type="button" className="remove-button" aria-label={`Remove subject ${index + 1}`} onClick={() => setMarks((previous) => previous.filter((_, row) => row !== index))}>×</button>
                </div>
              ))}
            </div>
            <button type="button" className="secondary-button" onClick={() => setMarks((previous) => [...previous, { subject: "", marks: "", maximum_marks: "100" }])}>+ Add subject</button>

            <h3>Grading policy</h3>
            <div className="form-grid">
              <Field label="Policy name" required value={policy.name} onChange={(value) => setPolicy((previous) => ({ ...previous, name: value }))} />
              <Field label="Minimum overall passing percentage" required type="number" min="0" max="100" step="0.01" value={policy.minimum_passing_percentage} onChange={(value) => setPolicy((previous) => ({ ...previous, minimum_passing_percentage: value }))} />
              <Field label="Minimum subject passing percentage" required type="number" min="0" max="100" step="0.01" value={policy.subject_passing_percentage} onChange={(value) => setPolicy((previous) => ({ ...previous, subject_passing_percentage: value }))} />
              <label className="field">
                <span>Weighted subjects (optional JSON)</span>
                <input value={policy.weighted_subjects_text} onChange={(event) => setPolicy((previous) => ({ ...previous, weighted_subjects_text: event.target.value }))} placeholder='{"Mathematics": 2}' />
              </label>
            </div>
            <div className="grade-editor">
              <div className="grade-row grade-header"><span>Grade</span><span>Minimum %</span><span>Maximum %</span></div>
              {grades.map((grade, index) => (
                <div className="grade-row" key={index}>
                  <input aria-label={`Grade label ${index + 1}`} value={grade.grade} onChange={(event) => updateGrade(index, "grade", event.target.value)} />
                  <input aria-label={`Grade minimum ${index + 1}`} type="number" min="0" max="100" step="0.01" value={grade.min_percentage} onChange={(event) => updateGrade(index, "min_percentage", event.target.value)} />
                  <input aria-label={`Grade maximum ${index + 1}`} type="number" min="0" max="100" step="0.01" value={grade.max_percentage} onChange={(event) => updateGrade(index, "max_percentage", event.target.value)} />
                </div>
              ))}
            </div>
            <label className="check-line"><input type="checkbox" checked={policy.require_subject_pass} onChange={(event) => setPolicy((previous) => ({ ...previous, require_subject_pass: event.target.checked }))} /> Require passing marks in every subject</label>
            <label className="check-line"><input type="checkbox" checked={rankRequested} onChange={(event) => setRankRequested(event.target.checked)} /> Include class rank when complete comparison marks are available</label>
            <label className="field"><span>Teacher remarks</span><textarea rows="3" maxLength="4000" value={teacherRemarks} onChange={(event) => setTeacherRemarks(event.target.value)} placeholder="Optional remarks for the report card" /></label>
            <div className="workflow-actions">
              <a className="secondary-button" href="/">Cancel</a>
              <button className="generate-button" disabled={busy}>{busy ? "Calculating preview…" : "Preview report card"}</button>
            </div>
          </form>
        )}

        {preview && !issued && (
          <section className="workflow-form report-preview">
            <h2>Review report card</h2>
            <p><b>{preview.details.name}</b> · Roll {preview.details.roll_number} · Class {preview.details.class_name}{preview.details.section ? `-${preview.details.section}` : ""} · {preview.details.academic_year} · {preview.details.examination_name}</p>
            <SubjectResults results={preview.subject_results} />
            <div className="preview-summary">
              <p><b>Total:</b> {preview.total_marks} / {preview.total_maximum_marks}</p>
              <p><b>Overall percentage:</b> {preview.percentage}%</p>
              <p><b>Overall grade:</b> {preview.overall_grade} · <b>Status:</b> {preview.passed ? "PASS" : "FAIL"}</p>
              {preview.rank !== null && <p><b>Class rank:</b> {preview.rank}</p>}
              {preview.percentile !== null && <p><b>Class percentile:</b> {preview.percentile}%</p>}
              {preview.rank_unavailable_reason && <p className="rank-unavailable">{preview.rank_unavailable_reason}</p>}
            </div>
            <p className="approval-note">Confirming saves and issues the report card using the grading policy shown above.</p>
            <div className="workflow-actions">
              <button className="secondary-button" disabled={busy} onClick={() => setPreview(null)}>Edit details or marks</button>
              <button className="generate-button" disabled={busy} onClick={issueReport}>{busy ? "Issuing report…" : "Confirm and issue"}</button>
            </div>
          </section>
        )}

        {issued && (
          <section className="workflow-form issued-card">
            <h2>Report card issued</h2>
            <p>The report has been saved successfully.</p>
            <a
              className="generate-button pdf-link"
              href={resolvePdfUrl(issued.pdf_url)}
              target="_blank"
              rel="noreferrer"
              download
            >
              Download report card PDF
            </a>
            <a className="secondary-button" href="/manual/">Create another manually</a>
            <a className="secondary-button" href="/assistant/">Use AI assistant</a>
          </section>
        )}
      </section>
  );

  if (embedded) {
    return (
      <div className="manual-embedded-wrapper">
        <div className="manual-embedded-intro">
          <p className="eyebrow">DIRECT MANUAL ENTRY</p>
          <h2>Manual Report Card Form</h2>
          <p>Enter student marks and grading boundaries directly by hand. Exact same calculations and PDF format as manual report cards, without requiring AI.</p>
        </div>
        {panelContent}
      </div>
    );
  }

  return (
    <main className="assistant-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark">R</span><span>Reportly</span>
        </a>
        <nav className="workflow-nav" aria-label="Report creation methods">
          <a className="admin-link active-workflow" href="/manual/">Manual entry</a>
          <a className="admin-link" href="/assistant/">AI assistant</a>
          <a className="admin-link" href="/admin/">Admin portal <span aria-hidden="true">↗</span></a>
          <SignOutButton />
        </nav>
      </header>
      <section className="assistant-intro">
        <p className="eyebrow">TEACHER WORKSPACE</p>
        <h1>Manual report card</h1>
        <p>Enter student marks and grading rules directly. Calculations are validated by the server; no AI is needed.</p>
      </section>

      {panelContent}
    </main>
  );
}
