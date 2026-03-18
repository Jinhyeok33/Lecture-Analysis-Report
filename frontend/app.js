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

const metadataCsvInput = document.getElementById("metadata-csv");
const csvSessionPicker = document.getElementById("csv-session-picker");
const csvSessionSelect = document.getElementById("csv-session-select");
const csvApplyBtn = document.getElementById("csv-apply");

const steps = ["전처리 중", "청킹 중", "NLP 분석 중", "LLM 분석 중", "리포트 생성 중"];

let isRunning = false;
let toastTimer = null;
let progressTimer = null;


let csvRows = [];
let csvHeaders = [];
const CSV_FIELD_NAMES = [
  "course_id",
  "course_name",
  "date",
  "time",
  "subject",
  "content",
  "instructor",
  "sub_instructor",
];

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
  }, 2500);
}

function disableDownloads() {
  downloadPdf.setAttribute("aria-disabled", "true");
  downloadJson.setAttribute("aria-disabled", "true");
  downloadPdf.removeAttribute("download");
  downloadJson.removeAttribute("download");
  downloadPdf.href = "#";
  downloadJson.href = "#";
}

function enableDownloads(pdfUrl, jsonUrl, lectureId) {
  downloadPdf.setAttribute("aria-disabled", "false");
  downloadJson.setAttribute("aria-disabled", "false");
  downloadPdf.href = pdfUrl;
  downloadJson.href = jsonUrl;
  downloadPdf.setAttribute("download", `report_${lectureId}.pdf`);
  downloadJson.setAttribute("download", `integrated_${lectureId}.json`);
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

function extractNumber(text) {
  const match = `${text}`.match(/-?\d+(\.\d+)?/);
  return match ? Number.parseFloat(match[0]) : NaN;
}

function toScorePercent(scoreText) {
  const value = extractNumber(scoreText);
  if (Number.isNaN(value)) return 0;
  if (value <= 5) return Math.max(0, Math.min(100, Math.round(value * 20)));
  return Math.max(0, Math.min(100, Math.round(value)));
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

function getChunkPriority(chunk) {
  const issues = Array.isArray(chunk.issues) ? chunk.issues.length : 0;
  if (issues >= 2) return "high";
  if (issues === 1) return "medium";
  return "low";
}

function getChunkPriorityLabel(priority) {
  if (priority === "high") return "HIGH";
  if (priority === "medium") return "MEDIUM";
  return "LOW";
}

function renderChunks(chunks) {
  clearChildren(chunkList);
  if (!chunks.length) {
    const emptyText = document.createElement("p");
    emptyText.className = "empty";
    emptyText.textContent = "청크 분석 데이터가 없습니다.";
    chunkList.appendChild(emptyText);
    return;
  }

  chunks.forEach((chunk) => {
    const wrapper = document.createElement("div");
    const head = document.createElement("div");
    const title = document.createElement("strong");
    const badge = document.createElement("span");
    const summary = document.createElement("p");

    const priority = getChunkPriority(chunk);
    const summaryText =
      (Array.isArray(chunk.issues) && chunk.issues[0]) ||
      (Array.isArray(chunk.strengths) && chunk.strengths[0]) ||
      "요약 없음";

    wrapper.className = "chunk";
    head.className = "chunk-head";
    badge.className = `chunk-badge is-${priority}`;
    title.textContent = `Chunk ${chunk.chunk_id ?? "?"}`;
    badge.textContent = getChunkPriorityLabel(priority);
    summary.textContent = summaryText;

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

function averageNumeric(values) {
  const nums = values.filter((v) => typeof v === "number" && Number.isFinite(v));
  if (!nums.length) return 0;
  return nums.reduce((acc, curr) => acc + curr, 0) / nums.length;
}

function avgCategory(summaryScores, key) {
  const category = summaryScores?.[key] || {};
  return averageNumeric(Object.values(category));
}

function toUiData(payload, formValues) {
  const analysisRoot = payload.analysis || {};
  const metadata = analysisRoot.metadata || {};
  const analysis = analysisRoot.analysis || {};
  const summaryScores = analysis.summary_scores || {};

  const structure = avgCategory(summaryScores, "lecture_structure");
  const concept = avgCategory(summaryScores, "concept_clarity");
  const practice = avgCategory(summaryScores, "practice_linkage");
  const interaction = avgCategory(summaryScores, "interaction");

  const overall5 = averageNumeric([structure, concept, practice, interaction]);
  const overall100 = Math.round(overall5 * 20);

  const strengths = Array.isArray(analysis.overall_strengths) && analysis.overall_strengths.length
    ? analysis.overall_strengths
    : ["강점 데이터가 없습니다."];

  const weaknesses = Array.isArray(analysis.overall_issues) && analysis.overall_issues.length
    ? analysis.overall_issues
    : ["개선 이슈 데이터가 없습니다."];

  const recommendations = weaknesses.slice(0, 3).map((text) => `개선: ${text}`);
  const sessions = Array.isArray(metadata.sessions) ? metadata.sessions : [];
  const normalizedFormTime = (formValues.time || "").trim();
  const matchedSession = sessions.find((session) => (session?.time || "").trim() === normalizedFormTime);
  const firstSession = sessions[0] || {};
  const resolvedTime = matchedSession?.time || firstSession.time || formValues.time;

  const repeatRatio = analysis.language_quality?.repeat_ratio;
  const incompleteRatio = analysis.language_quality?.incomplete_sentence_ratio;
  const speedWpm = analysis.concept_clarity_metrics?.speech_rate_wpm;
  const questionCount = analysis.interaction_metrics?.understanding_question_count;

  return {
    course_name: metadata.course_name || formValues.course_name,
    instructor: metadata.instructor || formValues.instructor,
    date: metadata.date || formValues.date,
    time: resolvedTime,
    overall: {
      score: overall100,
      level: getScoreLevel(overall100),
      delta: overall100 - 78,
    },
    scores: {
      structure: structure ? `${structure.toFixed(1)} / 5` : "-",
      delivery: concept ? `${concept.toFixed(1)} / 5` : "-",
      interaction: interaction ? `${interaction.toFixed(1)} / 5` : "-",
    },
    strengths,
    weaknesses,
    risks: weaknesses,
    primary_action: recommendations[0] || "주요 액션 없음",
    recommendations: recommendations.length ? recommendations : ["추천 개선 방향이 없습니다."],
    metrics: {
      repeat: typeof repeatRatio === "number" ? `${(repeatRatio * 100).toFixed(1)}%` : "-",
      complete:
        typeof incompleteRatio === "number" ? `${((1 - incompleteRatio) * 100).toFixed(1)}%` : "-",
      speed: typeof speedWpm === "number" ? `${speedWpm} WPM` : "-",
      question: typeof questionCount === "number" ? `${questionCount}회` : "-",
    },
    llm: {
      structure: structure ? `평균 ${structure.toFixed(1)} / 5` : "-",
      concept: concept ? `평균 ${concept.toFixed(1)} / 5` : "-",
      practice: practice ? `평균 ${practice.toFixed(1)} / 5` : "-",
      interaction: interaction ? `평균 ${interaction.toFixed(1)} / 5` : "-",
    },
    chunks: Array.isArray(payload.chunks) ? payload.chunks : [],
  };
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

function stopProgressAnimation() {
  if (progressTimer) {
    window.clearInterval(progressTimer);
    progressTimer = null;
  }
}

function startProgressAnimation() {
  let index = 0;
  setActiveStep(index);
  stopProgressAnimation();
  progressTimer = window.setInterval(() => {
    if (index < steps.length - 1) {
      index += 1;
      setActiveStep(index);
    }
  }, 3000);
}


function parseCsvLine(line) {
  const result = [];
  let current = "";
  let inQuotes = false;

  for (let i = 0; i < line.length; i += 1) {
    const ch = line[i];
    if (inQuotes) {
      if (ch === '"' && line[i + 1] === '"') {
        current += '"';
        i += 1;
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

function decodeCsvText(buffer) {
  const decoders = [
    { encoding: "utf-8", options: { fatal: true } },
    { encoding: "euc-kr", options: { fatal: true } },
    { encoding: "utf-8", options: { fatal: false } },
  ];

  for (const decoderInfo of decoders) {
    try {
      const decoder = new TextDecoder(decoderInfo.encoding, decoderInfo.options);
      return decoder.decode(buffer);
    } catch (_err) {
      // try next encoding
    }
  }

  throw new Error("Cannot decode CSV. Save file as UTF-8 or CP949(EUC-KR).");
}

function applyRowToForm(headers, row) {
  let applied = 0;
  headers.forEach((header, index) => {
    const key = header.trim().replace(/^﻿/, "").toLowerCase();
    if (!CSV_FIELD_NAMES.includes(key)) return;
    const input = form.querySelector(`[name="${key}"]`);
    if (!input) return;
    input.value = row[index] ?? "";
    applied += 1;
  });
  return applied;
}

function populateCsvSessions(headers, rows) {
  clearChildren(csvSessionSelect);

  const dateIdx = headers.findIndex((h) => h.trim().replace(/^﻿/, "").toLowerCase() === "date");
  const timeIdx = headers.findIndex((h) => h.trim().replace(/^﻿/, "").toLowerCase() === "time");
  const subjectIdx = headers.findIndex((h) => h.trim().replace(/^﻿/, "").toLowerCase() === "subject");

  rows.forEach((row, index) => {
    const option = document.createElement("option");
    const d = dateIdx >= 0 ? row[dateIdx] || "" : "";
    const tm = timeIdx >= 0 ? row[timeIdx] || "" : "";
    const sb = subjectIdx >= 0 ? row[subjectIdx] || "" : "";
    option.value = String(index);
    option.textContent = `${d}  ${tm}  |  ${sb}`.trim();
    csvSessionSelect.appendChild(option);
  });
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
  setRunState("running", "실제 파이프라인 실행 중…");
  startProgressAnimation();

  startButton.textContent = "분석 중…";
  startButton.disabled = true;

  const formValues = getFormValues();

  try {
    const body = new FormData(form);
    const response = await fetch("/api/analyze", {
      method: "POST",
      body,
    });

    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `요청 실패 (${response.status})`);
    }

    const uiData = toUiData(payload, formValues);
    summaryGrid.setAttribute("data-ready", "true");
    summaryOverview.setAttribute("data-ready", "true");
    setSummaryValues(uiData);

    enableDownloads(payload.downloads.pdf_url, payload.downloads.json_url, payload.lecture_id);

    stopProgressAnimation();
    setActiveStep(steps.length - 1);
    setRunState("done", "분석 완료");
    showToast("실제 분석이 완료되어 다운로드가 활성화되었습니다.");
  } catch (error) {
    stopProgressAnimation();
    setRunState("error", "분석 실패");
    showToast(error instanceof Error ? error.message : "분석 중 오류가 발생했습니다.");
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


if (metadataCsvInput) {
  metadataCsvInput.addEventListener("change", () => {
    const file = metadataCsvInput.files && metadataCsvInput.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      try {
        const buffer = event.target?.result;
        if (!(buffer instanceof ArrayBuffer)) {
          throw new Error("Could not read CSV file.");
        }

        const text = decodeCsvText(buffer);
        const lines = text.split(/\r?\n/).filter((line) => line.trim());
        if (lines.length < 2) {
          throw new Error("CSV must include header and at least one data row.");
        }

        csvHeaders = parseCsvLine(lines[0]);
        csvRows = lines.slice(1).map((line) => parseCsvLine(line));

        if (csvRows.length === 1) {
          const applied = applyRowToForm(csvHeaders, csvRows[0]);
          if (csvSessionPicker) csvSessionPicker.hidden = true;
          showToast(applied > 0 ? `Applied ${applied} fields from CSV.` : "CSV headers do not match expected fields.");
          return;
        }

        populateCsvSessions(csvHeaders, csvRows);
        if (csvSessionPicker) csvSessionPicker.hidden = false;
        showToast(`Loaded ${csvRows.length} sessions. Select one to apply.`);
      } catch (error) {
        showToast(error instanceof Error ? error.message : "Error while processing CSV.");
      }
    };
    reader.readAsArrayBuffer(file);
  });
}

if (csvApplyBtn) {
  csvApplyBtn.addEventListener("click", () => {
    const selected = Number(csvSessionSelect?.value ?? -1);
    if (!Number.isInteger(selected) || selected < 0 || selected >= csvRows.length) {
      showToast("No applicable fields found in selected session.");
      return;
    }

    const applied = applyRowToForm(csvHeaders, csvRows[selected]);
    showToast(applied > 0 ? `Applied ${applied} fields from selected session.` : "No applicable fields found in selected session.");
  });
}

startButton.addEventListener("click", () => {
  void startAnalysis();
});

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
