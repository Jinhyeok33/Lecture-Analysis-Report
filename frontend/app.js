const form = document.getElementById("analysis-form");
const startButton = document.getElementById("start-analysis");
const statusList = Array.from(document.querySelectorAll("#status-list li"));
const statusLive = document.getElementById("status-live");
const progressBar = document.getElementById("progress-bar");
const summaryGrid = document.getElementById("summary-grid");
const summaryOverview = document.getElementById("summary-overview");
const lectureInfo = document.getElementById("lecture-info");
const scoreStructure = document.getElementById("score-structure");
const scoreDelivery = document.getElementById("score-delivery");
const scoreInteraction = document.getElementById("score-interaction");
const scoreConcept = document.getElementById("score-concept");
const scorePractice = document.getElementById("score-practice");
const meterStructure = document.getElementById("meter-structure");
const meterDelivery = document.getElementById("meter-delivery");
const meterInteraction = document.getElementById("meter-interaction");
const meterConcept = document.getElementById("meter-concept");
const meterPractice = document.getElementById("meter-practice");
const overallScore = document.getElementById("overall-score");
const overallLevel = document.getElementById("overall-level");
const overallDelta = document.getElementById("overall-delta");
const analysisPill = document.getElementById("analysis-pill");
const strengthList = document.getElementById("strength-list");
const weaknessList = document.getElementById("weakness-list");
const evidenceList = document.getElementById("evidence-list");
const strengthMore = document.getElementById("strength-more");
const weaknessMore = document.getElementById("weakness-more");
const evidenceMore = document.getElementById("evidence-more");
const downloadPdf = document.getElementById("download-pdf");
const downloadJson = document.getElementById("download-json");
const scrollButtons = Array.from(document.querySelectorAll("[data-scroll]"));
const uiToast = document.getElementById("ui-toast");
const heroScoreValue = document.getElementById("hero-score-value");
const heroRingScore = document.getElementById("hero-ring-score");
const heroRing = document.getElementById("hero-ring");
const heroTop1 = document.getElementById("hero-top-1");
const heroTop2 = document.getElementById("hero-top-2");
const heroTop3 = document.getElementById("hero-top-3");

const detailLanguageSummary = document.getElementById("detail-language-summary");
const detailStructureSummary = document.getElementById("detail-structure-summary");
const detailConceptSummary = document.getElementById("detail-concept-summary");
const detailPracticeSummary = document.getElementById("detail-practice-summary");
const detailInteractionSummary = document.getElementById("detail-interaction-summary");
const detailLanguageItems = document.getElementById("detail-language-items");
const detailStructureItems = document.getElementById("detail-structure-items");
const detailConceptItems = document.getElementById("detail-concept-items");
const detailPracticeItems = document.getElementById("detail-practice-items");
const detailInteractionItems = document.getElementById("detail-interaction-items");

const steps = [
  "NLP 분석 중",
  "LLM 분석 중",
  "통합 중",
  "리포트 생성 중",
];

let isRunning = false;
let pdfUrl = null;
let jsonUrl = null;
let toastTimer = null;
const JOB_POLL_INTERVAL_MS = 1200;

const SUMMARY_PREVIEW_COUNT = 3;
const EVIDENCE_ITEM_LABELS = {
  learning_objective_intro: "학습 목표 안내",
  previous_lesson_linkage: "전날 복습 연계",
  explanation_sequence: "설명 순서",
  key_point_emphasis: "핵심 내용 강조",
  closing_summary: "마무리 요약",
  concept_definition: "개념 정의",
  analogy_example_usage: "비유 및 예시 활용",
  prerequisite_check: "선행 개념 확인",
  example_appropriateness: "예시 적절성",
  practice_transition: "실습 연계",
  error_handling: "오류 대응",
  participation_induction: "참여 유도",
  question_response_sufficiency: "질문 응답 충분성",
};

function setActiveStep(index) {
  statusList.forEach((item, idx) => {
    item.classList.toggle("is-active", idx === index);
  });
  const progress = Math.round(((index + 1) / steps.length) * 100);
  progressBar.style.width = `${progress}%`;
  statusLive.textContent = `${steps[index]}…`;
}

function setRunState(state, message) {
  analysisPill.classList.remove("is-idle", "is-running", "is-done", "is-error");
  if (state === "running") {
    analysisPill.classList.add("is-running");
    analysisPill.textContent = "진행 중";
  } else if (state === "done") {
    analysisPill.classList.add("is-done");
    analysisPill.textContent = "완료";
  } else if (state === "error") {
    analysisPill.classList.add("is-error");
    analysisPill.textContent = "확인 필요";
  } else {
    analysisPill.classList.add("is-idle");
    analysisPill.textContent = "대기";
  }

  if (message) {
    statusLive.textContent = message;
  }
}

