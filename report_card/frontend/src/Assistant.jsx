import { useEffect, useMemo, useRef, useState } from "react";
import { SignOutButton } from "./Auth.jsx";
import ManualReport from "./ManualReport.jsx";

const API_URL = import.meta.env.VITE_API_URL || "/api";
const SESSION_KEY = "report-card-assistant-session";

function resolvePdfUrl(pdfUrl) {
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
const WELCOME =
  "Welcome to the AI Report Card Assistant! I'll ask for the report details one question at a time. Your answers are saved in this conversation as we go.";

const DEFAULT_GRADES = [
  { grade: "A", min_percentage: "90", max_percentage: "100" },
  { grade: "B", min_percentage: "80", max_percentage: "89.99" },
  { grade: "C", min_percentage: "70", max_percentage: "79.99" },
  { grade: "D", min_percentage: "60", max_percentage: "69.99" },
  { grade: "E", min_percentage: "50", max_percentage: "59.99" },
  { grade: "F", min_percentage: "0", max_percentage: "49.99" },
];

const SUGGESTED_PROMPTS = [
  {
    icon: "👋",
    title: "Say Hey to Begin",
    desc: "Hey! I'd like to create a new student report card.",
  },
  {
    icon: "📝",
    title: "Make a Student Report Card",
    desc: "Create a report card for Rahul Sharma, Class 10A, Roll 15, Academic Year 2026-2027, Exam Final Examination. Math: 85/100, Science: 90/100, English: 88/100. Remarks: Excellent progress.",
  },
  {
    icon: "⚡",
    title: "Flash Signal Modal",
    desc: "Open the Flash Signal modal to see live auto-filled details and issue an official PDF.",
  },
  {
    icon: "💡",
    title: "Teacher Remarks",
    desc: "Suggest 3 constructive feedback remarks for a student excelling in Science but needing support in Math.",
  },
];

async function requestJson(url, options = {}) {
  const response = await fetch(url, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });
  const body = response.headers.get("content-type")?.includes("application/json")
    ? await response.json()
    : {};
  if (!response.ok) {
    if (response.status === 403) {
      throw new Error(
        "Please sign in as a staff user through the Admin portal to use the assistant.",
      );
    }
    throw new Error(formatError(body) || `Request failed (${response.status}).`);
  }
  return body;
}

function formatError(body) {
  if (typeof body.detail === "string") return body.detail;
  return Object.values(body)
    .flatMap((value) => (Array.isArray(value) ? value : [value]))
    .map((value) => (typeof value === "string" ? value : JSON.stringify(value)))
    .join(" ");
}

function csrfToken() {
  return (
    document.cookie
      .split("; ")
      .find((cookie) => cookie.startsWith("csrftoken="))
      ?.split("=")[1] || ""
  );
}

function comparisonCsvFromState(comparisons = []) {
  return comparisons
    .flatMap((student) =>
      (student.marks || []).map((mark) =>
        [
          student.roll_number,
          mark.subject,
          mark.marks,
          mark.maximum_marks,
        ].join(", "),
      ),
    )
    .join("\n");
}

/* =========================================================================
   Report Card Interactive Widget
   ========================================================================= */
