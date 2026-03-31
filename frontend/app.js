const CATEGORY_CONFIG = [
  { key: "language", label: "언어 표현 품질", scoreId: "score-language", meterId: "meter-language", summaryId: "detail-language-summary", itemsId: "detail-language-items" },
  { key: "structure", label: "강의 도입 및 구조", scoreId: "score-structure", meterId: "meter-structure", summaryId: "detail-structure-summary", itemsId: "detail-structure-items" },
  { key: "concept", label: "개념 설명 명확성", scoreId: "score-concept", meterId: "meter-concept", summaryId: "detail-concept-summary", itemsId: "detail-concept-items" },
  { key: "practice", label: "예시 및 실습 연계", scoreId: "score-practice", meterId: "meter-practice", summaryId: "detail-practice-summary", itemsId: "detail-practice-items" },
  { key: "interaction", label: "수강생 상호작용", scoreId: "score-interaction", meterId: "meter-interaction", summaryId: "detail-interaction-summary", itemsId: "detail-interaction-items" },
];

const EVIDENCE_ITEM_LABELS = {
  learning_objective_intro: "학습 목표 제시",
  previous_lesson_linkage: "이전 학습 연계",
  explanation_sequence: "설명 순서",
  key_point_emphasis: "핵심 강조",
  closing_summary: "마무리 요약",
  concept_definition: "개념 정의",
  analogy_example_usage: "비유와 예시",
  prerequisite_check: "선행 개념 확인",
  example_appropriateness: "예시 적절성",
  practice_transition: "실습 전환",
  error_handling: "오류 대응",
  participation_induction: "참여 유도",
  question_response_sufficiency: "질문 응답 충분성",
};

const RUN_STEPS = ["nlp", "llm", "integrate", "report"];
const JOB_POLL_INTERVAL_MS = 1200;
const RISK_SCORE = 75;
const CSV_FIELDS = ["course_id", "course_name", "date", "time", "subject", "content", "instructor", "sub_instructor"];
const FILTER_PARAM_KEYS = ["instructor", "course", "period"];
const REQUIRED_MESSAGES = {
  script_file: "TXT 파일을 업로드해 주세요.",
  course_id: "course_id를 입력해 주세요.",
  course_name: "과정명을 입력해 주세요.",
  date: "날짜를 선택해 주세요.",
  time: "시간을 입력해 주세요.",
  subject: "주제를 입력해 주세요.",
  content: "내용을 입력해 주세요.",
  instructor: "강사명을 입력해 주세요.",
  sub_instructor: "보조 강사명을 입력해 주세요.",
};
const LOCALE = document.documentElement.lang?.startsWith("ko")
  ? "ko-KR"
  : navigator.languages?.[0] || navigator.language || "en-US";
const numberFormatter = new Intl.NumberFormat(LOCALE);
const shortDateFormatter = new Intl.DateTimeFormat(LOCALE, { month: "2-digit", day: "2-digit" });
const compactDateFormatter = new Intl.DateTimeFormat(LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});
const longDateFormatter = new Intl.DateTimeFormat(LOCALE, {
  year: "numeric",
  month: "long",
  day: "numeric",
});

const dom = {
  viewDashboard: document.getElementById("view-dashboard"),
  viewDetail: document.getElementById("view-detail"),
  viewAnalyze: document.getElementById("view-analyze"),
  routeLinks: Array.from(document.querySelectorAll("[data-route-link]")),
  navLinks: Array.from(document.querySelectorAll(".top-nav__link")),
  headerRefresh: document.getElementById("header-refresh"),
  toast: document.getElementById("ui-toast"),
  filterInstructor: document.getElementById("filter-instructor"),
  filterCourse: document.getElementById("filter-course"),
  filterPeriod: document.getElementById("filter-period"),
  dashboardTotal: document.getElementById("dashboard-total"),
  dashboardAverage: document.getElementById("dashboard-average"),
  dashboardRisk: document.getElementById("dashboard-risk"),
  dashboardDelta: document.getElementById("dashboard-delta"),
  trendCaption: document.getElementById("trend-caption"),
  trendChart: document.getElementById("trend-chart"),
  categoryList: document.getElementById("dashboard-category-list"),
  reportTableBody: document.getElementById("report-table-body"),
  issueList: document.getElementById("issue-list"),
  detailTitle: document.getElementById("detail-title"),
  detailSubtitle: document.getElementById("detail-subtitle"),
  detailMetaCourse: document.getElementById("detail-meta-course"),
  detailMetaInstructor: document.getElementById("detail-meta-instructor"),
  detailMetaTime: document.getElementById("detail-meta-time"),
  detailMetaTopic: document.getElementById("detail-meta-topic"),
  detailOverallScore: document.getElementById("detail-overall-score"),
  detailOverallLevel: document.getElementById("detail-overall-level"),
  detailOverallDelta: document.getElementById("detail-overall-delta"),
  detailStrengthList: document.getElementById("detail-strength-list"),
  detailWeaknessList: document.getElementById("detail-weakness-list"),
  detailEvidenceList: document.getElementById("detail-evidence-list"),
  downloadPdf: document.getElementById("download-pdf"),
  downloadJson: document.getElementById("download-json"),
  detailBackDashboard: document.getElementById("detail-back-dashboard"),
  detailCompareReport: document.getElementById("detail-compare-report"),
  analysisForm: document.getElementById("analysis-form"),
  uploadZone: document.getElementById("script-upload-zone"),
  scriptFile: document.getElementById("script-file"),
  uploadFileName: document.getElementById("upload-file-name"),
  metadataCsv: document.getElementById("metadata-csv"),
  csvSessionPicker: document.getElementById("csv-session-picker"),
  csvSessionSelect: document.getElementById("csv-session-select"),
  csvApply: document.getElementById("csv-apply"),
  analysisPill: document.getElementById("analysis-pill"),
  statusLive: document.getElementById("status-live"),
  progressBar: document.getElementById("progress-bar"),
  statusList: Array.from(document.querySelectorAll("#status-list li")),
  startAnalysis: document.getElementById("start-analysis"),
  runLogList: document.getElementById("run-log-list"),
  analyzeOpenReport: document.getElementById("analyze-open-report"),
};

CATEGORY_CONFIG.forEach((category) => {
  category.scoreNode = document.getElementById(category.scoreId);
  category.meterNode = document.getElementById(category.meterId);
  category.summaryNode = document.getElementById(category.summaryId);
  category.itemsNode = document.getElementById(category.itemsId);
});

const state = {
  reports: [],
  filteredReports: [],
  currentReportId: "",
  toastTimer: null,
  isRunning: false,
  lastStatusSignature: "",
  csvHeaders: [],
  csvRows: [],
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function clampPercent(value) {
  return Math.round(clamp(Number(value) || 0, 0, 100));
}

function clampRatio(value) {
  return clamp(Number(value) || 0, 0, 1);
}

function averageNumbers(values, fallback = 0) {
  const numbers = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!numbers.length) return fallback;
  return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
}