function showToast(message) {
  if (!uiToast) return;
  uiToast.textContent = message;
  uiToast.classList.add("is-visible");
  if (toastTimer) {
    window.clearTimeout(toastTimer);
  }
  toastTimer = window.setTimeout(() => {
    uiToast.classList.remove("is-visible");
  }, 2400);
}

function disableDownloads() {
  if (pdfUrl?.startsWith("blob:")) {
    URL.revokeObjectURL(pdfUrl);
  }
  if (jsonUrl?.startsWith("blob:")) {
    URL.revokeObjectURL(jsonUrl);
  }
  pdfUrl = null;
  jsonUrl = null;
  downloadPdf.setAttribute("aria-disabled", "true");
  downloadJson.setAttribute("aria-disabled", "true");
  downloadPdf.removeAttribute("download");
  downloadJson.removeAttribute("download");
  downloadPdf.href = "#";
  downloadJson.href = "#";
}

function enableDownloads(downloads) {
  const nextPdfUrl = resolveDownloadUrl(downloads?.pdfUrl || downloads?.pdf_url);
  const nextJsonUrl = resolveDownloadUrl(downloads?.jsonUrl || downloads?.json_url);

  if (!nextPdfUrl || !nextJsonUrl) {
    disableDownloads();
    return;
  }

  pdfUrl = nextPdfUrl;
  jsonUrl = nextJsonUrl;

  downloadPdf.setAttribute("aria-disabled", "false");
  downloadJson.setAttribute("aria-disabled", "false");
  downloadPdf.href = pdfUrl;
  downloadJson.href = jsonUrl;
  downloadPdf.setAttribute("download", "analysis_report.pdf");
  downloadJson.setAttribute("download", "analysis.json");
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function clampFive(value) {
  return Math.max(1, Math.min(5, value));
}

function clampUnit(value) {
  return Math.max(0, Math.min(1, value));
}

function averageNumbers(values, fallback = 0) {
  const numbers = values.filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!numbers.length) return fallback;
  return numbers.reduce((sum, value) => sum + value, 0) / numbers.length;
}

function numericValues(record) {
  if (!record || typeof record !== "object") return [];
  return Object.values(record).filter((value) => typeof value === "number" && Number.isFinite(value));
}

function averageScoreGroup(group) {
  return averageNumbers(numericValues(group), 0);
}

function fivePointToPercent(score) {
  if (typeof score !== "number" || !Number.isFinite(score) || score <= 0) {
    return 0;
  }
  return clampPercent((clampFive(score) / 5) * 100);
}

function resolveDownloadUrl(path) {
  if (typeof path !== "string" || !path.trim()) return "";
  return new URL(path, window.location.href).toString();
}

function sanitizeText(value, fallback = "-") {
  return typeof value === "string" && value.trim() ? value.trim() : fallback;
}

function firstNonEmpty(values, fallback = "") {
  if (!Array.isArray(values)) return fallback;
  const found = values.find((value) => typeof value === "string" && value.trim());
  return found ? found.trim() : fallback;
}

function summarizeSessionField(sessions, fieldName) {
  const values = Array.isArray(sessions)
    ? sessions
        .map((session) => sanitizeText(session?.[fieldName], ""))
        .filter(Boolean)
    : [];

  if (!values.length) return "-";
  if (values.length === 1) return values[0];
  return `${values[0]} 외 ${values.length - 1}건`;
}

function formatScoreText(score) {
  return `${clampPercent(score)}점`;
}

function describeCategorySummary(type, score) {
  switch (type) {
    case "language":
      if (score >= 80) return "언어 표현 품질이 안정적입니다.";
      if (score >= 60) return "표현 품질 관리가 필요합니다.";
      return "언어 표현 보강이 필요합니다.";
    case "structure":
      if (score >= 80) return "강의 도입 및 구조가 안정적입니다.";
      if (score >= 60) return "강의 도입 및 구조 보강이 필요합니다.";
      return "강의 도입 및 구조 개선이 필요합니다.";
    case "concept":
      if (score >= 80) return "개념 설명 명확성이 우수합니다.";
      if (score >= 60) return "개념 설명 명확성 보강이 필요합니다.";
      return "개념 설명 명확성 개선이 필요합니다.";
    case "practice":
      if (score >= 80) return "예시 및 실습 연계가 자연스럽습니다.";
      if (score >= 60) return "예시 및 실습 연계 보강이 필요합니다.";
      return "예시 및 실습 연계 개선이 필요합니다.";
    case "interaction":
      if (score >= 80) return "수강생 상호작용이 원활합니다.";
      if (score >= 60) return "수강생 상호작용 보강이 필요합니다.";
      return "수강생 상호작용 개선이 필요합니다.";
    default:
      return "-";
  }
}

