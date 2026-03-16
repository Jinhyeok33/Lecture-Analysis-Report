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
const meterStructure = document.getElementById("meter-structure");
const meterDelivery = document.getElementById("meter-delivery");
const meterInteraction = document.getElementById("meter-interaction");
const overallScore = document.getElementById("overall-score");
const overallLevel = document.getElementById("overall-level");
const overallDelta = document.getElementById("overall-delta");
const riskList = document.getElementById("risk-list");
const primaryAction = document.getElementById("primary-action");
const analysisPill = document.getElementById("analysis-pill");
const strengthList = document.getElementById("strength-list");
const weaknessList = document.getElementById("weakness-list");
const recommendList = document.getElementById("recommend-list");
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
  const concept = Number.parseFloat(clampFive((structure + delivery) / 2).toFixed(1));
  const practice = Number.parseFloat(clampFive(delivery - 0.1).toFixed(1));

  const repeatCount = parseMetricNumber(data.metrics?.repeat || "", 5);
  const completePercent = parseMetricNumber(data.metrics?.complete || "", 84);
  const speedWpm = parseMetricNumber(data.metrics?.speed || "", 150);
  const questionCount = parseMetricNumber(data.metrics?.question || "", 6);
  const incompleteRatio = Number.parseFloat(
    Math.max(0, Math.min(1, (100 - completePercent) / 100)).toFixed(2)
  );
  const repeatRatio = Number.parseFloat(Math.min(0.35, repeatCount / 40).toFixed(2));

  const issues = Array.isArray(data.weaknesses) ? data.weaknesses : [];
  const recommendations = Array.isArray(data.recommendations) ? data.recommendations : [];
  const evidences = issues.map((issue, index) => {
    if (recommendations[index]) return recommendations[index];
    return `${issue} 구간의 전개를 다시 점검해 주세요.`;
  });

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

function renderList(target, values) {
  clearChildren(target);
  values.forEach((value) => {
    const item = document.createElement("li");
    item.textContent = value;
    target.appendChild(item);
  });
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
  primaryAction.textContent = "분석 완료 후 표시됩니다.";

  clearChildren(lectureInfo);
  appendInfoRow(lectureInfo, "course_name", "분석 전…");
  appendInfoRow(lectureInfo, "instructor", "분석 전…");
  appendInfoRow(lectureInfo, "date / time", "분석 전…");

  setScoreDisplay(scoreStructure, meterStructure, "?");
  setScoreDisplay(scoreDelivery, meterDelivery, "?");
  setScoreDisplay(scoreInteraction, meterInteraction, "?");

  renderList(riskList, ["분석 완료 후 표시됩니다."]);
  renderList(strengthList, ["분석 완료 후 표시됩니다."]);
  renderList(weaknessList, ["분석 완료 후 표시됩니다."]);
  renderList(recommendList, ["분석 완료 후 표시됩니다."]);

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
  primaryAction.textContent = data.primary_action;
  renderList(riskList, data.risks);

  clearChildren(lectureInfo);
  appendInfoRow(lectureInfo, "course_name", data.course_name);
  appendInfoRow(lectureInfo, "instructor", data.instructor);
  appendInfoRow(lectureInfo, "date / time", `${data.date} · ${data.time}`);

  setScoreDisplay(scoreStructure, meterStructure, data.scores.structure);
  setScoreDisplay(scoreDelivery, meterDelivery, data.scores.delivery);
  setScoreDisplay(scoreInteraction, meterInteraction, data.scores.interaction);

  renderList(strengthList, data.strengths);
  renderList(weaknessList, data.weaknesses);
  renderList(recommendList, data.recommendations);

  metricRepeat.textContent = data.metrics.repeat;
  metricComplete.textContent = data.metrics.complete;
  metricSpeed.textContent = data.metrics.speed;
  metricQuestion.textContent = data.metrics.question;

  llmStructure.textContent = data.llm.structure;
  llmConcept.textContent = data.llm.concept;
  llmPractice.textContent = data.llm.practice;
  llmInteraction.textContent = data.llm.interaction;

  renderChunks(data.chunks);
  setHeroPreview(data.overall.score, data.weaknesses);
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
  const overallScoreValue = Math.round((structureScore + deliveryScore + interactionScore) / 3);
  const recommendations = [
    "전환 구간에 요약 문장을 추가하세요.",
    "질문 템플릿을 고정해 상호작용을 유지하세요.",
  ];
  const weaknesses = [
    "중반부 반복 표현이 다소 많습니다.",
    "속도 변동 구간에서 집중이 약해집니다.",
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
    },
    strengths: [
      "핵심 개념 전개가 안정적으로 이어집니다.",
      "질문 유도와 정리 멘트가 명확합니다.",
      "예시 흐름이 학습 목표와 잘 연결됩니다.",
    ],
    weaknesses,
    risks: weaknesses,
    primary_action: recommendations[0],
    recommendations,
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