function averageScoreGroup(group) {
  if (!group || typeof group !== "object") return 0;
  return averageNumbers(Object.values(group).filter((value) => typeof value === "number" && Number.isFinite(value)), 0);
}

function fivePointToPercent(score) {
  if (typeof score !== "number" || !Number.isFinite(score) || score <= 0) return 0;
  return clampPercent((clamp(score, 1, 5) / 5) * 100);
}

function sanitizeText(value, fallback = "-") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function hasBrokenText(value) {
  return typeof value === "string" && value.includes("\uFFFD");
}

function humanizeIdentifier(value) {
  const normalized = String(value || "")
    .trim()
    .replace(/^\d{4}-\d{2}-\d{2}_/, "")
    .replace(/[_-]+/g, " ")
    .replace(/\s+/g, " ");
  if (!normalized) return "-";
  return /^[\x00-\x7F ]+$/.test(normalized)
    ? normalized.replace(/\b[a-z]/g, (char) => char.toUpperCase())
    : normalized;
}

function sanitizeDisplayText(value, fallback = "-") {
  const sanitized = sanitizeText(value, "");
  if (!sanitized || hasBrokenText(sanitized)) return fallback;
  return sanitized;
}

function summarizeSessionField(sessions, fieldName) {
  const values = Array.isArray(sessions) ? sessions.map((session) => sanitizeText(session?.[fieldName], "")).filter(Boolean) : [];
  if (!values.length) return "-";
  if (values.length === 1) return values[0];
  return `${values[0]} 외 ${values.length - 1}건`;
}

function summarizeSessionDisplayField(sessions, fieldName) {
  const values = Array.isArray(sessions)
    ? sessions.map((session) => sanitizeDisplayText(session?.[fieldName], "")).filter(Boolean)
    : [];
  if (!values.length) return "-";
  if (values.length === 1) return values[0];
  return `${values[0]} 외 ${values.length - 1}건`;
}

function formatScore(score) {
  return `${numberFormatter.format(clampPercent(score))}점`;
}

function extractScoreValue(text) {
  const parsed = Number.parseInt(String(text || ""), 10);
  return Number.isFinite(parsed) ? clampPercent(parsed) : 0;
}

function parseReportDate(value) {
  if (typeof value !== "string" || !value.trim()) return NaN;
  return new Date(`${value}T00:00:00`).getTime();
}