function calculateRepeatExpressionScore(languageQuality = {}) {
  const repeatRatio = Number(languageQuality.repeat_ratio);
  if (!Number.isFinite(repeatRatio)) return null;
  return clampPercent((1 - clampUnit(repeatRatio / 0.35)) * 100);
}

function calculateCompletenessScore(languageQuality = {}) {
  const incompleteRatio = Number(languageQuality.incomplete_sentence_ratio);
  if (!Number.isFinite(incompleteRatio)) return null;
  return clampPercent((1 - clampUnit(incompleteRatio)) * 100);
}

function calculateLanguageConsistencyScore(languageQuality = {}) {
  const styleRatio = languageQuality.speech_style_ratio;
  if (!styleRatio || typeof styleRatio !== "object") return null;
  const values = Object.values(styleRatio).filter((value) => typeof value === "number" && Number.isFinite(value));
  if (!values.length) return null;
  return clampPercent(Math.max(...values) * 100);
}

function calculateSpeechRateScore(conceptClarityMetrics = {}) {
  const speechRate = Number(conceptClarityMetrics.speech_rate_wpm);
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

function deriveDeliveryScore(languageQuality = {}, conceptClarityMetrics = {}) {
  const repeatScore = 1 - clampUnit((Number(languageQuality.repeat_ratio) || 0) / 0.35);
  const incompleteScore = 1 - clampUnit((Number(languageQuality.incomplete_sentence_ratio) || 0) / 0.6);
  const speechScore = clampUnit((Number(conceptClarityMetrics.score) || 3) / 5);
  const deliveryScore = (repeatScore * 0.45 + incompleteScore * 0.35 + speechScore * 0.2) * 100;
  return clampPercent(deliveryScore);
}

function formatRepeatMetric(languageQuality = {}) {
  if (typeof languageQuality.total_filler_count === "number") {
    return `${languageQuality.total_filler_count}회`;
  }
  if (typeof languageQuality.repeat_ratio === "number") {
    return `${clampPercent(languageQuality.repeat_ratio * 100)}%`;
  }
  return "-";
}

function formatCompletenessMetric(languageQuality = {}) {
  if (typeof languageQuality.incomplete_sentence_ratio !== "number") return "-";
  return `${clampPercent((1 - languageQuality.incomplete_sentence_ratio) * 100)}%`;
}

function formatSpeedMetric(conceptClarityMetrics = {}) {
  if (typeof conceptClarityMetrics.speech_rate_wpm !== "number") return "-";
  return `${conceptClarityMetrics.speech_rate_wpm} WPM`;
}

function formatQuestionMetric(interactionMetrics = {}) {
  if (typeof interactionMetrics.understanding_question_count !== "number") return "-";
  return `${interactionMetrics.understanding_question_count}개`;
}

function buildScoreEntry(label, score) {
  if (typeof score !== "number" || !Number.isFinite(score)) {
    return { label, value: "-" };
  }
  return { label, value: formatScoreText(score) };
}

function averageEntryScores(entries) {
  return averageNumbers(
    entries
      .map((entry) => {
        const parsed = Number.parseInt(entry?.value, 10);
        return Number.isFinite(parsed) ? parsed : null;
      })
      .filter((value) => typeof value === "number"),
    0
  );
}

function buildDetailBreakdown(scoreGroup = {}) {
  const entries = Object.entries(scoreGroup).filter(
    ([, value]) => typeof value === "number" && Number.isFinite(value)
  );

  if (!entries.length) return [];

  return entries
    .map(([key, value]) => {
      const label = EVIDENCE_ITEM_LABELS[key] || key;
      return {
        label,
        value: formatScoreText(fivePointToPercent(value)),
      };
    });
}

function renderDetailBreakdown(container, entries = []) {
  clearChildren(container);

  if (!Array.isArray(entries) || !entries.length) {
    const empty = document.createElement("div");
    const label = document.createElement("span");
    const value = document.createElement("span");
    empty.className = "detail-subscore-row is-empty";
    label.textContent = "세부 점수";
    value.textContent = "-";
    empty.append(label, value);
    container.appendChild(empty);
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
    container.appendChild(row);
  });
}