function ReportCardWidget({ data }) {
  if (!data) return null;
  const {
    report_card_id,
    pdf_url,
    student_name,
    roll_number,
    class_name,
    section,
    academic_year,
    examination_name,
    total_marks,
    total_maximum_marks,
    percentage,
    overall_grade,
    passed,
    subject_results = [],
    teacher_remarks,
  } = data;

  const fullPdfUrl = resolvePdfUrl(pdf_url);
  const safeSubjectResults = Array.isArray(subject_results) ? subject_results : [];

  return (
    <div className="report-card-widget">
      <div className="rc-widget-header">
        <div className="rc-widget-title-area">
          <span className="rc-badge-official">OFFICIAL REPORT CARD</span>
          <h3 className="rc-student-name">{student_name}</h3>
          <div className="rc-meta-pills">
            <span>Roll: <b>{roll_number}</b></span>
            <span>Class: <b>{class_name}{section ? `-${section}` : ""}</b></span>
            <span>Year: <b>{academic_year}</b></span>
            <span>Exam: <b>{examination_name}</b></span>
          </div>
        </div>
        <a
          className="rc-download-pdf-btn primary"
          href={fullPdfUrl}
          target="_blank"
          rel="noreferrer"
          download
        >
          <span className="rc-pdf-icon">📄</span> Download Report Card PDF
        </a>
      </div>

      {/* Subject Marks Table */}
      <div className="rc-table-wrapper">
        <table className="rc-table">
          <thead>
            <tr>
              <th>Subject</th>
              <th>Marks</th>
              <th>Maximum</th>
              <th>Percent</th>
              <th>Grade</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {safeSubjectResults.map((sub, idx) => (
              <tr key={idx}>
                <td className="rc-subject-cell"><b>{sub.subject}</b></td>
                <td>{sub.marks}</td>
                <td>{sub.maximum_marks}</td>
                <td>{sub.percentage}%</td>
                <td><span className="rc-grade-pill">{sub.grade}</span></td>
                <td>
                  <span className={`rc-status-tag ${sub.passed ? "pass" : "fail"}`}>
                    {sub.passed ? "Pass" : "Needs support"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Summary Scores */}
      <div className="rc-summary-grid">
        <div className="rc-summary-item">
          <small>Total Marks</small>
          <strong>{total_marks} <span className="sub-max">/ {total_maximum_marks}</span></strong>
        </div>
        <div className="rc-summary-item">
          <small>Overall Percentage</small>
          <strong className="accent-percent">{percentage}%</strong>
        </div>
        <div className="rc-summary-item">
          <small>Overall Grade</small>
          <strong className="accent-grade">{overall_grade}</strong>
        </div>
        <div className="rc-summary-item">
          <small>Final Status</small>
          <span className={`rc-result-badge ${passed ? "pass" : "fail"}`}>
            {passed ? "PASSED" : "FAILED"}
          </span>
        </div>
      </div>

      {teacher_remarks && (
        <div className="rc-remarks-box">
          <b>Teacher Remarks:</b>
          <p>{teacher_remarks}</p>
        </div>
      )}

      <div className="rc-widget-footer">
        <span className="rc-stamp">✓ Saved in Database (ID: #{report_card_id}) · Standard Format</span>
        <a className="rc-download-link" href={fullPdfUrl} target="_blank" rel="noreferrer" download>
          Direct PDF Download ⬇
        </a>
      </div>
    </div>
  );
}

const ReportCardEmbed = ReportCardWidget;

/* =========================================================================
   Markdown & Report Card Parser
   ========================================================================= */
function parseReportCardTags(text) {
  if (!text) return { cleanText: "", reportCards: [], makeReportCardActions: [] };
  const reportCards = [];
  const makeReportCardActions = [];

  const regex = /:::report_card\s*([\s\S]*?)\s*:::/g;
  let match;
  while ((match = regex.exec(text)) !== null) {
    try {
      const data = JSON.parse(match[1]);
      reportCards.push(data);
    } catch {
      // ignore json parse error
    }
  }

  const actionRegex = /:::action_make_report_card\s*([\s\S]*?)\s*:::/g;
  while ((match = actionRegex.exec(text)) !== null) {
    try {
      const data = JSON.parse(match[1]);
      makeReportCardActions.push(data);
    } catch {
      // ignore json parse error
    }
  }

  const cleanText = text
    .replace(/:::report_card[\s\S]*?:::/g, "")
    .replace(/:::action_make_report_card[\s\S]*?:::/g, "")
    .trim();
  return { cleanText, reportCards, makeReportCardActions };
}

function MarkdownRenderer({ content, isStreaming, onTriggerAction, onOpenFlashModal }) {
  if (!content) {
    if (isStreaming) {
      return <span className="streaming-cursor" aria-label="generating response">▋</span>;
    }
    return null;
  }

  const { cleanText, reportCards, makeReportCardActions } = parseReportCardTags(content);
  const lines = cleanText ? cleanText.split("\n") : [];
  const blocks = [];
  let currentTable = null;
  let currentCode = null;
  let currentParagraph = [];

  function flushParagraph() {
    if (currentParagraph.length > 0) {
      const text = currentParagraph.join("\n").trim();
      if (text) {
        blocks.push({ type: "p", content: text });
      }
      currentParagraph = [];
    }
  }

  function flushTable() {
    if (currentTable) {
      blocks.push({ type: "table", ...currentTable });
      currentTable = null;
    }
  }

  function flushCode() {
    if (currentCode) {
      blocks.push({
        type: "code",
        code: currentCode.lines.join("\n"),
        lang: currentCode.lang,
      });
      currentCode = null;
    }
  }

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const trimmed = line.trim();

    // Code block
    if (trimmed.startsWith("```")) {
      if (currentCode) {
        flushCode();
      } else {
        flushParagraph();
        flushTable();
        currentCode = { lang: trimmed.slice(3).trim(), lines: [] };
      }
      continue;
    }
    if (currentCode) {
      currentCode.lines.push(line);
      continue;
    }

    // Markdown Table
    if (trimmed.startsWith("|") && trimmed.endsWith("|")) {
      flushParagraph();
      const cells = trimmed
        .slice(1, -1)
        .split("|")
        .map((c) => c.trim());
      const isSeparator = cells.every((c) => /^:?-+:?$/.test(c));
      if (!currentTable) {
        currentTable = { headers: cells, rows: [] };
      } else if (!isSeparator) {
        currentTable.rows.push(cells);
      }
      continue;
    } else if (currentTable) {
      flushTable();
    }

    // Headings
    if (/^#{1,4}\s/.test(trimmed)) {
      flushParagraph();
      const level = trimmed.match(/^#+/)[0].length;
      blocks.push({
        type: "heading",
        level,
        content: trimmed.replace(/^#+\s*/, ""),
      });
      continue;
    }

    // Bullet points
    if (/^[-*•]\s+/.test(trimmed)) {
      flushParagraph();
      blocks.push({ type: "bullet", content: trimmed.replace(/^[-*•]\s+/, "") });
      continue;
    }

    // Numbered list
    if (/^\d+\.\s+/.test(trimmed)) {
      flushParagraph();
      blocks.push({ type: "numbered", content: trimmed.replace(/^\d+\.\s+/, "") });
      continue;
    }

    if (!trimmed) {
      flushParagraph();
      continue;
    }

    currentParagraph.push(line);
  }

  flushParagraph();
  flushTable();
  flushCode();

  function renderInline(str) {
    if (!str) return null;
    const parts = [];
    const codeRegex = /`([^`]+)`/g;
    let lastIdx = 0;
    let match;
    while ((match = codeRegex.exec(str)) !== null) {
      if (match.index > lastIdx) {
        parts.push({ type: "text", val: str.substring(lastIdx, match.index) });
      }
      parts.push({ type: "code", val: match[1] });
      lastIdx = codeRegex.lastIndex;
    }
    if (lastIdx < str.length) {
      parts.push({ type: "text", val: str.substring(lastIdx) });
    }

    return parts.map((part, idx) => {
      if (part.type === "code") {
        return <code key={idx} className="chat-inline-code">{part.val}</code>;
      }
      const boldParts = part.val.split(/(\*\*[^*]+\*\*)/g);
      return (
        <span key={idx}>
          {boldParts.map((bp, bidx) => {
            if (bp.startsWith("**") && bp.endsWith("**")) {
              return <strong key={bidx}>{bp.slice(2, -2)}</strong>;
            }
            const italicParts = bp.split(/(\*[^*]+\*)/g);
            return italicParts.map((ip, iidx) => {
              if (ip.startsWith("*") && ip.endsWith("*") && ip.length > 2) {
                return <em key={iidx}>{ip.slice(1, -1)}</em>;
              }
              return ip;
            });
          })}
        </span>
      );
    });
  }

  return (
    <div className="chat-markdown-body">
      {blocks.map((block, idx) => {
        if (block.type === "heading") {
          const Tag = block.level === 1 ? "h2" : block.level === 2 ? "h3" : "h4";
          return <Tag key={idx} className="chat-rendered-heading">{renderInline(block.content)}</Tag>;
        }
        if (block.type === "bullet") {
          return (
            <div key={idx} className="chat-rendered-list-item">
              <span className="chat-bullet-dot">•</span>
              <span>{renderInline(block.content)}</span>
            </div>
          );
        }
        if (block.type === "numbered") {
          return (
            <div key={idx} className="chat-rendered-list-item numbered">
              <span>{renderInline(block.content)}</span>
            </div>
          );
        }
        if (block.type === "table") {
          return (
            <div key={idx} className="chat-table-wrapper">
              <table className="chat-rendered-table">
                <thead>
                  <tr>
                    {block.headers.map((h, hi) => (
                      <th key={hi}>{renderInline(h)}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {block.rows.map((row, ri) => (
                    <tr key={ri}>
                      {row.map((cell, ci) => (
                        <td key={ci}>{renderInline(cell)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        if (block.type === "code") {
          return (
            <pre key={idx} className="chat-rendered-code-block">
              <code>{block.code}</code>
            </pre>
          );
        }
        return <p key={idx} className="chat-rendered-p">{renderInline(block.content)}</p>;
      })}
      {isStreaming && <span className="streaming-cursor" aria-label="typing">▋</span>}

      {/* Render interactive Make Report Card actions */}
      {makeReportCardActions.map((action, idx) => (
        <div key={`rc-action-${idx}`} className="chat-make-report-card-card">
          <div className="action-card-top">
            <span className="action-card-pill">⚡ ALL DETAILS RECORDED</span>
            <h4>Official Report Card Confirmation</h4>
            <p>
              Parameters for <strong>{action.name || "the student"}</strong> (Roll {action.roll || "—"}) are validated.
              Ready to generate the official report card.
            </p>
          </div>
          <div className="action-card-buttons">
            <button
              type="button"
              className="big-action-btn"
              onClick={() => onTriggerAction && onTriggerAction("Make report card")}
            >
              ⚡ Make Report Card
            </button>
            <button
              type="button"
              className="secondary-button"
              onClick={() => onOpenFlashModal && onOpenFlashModal()}
            >
              View / Edit in Flash Form ⚡
            </button>
          </div>
        </div>
      ))}

      {/* Render embedded Report Cards */}
      {reportCards.map((rc, idx) => (
        <ReportCardWidget key={`rc-embed-${idx}`} data={rc} />
      ))}
    </div>
  );
}

/* =========================================================================
   Quick Make Report Card Modal
   ========================================================================= */
function QuickReportModal({
  isOpen,
  onClose,
  onCreated,
  chatHistory = [],
  context = null,
  sessionId = null,
}) {
  const [details, setDetails] = useState({
    name: "",
    roll_number: "",
    class_name: "",
    section: "",
    academic_year: "2024-2025",
    examination_name: "Annual Examination",
  });
  const [marks, setMarks] = useState([
    { subject: "Mathematics", marks: "", maximum_marks: "100" },
    { subject: "Science", marks: "", maximum_marks: "100" },
    { subject: "English", marks: "", maximum_marks: "100" },
  ]);
  const [remarks, setRemarks] = useState("");
  const [aiPrompt, setAiPrompt] = useState("");
  const [autoFilling, setAutoFilling] = useState(false);
  const [issuedCard, setIssuedCard] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Automatically sync form from conversational context and chat history
  useEffect(() => {
    if (!isOpen) return;

    if (context?.parameters) {
      const p = context.parameters;
      setDetails((prev) => ({
        name: p.name || prev.name,
        roll_number: p.roll_number || prev.roll_number,
        class_name: p.class_name || prev.class_name,
        section: p.section !== undefined && p.section !== null ? p.section : prev.section,
        academic_year: p.academic_year || prev.academic_year || "2024-2025",
        examination_name: p.examination_name || prev.examination_name || "Annual Examination",
      }));
      if (Array.isArray(p.marks) && p.marks.length > 0) {
        setMarks(p.marks);
      }
      if (p.teacher_remarks) {
        setRemarks(p.teacher_remarks);
      }
    }

    if (context?.report_card) {
      setIssuedCard(context.report_card);
    }
  }, [isOpen, context]);

  function syncRemarksFromDetails(customDetails = details, customMarks = marks) {
    const studentName = (customDetails.name || "Student").trim();
    const examName = (customDetails.examination_name || "Annual Examination").trim();
    const validMarks = (customMarks || []).filter(
      (m) => m && m.subject && m.subject.trim() && !isNaN(parseFloat(m.marks)),
    );
    if (validMarks.length === 0) {
      return `${studentName} has demonstrated commendable academic performance and dedication this academic year.`;
    }
    const sorted = [...validMarks].sort((a, b) => {
      const pA = parseFloat(a.marks) / (parseFloat(a.maximum_marks) || 100);
      const pB = parseFloat(b.marks) / (parseFloat(b.maximum_marks) || 100);
      return pB - pA;
    });
    const top1 = sorted[0];
    const top2 = sorted.length > 1 ? sorted[1] : null;
    const standoutText = top2
      ? `Standout proficiency and conceptual grasp in ${top1.subject} (${top1.marks}/${top1.maximum_marks || 100}) and ${top2.subject} (${top2.marks}/${top2.maximum_marks || 100}).`
      : `Standout proficiency and conceptual grasp in ${top1.subject} (${top1.marks}/${top1.maximum_marks || 100}).`;

    return `${studentName} has demonstrated commendable academic performance in ${examName}. ${standoutText} With continued curiosity and dedicated focus, ${studentName} will maintain an exemplary academic journey.`;
  }

  // Live real-time performance summary calculation as user fills details
  const liveStats = useMemo(() => {
    let totalMarks = 0;
    let totalMax = 0;
    let validCount = 0;
    let passCount = 0;

    (Array.isArray(marks) ? marks : []).forEach((m) => {
      if (!m) return;
      const obt = parseFloat(m.marks);
      const max = parseFloat(m.maximum_marks);
      if (!isNaN(obt) && !isNaN(max) && max > 0) {
        totalMarks += obt;
        totalMax += max;
        validCount++;
        if (obt / max >= 0.33) {
          passCount++;
        }
      }
    });

    const pct = totalMax > 0 ? (totalMarks / totalMax) * 100 : 0;
    let grade = "-";
    if (totalMax > 0 && validCount > 0) {
      if (pct >= 90) grade = "A";
      else if (pct >= 80) grade = "B";
      else if (pct >= 70) grade = "C";
      else if (pct >= 60) grade = "D";
      else if (pct >= 50) grade = "E";
      else grade = "F";
    }

    const passed = totalMax > 0 && pct >= 40 && passCount === validCount;

    return {
      totalMarks: totalMarks.toFixed(2).replace(/\.00$/, ""),
      totalMax: totalMax.toFixed(2).replace(/\.00$/, ""),
      percentage: pct.toFixed(2),
      grade,
      passed,
      validCount,
      passCount,
    };
  }, [marks]);

  function updateDetail(field, val) {
    setDetails((prev) => ({ ...prev, [field]: val }));
  }

  function updateMark(index, field, val) {
    setMarks((prev) =>
      prev.map((m, i) => (i === index ? { ...m, [field]: val } : m)),
    );
  }

  function addSubject() {
    setMarks((prev) => [...prev, { subject: "", marks: "", maximum_marks: "100" }]);
  }

  function removeSubject(index) {
    setMarks((prev) => prev.filter((_, i) => i !== index));
  }

  async function handleAutoFill() {
    setAutoFilling(true);
    setError("");
    try {
      const res = await requestJson(`${API_URL}/assistant/autofill/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
        body: JSON.stringify({
          prompt: aiPrompt.trim(),
          details: details,
          marks: marks,
          history: chatHistory,
        }),
      });
      if (res.details) setDetails(res.details);
      if (res.marks && res.marks.length) setMarks(res.marks);
      if (res.teacher_remarks) setRemarks(res.teacher_remarks);
    } catch (err) {
      setError(err.message || "Failed to auto-fill with AI.");
    } finally {
      setAutoFilling(false);
    }
  }

  function triggerDownload(pdfUrl, rollNumber, cardId) {
    if (!pdfUrl) return;
    const fullPdfUrl = resolvePdfUrl(pdfUrl);
    const link = document.createElement("a");
    link.href = fullPdfUrl;
    link.download = `report-card-${rollNumber || cardId}.pdf`;
    link.target = "_blank";
    link.rel = "noreferrer";
    document.body.appendChild(link);
    link.click();
    setTimeout(() => {
      document.body.removeChild(link);
    }, 400);
  }

  async function handleAutoCreateAndDownload() {
    setBusy(true);
    setError("");
    try {
      let currentDetails = { ...details };
      let currentMarks = marks.filter((m) => m.subject.trim());
      let currentRemarks = remarks;

      const hasEnteredDetails = Boolean(currentDetails.name.trim() && currentDetails.roll_number.trim());
      const hasEnteredMarks = currentMarks.length > 0 && currentMarks.some((m) => m.marks.trim() !== "");

      // Only invoke AI autofill if details/marks are missing, or user entered an explicit AI prompt
      if (aiPrompt.trim() || !hasEnteredDetails || !hasEnteredMarks) {
        const autoRes = await requestJson(`${API_URL}/assistant/autofill/`, {
          method: "POST",
          headers: { "X-CSRFToken": csrfToken() },
          body: JSON.stringify({
            prompt: aiPrompt.trim(),
            details: currentDetails,
            marks: currentMarks,
            history: chatHistory,
          }),
        });
        if (autoRes.details) {
          currentDetails = {
            ...currentDetails,
            ...autoRes.details,
            name: currentDetails.name.trim() || autoRes.details.name,
            roll_number: currentDetails.roll_number.trim() || autoRes.details.roll_number,
            class_name: currentDetails.class_name.trim() || autoRes.details.class_name,
            section: currentDetails.section.trim() || autoRes.details.section,
            academic_year: currentDetails.academic_year.trim() || autoRes.details.academic_year,
            examination_name: currentDetails.examination_name.trim() || autoRes.details.examination_name,
          };
          setDetails(currentDetails);
        }
        if (autoRes.marks && autoRes.marks.length && !hasEnteredMarks) {
          currentMarks = autoRes.marks;
          setMarks(autoRes.marks);
        }
        if (autoRes.teacher_remarks && (!currentRemarks.trim() || !hasEnteredDetails)) {
          currentRemarks = autoRes.teacher_remarks;
          setRemarks(autoRes.teacher_remarks);
        }
      }

      if (!currentRemarks.trim()) {
        currentRemarks = syncRemarksFromDetails(currentDetails, currentMarks);
      }

      const payload = {
        details: currentDetails,
        marks: currentMarks,
        rank_requested: true,
        teacher_remarks: currentRemarks,
        session_id: sessionId,
      };

      const result = await requestJson(`${API_URL}/assistant/quick-report-card/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      });

      setIssuedCard(result);
      onCreated(result);
      triggerDownload(result.pdf_url, result.roll_number, result.report_card_id);
    } catch (err) {
      setError(err.message || "Failed to auto-create report card.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");

    try {
      const cleanMarks = marks.filter((m) => m.subject.trim());
      const cleanRemarks = remarks.trim() || syncRemarksFromDetails(details, cleanMarks);

      const payload = {
        details,
        marks: cleanMarks,
        rank_requested: true,
        teacher_remarks: cleanRemarks,
        session_id: sessionId,
      };

      const result = await requestJson(`${API_URL}/assistant/quick-report-card/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
        body: JSON.stringify(payload),
      });

      setIssuedCard(result);
      onCreated(result);
      triggerDownload(result.pdf_url, result.roll_number, result.report_card_id);
    } catch (err) {
      setError(err.message || "Failed to create report card.");
    } finally {
      setBusy(false);
    }
  }

  if (!isOpen) return null;

  return (
    <div
      className="modal-overlay"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className={`modal-card ${issuedCard ? "expanded" : ""}`}>
        <div className="modal-header">
          <h3>⚡ Make Official Report Card (AI Assisted)</h3>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>

        {issuedCard ? (
          <div className="modal-body modal-report-embed-body">
            <ReportCardEmbed data={issuedCard} />
            <div className="modal-success-actions" style={{ marginTop: "1.2rem" }}>
              <button
                type="button"
                className="secondary-button"
                onClick={() => {
                  setIssuedCard(null);
                  setDetails({
                    name: "",
                    roll_number: "",
                    class_name: "",
                    section: "",
                    academic_year: "2023-2024",
                    examination_name: "Annual Examination",
                  });
                }}
              >
                + Make Another Report Card
              </button>
              <button type="button" className="secondary-button" onClick={onClose}>
                Done / Close
              </button>
            </div>
          </div>
        ) : (
          <>
            {/* AI Auto-Fill Toolbar */}
            <div className="modal-ai-bar">
              <div className="ai-bar-input-wrap">
                <span className="ai-sparkle">✨</span>
                <input
                  placeholder="Prompt or paste marks (e.g. 'Aarav Sharma roll 1024 class 10-B' or leave blank)..."
                  value={aiPrompt}
                  onChange={(e) => setAiPrompt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      handleAutoFill();
                    }
                  }}
                />
              </div>
              <button
                type="button"
                className="ai-autofill-btn"
                onClick={handleAutoFill}
                disabled={autoFilling || busy}
                title="Fill all form fields using LLM"
              >
                {autoFilling ? "Filling with AI…" : "✨ Auto-Fill with LLM"}
              </button>
              <button
                type="button"
                className="ai-autocreate-btn"
                onClick={handleAutoCreateAndDownload}
                disabled={autoFilling || busy}
                title="Instantly generate report card and download PDF"
              >
                {busy ? "Creating…" : "⚡ Auto-Create & Download PDF"}
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div className="modal-body">
                {error && <div className="notice error-notice">{error}</div>}

                <h4>Student Details</h4>
                <div className="form-grid">
                  <label className="field">
                    <span>Student Name *</span>
                    <input
                      required
                      value={details.name}
                      onChange={(e) => updateDetail("name", e.target.value)}
                      placeholder="e.g. Aarav Sharma"
                    />
                  </label>
                  <label className="field">
                    <span>Roll Number *</span>
                    <input
                      required
                      value={details.roll_number}
                      onChange={(e) => updateDetail("roll_number", e.target.value)}
                      placeholder="e.g. 1024"
                    />
                  </label>
                  <label className="field">
                    <span>Class *</span>
                    <input
                      required
                      value={details.class_name}
                      onChange={(e) => updateDetail("class_name", e.target.value)}
                      placeholder="e.g. 10"
                    />
                  </label>
                  <label className="field">
                    <span>Section</span>
                    <input
                      value={details.section}
                      onChange={(e) => updateDetail("section", e.target.value)}
                      placeholder="e.g. B"
                    />
                  </label>
                  <label className="field">
                    <span>Academic Year *</span>
                    <input
                      required
                      value={details.academic_year}
                      onChange={(e) => updateDetail("academic_year", e.target.value)}
                    />
                  </label>
                  <label className="field">
                    <span>Examination Name *</span>
                    <input
                      required
                      value={details.examination_name}
                      onChange={(e) => updateDetail("examination_name", e.target.value)}
                    />
                  </label>
                </div>

                <div className="modal-section-title">
                  <h4>Subject Marks</h4>
                  <button type="button" className="secondary-button small" onClick={addSubject}>
                    + Add Subject
                  </button>
                </div>

                <div className="modal-marks-list">
                  {marks.map((mark, idx) => {
                    const obt = parseFloat(mark.marks);
                    const max = parseFloat(mark.maximum_marks);
                    const rowPct = !isNaN(obt) && !isNaN(max) && max > 0 ? ((obt / max) * 100).toFixed(0) : null;
                    const rowGrade = rowPct !== null ? (rowPct >= 90 ? "A" : rowPct >= 80 ? "B" : rowPct >= 70 ? "C" : rowPct >= 60 ? "D" : rowPct >= 50 ? "E" : "F") : "";

                    return (
                      <div key={idx} className="modal-mark-row">
                        <input
                          required
                          placeholder="Subject (e.g. Mathematics)"
                          value={mark.subject}
                          onChange={(e) => updateMark(idx, "subject", e.target.value)}
                        />
                        <input
                          required
                          type="number"
                          step="0.01"
                          min="0"
                          placeholder="Marks"
                          value={mark.marks}
                          onChange={(e) => updateMark(idx, "marks", e.target.value)}
                        />
                        <input
                          required
                          type="number"
                          step="0.01"
                          min="0.01"
                          placeholder="Max"
                          value={mark.maximum_marks}
                          onChange={(e) => updateMark(idx, "maximum_marks", e.target.value)}
                        />
                        <div
                          className="row-grade-chip"
                          title={rowPct !== null ? `${rowPct}% - Grade ${rowGrade}` : "Enter marks"}
                        >
                          {rowPct !== null ? `${rowPct}% · ${rowGrade}` : "—"}
                        </div>
                        {marks.length > 1 ? (
                          <button
                            type="button"
                            className="remove-btn"
                            onClick={() => removeSubject(idx)}
                            title="Remove subject"
                          >
                            ×
                          </button>
                        ) : (
                          <div style={{ width: 32 }} />
                        )}
                      </div>
                    );
                  })}
                </div>

                {/* Real-time live score & grade preview as user fills details */}
                <div className="modal-live-summary">
                  <div className="modal-live-stat">
                    <span className="modal-live-label">Total Marks</span>
                    <span className="modal-live-val">{liveStats.totalMarks} / {liveStats.totalMax}</span>
                  </div>
                  <div className="modal-live-stat">
                    <span className="modal-live-label">Percentage</span>
                    <span className="modal-live-val">{liveStats.percentage}%</span>
                  </div>
                  <div className="modal-live-stat">
                    <span className="modal-live-label">Overall Grade</span>
                    <span className="modal-live-val">
                      <span className={`modal-grade-pill grade-${liveStats.grade}`}>
                        {liveStats.grade !== "-" ? `Grade ${liveStats.grade}` : "—"}
                      </span>
                    </span>
                  </div>
                  <div className="modal-live-stat">
                    <span className="modal-live-label">Result Status</span>
                    <span className="modal-live-val">
                      <span className={`modal-status-badge ${liveStats.passed ? "pass" : "fail"}`}>
                        {liveStats.passed ? "✅ Passed" : "⚠️ Needs Improvement"}
                      </span>
                    </span>
                  </div>
                </div>

                <div className="modal-section-title">
                  <h4>Teacher Remarks</h4>
                  <button
                    type="button"
                    className="secondary-button small"
                    onClick={() => setRemarks(syncRemarksFromDetails())}
                    title="Generate personalized remarks matching the student name and filled marks"
                  >
                    ✨ Auto-Sync Remarks
                  </button>
                </div>
                <label className="field">
                  <textarea
                    rows={2}
                    value={remarks}
                    onChange={(e) => setRemarks(e.target.value)}
                    placeholder="Remarks printed on the official report card"
                  />
                </label>
              </div>

              <div className="modal-footer">
                <button type="button" className="secondary-button" onClick={onClose} disabled={busy}>
                  Cancel
                </button>
                <button type="submit" className="generate-button" disabled={busy}>
                  {busy ? "Generating Official PDF…" : "✓ Create & Download Report Card"}
                </button>
              </div>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

/* =========================================================================
   Main Assistant Component
   ========================================================================= */
export default function Assistant() {
  const [activeTab, setActiveTab] = useState("chat"); // "chat" | "wizard"
  const [session, setSession] = useState(null);
  const [sessionContext, setSessionContext] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [showQuickModal, setShowQuickModal] = useState(false);

  // Chatbot State
  const [chatMessages, setChatMessages] = useState([]);
  const [inputMessage, setInputMessage] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamError, setStreamError] = useState("");
  const [copiedId, setCopiedId] = useState(null);
  const abortControllerRef = useRef(null);
  const chatBottomRef = useRef(null);
  const inputRef = useRef(null);

  // Workflow State
  const [policies, setPolicies] = useState([]);
  const [policyId, setPolicyId] = useState("");
  const [requirements, setRequirements] = useState("");
  const [grades, setGrades] = useState(DEFAULT_GRADES);
  const [policyForm, setPolicyForm] = useState({
    name: "School grading policy",
    minimum_passing_percentage: "40",
    subject_passing_percentage: "33",
    require_subject_pass: false,
    weighted_subjects: "{}",
  });
  const [comparisonCsv, setComparisonCsv] = useState("");
  const [comparisonComplete, setComparisonComplete] = useState(false);
  const [teacherRemarks, setTeacherRemarks] = useState("");
  const [workflowQuestion, setWorkflowQuestion] = useState("");

  // Initialize Session
  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const savedId = localStorage.getItem(SESSION_KEY);
        const existing = savedId
          ? await requestJson(`${API_URL}/assistant/sessions/${savedId}/`).catch(() => null)
          : null;
        const loaded =
          existing ||
          (await requestJson(`${API_URL}/assistant/sessions/`, {
            method: "POST",
            headers: { "X-CSRFToken": csrfToken() },
          }));
        if (!active) return;
        localStorage.setItem(SESSION_KEY, loaded.id);
        setSession(loaded);
        if (loaded.state?.chat_context) {
          setSessionContext(loaded.state.chat_context);
        }
        setComparisonComplete(Boolean(loaded.state?.comparison_complete));
        setComparisonCsv(comparisonCsvFromState(loaded.state?.comparisons));
        setTeacherRemarks(loaded.state?.teacher_remarks || "");
        setRequirements(loaded.state?.policy_requirements || "");
        if (loaded.state?.policy) {
          setPolicyForm((previous) => ({
            ...previous,
            ...loaded.state.policy,
            weighted_subjects: JSON.stringify(
              loaded.state.policy.weighted_subjects || {},
              null,
              2,
            ),
          }));
          setGrades(loaded.state.policy.grade_boundaries || DEFAULT_GRADES);
        }

        // Initialize Chat Messages
        if (loaded.messages && loaded.messages.length > 0) {
          setChatMessages(
            loaded.messages.map((m, idx) => ({
              id: `init-${idx}`,
              role: m.role,
              content: m.content,
              time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            })),
          );
        } else {
          setChatMessages([
            {
              id: "welcome-1",
              role: "assistant",
              content:
                "👋 Hello! I am **Reportly AI**, your intelligent academic assistant for student report cards.\n\nJust say **\"Hey\"** to start creating a report card step-by-step. I will ask you for each detail in sequence (Student Name, Roll Number, Class, Academic Year, Exam, and Marks).\n\n⚡ Notice the **Flash Signal** button in the message bar — it will automatically auto-fill as you chat, and you can generate the official PDF anytime!",
              time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
            },
          ]);
        }
      } catch (requestError) {
        if (active) setError(requestError.message);
      }
    }
    initialize();
    return () => {
      active = false;
    };
  }, []);

  // Auto-scroll chat
  useEffect(() => {
    if (chatBottomRef.current) {
      chatBottomRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [chatMessages, isStreaming]);

  // Fetch policies for existing_policy step
  useEffect(() => {
    if (session?.step !== "existing_policy") return;
    const params = new URLSearchParams({
      class_name: session.state.details.class_name,
      academic_year: session.state.details.academic_year,
    });
    requestJson(`${API_URL}/assistant/grading-policies/?${params}`)
      .then(setPolicies)
      .catch((requestError) => setError(requestError.message));
  }, [session?.id, session?.step]);

  /* =========================================================================
     Streaming Chat Handler
     ========================================================================= */
  async function handleSendChat(textToSend = null) {
    const text = (textToSend !== null ? textToSend : inputMessage).trim();
    if (!text || isStreaming) return;

    setInputMessage("");
    setStreamError("");

    const userMessageId = `user-${Date.now()}`;
    const assistantMessageId = `asst-${Date.now() + 1}`;
    const nowTime = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    const updatedWithUser = [
      ...chatMessages,
      { id: userMessageId, role: "user", content: text, time: nowTime },
    ];

    setChatMessages([
      ...updatedWithUser,
      { id: assistantMessageId, role: "assistant", content: "", isStreaming: true, time: nowTime },
    ]);
    setIsStreaming(true);

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const response = await fetch(`${API_URL}/assistant/chat/stream/`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-CSRFToken": csrfToken(),
        },
        credentials: "include",
        body: JSON.stringify({
          message: text,
          session_id: session?.id,
          history: updatedWithUser.slice(-10).map((m) => ({ role: m.role, content: m.content })),
          context: {
            step: session?.step,
            details: session?.state?.details,
            marks: session?.state?.marks,
            calculation: session?.state?.calculation,
          },
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        if (response.status === 403) {
          throw new Error("Please sign in as a staff user to chat with the assistant.");
        }
        throw new Error(`Chat stream request failed (${response.status})`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let accumulated = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data:")) {
            const jsonStr = trimmed.slice(5).trim();
            if (!jsonStr) continue;
            try {
              const parsed = JSON.parse(jsonStr);
              if (parsed.context) {
                setSessionContext(parsed.context);
              }
              if (parsed.delta) {
                accumulated += parsed.delta;
                setChatMessages((prev) =>
                  prev.map((msg) =>
                    msg.id === assistantMessageId ? { ...msg, content: accumulated } : msg,
                  ),
                );
              } else if (parsed.error) {
                throw new Error(parsed.error);
              }
            } catch (err) {
              if (err.message && err.message.includes("AI service")) {
                throw err;
              }
            }
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setStreamError(err.message || "Failed to generate stream response.");
        setChatMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content:
                    (msg.content ? msg.content + "\n\n" : "") +
                    `⚠️ *${err.message || "Connection interrupted. Please try again."}*`,
                }
              : msg,
          ),
        );
      }
    } finally {
      setIsStreaming(false);
      setChatMessages((prev) =>
        prev.map((msg) => (msg.id === assistantMessageId ? { ...msg, isStreaming: false } : msg)),
      );
      abortControllerRef.current = null;
      if (inputRef.current) inputRef.current.focus();
    }
  }

  function handleStopGenerating() {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setIsStreaming(false);
    }
  }

  function handleCopy(text, id) {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }

  function handleResetChat() {
    if (isStreaming) handleStopGenerating();
    setSessionContext(null);
    setChatMessages([
      {
        id: `welcome-${Date.now()}`,
        role: "assistant",
        content:
          "👋 **New conversation started.**\n\nJust say **\"Hey\"** to start creating a report card step-by-step, or open the ⚡ **Flash Signal** modal anytime to see live parameters.",
        time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  }

  function handleQuickReportCreated(result) {
    setSessionContext((prev) => ({
      ...(prev || {}),
      step: "issued",
      report_card: result,
    }));
    const cardTag = `\n\n:::report_card\n${JSON.stringify(result)}\n:::\n`;
    const message = {
      id: `rc-msg-${Date.now()}`,
      role: "assistant",
      content: `🎉 **Official Report Card Created Successfully!**\n\nThe report card for **${result.student_name}** (Roll: ${result.roll_number}, Class: ${result.class_name}) has been issued and stored in the database. You can download the official PDF below:${cardTag}`,
      time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    setChatMessages((prev) => [...prev, message]);
  }

  /* =========================================================================
     Workflow Advance Handler
     ========================================================================= */
  async function send(action, data = {}) {
    if (!session) return;
    setBusy(true);
    setError("");
    try {
      const updated = await requestJson(`${API_URL}/assistant/sessions/${session.id}/`, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken() },
        body: JSON.stringify({ action, data }),
      });
      setSession(updated);
      setComparisonComplete(Boolean(updated.state?.comparison_complete));
      setComparisonCsv(comparisonCsvFromState(updated.state?.comparisons));
      setTeacherRemarks(updated.state?.teacher_remarks || "");
      setRequirements(updated.state?.policy_requirements || "");
      if (updated.state?.policy) {
        setPolicyForm((previous) => ({
          ...previous,
          ...updated.state.policy,
          weighted_subjects: JSON.stringify(updated.state.policy.weighted_subjects || {}, null, 2),
        }));
        setGrades(updated.state.policy.grade_boundaries || DEFAULT_GRADES);
      }
      return true;
    } catch (requestError) {
      setError(requestError.message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  function updatePolicy(field, value) {
    setPolicyForm((previous) => ({ ...previous, [field]: value }));
  }

  function buildPolicyData() {
    let weightedSubjects;
    try {
      weightedSubjects = JSON.parse(policyForm.weighted_subjects || "{}");
    } catch {
      throw new Error('Subject weights must be valid JSON, for example {"Mathematics": 2}.');
    }
    return {
      ...policyForm,
      grade_boundaries: grades,
      weighted_subjects: weightedSubjects,
    };
  }

  function parseComparisonCsv() {
    const students = new Map();
    const lines = comparisonCsv.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
    for (const [index, line] of lines.entries()) {
      const [rollNumber, subject, obtained, maximum] = line.split(",").map((part) => part.trim());
      if (!rollNumber || !subject || !obtained || !maximum) {
        throw new Error(
          `Comparison row ${index + 1} needs: roll number, subject, marks, maximum marks.`,
        );
      }
      const student = students.get(rollNumber) || { roll_number: rollNumber, marks: [] };
      student.marks.push({ subject, marks: obtained, maximum_marks: maximum });
      students.set(rollNumber, student);
    }
    return [...students.values()];
  }

  const step = session?.step || "marks";
  const calculation = session?.state?.calculation;
  const intakeInput = session?.state?.intake?.input;

  const filledCount = useMemo(() => {
    const p = sessionContext?.parameters || {};
    let count = 0;
    if (p.name?.trim()) count++;
    if (p.roll_number?.trim()) count++;
    if (p.class_name?.trim()) count++;
    if (p.academic_year?.trim()) count++;
    if (p.examination_name?.trim()) count++;
    if (Array.isArray(p.marks) && p.marks.length > 0) count++;
    return count;
  }, [sessionContext]);

  return (
    <main className="assistant-shell">
      {/* Top Header */}
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark">R</span>
          <span>Reportly</span>
        </a>
        <div className="streaming-badge" title="Streaming Groq LLM Assistant Active">
          <span className="pulsing-green-dot" />
          <span>AI Streaming Assistant</span>
        </div>
        <div className="tab-switcher">
          <button
            className={`tab-btn ${activeTab === "chat" ? "active" : ""}`}
            onClick={() => setActiveTab("chat")}
          >
            💬 AI Chatbot
          </button>
          <button
            className={`tab-btn ${activeTab === "wizard" ? "active" : ""}`}
            onClick={() => setActiveTab("wizard")}
          >
            📋 Report Builder
          </button>
          <button
            className={`tab-btn ${activeTab === "manual" ? "active" : ""}`}
            onClick={() => setActiveTab("manual")}
          >
            ✍️ Manual Entry
          </button>
        </div>
        <nav className="workflow-nav" aria-label="Creation modes">
          <a className="admin-link" href="/">Dashboard</a>
          <a className="admin-link active-workflow" href="/assistant/">AI Assistant</a>
          <a className="admin-link" href="/manual/">Manual</a>
          <a className="admin-link" href="/admin/">
            Admin portal <span aria-hidden="true">↗</span>
          </a>
          <SignOutButton />
        </nav>
      </header>

      {/* Intro Header */}
      <section className="assistant-intro">
        <div className="assistant-intro-header">
          <div>
            <p className="eyebrow">INTELLIGENT TEACHER ASSISTANT</p>
            <h1>AI Academic Chatbot & Report Generator</h1>
            <p>
              Create official student report cards via chat, step-by-step wizard, or direct manual entry. All PDFs are generated with standard ReportLab formatting.
            </p>
          </div>
          <div className="assistant-header-actions">
            <button
              className={`generate-button quick-make-btn ${filledCount > 0 ? "has-data" : ""}`}
              onClick={() => setShowQuickModal(true)}
              title={
                filledCount > 0
                  ? `⚡ Flash Signal: ${filledCount}/6 details synced from chat! Click to view or create.`
                  : "⚡ Flash Signal: Auto-fills as you chat. Click to open."
              }
            >
              ⚡ Flash Signal {filledCount > 0 ? `(${filledCount}/6)` : "+ Make Report"}
            </button>
            {activeTab !== "chat" && (
              <button className="secondary-button" onClick={() => setActiveTab("chat")}>
                💬 Switch to Chatbot
              </button>
            )}
            {activeTab !== "manual" && (
              <button className="secondary-button" onClick={() => setActiveTab("manual")}>
                ✍️ Manual Entry
              </button>
            )}
            {activeTab === "chat" && (
              <button className="secondary-button" onClick={handleResetChat} title="Clear and restart conversation">
                ↻ New Chat
              </button>
            )}
          </div>
        </div>
      </section>

      {/* Quick Make Report Card Modal */}
      {showQuickModal && (
        <QuickReportModal
          isOpen={showQuickModal}
          onClose={() => setShowQuickModal(false)}
          onCreated={handleQuickReportCreated}
          chatHistory={chatMessages}
          context={sessionContext}
          sessionId={session?.id}
        />
      )}

      {/* Main Tab Content */}
      {activeTab === "chat" && (
        <section className="chatbot-wrapper">
          {/* Chat Messages Log */}
          <div className="chatbot-messages-area">
            {chatMessages.length === 1 && chatMessages[0].role === "assistant" && (
              <div className="chatbot-hero">
                <div className="chatbot-hero-avatar">🤖</div>
                <h2>How can I help you today?</h2>
                <p>Pick a prompt or type any question to draft or issue an official report card.</p>
                <div className="prompt-chips-grid">
                  {SUGGESTED_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      className="prompt-chip"
                      onClick={() => handleSendChat(prompt.desc)}
                    >
                      <span className="prompt-chip-icon">{prompt.icon}</span>
                      <div className="prompt-chip-text">
                        <strong>{prompt.title}</strong>
                        <span>{prompt.desc}</span>
                      </div>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {chatMessages.map((msg) => (
              <div key={msg.id} className={`chat-message-row ${msg.role}`}>
                <div className="chat-avatar-bubble">
                  {msg.role === "assistant" ? "🤖" : "👤"}
                </div>
                <div className="chat-content-container">
                  <div className="chat-meta">
                    <span className="chat-author">{msg.role === "assistant" ? "Reportly AI" : "You"}</span>
                    {msg.time && <span className="chat-timestamp">{msg.time}</span>}
                  </div>
                  <div className="chat-bubble-body">
                    <MarkdownRenderer
                      content={msg.content}
                      isStreaming={msg.isStreaming}
                      onTriggerAction={handleSendChat}
                      onOpenFlashModal={() => setShowQuickModal(true)}
                    />
                  </div>
                  {msg.role === "assistant" && !msg.isStreaming && msg.content && (
                    <div className="chat-message-actions">
                      <button
                        className="copy-btn"
                        onClick={() => handleCopy(msg.content, msg.id)}
                        title="Copy text to clipboard"
                      >
                        {copiedId === msg.id ? "✓ Copied" : "📋 Copy"}
                      </button>
                      <button
                        className="action-btn"
                        onClick={() => setShowQuickModal(true)}
                        title="Create an official report card"
                      >
                        ⚡ Flash Signal {filledCount > 0 ? `(${filledCount}/6)` : ""}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={chatBottomRef} />
          </div>

          {/* Composer */}
          <div className="chatbot-composer-container">
            {streamError && <div className="notice error-notice">{streamError}</div>}
            <form
              className="chatbot-input-form"
              onSubmit={(e) => {
                e.preventDefault();
                handleSendChat();
              }}
            >
              <textarea
                ref={inputRef}
                rows={1}
                className="chatbot-textarea"
                placeholder="Say 'Hey' to begin, or type student details / marks…"
                value={inputMessage}
                disabled={isStreaming}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSendChat();
                  }
                }}
              />
              <div className="composer-button-group">
                <button
                  type="button"
                  className={`quick-icon-btn ${filledCount > 0 ? "has-data" : ""}`}
                  onClick={() => setShowQuickModal(true)}
                  title={
                    filledCount > 0
                      ? `⚡ Flash Signal: ${filledCount}/6 details auto-filled from chat. Click to view or create report card.`
                      : "⚡ Flash Signal: Auto-fills as you chat. Click to open form."
                  }
                >
                  ⚡
                  {filledCount > 0 && <span className="quick-btn-badge">{filledCount}/6</span>}
                </button>
                {isStreaming ? (
                  <button
                    type="button"
                    className="stop-button"
                    onClick={handleStopGenerating}
                    title="Stop generating response"
                  >
                    ⏹ Stop
                  </button>
                ) : (
                  <button
                    type="submit"
                    className="send-button"
                    disabled={!inputMessage.trim()}
                    title="Send message"
                  >
                    Send ➔
                  </button>
                )}
              </div>
            </form>
            <p className="composer-hint">
              Press <b>Enter</b> to send, <b>Shift + Enter</b> for newline · Chatbot automatically creates report cards & generates PDFs
            </p>
          </div>
        </section>
      )}

      {/* Report Builder Wizard Tab */}
      {activeTab === "wizard" && (
        <section className="assistant-panel">
          <div className="wizard-tab-header">
            <span className="step-badge">Step: {step.toUpperCase()}</span>
            <button className="secondary-button" onClick={() => setActiveTab("chat")}>
              💬 Open AI Chatbot for Guidance
            </button>
          </div>

          <div className="chat-log" aria-live="polite">
            {(session?.messages || [{ role: "assistant", content: WELCOME }]).map(
              (message, index) => (
                <p className={`chat-message ${message.role}`} key={`${index}-${message.content}`}>
                  {message.content}
                </p>
              ),
            )}
          </div>

          {error && <div className="notice error-notice" role="alert">{error}</div>}
          {!session && !error && <p className="empty-state">Restoring your saved assistant session…</p>}
          {!session && error && (
            <div className="assistant-auth">
              <p>Staff sign-in is required to save and issue report cards.</p>
              <a className="summary-button" href="/login/?next=%2Fassistant%2F">
                Sign in or create a teacher account
              </a>
              <button className="secondary-button" onClick={() => window.location.reload()}>
                Try again
              </button>
            </div>
          )}

          {session && step === "confirm_marks" && (
            <section className="workflow-form">
              <h2>Confirm marks before grading</h2>
              <p>
                <b>{session.state.details.name}</b> · Roll {session.state.details.roll_number} · Class{" "}
                {session.state.details.class_name}
                {session.state.details.section ? `-${session.state.details.section}` : ""} ·{" "}
                {session.state.details.academic_year} · {session.state.details.examination_name}
              </p>
              <SubjectTable rows={session.state.marks} />
              <div className="workflow-actions">
                <button className="secondary-button" disabled={busy} onClick={() => send("edit_marks")}>
                  Edit details or marks
                </button>
                <button className="generate-button" disabled={busy} onClick={() => send("confirm_marks")}>
                  Marks are correct — continue
                </button>
              </div>
            </section>
          )}

          {session && step === "policy_choice" && (
            <section className="workflow-form">
              <h2>
                {session.messages.at(-1)?.content ||
                  "Do you already have a grading system that your school follows?"}
              </h2>
              <div className="choice-list">
                <button onClick={() => send("choose_policy", { mode: "existing" })}>
                  1. Yes, I have an existing grading system.
                </button>
                <button onClick={() => send("choose_policy", { mode: "proposal" })}>
                  2. No, create a grading system for me.
                </button>
                <button onClick={() => send("choose_policy", { mode: "custom" })}>
                  3. I want to customize the grading system.
                </button>
              </div>
              <button className="secondary-button" disabled={busy} onClick={() => send("back_to_marks")}>
                Back to student details and marks
              </button>
            </section>
          )}

          {session && step === "existing_policy" && (
            <section className="workflow-form">
              <h2>Select an approved school policy</h2>
              {policies.length ? (
                <>
                  <select value={policyId} onChange={(event) => setPolicyId(event.target.value)}>
                    <option value="">Choose a policy</option>
                    {policies.map((policy) => (
                      <option value={policy.id} key={policy.id}>
                        {policy.name}
                        {policy.class_name ? ` · Class ${policy.class_name}` : ""}
                        {policy.academic_year ? ` · ${policy.academic_year}` : ""}
                      </option>
                    ))}
                  </select>
                  <div className="workflow-actions">
                    <button className="secondary-button" onClick={() => send("back_to_marks")}>
                      Back to marks
                    </button>
                    <button
                      className="generate-button"
                      disabled={!policyId || busy}
                      onClick={() => send("select_policy", { policy_id: policyId })}
                    >
                      Use approved policy
                    </button>
                  </div>
                </>
              ) : (
                <p>No approved matching policies are available. Go back and choose a proposal or custom policy.</p>
              )}
            </section>
          )}

          {session && step === "requirements" && (
            <form
              className="workflow-form"
              onSubmit={(event) => {
                event.preventDefault();
                send("propose_policy", { requirements });
              }}
            >
              <h2>Institution requirements</h2>
              <p>The AI proposal will be marked unapproved until you review and approve it.</p>
              <textarea
                rows="5"
                required
                maxLength="4000"
                value={requirements}
                onChange={(event) => setRequirements(event.target.value)}
                placeholder="Describe grade bands, passing thresholds, subject-wise pass rules, and any weighted subjects."
              />
              <div className="workflow-actions">
                <button className="secondary-button" type="button" onClick={() => send("back_to_marks")}>
                  Back to marks
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  disabled={busy || !requirements.trim()}
                  onClick={() => send("clarify_requirements", { requirements })}
                >
                  Ask AI to clarify
                </button>
                <button className="generate-button" disabled={busy}>
                  {busy ? "Preparing proposal…" : "Propose grading policy"}
                </button>
              </div>
            </form>
          )}

          {session && (step === "custom_policy" || step === "approve_policy") && (
            <PolicyEditor
              step={step}
              grades={grades}
              setGrades={setGrades}
              policyForm={policyForm}
              updatePolicy={updatePolicy}
              busy={busy}
              onSubmit={(event) => {
                event.preventDefault();
                try {
                  send(step === "custom_policy" ? "submit_custom_policy" : "edit_policy", buildPolicyData());
                } catch (parseError) {
                  setError(parseError.message);
                }
              }}
              onApprove={() => send("approve_policy")}
              onBack={() => send("back_to_marks")}
            />
          )}

          {session && step === "comparison" && (
            <section className="workflow-form">
              <h2>Class comparison marks</h2>
              {session.state.comparisons?.length > 0 && (
                <p>
                  {session.state.comparisons.length} saved comparison record(s) are available for this
                  class, examination, and academic year.
                </p>
              )}
              <p>
                For a valid rank, enter every subject for students in the same class, examination, and
                academic year. One CSV row per subject: roll number, subject, marks obtained, maximum marks.
              </p>
              <label className="check-line">
                <input
                  type="checkbox"
                  checked={comparisonComplete}
                  onChange={(event) => setComparisonComplete(event.target.checked)}
                />{" "}
                I confirm these comparison records include all students in this class and examination
              </label>
              <textarea
                rows="7"
                value={comparisonCsv}
                onChange={(event) => setComparisonCsv(event.target.value)}
                placeholder={"R-13, Mathematics, 75, 100\nR-13, Science, 80, 100\nR-14, Mathematics, 90, 100\nR-14, Science, 85, 100"}
              />
              <label className="field csv-upload">
                <span>Or import a CSV file (roll number, subject, marks, maximum marks)</span>
                <input
                  type="file"
                  accept=".csv,text/csv"
                  onChange={async (event) => {
                    const file = event.target.files?.[0];
                    if (!file) return;
                    try {
                      setComparisonCsv(await file.text());
                      setError("");
                    } catch {
                      setError("Could not read the selected CSV file.");
                    }
                  }}
                />
              </label>
              <div className="workflow-actions">
                <button className="secondary-button" disabled={busy} onClick={() => send("back_to_marks")}>
                  Back to marks
                </button>
                {session.state.comparisons?.length > 0 && (
                  <button className="secondary-button" disabled={busy} onClick={() => send("use_saved_comparisons")}>
                    Use saved class marks
                  </button>
                )}
                <button className="secondary-button" disabled={busy} onClick={() => send("skip_comparisons")}>
                  Continue without class rank
                </button>
                <button
                  className="generate-button"
                  disabled={busy || !comparisonComplete}
                  onClick={() => {
                    try {
                      send("add_comparisons", {
                        comparisons: parseComparisonCsv(),
                        comparison_complete: true,
                      });
                    } catch (parseError) {
                      setError(parseError.message);
                    }
                  }}
                >
                  Validate comparisons and preview
                </button>
              </div>
            </section>
          )}

          {session && step === "preview" && calculation && (
            <section className="workflow-form report-preview">
              <h2>Report card preview</h2>
              <p>
                <b>{calculation.details.name}</b> · Roll {calculation.details.roll_number} · Class{" "}
                {calculation.details.class_name}
                {calculation.details.section ? `-${calculation.details.section}` : ""} ·{" "}
                {calculation.details.academic_year} · {calculation.details.examination_name}
              </p>
              <SubjectTable rows={calculation.subject_results} showResults />
              <div className="preview-summary">
                <p>
                  <b>Total:</b> {calculation.total_marks} / {calculation.total_maximum_marks}
                </p>
                <p>
                  <b>Overall percentage:</b> {calculation.percentage}%
                </p>
                <p>
                  <b>Overall grade:</b> {calculation.overall_grade} · <b>Status:</b>{" "}
                  {calculation.passed ? "PASS" : "FAIL"}
                </p>
                {calculation.rank !== null && <p><b>Class rank:</b> {calculation.rank}</p>}
                {calculation.percentile !== null && (
                  <p><b>Class percentile:</b> {calculation.percentile}%</p>
                )}
                {calculation.rank_unavailable_reason && (
                  <p className="rank-unavailable">{calculation.rank_unavailable_reason}</p>
                )}
              </div>
              <div className="feedback-preview">
                <b>AI-generated academic feedback (teacher review):</b>
                <p>{session.state.teacher_feedback}</p>
              </div>
              <label className="field">
                <span>Teacher remarks</span>
                <textarea
                  rows="3"
                  maxLength="4000"
                  value={teacherRemarks}
                  onChange={(event) => setTeacherRemarks(event.target.value)}
                  placeholder="Optional remarks for the report card"
                />
              </label>
              <p className="approval-note">Confirming will save and issue the official report card.</p>
              <div className="workflow-actions">
                <button
                  className="secondary-button"
                  disabled={busy}
                  onClick={() => send("back_to_marks", { teacher_remarks: teacherRemarks })}
                >
                  Back to edit marks
                </button>
                <button
                  className="generate-button"
                  disabled={busy}
                  onClick={() => send("issue_report", { teacher_remarks: teacherRemarks })}
                >
                  {busy ? "Issuing report…" : "Confirm and issue report card"}
                </button>
              </div>
            </section>
          )}

          {session && step === "issued" && (
            <section className="workflow-form issued-card">
              <h2>Report card issued</h2>
              <p>Your report card has been saved in the database. Download the official PDF below:</p>
              <div className="issued-pdf-actions">
                <a
                  className="generate-button pdf-link"
                  href={`${API_URL}/assistant/sessions/${session.id}/pdf/`}
                  target="_blank"
                  rel="noreferrer"
                  download
                >
                  📄 Download Official Report Card PDF
                </a>
                <button
                  className="secondary-button"
                  onClick={() => {
                    localStorage.removeItem(SESSION_KEY);
                    window.location.reload();
                  }}
                >
                  Start another report card
                </button>
              </div>
            </section>
          )}

          {session && step === "marks" && intakeInput && (
            <form
              className="assistant-question chatbot-composer"
              onSubmit={async (event) => {
                event.preventDefault();
                const answer = workflowQuestion.trim();
                if (!answer) return;
                if (await send("intake_answer", { answer })) setWorkflowQuestion("");
              }}
            >
              <label className="field">
                <span>{intakeInput.label}</span>
                <input
                  autoFocus
                  type={intakeInput.type}
                  min={intakeInput.min}
                  max={intakeInput.max}
                  step={intakeInput.step}
                  maxLength={intakeInput.max_length || undefined}
                  required={intakeInput.required}
                  disabled={busy}
                  value={workflowQuestion}
                  onChange={(event) => setWorkflowQuestion(event.target.value)}
                  placeholder={intakeInput.placeholder || "Type your answer…"}
                />
              </label>
              <div className="chatbot-actions">
                <button
                  className="generate-button"
                  disabled={busy || (!workflowQuestion.trim() && intakeInput.required)}
                >
                  {busy ? "Saving…" : "Send"}
                </button>
                {!intakeInput.required && (
                  <button
                    type="button"
                    className="secondary-button"
                    disabled={busy}
                    onClick={async () => {
                      if (await send("intake_answer", { answer: "skip" })) setWorkflowQuestion("");
                    }}
                  >
                    Skip
                  </button>
                )}
              </div>
            </form>
          )}
        </section>
      )}

      {/* Direct Manual Entry Tab */}
      {activeTab === "manual" && (
        <ManualReport embedded />
      )}
    </main>
  );
}

function Field({ label, value, onChange, type = "text", ...inputProps }) {
  return (
    <label className="field">
      <span>{label}</span>
      <input type={type} value={value ?? ""} onChange={(event) => onChange(event.target.value)} {...inputProps} />
    </label>
  );
}

function SubjectTable({ rows, showResults = false }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Subject</th>
            <th>Marks</th>
            <th>Maximum</th>
            {showResults && (
              <>
                <th>Percent</th>
                <th>Grade</th>
                <th>Result</th>
              </>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={`${row.subject}-${index}`}>
              <td>{row.subject}</td>
              <td>{row.marks}</td>
              <td>{row.maximum_marks}</td>
              {showResults && (
                <>
                  <td>{row.percentage}%</td>
                  <td>{row.grade}</td>
                  <td>{row.passed ? "Pass" : "Needs support"}</td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function PolicyEditor({
  step,
  grades,
  setGrades,
  policyForm,
  updatePolicy,
  busy,
  onSubmit,
  onApprove,
  onBack,
}) {
  return (
    <form className="workflow-form" onSubmit={onSubmit}>
      <h2>{step === "custom_policy" ? "Customize grading policy" : "Review grading policy"}</h2>
      {step === "approve_policy" && policyForm.ai_generated_proposal && (
        <p className="proposal-label">AI-generated proposal — teacher approval is required before use.</p>
      )}
      <Field label="Policy name" value={policyForm.name} onChange={(value) => updatePolicy("name", value)} required />
      <h3>Grade boundaries (inclusive percentages)</h3>
      <div className="grade-editor">
        <div className="grade-row grade-header">
          <span>Grade</span>
          <span>Minimum %</span>
          <span>Maximum %</span>
        </div>
        {grades.map((grade, index) => (
          <div className="grade-row" key={index}>
            <input
              aria-label={`Grade label ${index + 1}`}
              value={grade.grade}
              onChange={(event) =>
                setGrades((previous) =>
                  previous.map((row, rowIndex) =>
                    rowIndex === index ? { ...row, grade: event.target.value } : row,
                  ),
                )
              }
            />
            <input
              aria-label={`Minimum percentage ${index + 1}`}
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={grade.min_percentage}
              onChange={(event) =>
                setGrades((previous) =>
                  previous.map((row, rowIndex) =>
                    rowIndex === index ? { ...row, min_percentage: event.target.value } : row,
                  ),
                )
              }
            />
            <input
              aria-label={`Maximum percentage ${index + 1}`}
              type="number"
              min="0"
              max="100"
              step="0.01"
              value={grade.max_percentage}
              onChange={(event) =>
                setGrades((previous) =>
                  previous.map((row, rowIndex) =>
                    rowIndex === index ? { ...row, max_percentage: event.target.value } : row,
                  ),
                )
              }
            />
          </div>
        ))}
      </div>
      {step === "custom_policy" && (
        <button
          type="button"
          className="secondary-button"
          onClick={() =>
            setGrades((previous) => [...previous, { grade: "", min_percentage: "", max_percentage: "" }])
          }
        >
          + Add grade
        </button>
      )}
      <div className="form-grid">
        <Field
          label="Overall minimum passing %"
          type="number"
          min="0"
          max="100"
          step="0.01"
          value={policyForm.minimum_passing_percentage}
          onChange={(value) => updatePolicy("minimum_passing_percentage", value)}
          required
        />
        <Field
          label="Subject minimum passing %"
          type="number"
          min="0"
          max="100"
          step="0.01"
          value={policyForm.subject_passing_percentage}
          onChange={(value) => updatePolicy("subject_passing_percentage", value)}
          required
        />
      </div>
      <label className="check-line">
        <input
          type="checkbox"
          checked={Boolean(policyForm.require_subject_pass)}
          onChange={(event) => updatePolicy("require_subject_pass", event.target.checked)}
        />{" "}
        Require passing marks in every subject
      </label>
      <label className="field">
        <span>Weighted subjects (optional JSON object)</span>
        <textarea
          rows="2"
          value={policyForm.weighted_subjects}
          onChange={(event) => updatePolicy("weighted_subjects", event.target.value)}
          placeholder={'{"Mathematics": 2, "English": 1}'}
        />
      </label>
      <p className="field-hint">
        Weights affect the overall grade percentage. Total marks remain the sum of marks obtained.
      </p>
      <div className="workflow-actions">
        <button type="button" className="secondary-button" onClick={onBack}>
          Back to student details
        </button>
        {step === "custom_policy" ? (
          <button className="generate-button" disabled={busy}>
            Review policy
          </button>
        ) : (
          <button type="button" className="generate-button" disabled={busy} onClick={onApprove}>
            Approve policy and continue
          </button>
        )}
        {step === "approve_policy" && (
          <button type="submit" className="secondary-button" disabled={busy}>
            Save policy edits
          </button>
        )}
      </div>
    </form>
  );
}