function formatDateLabel(value) {
  if (typeof value !== "string" || !value.trim()) return "-";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return sanitizeText(value);
  const parts = Object.fromEntries(shortDateFormatter.formatToParts(date).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return parts.month && parts.day ? `${parts.month}.${parts.day}` : shortDateFormatter.format(date);
}

function formatDateLong(value) {
  if (typeof value !== "string" || !value.trim()) return "-";
  const date = new Date(`${value}T00:00:00`);
  return Number.isNaN(date.getTime())
    ? value
    : longDateFormatter.format(date);
}

function formatDateCompact(value) {
  if (typeof value !== "string" || !value.trim()) return "-";
  const date = new Date(`${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  const parts = Object.fromEntries(compactDateFormatter.formatToParts(date).filter((part) => part.type !== "literal").map((part) => [part.type, part.value]));
  return parts.year && parts.month && parts.day
    ? `${parts.year}.${parts.month}.${parts.day}`
    : compactDateFormatter.format(date);
}

function formatDelta(delta, emptyText = "비교 기준 없음") {
  if (typeof delta !== "number" || !Number.isFinite(delta)) return emptyText;
  if (delta > 0) return `이전 대비 +${Math.round(delta)}p`;
  if (delta < 0) return `이전 대비 ${Math.round(delta)}p`;
  return "이전 대비 0p";
}

function setMetricFigure(node, value, unit = "") {
  if (!node) return;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    node.textContent = "-";
    return;
  }
  const rounded = Math.round(value);
  const prefix = rounded > 0 && unit === "p" ? "+" : "";
  node.innerHTML = `<span class="metric-number">${prefix}${numberFormatter.format(rounded)}</span>${unit ? `<span class="metric-unit">${unit}</span>` : ""}`;
}

function getScoreLevel(score) {
  if (score >= 90) return "우수";
  if (score >= 80) return "양호";
  if (score >= 70) return "보통";
  return "개선 필요";
}

function clearChildren(node) {
  while (node && node.firstChild) node.removeChild(node.firstChild);
}

function showToast(message) {
  if (!dom.toast) return;
  dom.toast.textContent = message;
  dom.toast.classList.add("is-visible");
  if (state.toastTimer) window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => dom.toast.classList.remove("is-visible"), 2400);
}

function getSearchParams() {
  return new URLSearchParams(window.location.search);
}

function syncFilterStateToUrl() {
  const url = new URL(window.location.href);
  const params = url.searchParams;
  const nextState = {
    instructor: dom.filterInstructor.value,
    course: dom.filterCourse.value,
    period: dom.filterPeriod.value,
  };
  FILTER_PARAM_KEYS.forEach((key) => {
    const value = nextState[key];
    if (!value || value === "all") params.delete(key);
    else params.set(key, value);
  });
  const nextUrl = `${url.pathname}${params.toString() ? `?${params.toString()}` : ""}${url.hash}`;
  window.history.replaceState({}, "", nextUrl);
}

function applyFilterStateFromUrl() {
  const params = getSearchParams();
  const nextValues = {
    instructor: params.get("instructor") || "all",
    course: params.get("course") || "all",
    period: params.get("period") || "all",
  };
  dom.filterInstructor.value = Array.from(dom.filterInstructor.options).some((option) => option.value === nextValues.instructor)
    ? nextValues.instructor
    : "all";
  populateCourseOptions();
  dom.filterCourse.value = Array.from(dom.filterCourse.options).some((option) => option.value === nextValues.course)
    ? nextValues.course
    : "all";
  dom.filterPeriod.value = Array.from(dom.filterPeriod.options).some((option) => option.value === nextValues.period)
    ? nextValues.period
    : "all";
}

function setFieldError(name, message) {
  const errorNode = document.getElementById(`error-${name}`);
  if (errorNode) errorNode.textContent = message;
  if (name === "script_file") {
    dom.uploadZone.classList.toggle("is-invalid", Boolean(message));
    return;
  }
  const field = dom.analysisForm.querySelector(`[name="${name}"]`);
  if (field) {
    field.setAttribute("aria-invalid", message ? "true" : "false");
  }
}

function clearFieldErrors() {
  dom.analysisForm.querySelectorAll(".field-error").forEach((node) => {
    node.textContent = "";
  });
  dom.analysisForm.querySelectorAll("[aria-invalid='true']").forEach((node) => {
    node.setAttribute("aria-invalid", "false");
  });
  dom.uploadZone.classList.remove("is-invalid");
}

function validateAnalysisForm() {
  clearFieldErrors();
  let firstInvalid = null;

  if (!dom.scriptFile.files?.length) {
    setFieldError("script_file", REQUIRED_MESSAGES.script_file);
    firstInvalid = dom.uploadZone;
  }

  dom.analysisForm.querySelectorAll("[name][required]").forEach((field) => {
    if (field.name === "script_file") return;
    const value = typeof field.value === "string" ? field.value.trim() : field.value;
    if (value) return;
    setFieldError(field.name, REQUIRED_MESSAGES[field.name] || "필수 입력값을 확인해 주세요.");
    if (!firstInvalid) firstInvalid = field;
  });

  if (firstInvalid) {
    firstInvalid.focus();
    return false;
  }

  return true;
}

function setDownloadLink(node, url, filename) {
  if (!node) return;
  if (typeof url === "string" && url.trim()) {
    node.href = new URL(url, window.location.href).toString();
    node.setAttribute("aria-disabled", "false");
    node.setAttribute("download", filename);
  } else {
    node.href = "#";
    node.setAttribute("aria-disabled", "true");
    node.removeAttribute("download");
  }
}

function calculateRepeatExpressionScore(languageQuality = {}) {
  const repeatRatio = Number(languageQuality.repeat_ratio);
  if (!Number.isFinite(repeatRatio)) return null;
  return clampPercent((1 - clampRatio(repeatRatio / 0.35)) * 100);
}

function calculateCompletenessScore(languageQuality = {}) {
  const incompleteRatio = Number(languageQuality.incomplete_sentence_ratio);
  if (!Number.isFinite(incompleteRatio)) return null;
  return clampPercent((1 - clampRatio(incompleteRatio)) * 100);
}

function calculateLanguageConsistencyScore(languageQuality = {}) {
  const styleRatio = languageQuality.speech_style_ratio;
  if (!styleRatio || typeof styleRatio !== "object") return null;
  const values = Object.values(styleRatio).filter((value) => typeof value === "number" && Number.isFinite(value));
  return values.length ? clampPercent(Math.max(...values) * 100) : null;
}

function calculateSpeechRateScore(conceptMetrics = {}) {
  const speechRate = Number(conceptMetrics.speech_rate_wpm);
  if (!Number.isFinite(speechRate) || speechRate <= 0) return null;
  if (speechRate >= 120 && speechRate <= 170) return 100;
  if (speechRate < 120) return clampPercent(100 - (120 - speechRate) * 2);
  return clampPercent(100 - (speechRate - 170) * 2);
}

function calculateQuestionAdequacyScore(interactionMetrics = {}) {
  const questionCount = Number(interactionMetrics.understanding_question_count);
  if (!Number.isFinite(questionCount) || questionCount < 0) return null;
  return clampPercent(Math.min(questionCount / 8, 1) * 100);
}

function deriveLanguageScore(languageQuality = {}, conceptMetrics = {}) {
  const repeatScore = 1 - clampRatio((Number(languageQuality.repeat_ratio) || 0) / 0.35);
  const incompleteScore = 1 - clampRatio((Number(languageQuality.incomplete_sentence_ratio) || 0) / 0.6);
  const speechScore = clampRatio((Number(conceptMetrics.score) || 3) / 5);
  return clampPercent((repeatScore * 0.45 + incompleteScore * 0.35 + speechScore * 0.2) * 100);
}

function buildScoreEntry(label, score) {
  return { label, value: typeof score === "number" && Number.isFinite(score) ? formatScore(score) : "-" };
}

function buildDetailBreakdown(group = {}) {
  return Object.entries(group)
    .filter(([, value]) => typeof value === "number" && Number.isFinite(value))
    .map(([key, value]) => buildScoreEntry(EVIDENCE_ITEM_LABELS[key] || key, fivePointToPercent(value)));
}

function averageEntryScores(entries) {
  return averageNumbers(entries.map((entry) => extractScoreValue(entry.value)), 0);
}

function describeCategorySummary(type, score) {
  if (type === "language") return score >= 80 ? "언어 표현이 안정적입니다." : score >= 60 ? "표현 품질 보강이 필요합니다." : "언어 표현 개선이 필요합니다.";
  if (type === "structure") return score >= 80 ? "도입과 구조가 안정적입니다." : score >= 60 ? "강의 구조 보강이 필요합니다." : "구조 개선이 필요합니다.";
  if (type === "concept") return score >= 80 ? "개념 설명이 명확합니다." : score >= 60 ? "개념 설명 보강이 필요합니다." : "개념 설명 개선이 필요합니다.";
  if (type === "practice") return score >= 80 ? "예시와 실습 연결이 자연스럽습니다." : score >= 60 ? "실습 연계 보강이 필요합니다." : "실습 연계 개선이 필요합니다.";
  return score >= 80 ? "수강생 상호작용이 원활합니다." : score >= 60 ? "상호작용 보강이 필요합니다." : "상호작용 개선이 필요합니다.";
}

function buildDetailCategories(analysis = {}) {
  const language = [
    buildScoreEntry("반복 표현 관리", calculateRepeatExpressionScore(analysis.language_quality)),
    buildScoreEntry("발화 완결성", calculateCompletenessScore(analysis.language_quality)),
    buildScoreEntry("언어 일관성", calculateLanguageConsistencyScore(analysis.language_quality)),
  ];
  const structure = buildDetailBreakdown(analysis.summary_scores?.lecture_structure);
  const concept = [...buildDetailBreakdown(analysis.summary_scores?.concept_clarity), buildScoreEntry("발화 속도 적절성", calculateSpeechRateScore(analysis.concept_clarity_metrics))];
  const practice = buildDetailBreakdown(analysis.summary_scores?.practice_linkage);
  const interaction = [buildScoreEntry("이해 확인 질문", calculateQuestionAdequacyScore(analysis.interaction_metrics)), ...buildDetailBreakdown(analysis.summary_scores?.interaction)];
  return {
    language: { summary: describeCategorySummary("language", averageEntryScores(language)), details: language },
    structure: { summary: describeCategorySummary("structure", averageEntryScores(structure)), details: structure },
    concept: { summary: describeCategorySummary("concept", averageEntryScores(concept)), details: concept },
    practice: { summary: describeCategorySummary("practice", averageEntryScores(practice)), details: practice },
    interaction: { summary: describeCategorySummary("interaction", averageEntryScores(interaction)), details: interaction },
  };
}

function normalizeEvidenceEntries(entries) {
  if (!Array.isArray(entries)) return [];
  return entries.map((entry, index) => {
    if (typeof entry === "string" && entry.trim()) {
      return { item: `evidence_${index + 1}`, quote: entry.trim(), reason: "강의 분석 과정에서 추출된 근거입니다." };
    }
    if (!entry || typeof entry !== "object" || !sanitizeText(entry.quote, "")) return null;
    return {
      item: sanitizeText(entry.item, `evidence_${index + 1}`),
      quote: sanitizeText(entry.quote, ""),
      reason: sanitizeText(entry.reason || entry.explanation, "해당 발언이 분석 결과를 뒷받침합니다."),
    };
  }).filter(Boolean);
}

function prettifyEvidenceItem(key, index) {
  if (EVIDENCE_ITEM_LABELS[key]) return EVIDENCE_ITEM_LABELS[key];
  return typeof key === "string" && key.trim() ? key.replace(/_/g, " ") : `근거 ${index + 1}`;
}

function normalizeServerAnalysis(payload) {
  const integrated = payload?.analysis && typeof payload.analysis === "object" ? payload.analysis : {};
  const metadata = integrated.metadata && typeof integrated.metadata === "object" ? integrated.metadata : {};
  const analysis = integrated.analysis && typeof integrated.analysis === "object" ? integrated.analysis : {};
  const sessions = Array.isArray(metadata.sessions) ? metadata.sessions : [];
  const primarySession = sessions[0] || {};
  const lectureId = sanitizeText(integrated.lecture_id || payload?.lecture_id, "unknown_lecture");
  const courseId = sanitizeDisplayText(metadata.course_id, "");
  const fallbackLectureName = humanizeIdentifier(courseId || lectureId);
  const courseName = sanitizeDisplayText(metadata.course_name, fallbackLectureName);
  const instructor = sanitizeDisplayText(metadata.instructor, "-");
  const subInstructor = sanitizeDisplayText(metadata.sub_instructor, "-");
  const time = sanitizeDisplayText(primarySession.time, summarizeSessionDisplayField(sessions, "time"));
  const subject = sanitizeDisplayText(primarySession.subject, summarizeSessionDisplayField(sessions, "subject"));
  const content = sanitizeDisplayText(primarySession.content, summarizeSessionDisplayField(sessions, "content"));
  const numericScores = {
    language: deriveLanguageScore(analysis.language_quality, analysis.concept_clarity_metrics),
    structure: fivePointToPercent(averageScoreGroup(analysis.summary_scores?.lecture_structure)),
    concept: fivePointToPercent(averageScoreGroup(analysis.summary_scores?.concept_clarity)),
    practice: fivePointToPercent(averageScoreGroup(analysis.summary_scores?.practice_linkage)),
    interaction: fivePointToPercent(averageScoreGroup(analysis.summary_scores?.interaction)),
  };
  const overallScore = clampPercent(averageNumbers(Object.values(numericScores), 0));
  return {
    lecture_id: lectureId,
    course_id: courseId,
    course_name: courseName,
    date: sanitizeText(metadata.date),
    time,
    subject,
    content,
    instructor,
    sub_instructor: subInstructor,
    overall: { score: overallScore, level: getScoreLevel(overallScore) },
    scores: Object.fromEntries(Object.entries(numericScores).map(([key, value]) => [key, formatScore(value)])),
    numericScores,
    strengths: Array.isArray(analysis.overall_strengths) ? analysis.overall_strengths.filter((value) => typeof value === "string" && value.trim()) : [],
    weaknesses: Array.isArray(analysis.overall_issues) ? analysis.overall_issues.filter((value) => typeof value === "string" && value.trim()) : [],
    evidence: normalizeEvidenceEntries(analysis.overall_evidences),
    detailCategories: buildDetailCategories(analysis),
    downloads: payload?.downloads || {},
    updatedAt: Number(payload?.updated_at) || Date.now() / 1000,
  };
}

function sortReports(items) {
  return [...items].sort((a, b) => {
    const dateDiff = parseReportDate(b.date) - parseReportDate(a.date);
    return dateDiff !== 0 ? dateDiff : (b.updatedAt || 0) - (a.updatedAt || 0);
  });
}

function buildOptionList(items, getValue, getLabel) {
  const seen = new Map();
  items.forEach((item) => {
    const value = getValue(item);
    if (!value || seen.has(value)) return;
    seen.set(value, getLabel(item));
  });
  return Array.from(seen.entries())
    .map(([value, label]) => ({ value, label }))
    .sort((a, b) => a.label.localeCompare(b.label, "ko"));
}

function syncSelectOptions(select, baseLabel, options) {
  const current = select.value;
  clearChildren(select);
  const defaultOption = document.createElement("option");
  defaultOption.value = "all";
  defaultOption.textContent = baseLabel;
  select.appendChild(defaultOption);
  options.forEach((option) => {
    const node = document.createElement("option");
    node.value = option.value;
    node.textContent = option.label;
    select.appendChild(node);
  });
  select.value = options.some((option) => option.value === current) ? current : "all";
}

function reportsForCourseOptions() {
  const instructor = dom.filterInstructor.value;
  if (!instructor || instructor === "all") return state.reports;
  return state.reports.filter((item) => item.instructor === instructor);
}

function populateCourseOptions() {
  syncSelectOptions(
    dom.filterCourse,
    "전체 과정",
    buildOptionList(reportsForCourseOptions(), (item) => item.course_id || item.course_name, (item) => item.course_name || item.course_id)
  );
}

function populateFilterOptions() {
  syncSelectOptions(dom.filterInstructor, "전체 강사", buildOptionList(state.reports, (item) => item.instructor, (item) => item.instructor));
  populateCourseOptions();
}

function applyFilters() {
  const instructor = dom.filterInstructor.value;
  const course = dom.filterCourse.value;
  const period = dom.filterPeriod.value;
  const now = Date.now();
  const filtered = state.reports.filter((report) => {
    if (instructor !== "all" && report.instructor !== instructor) return false;
    if (course !== "all" && (report.course_id || report.course_name) !== course) return false;
    if (period !== "all") {
      const reportTime = parseReportDate(report.date);
      if (Number.isNaN(reportTime)) return false;
      const dayDiff = (now - reportTime) / (1000 * 60 * 60 * 24);
      if (dayDiff > Number(period)) return false;
    }
    return true;
  });
  state.filteredReports = sortReports(filtered);
  return state.filteredReports;
}

function renderCategoryBars(items) {
  clearChildren(dom.categoryList);
  items.forEach((item) => {
    const wrapper = document.createElement("div");
    const head = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("span");
    const track = document.createElement("div");
    const fill = document.createElement("span");
    wrapper.className = "category-bar";
    head.className = "category-bar__head";
    track.className = "category-bar__track";
    label.textContent = item.label;
    value.textContent = formatScore(item.value);
    fill.style.width = `${clampPercent(item.value)}%`;
    head.append(label, value);
    track.appendChild(fill);
    wrapper.append(head, track);
    dom.categoryList.appendChild(wrapper);
  });
}

function renderTrendChart(items) {
  if (!items.length) {
    dom.trendChart.innerHTML = '<text x="50%" y="50%" text-anchor="middle" fill="#715d4c" font-size="20">표시할 리포트가 없습니다.</text>';
    dom.trendCaption.textContent = "필터에 맞는 리포트가 없습니다.";
    return;
  }

  const ordered = [...items].reverse();
  const width = 880;
  const height = 280;
  const left = 56;
  const right = 24;
  const top = 28;
  const bottom = 42;
  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;
  const points = ordered.map((item, index) => {
    const x = left + (chartWidth * index) / Math.max(ordered.length - 1, 1);
    const y = top + chartHeight - (clampPercent(item.overall.score) / 100) * chartHeight;
    return { x, y, score: clampPercent(item.overall.score), label: formatDateLabel(item.date) };
  });
  const polyline = points.map((point) => `${point.x},${point.y}`).join(" ");
  const grid = [0, 25, 50, 75, 100]
    .map((score) => {
      const y = top + chartHeight - (score / 100) * chartHeight;
      return `<line x1="${left}" y1="${y}" x2="${width - right}" y2="${y}" stroke="rgba(113,93,76,0.15)" stroke-dasharray="4 6" />
        <text x="${left - 12}" y="${y + 5}" text-anchor="end" fill="#715d4c" font-size="12">${score}</text>`;
    })
    .join("");
  const markers = points
    .map(
      (point) => `<circle cx="${point.x}" cy="${point.y}" r="5.5" fill="#d86c1f" />
        <text x="${point.x}" y="${point.y - 12}" text-anchor="middle" fill="#261c15" font-size="12" font-weight="700">${point.score}</text>
        <text x="${point.x}" y="${height - 12}" text-anchor="middle" fill="#715d4c" font-size="12">${point.label}</text>`
    )
    .join("");
  dom.trendChart.innerHTML = `${grid}<polyline points="${polyline}" fill="none" stroke="#d86c1f" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" />${markers}`;
  dom.trendCaption.textContent = `최근 ${items.length}건 점수 추이`;
}

function findWeakestCategory(report) {
  return CATEGORY_CONFIG.reduce((weakest, category) => {
    const value = report.numericScores[category.key];
    if (!weakest || value < weakest.value) return { label: category.label, value };
    return weakest;
  }, null);
}

function renderIssueList(items) {
  clearChildren(dom.issueList);
  const counts = new Map();
  items.forEach((report) => report.weaknesses.forEach((issue) => counts.set(issue, (counts.get(issue) || 0) + 1)));
  const topIssues = Array.from(counts.entries()).sort((a, b) => b[1] - a[1]).slice(0, 5);
  if (!topIssues.length) {
    const li = document.createElement("li");
    li.textContent = "집계할 개선 필요 사항이 없습니다.";
    dom.issueList.appendChild(li);
    return;
  }
  topIssues.forEach(([issue, count]) => {
    const li = document.createElement("li");
    li.textContent = `${issue} · ${count}회`;
    dom.issueList.appendChild(li);
  });
}

function createActionLink(label, href, options = {}) {
  const link = document.createElement("a");
  link.className = "table-action";
  link.textContent = label;
  link.href = href;
  if (options.target) link.target = options.target;
  if (options.rel) link.rel = options.rel;
  return link;
}

function renderReportTable(items) {
  clearChildren(dom.reportTableBody);
  if (!items.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.textContent = "표시할 리포트가 없습니다.";
    row.appendChild(cell);
    dom.reportTableBody.appendChild(row);
    return;
  }

  items.forEach((report) => {
    const row = document.createElement("tr");
    const weakest = findWeakestCategory(report);
    const dateCell = document.createElement("td");
    const courseCell = document.createElement("td");
    const instructorCell = document.createElement("td");
    const scoreCell = document.createElement("td");
    const categoryCell = document.createElement("td");
    dateCell.className = "report-cell--date";
    courseCell.className = "report-cell--course";
    instructorCell.className = "report-cell--instructor";
    scoreCell.className = "report-cell--score";
    categoryCell.className = "report-cell--category";
    dateCell.textContent = formatDateCompact(report.date);
    const courseLink = document.createElement("a");
    courseLink.className = "table-link";
    courseLink.href = `#report/${encodeURIComponent(report.lecture_id)}`;
    courseLink.textContent = report.course_name;
    courseLink.title = report.course_name;
    courseCell.appendChild(courseLink);
    instructorCell.textContent = report.instructor;
    scoreCell.textContent = formatScore(report.overall.score);
    categoryCell.textContent = weakest ? weakest.label : "-";
    row.append(dateCell, courseCell, instructorCell, scoreCell, categoryCell);

    const actionCell = document.createElement("td");
    actionCell.className = "report-cell--actions";
    const actionWrap = document.createElement("div");
    actionWrap.className = "table-actions";
    const pdfUrl = report.downloads?.pdf_url || report.downloads?.pdfUrl;
    actionWrap.append(
      createActionLink("상세", `#report/${encodeURIComponent(report.lecture_id)}`),
      pdfUrl
        ? createActionLink("PDF", new URL(pdfUrl, window.location.href).toString(), {
            target: "_blank",
            rel: "noopener",
          })
        : createActionLink("PDF", "#")
    );
    if (!pdfUrl) {
      actionWrap.lastChild.setAttribute("aria-disabled", "true");
    }
    actionCell.appendChild(actionWrap);
    row.appendChild(actionCell);
    dom.reportTableBody.appendChild(row);
  });
}

function buildDashboardStats(items) {
  const latest = items.slice(0, 3);
  const previous = items.slice(3, 6);
  return {
    total: items.length,
    average: clampPercent(averageNumbers(items.map((item) => item.overall.score), 0)),
    risk: items.filter((item) => item.overall.score < RISK_SCORE).length,
    delta: latest.length && previous.length ? averageNumbers(latest.map((item) => item.overall.score), 0) - averageNumbers(previous.map((item) => item.overall.score), 0) : null,
    categories: CATEGORY_CONFIG.map((category) => ({
      key: category.key,
      label: category.label,
      value: clampPercent(averageNumbers(items.map((item) => item.numericScores[category.key]), 0)),
    })),
  };
}

function renderDashboard() {
  const items = applyFilters();
  const stats = buildDashboardStats(items);
  setMetricFigure(dom.dashboardTotal, stats.total, "건");
  setMetricFigure(dom.dashboardAverage, stats.average, "점");
  setMetricFigure(dom.dashboardRisk, stats.risk, "건");
  setMetricFigure(dom.dashboardDelta, stats.delta, "p");
  renderCategoryBars(stats.categories);
  renderTrendChart(items.slice(0, 8));
  renderReportTable(items);
  renderIssueList(items);
}

function renderSimpleList(node, values, fallbackText) {
  clearChildren(node);
  const items = values.length ? values : [fallbackText];
  items.forEach((value) => {
    const li = document.createElement("li");
    li.textContent = value;
    node.appendChild(li);
  });
}

function renderEvidence(node, entries) {
  clearChildren(node);
  if (!entries.length) {
    const li = document.createElement("li");
    li.textContent = "표시할 분석 근거가 없습니다.";
    node.appendChild(li);
    return;
  }
  entries.forEach((entry, index) => {
    const li = document.createElement("li");
    const wrap = document.createElement("div");
    const item = document.createElement("p");
    const quote = document.createElement("p");
    const reason = document.createElement("p");
    wrap.className = "evidence-item";
    item.className = "evidence-item__item";
    quote.className = "evidence-item__quote";
    reason.className = "evidence-item__reason";
    item.textContent = prettifyEvidenceItem(entry.item, index);
    quote.textContent = `“${entry.quote}”`;
    reason.textContent = entry.reason;
    wrap.append(item, quote, reason);
    li.appendChild(wrap);
    node.appendChild(li);
  });
}

function renderDetailBreakdown(node, entries) {
  clearChildren(node);
  if (!entries.length) {
    const row = document.createElement("div");
    row.className = "detail-subscore-row";
    row.innerHTML = "<span>세부 점수</span><span>-</span>";
    node.appendChild(row);
    return;
  }
  entries.forEach((entry) => {
    const row = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("span");
    row.className = "detail-subscore-row";
    label.textContent = entry.label;
    value.textContent = entry.value;
    row.append(label, value);
    node.appendChild(row);
  });
}

function findReportById(lectureId) {
  return state.reports.find((report) => report.lecture_id === lectureId) || null;
}

function findPreviousReport(report) {
  return sortReports(
    state.reports.filter(
      (item) =>
        item.lecture_id !== report.lecture_id &&
        item.instructor === report.instructor &&
        item.course_id === report.course_id &&
        parseReportDate(item.date) < parseReportDate(report.date)
    )
  )[0] || null;
}

function setScoreCard(category, report) {
  category.scoreNode.textContent = report.scores[category.key];
  category.meterNode.style.width = `${report.numericScores[category.key]}%`;
  category.summaryNode.textContent = report.detailCategories[category.key].summary;
  renderDetailBreakdown(category.itemsNode, report.detailCategories[category.key].details);
}

function renderEmptyDetail() {
  dom.detailTitle.textContent = "리포트 상세";
  dom.detailSubtitle.textContent = "대시보드에서 리포트를 선택하면 상세 결과를 확인할 수 있습니다.";
  dom.detailMetaCourse.textContent = "-";
  dom.detailMetaInstructor.textContent = "-";
  dom.detailMetaTime.textContent = "-";
  dom.detailMetaTopic.textContent = "-";
  dom.detailOverallScore.textContent = "-";
  dom.detailOverallLevel.textContent = "선택 전";
  dom.detailOverallDelta.textContent = "비교 기준 없음";
  renderSimpleList(dom.detailStrengthList, [], "표시할 강점이 없습니다.");
  renderSimpleList(dom.detailWeaknessList, [], "표시할 개선 필요 사항이 없습니다.");
  renderEvidence(dom.detailEvidenceList, []);
  CATEGORY_CONFIG.forEach((category) => {
    category.scoreNode.textContent = "-";
    category.meterNode.style.width = "0%";
    category.summaryNode.textContent = "-";
  renderDetailBreakdown(category.itemsNode, []);
  });
  setDownloadLink(dom.downloadPdf, "", "report.pdf");
  setDownloadLink(dom.downloadJson, "", "integrated.json");
  dom.detailCompareReport.href = "#";
  dom.detailCompareReport.setAttribute("aria-disabled", "true");
}

function renderDetailReport(report) {
  if (!report) {
    renderEmptyDetail();
    return;
  }
  state.currentReportId = report.lecture_id;
  const previousReport = findPreviousReport(report);
  const delta = previousReport ? report.overall.score - previousReport.overall.score : null;
  dom.detailTitle.textContent = report.course_name;
  dom.detailSubtitle.textContent = `${formatDateLong(report.date)} · ${report.instructor} 강사 리포트`;
  dom.detailMetaCourse.textContent = report.course_name;
  dom.detailMetaInstructor.textContent = `${report.instructor}${report.sub_instructor && report.sub_instructor !== "-" ? ` / 보조 ${report.sub_instructor}` : ""}`;
  dom.detailMetaTime.textContent = `${formatDateLong(report.date)} · ${report.time}`;
  dom.detailMetaTopic.textContent = `${report.subject} / ${report.content}`;
  dom.detailOverallScore.textContent = formatScore(report.overall.score);
  dom.detailOverallLevel.textContent = report.overall.level;
  dom.detailOverallDelta.textContent = formatDelta(delta);
  renderSimpleList(dom.detailStrengthList, report.strengths, "표시할 강점이 없습니다.");
  renderSimpleList(dom.detailWeaknessList, report.weaknesses, "표시할 개선 필요 사항이 없습니다.");
  renderEvidence(dom.detailEvidenceList, report.evidence);
  CATEGORY_CONFIG.forEach((category) => setScoreCard(category, report));
  setDownloadLink(dom.downloadPdf, report.downloads?.pdf_url || report.downloads?.pdfUrl, `report_${report.lecture_id}.pdf`);
  setDownloadLink(dom.downloadJson, report.downloads?.json_url || report.downloads?.jsonUrl, `integrated_${report.lecture_id}.json`);
  dom.detailCompareReport.href = previousReport ? `#report/${encodeURIComponent(previousReport.lecture_id)}` : "#";
  dom.detailCompareReport.setAttribute("aria-disabled", previousReport ? "false" : "true");
}

function resetRunState() {
  dom.analysisPill.className = "analysis-pill is-idle";
  dom.analysisPill.textContent = "대기";
  dom.statusLive.textContent = "대기 중";
  dom.progressBar.style.width = "0%";
  dom.statusList.forEach((item) => item.classList.remove("is-active"));
  clearChildren(dom.runLogList);
  const li = document.createElement("li");
  li.textContent = "로그가 아직 없습니다.";
  dom.runLogList.appendChild(li);
  dom.analyzeOpenReport.hidden = true;
  dom.analyzeOpenReport.href = "#";
  dom.analyzeOpenReport.removeAttribute("data-lecture-id");
}

function appendRunLog(message) {
  if (!message) return;
  if (dom.runLogList.children.length === 1 && dom.runLogList.firstChild.textContent === "로그가 아직 없습니다.") {
    clearChildren(dom.runLogList);
  }
  const li = document.createElement("li");
  const timestamp = new Date().toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  li.textContent = `${timestamp} · ${message}`;
  dom.runLogList.appendChild(li);
}

function setRunState(stateName, message) {
  dom.analysisPill.className = "analysis-pill";
  if (stateName === "running") {
    dom.analysisPill.classList.add("is-running");
    dom.analysisPill.textContent = "진행 중";
  } else if (stateName === "done") {
    dom.analysisPill.classList.add("is-done");
    dom.analysisPill.textContent = "완료";
  } else if (stateName === "error") {
    dom.analysisPill.classList.add("is-error");
    dom.analysisPill.textContent = "오류";
  } else {
    dom.analysisPill.classList.add("is-idle");
    dom.analysisPill.textContent = "대기";
  }
  if (message) dom.statusLive.textContent = message;
}

function getStatusStepIndex(status) {
  const stepIndex = Number(status?.step_index);
  if (Number.isInteger(stepIndex) && stepIndex >= 0) return Math.min(stepIndex, RUN_STEPS.length - 1);
  return RUN_STEPS.indexOf(status?.stage);
}

function setActiveStep(index) {
  dom.statusList.forEach((item, itemIndex) => item.classList.toggle("is-active", itemIndex === index));
  dom.progressBar.style.width = `${((index + 1) / RUN_STEPS.length) * 100}%`;
}

function applyAnalysisStatus(status) {
  const index = getStatusStepIndex(status);
  if (index >= 0) setActiveStep(index);
  const message = sanitizeText(status?.message, "분석 중");
  setRunState(status?.state === "error" ? "error" : status?.state === "done" ? "done" : "running", message);
  const signature = `${status?.state || ""}:${status?.stage || ""}:${message}`;
  if (signature !== state.lastStatusSignature) {
    appendRunLog(message);
    state.lastStatusSignature = signature;
  }
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};
  try {
    return JSON.parse(text);
  } catch {
    return { ok: response.ok, error: text };
  }
}

async function requestReports() {
  const response = await fetch("/api/reports", { cache: "no-store" });
  const payload = await readJsonResponse(response);
  if (!response.ok || payload?.ok === false) {
    throw new Error(sanitizeText(payload?.error, `리포트 목록을 불러오지 못했습니다. (${response.status})`));
  }
  return Array.isArray(payload?.reports) ? payload.reports : [];
}

async function requestAnalysis() {
  const response = await fetch("/api/analyze", { method: "POST", body: new FormData(dom.analysisForm) });
  const payload = await readJsonResponse(response);
  if (!response.ok || payload?.ok === false) {
    throw new Error(sanitizeText(payload?.error, `분석 요청에 실패했습니다. (${response.status})`));
  }
  return payload;
}

async function requestAnalysisStatus(jobId) {
  const response = await fetch(`/api/analyze/status?job_id=${encodeURIComponent(jobId)}`, { cache: "no-store" });
  const payload = await readJsonResponse(response);
  if (!response.ok || payload?.ok === false) {
    throw new Error(sanitizeText(payload?.error, `분석 상태 조회에 실패했습니다. (${response.status})`));
  }
  return payload;
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

async function waitForAnalysisResult(jobId) {
  while (true) {
    const status = await requestAnalysisStatus(jobId);
    applyAnalysisStatus(status);
    if (status?.state === "done") return status.result || {};
    if (status?.state === "error") {
      throw new Error(sanitizeText(status?.error || status?.message, "분석 중 오류가 발생했습니다."));
    }
    await sleep(JOB_POLL_INTERVAL_MS);
  }
}

function upsertReport(report) {
  state.reports = sortReports([report, ...state.reports.filter((item) => item.lecture_id !== report.lecture_id)]);
}

async function refreshReports(showNotice = false) {
  const rawReports = await requestReports();
  state.reports = sortReports(rawReports.map((item) => normalizeServerAnalysis(item)));
  populateFilterOptions();
  applyFilterStateFromUrl();
  renderDashboard();
  if (showNotice) showToast("리포트 목록을 새로고침했습니다.");
}

async function startAnalysis() {
  if (state.isRunning) return;
  if (!validateAnalysisForm()) {
    showToast("입력 오류를 확인해 주세요.");
    return;
  }

  state.isRunning = true;
  state.lastStatusSignature = "";
  dom.startAnalysis.disabled = true;
  dom.startAnalysis.textContent = "분석 중…";
  resetRunState();
  setRunState("running", "분석 요청 중");
  appendRunLog("분석 요청을 시작했습니다.");

  try {
    const job = await requestAnalysis();
    applyAnalysisStatus(job);
    appendRunLog(`Job ID ${job.job_id} 접수`);
    const result = await waitForAnalysisResult(job.job_id);
    const report = normalizeServerAnalysis({ ...result, updated_at: Date.now() / 1000 });
    upsertReport(report);
    populateFilterOptions();
    renderDashboard();
    renderDetailReport(report);
    setRunState("done", "분석이 완료되었습니다.");
    appendRunLog("리포트 생성이 완료되었습니다.");
    dom.analyzeOpenReport.hidden = false;
    dom.analyzeOpenReport.dataset.lectureId = report.lecture_id;
    dom.analyzeOpenReport.href = `#report/${encodeURIComponent(report.lecture_id)}`;
    showToast("새 리포트를 생성했습니다.");
    navigateToReport(report.lecture_id);
  } catch (error) {
    const message = error instanceof Error ? error.message : "분석 중 오류가 발생했습니다.";
    setRunState("error", message);
    appendRunLog(message);
    showToast(message);
  } finally {
    state.isRunning = false;
    dom.startAnalysis.disabled = false;
    dom.startAnalysis.textContent = "분석 시작";
  }
}

function parseCsvLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (inQuotes) {
      if (char === '"' && line[index + 1] === '"') {
        current += '"';
        index += 1;
      } else if (char === '"') {
        inQuotes = false;
      } else {
        current += char;
      }
    } else if (char === '"') {
      inQuotes = true;
    } else if (char === ",") {
      result.push(current.trim());
      current = "";
    } else {
      current += char;
    }
  }
  result.push(current.trim());
  return result;
}

