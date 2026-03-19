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
  downloadPdf.setAttribute("aria-disabled", "true");
  downloadJson.setAttribute("aria-disabled", "true");
  downloadPdf.removeAttribute("download");
  downloadJson.removeAttribute("download");
  downloadPdf.href = "#";
  downloadJson.href = "#";
}

function enableDownloads(pdfBlob, jsonBlob) {
  if (pdfUrl) URL.revokeObjectURL(pdfUrl);
  if (jsonUrl) URL.revokeObjectURL(jsonUrl);

  pdfUrl = URL.createObjectURL(pdfBlob);
  jsonUrl = URL.createObjectURL(jsonBlob);

  downloadPdf.setAttribute("aria-disabled", "false");
  downloadJson.setAttribute("aria-disabled", "false");
  downloadPdf.href = pdfUrl;
  downloadJson.href = jsonUrl;
  downloadPdf.setAttribute("download", "analysis_report.pdf");
  downloadJson.setAttribute("download", "analysis.json");
}

function clampScore(value) {
  return Math.max(60, Math.min(96, value));
}

function computeScore(seed, multiplier) {
  return clampScore(70 + (seed * multiplier) % 26);
}

function escapePdf(text) {
  return text.replace(/\\/g, "\\\\").replace(/\(/g, "\\(").replace(/\)/g, "\\)");
}

function createFallbackPdfBlob() {
  const lines = [
    "EduInsightAI Report",
    "Analysis summary is ready.",
    "Please review the JSON for details.",
  ];
  const escaped = lines.map(escapePdf);
  const textLines = escaped
    .map((line, idx) => `${idx === 0 ? "" : "0 -22 Td "}(${line}) Tj`)
    .join(" ");
  const stream = `BT /F1 18 Tf 72 720 Td ${textLines} ET`;

  const objects = [];
  objects.push("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n");
  objects.push("2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n");
  objects.push(
    "3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
  );
  objects.push(`4 0 obj\n<< /Length ${stream.length} >>\nstream\n${stream}\nendstream\nendobj\n`);
  objects.push("5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n");

  const header = "%PDF-1.4\n";
  let offset = header.length;
  const xrefEntries = ["0000000000 65535 f \n"];

  objects.forEach((obj) => {
    const entry = offset.toString().padStart(10, "0");
    xrefEntries.push(`${entry} 00000 n \n`);
    offset += obj.length;
  });

  const xref = `xref\n0 ${objects.length + 1}\n${xrefEntries.join("")}`;
  const trailer = `trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${offset}\n%%EOF`;

  const pdfContent = header + objects.join("") + xref + trailer;
  return new Blob([pdfContent], { type: "application/pdf" });
}

function clampFive(value) {
  return Math.max(1, Math.min(5, value));
}

function toFivePointScore(scoreText) {
  const raw = extractScoreValue(scoreText);
  const score = raw > 0 ? raw / 20 : 3;
  return Number.parseFloat(clampFive(score).toFixed(1));
}

function parseMetricNumber(text, fallback = 0) {
  if (typeof text !== "string") return fallback;
  const matched = text.match(/\d+/);
  if (!matched) return fallback;
  const value = Number.parseInt(matched[0], 10);
  return Number.isNaN(value) ? fallback : value;
}

