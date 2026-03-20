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
const chunkList = document.getElementById("chunk-list");
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

const metricRepeat = document.getElementById("metric-repeat");
const metricComplete = document.getElementById("metric-complete");
const metricSpeed = document.getElementById("metric-speed");
const metricQuestion = document.getElementById("metric-question");
const llmStructure = document.getElementById("llm-structure");
const llmConcept = document.getElementById("llm-concept");
const llmPractice = document.getElementById("llm-practice");
const llmInteraction = document.getElementById("llm-interaction");

const steps = [
  "전처리 중",
  "청킹 중",
  "NLP 분석 중",
  "LLM 분석 중",
  "리포트 생성 중",
];

let isRunning = false;
let timerId = null;
let pdfUrl = null;
let jsonUrl = null;
let toastTimer = null;

const SUMMARY_PREVIEW_COUNT = 3;
const EVIDENCE_ITEM_LABELS = {
  learning_objective_intro: "학습 목표 제시",
  previous_lesson_linkage: "이전 학습 연계",
  explanation_sequence: "설명 순서",
  key_point_emphasis: "핵심 강조",
  closing_summary: "마무리 요약",
  concept_definition: "개념 정의",
  analogy_example_usage: "비유/예시 활용",
  prerequisite_check: "사전 지식 점검",
  example_appropriateness: "예시 적절성",
  practice_transition: "실습 전환",
  error_handling: "오류 대응",
  participation_induction: "참여 유도",
  question_response_sufficiency: "질문 응답 충실도",
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

function describeDimension(type, score) {
  switch (type) {
    case "structure":
      if (score >= 80) return "목표-전개-정리 흐름이 안정적입니다.";
      if (score >= 60) return "구조는 유지되지만 핵심 강조 보강이 필요합니다.";
      return "도입과 마무리 구조 보강이 필요합니다.";
    case "concept":
      if (score >= 80) return "핵심 개념 정의가 명확합니다.";
      if (score >= 60) return "개념 설명은 가능하지만 예시 보강이 필요합니다.";
      return "개념 정의와 비유 설명 보강이 필요합니다.";
    case "practice":
      if (score >= 80) return "예시와 실습 연결이 자연스럽습니다.";
      if (score >= 60) return "실습 전환은 되지만 단계 안내를 더 보강해야 합니다.";
      return "예시 제시와 실습 연결 흐름 개선이 필요합니다.";
    case "interaction":
      if (score >= 80) return "참여 유도와 응답 흐름이 좋습니다.";
      if (score >= 60) return "질문은 있으나 상호작용 밀도를 더 높일 수 있습니다.";
      return "이해 확인 질문과 응답 밀도 보강이 필요합니다.";
    default:
      return "-";
  }
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

function priorityFromScore(score) {
  if (score < 60) return "high";
  if (score < 75) return "medium";
  return "low";
}

function normalizeChunks(chunks) {
  if (!Array.isArray(chunks)) return [];

  return chunks.map((chunk, index) => {
    const scoreGroups = Object.values(chunk?.scores || {}).flatMap((group) => numericValues(group));
    const chunkScore = fivePointToPercent(averageNumbers(scoreGroups, 0));
    const issue = firstNonEmpty(chunk?.issues, "");
    const strength = firstNonEmpty(chunk?.strengths, "");
    const evidence = Array.isArray(chunk?.evidence)
      ? chunk.evidence.find((entry) => entry && typeof entry.reason === "string" && entry.reason.trim())
      : null;
    const summary =
      issue ||
      strength ||
      sanitizeText(evidence?.reason, "") ||
      "세부 분석 결과를 확인하세요.";
    const timeRange = [sanitizeText(chunk?.start_time, ""), sanitizeText(chunk?.end_time, "")]
      .filter(Boolean)
      .join(" - ");

    return {
      title: timeRange
        ? `Chunk ${chunk?.chunk_id || index + 1} (${timeRange})`
        : `Chunk ${chunk?.chunk_id || index + 1}`,
      priority: priorityFromScore(chunkScore),
      summary,
    };
  });
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
    metrics: {
      repeat: formatRepeatMetric(analysis.language_quality),
      complete: formatCompletenessMetric(analysis.language_quality),
      speed: formatSpeedMetric(analysis.concept_clarity_metrics),
      question: formatQuestionMetric(analysis.interaction_metrics),
    },
    llm: {
      structure: describeDimension("structure", structureScore),
      concept: describeDimension("concept", conceptScore),
      practice: describeDimension("practice", practiceScore),
      interaction: describeDimension("interaction", interactionScore),
    },
    chunks: normalizeChunks(payload?.chunks),
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

function getChunkPriorityLabel(priority) {
  if (priority === "high") return "HIGH";
  if (priority === "medium") return "MEDIUM";
  return "LOW";
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

function renderChunks(chunks) {
  clearChildren(chunkList);
  if (!Array.isArray(chunks) || !chunks.length) {
    const emptyText = document.createElement("p");
    emptyText.className = "empty";
    emptyText.textContent = "chunk 분석 결과가 없습니다.";
    chunkList.appendChild(emptyText);
    return;
  }

  chunks.forEach((chunk) => {
    const wrapper = document.createElement("div");
    const head = document.createElement("div");
    const title = document.createElement("strong");
    const badge = document.createElement("span");
    const summary = document.createElement("p");

    wrapper.className = "chunk";
    head.className = "chunk-head";
    badge.className = `chunk-badge is-${chunk.priority}`;
    title.textContent = chunk.title;
    badge.textContent = getChunkPriorityLabel(chunk.priority);
    summary.textContent = chunk.summary;

    head.append(title, badge);
    wrapper.append(head, summary);
    chunkList.appendChild(wrapper);
  });
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

  metricRepeat.textContent = "?";
  metricComplete.textContent = "?";
  metricSpeed.textContent = "?";
  metricQuestion.textContent = "?";
  llmStructure.textContent = "?";
  llmConcept.textContent = "?";
  llmPractice.textContent = "?";
  llmInteraction.textContent = "?";

  clearChildren(chunkList);
  const emptyText = document.createElement("p");
  emptyText.className = "empty";
  emptyText.textContent = "분석 완료 후 표시됩니다.";
  chunkList.appendChild(emptyText);

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

  metricRepeat.textContent = data.metrics.repeat;
  metricComplete.textContent = data.metrics.complete;
  metricSpeed.textContent = data.metrics.speed;
  metricQuestion.textContent = data.metrics.question;

  llmStructure.textContent = data.llm.structure;
  llmConcept.textContent = data.llm.concept;
  llmPractice.textContent = data.llm.practice;
  llmInteraction.textContent = data.llm.interaction;

  renderChunks(data.chunks);
  setHeroPreview(data.overall.score, data.weaknesses || []);
}

function stopProgressLoop() {
  if (timerId) {
    window.clearInterval(timerId);
    timerId = null;
  }
}

function startProgressLoop() {
  stopProgressLoop();
  let index = 0;
  setActiveStep(index);
  timerId = window.setInterval(() => {
    index = Math.min(index + 1, steps.length - 1);
    setActiveStep(index);
  }, 1500);
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
  setRunState("running", "전처리 중…");

  startButton.textContent = "분석 중…";
  startButton.disabled = true;

  startProgressLoop();

  try {
    const payload = await requestAnalysis();
    const analysisData = normalizeServerAnalysis(payload);

    stopProgressLoop();
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
    stopProgressLoop();
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