function applyRowToForm(headers, values) {
  let count = 0;
  headers.forEach((header, index) => {
    const key = header.trim().replace(/^\uFEFF/, "").toLowerCase();
    if (!CSV_FIELDS.includes(key)) return;
    const field = dom.analysisForm.querySelector(`[name="${key}"]`);
    if (!field) return;
    field.value = values[index] || "";
    count += 1;
  });
  return count;
}

function parseRoute() {
  const hash = window.location.hash.replace(/^#/, "").trim();
  if (!hash || hash === "dashboard") return { name: "dashboard" };
  if (hash === "analyze") return { name: "analyze" };
  if (hash === "detail") return { name: "detail", lectureId: state.currentReportId || state.reports[0]?.lecture_id || "" };
  if (hash.startsWith("report/")) return { name: "detail", lectureId: decodeURIComponent(hash.slice("report/".length)) };
  return { name: "dashboard" };
}

function showView(name) {
  dom.viewDashboard.hidden = name !== "dashboard";
  dom.viewDetail.hidden = name !== "detail";
  dom.viewAnalyze.hidden = name !== "analyze";
  dom.navLinks.forEach((button) => {
    const route = button.dataset.routeLink;
    const isActive = (name === "dashboard" && route === "dashboard") || (name === "detail" && route === "detail") || (name === "analyze" && route === "analyze");
    button.classList.toggle("is-active", isActive);
  });
}

function setHash(nextHash) {
  if (window.location.hash === nextHash) {
    handleRoute();
    return;
  }
  window.location.hash = nextHash;
}

function navigateToDashboard() {
  setHash("#dashboard");
}

function navigateToAnalyze() {
  setHash("#analyze");
}

function navigateToReport(lectureId) {
  if (!lectureId) {
    navigateToDashboard();
    return;
  }
  setHash(`#report/${encodeURIComponent(lectureId)}`);
}

function handleRouteLink(route) {
  if (route === "dashboard") navigateToDashboard();
  else if (route === "analyze") navigateToAnalyze();
  else if (route === "detail") navigateToReport(state.currentReportId || state.reports[0]?.lecture_id || "");
}

function handleRoute() {
  const route = parseRoute();
  if (route.name === "dashboard") {
    showView("dashboard");
    renderDashboard();
    return;
  }
  if (route.name === "analyze") {
    showView("analyze");
    return;
  }
  showView("detail");
  renderDetailReport(findReportById(route.lectureId));
}

function bindEvents() {
  dom.routeLinks.forEach((link) =>
    link.addEventListener("click", (event) => {
      event.preventDefault();
      handleRouteLink(link.dataset.routeLink);
    })
  );
  dom.headerRefresh.addEventListener("click", async () => {
    try {
      await refreshReports(true);
      handleRoute();
    } catch (error) {
      showToast(error instanceof Error ? error.message : "새로고침에 실패했습니다.");
    }
  });
  dom.filterInstructor.addEventListener("change", () => {
    populateCourseOptions();
    syncFilterStateToUrl();
    renderDashboard();
  });
  [dom.filterCourse, dom.filterPeriod].forEach((select) =>
    select.addEventListener("change", () => {
      syncFilterStateToUrl();
      renderDashboard();
    })
  );
  dom.detailBackDashboard.addEventListener("click", (event) => {
    event.preventDefault();
    navigateToDashboard();
  });
  dom.detailCompareReport.addEventListener("click", (event) => {
    event.preventDefault();
    const current = findReportById(state.currentReportId);
    const previous = current ? findPreviousReport(current) : null;
    if (!previous) {
      showToast("비교할 이전 리포트가 없습니다.");
      return;
    }
    navigateToReport(previous.lecture_id);
  });
  dom.downloadPdf.addEventListener("click", (event) => {
    if (dom.downloadPdf.getAttribute("aria-disabled") === "true") event.preventDefault();
  });
  dom.downloadJson.addEventListener("click", (event) => {
    if (dom.downloadJson.getAttribute("aria-disabled") === "true") event.preventDefault();
  });
  dom.analysisForm.addEventListener("submit", (event) => {
    event.preventDefault();
    startAnalysis();
  });
  dom.startAnalysis.addEventListener("click", startAnalysis);
  dom.scriptFile.addEventListener("change", () => {
    const file = dom.scriptFile.files?.[0];
    dom.uploadFileName.textContent = file ? file.name : "선택된 파일 없음";
  });
  dom.metadataCsv.addEventListener("change", () => {
    const file = dom.metadataCsv.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const text = String(event.target?.result || "");
      const lines = text.split(/\r?\n/).filter((line) => line.trim());
      if (lines.length < 2) {
        showToast("CSV에 헤더와 데이터 행이 필요합니다.");
        return;
      }
      state.csvHeaders = parseCsvLine(lines[0]);
      state.csvRows = lines.slice(1).map((line) => parseCsvLine(line));
      if (state.csvRows.length === 1) {
        const count = applyRowToForm(state.csvHeaders, state.csvRows[0]);
        dom.csvSessionPicker.hidden = true;
        showToast(count ? `CSV에서 ${count}개 필드를 불러왔습니다.` : "일치하는 CSV 헤더가 없습니다.");
        return;
      }
      clearChildren(dom.csvSessionSelect);
      const dateIndex = state.csvHeaders.findIndex((header) => header.trim().replace(/^\uFEFF/, "").toLowerCase() === "date");
      const timeIndex = state.csvHeaders.findIndex((header) => header.trim().toLowerCase() === "time");
      const subjectIndex = state.csvHeaders.findIndex((header) => header.trim().replace(/^\uFEFF/, "").toLowerCase() === "subject");
      state.csvRows.forEach((row, index) => {
        const option = document.createElement("option");
        option.value = String(index);
        option.textContent = `${row[dateIndex] || ""}  ${row[timeIndex] || ""}  |  ${row[subjectIndex] || ""}`;
        dom.csvSessionSelect.appendChild(option);
      });
      dom.csvSessionPicker.hidden = false;
      showToast(`${state.csvRows.length}개 세션을 불러왔습니다.`);
    };
    reader.readAsText(file);
  });
  dom.csvApply.addEventListener("click", () => {
    const row = state.csvRows[Number(dom.csvSessionSelect.value)];
    if (!row) return;
    const count = applyRowToForm(state.csvHeaders, row);
    showToast(count ? `세션 데이터 ${count}개 필드를 적용했습니다.` : "적용할 필드를 찾지 못했습니다.");
  });
  dom.analysisForm.querySelectorAll("[name]").forEach((field) => {
    const eventName = field.tagName === "SELECT" || field.type === "date" || field.type === "file" ? "change" : "input";
    field.addEventListener(eventName, () => {
      if (field.name === "script_file") {
        setFieldError("script_file", "");
      } else {
        setFieldError(field.name, "");
      }
    });
  });
  dom.analyzeOpenReport.addEventListener("click", (event) => {
    event.preventDefault();
    navigateToReport(dom.analyzeOpenReport.dataset.lectureId || state.currentReportId);
  });
  window.addEventListener("hashchange", handleRoute);
  window.addEventListener("beforeunload", (event) => {
    if (state.isRunning) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
}

async function bootstrap() {
  bindEvents();
  resetRunState();
  renderEmptyDetail();
  try {
    await refreshReports(false);
  } catch (error) {
    renderDashboard();
    showToast(error instanceof Error ? error.message : "리포트 목록을 불러오지 못했습니다.");
  }
  handleRoute();
}

bootstrap();