function buildReportPayload(data) {
    const structure = toFivePointScore(data.scores?.structure || "");
  const delivery = toFivePointScore(data.scores?.delivery || "");
  const interaction = toFivePointScore(data.scores?.interaction || "");
  const concept = toFivePointScore(data.scores?.concept || "");
  const practice = toFivePointScore(data.scores?.practice || "");

  const repeatCount = parseMetricNumber(data.metrics?.repeat || "", 5);
  const completePercent = parseMetricNumber(data.metrics?.complete || "", 84);
  const speedWpm = parseMetricNumber(data.metrics?.speed || "", 150);
  const questionCount = parseMetricNumber(data.metrics?.question || "", 6);
  const incompleteRatio = Number.parseFloat(
    Math.max(0, Math.min(1, (100 - completePercent) / 100)).toFixed(2)
  );
  const repeatRatio = Number.parseFloat(Math.min(0.35, repeatCount / 40).toFixed(2));

  const issues = Array.isArray(data.weaknesses) ? data.weaknesses : [];
  const evidenceEntries = normalizeEvidenceEntries(data.evidence || data.evidences || []);
  const evidences = evidenceEntries.map((entry) => `"${entry.quote}" - ${entry.reason}`);

  return {
    lecture_id: `${data.date || "unknown"}_${data.course_id || "lecture"}`,
    metadata: {
      course_id: data.course_id || "-",
      course_name: data.course_name || "-",
      date: data.date || "-",
      instructor: data.instructor || "-",
      sub_instructor: data.sub_instructor || "-",
      sessions: [
        {
          time: data.time || "-",
          subject: data.subject || "-",
          content: data.content || "-",
        },
      ],
    },
    analysis: {
      language_quality: {
        repeat_expressions: {
          이제: Math.max(1, repeatCount),
          그래서: Math.max(1, Math.round(repeatCount * 0.8)),
          어쨌든: Math.max(1, Math.round(repeatCount * 0.4)),
        },
        repeat_ratio: repeatRatio,
        incomplete_sentence_ratio: incompleteRatio,
        speech_style_ratio: {
          formal: 0.9,
          informal: 0.1,
        },
      },
      concept_clarity_metrics: {
        speech_rate_wpm: speedWpm,
      },
      interaction_metrics: {
        understanding_question_count: questionCount,
      },
      summary_scores: {
        lecture_structure: {
          learning_objective_intro: clampFive(structure + 0.2),
          previous_lesson_linkage: clampFive(structure - 0.3),
          explanation_sequence: clampFive(structure + 0.1),
          key_point_emphasis: clampFive(structure - 0.1),
          closing_summary: clampFive(structure - 0.4),
        },
        concept_clarity: {
          concept_definition: clampFive(concept + 0.2),
          analogy_example_usage: clampFive(concept),
          prerequisite_check: clampFive(concept - 0.2),
        },
        practice_linkage: {
          example_appropriateness: clampFive(practice + 0.2),
          practice_transition: clampFive(practice),
          error_handling: clampFive(practice - 0.2),
        },
        interaction: {
          participation_induction: clampFive(interaction - 0.2),
          question_response_sufficiency: clampFive(interaction),
        },
      },
      overall_strengths: Array.isArray(data.strengths) ? data.strengths : [],
      overall_issues: issues,
      overall_evidences: evidences,
    },
  };
}

async function createPdfBlob(analysisData) {
  const payload = buildReportPayload(analysisData);
  const response = await fetch("/api/report/pdf", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`PDF API failed: ${response.status}`);
  }

  return await response.blob();
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