function buildDetailCategories(analysis = {}) {
  const languageEntries = [
    buildScoreEntry("불필요한 반복 표현", calculateRepeatExpressionScore(analysis.language_quality)),
    buildScoreEntry("발화 완결성", calculateCompletenessScore(analysis.language_quality)),
    buildScoreEntry("언어 일관성", calculateLanguageConsistencyScore(analysis.language_quality)),
  ];
  const structureEntries = buildDetailBreakdown(analysis.summary_scores?.lecture_structure);
  const conceptEntries = [
    ...buildDetailBreakdown(analysis.summary_scores?.concept_clarity),
    buildScoreEntry("발화 속도 적절성", calculateSpeechRateScore(analysis.concept_clarity_metrics)),
  ];
  const practiceEntries = buildDetailBreakdown(analysis.summary_scores?.practice_linkage);
  const interactionEntries = [
    buildScoreEntry("이해 확인 질문", calculateQuestionAdequacyScore(analysis.interaction_metrics)),
    ...buildDetailBreakdown(analysis.summary_scores?.interaction),
  ];

  return {
    language: {
      summary: describeCategorySummary("language", averageEntryScores(languageEntries)),
      details: languageEntries,
    },
    structure: {
      summary: describeCategorySummary("structure", averageEntryScores(structureEntries)),
      details: structureEntries,
    },
    concept: {
      summary: describeCategorySummary("concept", averageEntryScores(conceptEntries)),
      details: conceptEntries,
    },
    practice: {
      summary: describeCategorySummary("practice", averageEntryScores(practiceEntries)),
      details: practiceEntries,
    },
    interaction: {
      summary: describeCategorySummary("interaction", averageEntryScores(interactionEntries)),
      details: interactionEntries,
    },
  };
}