function getChunkPriority(index, seed) {
  const priority = (seed + index) % 3;
  if (priority === 0) return "high";
  if (priority === 1) return "medium";
  return "low";
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

function buildAnalysisData(formValues, file) {
  const seedBase =
    formValues.course_id.length +
    formValues.course_name.length +
    formValues.subject.length +
    formValues.instructor.length +
    formValues.sub_instructor.length;
  const seed = seedBase + (file ? Math.round(file.size / 1024) : 12);

  const structureScore = computeScore(seed, 3);
  const deliveryScore = computeScore(seed, 5);
  const interactionScore = computeScore(seed, 7);
  const conceptScore = clampScore(Math.round((structureScore + deliveryScore) / 2));
  const practiceScore = clampScore(Math.round((deliveryScore + interactionScore) / 2) - 2);
  const overallScoreValue = Math.round(
    (structureScore + deliveryScore + interactionScore + conceptScore + practiceScore) / 5
  );

  const strengths = [
    "강의 시작에서 목표를 분명하게 안내해 학습 방향이 선명합니다.",
    "개념 설명 순서가 안정적이라 초반 이해 부담이 낮습니다.",
    "예시 제시 후 핵심 개념을 다시 정리해 기억 고정에 유리합니다.",
    "질문 유도 멘트가 적절히 배치되어 참여를 끌어냅니다.",
    "마무리 요약에서 다음 학습 포인트를 분명히 연결합니다.",
  ];

  const weaknesses = [
    "중반부 일부 구간에서 반복 표현이 늘어 전달 밀도가 떨어집니다.",
    "난이도 전환 시 사전지식 확인이 부족해 이탈 위험이 있습니다.",
    "실습 안내가 텍스트 중심이라 따라가기 어려운 순간이 있습니다.",
    "핵심 개념 대비 예시 비중이 순간적으로 과해 초점이 흐려집니다.",
    "마지막 질의응답에서 요점 회수가 부족해 정리감이 약해집니다.",
  ];

  const evidence = [
    {
      item: "learning_objective_intro",
      quote: "오늘은 데코레이터 패턴과 옵저버 패턴을 배워보겠습니다.",
      reason: "강의 시작에서 학습 목표를 명확히 제시함",
    },
    {
      item: "explanation_sequence",
      quote: "먼저 개념을 정리하고, 바로 코드 예제로 확인해볼게요.",
      reason: "설명 순서가 개념에서 실습으로 자연스럽게 이어짐",
    },
    {
      item: "prerequisite_check",
      quote: "이 부분은 이벤트 루프를 이미 이해하고 있다는 전제로 진행합니다.",
      reason: "사전지식 전제가 있으나 확인 질문이 없어 일부 학습자 이탈 가능",
    },
    {
      item: "practice_transition",
      quote: "이제 방금 본 패턴을 실습 코드에 그대로 적용해봅시다.",
      reason: "개념 설명 뒤 실습으로 빠르게 전환해 적용 흐름을 강화함",
    },
    {
      item: "closing_summary",
      quote: "정리하면, 오늘은 상태 변화와 구독 구조를 연결하는 법을 봤습니다.",
      reason: "종료 구간에서 학습 포인트를 압축해 재강조함",
    },
  ];

  return {
    ...formValues,
    overall: {
      score: overallScoreValue,
      level: getScoreLevel(overallScoreValue),
      delta: overallScoreValue - 78,
    },
    scores: {
      structure: `${structureScore}점`,
      delivery: `${deliveryScore}점`,
      interaction: `${interactionScore}점`,
      concept: `${conceptScore}점`,
      practice: `${practiceScore}점`,
    },
    strengths,
    weaknesses,
    evidence,
    metrics: {
      repeat: `${(seed % 6) + 3}회`,
      complete: `${computeScore(seed, 2)}%`,
      speed: `${(seed % 40) + 120} WPM`,
      question: `${(seed % 5) + 4}개`,
    },
    llm: {
      structure: "목표-전개-정리 구성이 선명합니다.",
      concept: "핵심 용어 정의가 일관됩니다.",
      practice: "실습 안내가 명료합니다.",
      interaction: "질문 타이밍이 효과적입니다.",
    },
    chunks: Array.from({ length: 3 }).map((_, index) => ({
      title: `Chunk ${index + 1}`,
      priority: getChunkPriority(index, seed),
      summary:
        index % 2 === 0
          ? "요점 정리와 예시가 연결되어 있습니다."
          : "전개는 안정적이지만 문장 반복이 관찰됩니다.",
    })),
  };
}

function getFormValues() {
  const formData = new FormData(form);
  return {
    course_id: formData.get("course_id")?.toString().trim() || "-",
    course_name: formData.get("course_name")?.toString().trim() || "-",
    date: formData.get("date")?.toString().trim() || "-",
    time: formData.get("time")?.toString().trim() || "-",
    subject: formData.get("subject")?.toString().trim() || "-",
    content: formData.get("content")?.toString().trim() || "-",
    instructor: formData.get("instructor")?.toString().trim() || "-",
    sub_instructor: formData.get("sub_instructor")?.toString().trim() || "-",
  };
}

function startAnalysis() {
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

  let index = 0;
  setActiveStep(index);

  timerId = window.setInterval(() => {
    index += 1;
    if (index >= steps.length) {
      window.clearInterval(timerId);
      void finishAnalysis();
      return;
    }
    setActiveStep(index);
  }, 1100);
}

async function finishAnalysis() {
  isRunning = false;
  startButton.textContent = "다시 분석";
  startButton.disabled = false;
  progressBar.style.width = "100%";
  setRunState("done", "분석 완료");

  const fileInput = document.getElementById("script-file");
  const file = fileInput.files[0] || null;
  const formValues = getFormValues();
  const analysisData = buildAnalysisData(formValues, file);

  summaryGrid.setAttribute("data-ready", "true");
  summaryOverview.setAttribute("data-ready", "true");
  setSummaryValues(analysisData);

  const jsonBlob = new Blob([JSON.stringify(analysisData, null, 2)], {
    type: "application/json",
  });
  let pdfBlob;
  try {
    pdfBlob = await createPdfBlob(analysisData);
  } catch (error) {
    console.error(error);
    pdfBlob = createFallbackPdfBlob();
    showToast("PDF API 연결에 실패해 기본 PDF로 대체했습니다.");
  }

  enableDownloads(pdfBlob, jsonBlob);
  showToast("분석이 완료되어 다운로드가 활성화되었습니다.");
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