function normalizeServerAnalysis(payload) {
  const integrated = payload?.analysis && typeof payload.analysis === "object" ? payload.analysis : {};
  const metadata = integrated.metadata || {};
  const analysis = integrated.analysis || {};
  const sessions = Array.isArray(metadata.sessions) ? metadata.sessions : [];
  const primarySession = sessions[0] || {};

  const structureScore = fivePointToPercent(averageScoreGroup(analysis.summary_scores?.lecture_structure));
  const conceptScore = fivePointToPercent(averageScoreGroup(analysis.summary_scores?.concept_clarity));
  const practiceScore = fivePointToPercent(averageScoreGroup(analysis.summary_scores?.practice_linkage));
  const interactionScore = fivePointToPercent(averageScoreGroup(analysis.summary_scores?.interaction));
  const deliveryScore = deriveDeliveryScore(
    analysis.language_quality,
    analysis.concept_clarity_metrics
  );
  const detailCategories = buildDetailCategories(analysis);
  const overallScoreValue = clampPercent(
    averageNumbers(
      [structureScore, deliveryScore, interactionScore, conceptScore, practiceScore],
      0
    )
  );

  return {
    lecture_id: sanitizeText(integrated.lecture_id || payload?.lecture_id, "unknown_lecture"),
    course_id: sanitizeText(metadata.course_id),
    course_name: sanitizeText(metadata.course_name),
    date: sanitizeText(metadata.date),
    time: sanitizeText(primarySession.time || summarizeSessionField(sessions, "time")),
    subject: summarizeSessionField(sessions, "subject"),
    content: summarizeSessionField(sessions, "content"),
    instructor: sanitizeText(metadata.instructor),
    sub_instructor: sanitizeText(metadata.sub_instructor),
    overall: {
      score: overallScoreValue,
      level: getScoreLevel(overallScoreValue),
      delta: overallScoreValue - 78,
    },
    scores: {
      structure: formatScoreText(structureScore),
      delivery: formatScoreText(deliveryScore),
      interaction: formatScoreText(interactionScore),
      concept: formatScoreText(conceptScore),
      practice: formatScoreText(practiceScore),
    },
    strengths: Array.isArray(analysis.overall_strengths)
      ? analysis.overall_strengths.filter((value) => typeof value === "string" && value.trim())
      : [],
    weaknesses: Array.isArray(analysis.overall_issues)
      ? analysis.overall_issues.filter((value) => typeof value === "string" && value.trim())
      : [],
    evidence: Array.isArray(analysis.overall_evidences) ? analysis.overall_evidences : [],
    detailCategories,
  };
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

async function requestAnalysis() {
  const response = await fetch("/api/analyze", {
    method: "POST",
    body: new FormData(form),
  });
  const payload = await readJsonResponse(response);

  if (!response.ok || payload?.ok === false) {
    const message =
      typeof payload?.error === "string" && payload.error.trim()
        ? payload.error.trim()
        : `실 분석 서버 요청에 실패했습니다. (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

async function requestAnalysisStatus(jobId) {
  const response = await fetch(`/api/analyze/status?job_id=${encodeURIComponent(jobId)}`, {
    cache: "no-store",
  });
  const payload = await readJsonResponse(response);

  if (!response.ok || payload?.ok === false) {
    const message =
      typeof payload?.error === "string" && payload.error.trim()
        ? payload.error.trim()
        : `분석 상태 조회에 실패했습니다. (${response.status})`;
    throw new Error(message);
  }

  return payload;
}

function getStatusStepIndex(status) {
  const directIndex = Number(status?.step_index);
  if (Number.isInteger(directIndex) && directIndex >= 0) {
    return Math.min(directIndex, steps.length - 1);
  }

  switch (status?.stage) {
    case "nlp":
      return 0;
    case "llm":
      return 1;
    case "integrate":
      return 2;
    case "report":
    case "done":
      return steps.length - 1;
    default:
      return null;
  }
}

function clearActiveStep() {
  statusList.forEach((item) => item.classList.remove("is-active"));
  progressBar.style.width = "0%";
}

function applyAnalysisStatus(status) {
  const nextStepIndex = getStatusStepIndex(status);
  if (typeof nextStepIndex === "number") {
    setActiveStep(nextStepIndex);
  }

  const message =
    typeof status?.message === "string" && status.message.trim() ? status.message.trim() : "분석 중…";

  if (status?.state === "queued" || status?.state === "running") {
    setRunState("running", message);
  }
}

function sleep(ms) {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

async function waitForAnalysisResult(jobId) {
  while (true) {
    const status = await requestAnalysisStatus(jobId);
    applyAnalysisStatus(status);

    if (status?.state === "done") {
      return status?.result || {};
    }

    if (status?.state === "error") {
      const message =
        typeof status?.error === "string" && status.error.trim()
          ? status.error.trim()
          : typeof status?.message === "string" && status.message.trim()
            ? status.message.trim()
            : "분석 중 오류가 발생했습니다.";
      throw new Error(message);
    }

    await sleep(JOB_POLL_INTERVAL_MS);
  }
}

function extractScoreValue(scoreText) {
  const parsed = Number.parseInt(scoreText, 10);
  if (Number.isNaN(parsed)) return 0;
  return Math.max(0, Math.min(100, parsed));
}

function toScorePercent(scoreText) {
  return extractScoreValue(scoreText);
}

function getScoreLevel(overall) {
  if (overall >= 90) return "우수";
  if (overall >= 80) return "양호";
  if (overall >= 70) return "보통";
  return "개선 필요";
}

function formatDelta(delta) {
  if (delta > 0) return `기준 대비 +${delta}p`;
  if (delta < 0) return `기준 대비 ${delta}p`;
  return "기준 대비 0p";
}

function clearChildren(node) {
  while (node.firstChild) {
    node.removeChild(node.firstChild);
  }
}

function appendInfoRow(container, keyText, valueText) {
  const wrapper = document.createElement("div");
  const key = document.createElement("span");
  const value = document.createElement("strong");
  key.textContent = keyText;
  value.textContent = valueText;
  wrapper.append(key, value);
  container.appendChild(wrapper);
}

function setScoreDisplay(labelNode, meterNode, scoreText) {
  labelNode.textContent = scoreText;
  meterNode.style.width = `${toScorePercent(scoreText)}%`;
}

function setHeroPreview(score, weaknesses = []) {
  if (!heroScoreValue || !heroRingScore || !heroRing) return;

  if (typeof score === "number") {
    const clamped = Math.max(0, Math.min(100, score));
    heroScoreValue.textContent = `${clamped}`;
    heroRingScore.textContent = `${clamped}`;
    heroRing.style.setProperty("--ring-value", `${clamped}`);
  } else {
    heroScoreValue.textContent = "-";
    heroRingScore.textContent = "-";
    heroRing.style.setProperty("--ring-value", "0");
  }

  const fallback = "분석 후 자동 제안됩니다.";
  if (heroTop1) heroTop1.textContent = weaknesses[0] || fallback;
  if (heroTop2) heroTop2.textContent = weaknesses[1] || fallback;
  if (heroTop3) heroTop3.textContent = weaknesses[2] || fallback;
}

function renderList(target, values, fallbackText = "분석 완료 후 표시됩니다.") {
  clearChildren(target);
  const listValues = Array.isArray(values)
    ? values.filter((value) => typeof value === "string" && value.trim())
    : [];
  const source = listValues.length ? listValues : [fallbackText];

  source.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    target.appendChild(item);
  });
}

function prettifyEvidenceItem(item, index) {
  if (typeof item !== "string" || !item.trim()) {
    return `근거 ${index + 1}`;
  }

  const normalized = item.trim();
  if (EVIDENCE_ITEM_LABELS[normalized]) {
    return EVIDENCE_ITEM_LABELS[normalized];
  }

  return normalized
    .replace(/_/g, " ")
    .replace(/\b\w/g, (ch) => ch.toUpperCase());
}

function normalizeEvidenceEntries(rawEvidence) {
  if (!Array.isArray(rawEvidence)) return [];

  return rawEvidence
    .map((entry, index) => {
      if (typeof entry === "string") {
        const text = entry.trim();
        if (!text) return null;
        return {
          item: `evidence_${index + 1}`,
          quote: text,
          reason: "강의 흐름에서 관찰된 근거입니다.",
        };
      }

      if (!entry || typeof entry !== "object") return null;
      const quote = typeof entry.quote === "string" ? entry.quote.trim() : "";
      const reasonSource = typeof entry.reason === "string" ? entry.reason : entry.explanation;
      const reason = typeof reasonSource === "string" ? reasonSource.trim() : "";
      const item =
        typeof entry.item === "string" && entry.item.trim()
          ? entry.item.trim()
          : `evidence_${index + 1}`;
      if (!quote) return null;

      return {
        item,
        quote,
        reason: reason || "해당 발언이 분석 결과를 뒷받침합니다.",
      };
    })
    .filter(Boolean);
}

function renderEvidence(target, entries) {
  clearChildren(target);

  if (!entries.length) {
    const empty = document.createElement("li");
    empty.textContent = "분석 완료 후 표시됩니다.";
    target.appendChild(empty);
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
    target.appendChild(li);
  });
}

function initializeListPreview(listNode, toggleButton) {
  if (!listNode || !toggleButton) return;

  const items = Array.from(listNode.children);
  if (items.length <= SUMMARY_PREVIEW_COUNT) {
    items.forEach((item) => item.classList.remove("is-collapsed"));
    toggleButton.hidden = true;
    toggleButton.textContent = "더보기";
    return;
  }

  const expanded = toggleButton.dataset.expanded === "true";
  items.forEach((item, index) => {
    item.classList.toggle("is-collapsed", !expanded && index >= SUMMARY_PREVIEW_COUNT);
  });

  toggleButton.hidden = false;
  toggleButton.textContent = expanded ? "접기" : "더보기";
}

function toggleListPreview(listNode, toggleButton) {
  if (!listNode || !toggleButton || toggleButton.hidden) return;
  const expanded = toggleButton.dataset.expanded === "true";
  toggleButton.dataset.expanded = (!expanded).toString();
  initializeListPreview(listNode, toggleButton);
}

function resetSummaryValues() {
  overallScore.textContent = "-";
  overallLevel.textContent = "분석 전";
  overallDelta.textContent = "기준 대비 -";

  clearChildren(lectureInfo);
  appendInfoRow(lectureInfo, "course_name", "분석 전…");
  appendInfoRow(lectureInfo, "instructor", "분석 전…");
  appendInfoRow(lectureInfo, "sub_instructor", "분석 전…");
  appendInfoRow(lectureInfo, "date / time", "분석 전…");
  appendInfoRow(lectureInfo, "subject", "분석 전…");
  appendInfoRow(lectureInfo, "content", "분석 전…");

  setScoreDisplay(scoreStructure, meterStructure, "?");
  setScoreDisplay(scoreDelivery, meterDelivery, "?");
  setScoreDisplay(scoreInteraction, meterInteraction, "?");
  setScoreDisplay(scoreConcept, meterConcept, "?");
  setScoreDisplay(scorePractice, meterPractice, "?");

  renderList(strengthList, []);
  renderList(weaknessList, []);
  renderEvidence(evidenceList, []);

  [strengthMore, weaknessMore, evidenceMore].forEach((button) => {
    if (!button) return;
    button.dataset.expanded = "false";
    button.hidden = true;
    button.textContent = "더보기";
  });

  initializeListPreview(strengthList, strengthMore);
  initializeListPreview(weaknessList, weaknessMore);
  initializeListPreview(evidenceList, evidenceMore);

  detailLanguageSummary.textContent = "?";
  detailStructureSummary.textContent = "?";
  detailConceptSummary.textContent = "?";
  detailPracticeSummary.textContent = "?";
  detailInteractionSummary.textContent = "?";
  renderDetailBreakdown(detailLanguageItems, []);
  renderDetailBreakdown(detailStructureItems, []);
  renderDetailBreakdown(detailConceptItems, []);
  renderDetailBreakdown(detailPracticeItems, []);
  renderDetailBreakdown(detailInteractionItems, []);

  setHeroPreview(null, []);
}

function setSummaryValues(data) {
  overallScore.textContent = `${data.overall.score}점`;
  overallLevel.textContent = data.overall.level;
  overallDelta.textContent = formatDelta(data.overall.delta);

  clearChildren(lectureInfo);
  appendInfoRow(lectureInfo, "course_name", data.course_name || "-");
  appendInfoRow(lectureInfo, "instructor", data.instructor || "-");
  appendInfoRow(lectureInfo, "sub_instructor", data.sub_instructor || "-");
  appendInfoRow(lectureInfo, "date / time", `${data.date || "-"} · ${data.time || "-"}`);
  appendInfoRow(lectureInfo, "subject", data.subject || "-");
  appendInfoRow(lectureInfo, "content", data.content || "-");

  setScoreDisplay(scoreStructure, meterStructure, data.scores?.structure || "?");
  setScoreDisplay(scoreDelivery, meterDelivery, data.scores?.delivery || "?");
  setScoreDisplay(scoreInteraction, meterInteraction, data.scores?.interaction || "?");
  setScoreDisplay(scoreConcept, meterConcept, data.scores?.concept || "?");
  setScoreDisplay(scorePractice, meterPractice, data.scores?.practice || "?");

  renderList(strengthList, data.strengths || []);
  renderList(weaknessList, data.weaknesses || []);

  const normalizedEvidence = normalizeEvidenceEntries(data.evidence || data.evidences || []);
  renderEvidence(evidenceList, normalizedEvidence);

  [strengthMore, weaknessMore, evidenceMore].forEach((button) => {
    if (!button) return;
    button.dataset.expanded = "false";
    button.hidden = true;
    button.textContent = "더보기";
  });

  initializeListPreview(strengthList, strengthMore);
  initializeListPreview(weaknessList, weaknessMore);
  initializeListPreview(evidenceList, evidenceMore);

  detailLanguageSummary.textContent = data.detailCategories.language.summary;
  detailStructureSummary.textContent = data.detailCategories.structure.summary;
  detailConceptSummary.textContent = data.detailCategories.concept.summary;
  detailPracticeSummary.textContent = data.detailCategories.practice.summary;
  detailInteractionSummary.textContent = data.detailCategories.interaction.summary;
  renderDetailBreakdown(detailLanguageItems, data.detailCategories.language.details);
  renderDetailBreakdown(detailStructureItems, data.detailCategories.structure.details);
  renderDetailBreakdown(detailConceptItems, data.detailCategories.concept.details);
  renderDetailBreakdown(detailPracticeItems, data.detailCategories.practice.details);
  renderDetailBreakdown(detailInteractionItems, data.detailCategories.interaction.details);
  setHeroPreview(data.overall.score, data.weaknesses || []);
}

async function startAnalysis() {
  if (isRunning) return;
  if (!form.checkValidity()) {
    form.reportValidity();
    setRunState("error", "입력값을 확인해 주세요.");
    showToast("필수 입력을 먼저 완료해 주세요.");
    return;
  }

  isRunning = true;
  disableDownloads();
  summaryGrid.setAttribute("data-ready", "false");
  summaryOverview.setAttribute("data-ready", "false");
  resetSummaryValues();
  clearActiveStep();
  setRunState("running", "분석 요청 준비 중…");

  startButton.textContent = "분석 중…";
  startButton.disabled = true;

  try {
    const job = await requestAnalysis();
    applyAnalysisStatus(job);
    const payload = await waitForAnalysisResult(job.job_id);
    const analysisData = normalizeServerAnalysis(payload);

    setActiveStep(steps.length - 1);
    progressBar.style.width = "100%";
    summaryGrid.setAttribute("data-ready", "true");
    summaryOverview.setAttribute("data-ready", "true");
    setSummaryValues(analysisData);
    enableDownloads(payload.downloads);
    setRunState("done", "분석 완료");
    showToast("실 분석 결과와 다운로드가 준비되었습니다.");
  } catch (error) {
    console.error(error);
    setRunState(
      "error",
      error instanceof Error ? error.message : "분석 중 오류가 발생했습니다."
    );
    showToast(
      error instanceof Error ? error.message : "실 분석 서버 연결에 실패했습니다."
    );
  } finally {
    isRunning = false;
    startButton.textContent = "다시 분석";
    startButton.disabled = false;
  }
}

if (scrollButtons.length) {
  scrollButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const targetId = button.getAttribute("data-scroll");
      if (!targetId) return;
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  });
}

const metadataCsvInput = document.getElementById("metadata-csv");
const csvSessionPicker = document.getElementById("csv-session-picker");
const csvSessionSelect = document.getElementById("csv-session-select");
const csvApplyBtn = document.getElementById("csv-apply");

let csvRows = [];
let csvHeaders = [];

const CSV_FIELD_NAMES = ["course_id", "course_name", "date", "time", "subject", "content", "instructor", "sub_instructor"];

function parseCsvLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i++;
      } else if (ch === '"') {
        inQuotes = false;
      } else {
        current += ch;
      }
    } else if (ch === '"') {
      inQuotes = true;
    } else if (ch === ",") {
      result.push(current.trim());
      current = "";
    } else {
      current += ch;
    }
  }
  result.push(current.trim());
  return result;
}

function applyRowToForm(headers, values) {
  let filled = 0;
  headers.forEach((header, index) => {
    const key = header.trim().replace(/^\uFEFF/, "").toLowerCase();
    if (!CSV_FIELD_NAMES.includes(key) || index >= values.length) return;
    const el = form.querySelector(`[name="${key}"]`);
    if (!el) return;
    el.value = values[index];
    filled++;
  });
  return filled;
}

metadataCsvInput.addEventListener("change", () => {
  const file = metadataCsvInput.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (e) => {
    const text = e.target.result;
    const lines = text.split(/\r?\n/).filter((l) => l.trim());
    if (lines.length < 2) {
      showToast("CSV에 헤더와 데이터 행이 필요합니다.");
      return;
    }

    csvHeaders = parseCsvLine(lines[0]);
    csvRows = lines.slice(1).map((l) => parseCsvLine(l));

    if (csvRows.length === 1) {
      const count = applyRowToForm(csvHeaders, csvRows[0]);
      showToast(count > 0 ? `CSV에서 ${count}개 필드를 불러왔습니다.` : "CSV 헤더가 일치하지 않습니다.");
      csvSessionPicker.hidden = true;
      return;
    }

    const dateIdx = csvHeaders.findIndex((h) => h.trim().toLowerCase() === "date");
    const timeIdx = csvHeaders.findIndex((h) => h.trim().toLowerCase() === "time");
    const subjectIdx = csvHeaders.findIndex((h) => h.trim().replace(/^\uFEFF/, "").toLowerCase() === "subject");

    clearChildren(csvSessionSelect);
    csvRows.forEach((row, i) => {
      const option = document.createElement("option");
      option.value = i;
      const datePart = dateIdx >= 0 ? row[dateIdx] : "";
      const timePart = timeIdx >= 0 ? row[timeIdx] : "";
      const subjectPart = subjectIdx >= 0 ? row[subjectIdx] : "";
      option.textContent = `${datePart}  ${timePart}  |  ${subjectPart}`;
      csvSessionSelect.appendChild(option);
    });

    csvSessionPicker.hidden = false;
    showToast(`${csvRows.length}개 세션을 불러왔습니다. 세션을 선택하세요.`);
  };
  reader.readAsText(file);
});

csvApplyBtn.addEventListener("click", () => {
  const selectedIndex = Number(csvSessionSelect.value);
  if (!csvRows[selectedIndex]) return;
  const count = applyRowToForm(csvHeaders, csvRows[selectedIndex]);
  showToast(count > 0 ? `세션 데이터 ${count}개 필드를 적용했습니다.` : "적용할 필드를 찾지 못했습니다.");
});

if (strengthMore) {
  strengthMore.addEventListener("click", () => toggleListPreview(strengthList, strengthMore));
}
if (weaknessMore) {
  weaknessMore.addEventListener("click", () => toggleListPreview(weaknessList, weaknessMore));
}
if (evidenceMore) {
  evidenceMore.addEventListener("click", () => toggleListPreview(evidenceList, evidenceMore));
}

startButton.addEventListener("click", startAnalysis);

downloadPdf.addEventListener("click", (event) => {
  if (downloadPdf.getAttribute("aria-disabled") === "true") {
    event.preventDefault();
  }
});

downloadJson.addEventListener("click", (event) => {
  if (downloadJson.getAttribute("aria-disabled") === "true") {
    event.preventDefault();
  }
});

disableDownloads();
resetSummaryValues();
setRunState("idle", "대기 중…");

window.addEventListener("beforeunload", (event) => {
  if (isRunning) {
    event.preventDefault();
    event.returnValue = "";
  }
});

