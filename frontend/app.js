const form = document.getElementById("analysis-form");
const startButton = document.getElementById("start-analysis");
const statusList = Array.from(document.querySelectorAll("#status-list li"));
const statusLive = document.getElementById("status-live");
const progressBar = document.getElementById("progress-bar");
const summaryGrid = document.getElementById("summary-grid");
const lectureInfo = document.getElementById("lecture-info");
const scoreStructure = document.getElementById("score-structure");
const scoreDelivery = document.getElementById("score-delivery");
const scoreInteraction = document.getElementById("score-interaction");
const meterStructure = document.getElementById("meter-structure");
const meterDelivery = document.getElementById("meter-delivery");
const meterInteraction = document.getElementById("meter-interaction");
const strengthList = document.getElementById("strength-list");
const weaknessList = document.getElementById("weakness-list");
const recommendList = document.getElementById("recommend-list");
const chunkList = document.getElementById("chunk-list");
const downloadPdf = document.getElementById("download-pdf");
const downloadJson = document.getElementById("download-json");
const scrollButton = document.querySelector("[data-scroll]");

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

function setActiveStep(index) {
  statusList.forEach((item, idx) => {
    item.classList.toggle("is-active", idx === index);
  });
  const progress = Math.round(((index + 1) / steps.length) * 100);
  progressBar.style.width = `${progress}%`;
  statusLive.textContent = `${steps[index]}…`;
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

function createPdfBlob() {
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

function toScorePercent(scoreText) {
  const parsed = Number.parseInt(scoreText, 10);
  if (Number.isNaN(parsed)) return 0;
  return Math.max(0, Math.min(100, parsed));
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
    const title = document.createElement("strong");
    const summary = document.createElement("p");

    wrapper.className = "chunk";
    title.textContent = chunk.title;
    summary.textContent = chunk.summary;

    wrapper.append(title, summary);
    chunkList.appendChild(wrapper);
  });
}

function setSummaryValues(data) {
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
}

function buildAnalysisData(formValues, file) {
  const seedBase =
    formValues.course_id.length +
    formValues.course_name.length +
    formValues.subject.length +
    formValues.instructor.length +
    formValues.sub_instructor.length;
  const seed = seedBase + (file ? Math.round(file.size / 1024) : 12);

  return {
    ...formValues,
    scores: {
      structure: `${computeScore(seed, 3)}점`,
      delivery: `${computeScore(seed, 5)}점`,
      interaction: `${computeScore(seed, 7)}점`,
    },
    strengths: [
      "핵심 개념 전개가 안정적으로 이어집니다.",
      "질문 유도와 정리 멘트가 명확합니다.",
      "예시 흐름이 학습 목표와 잘 연결됩니다.",
    ],
    weaknesses: [
      "중반부 반복 표현이 다소 많습니다.",
      "속도 변동 구간에서 집중이 약해집니다.",
    ],
    recommendations: [
      "전환 구간에 요약 문장을 추가하세요.",
      "질문 템플릿을 고정해 상호작용을 유지하세요.",
    ],
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
      summary: "요점 정리와 예시가 연결되어 있습니다.",
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
    return;
  }

  isRunning = true;
  disableDownloads();
  summaryGrid.setAttribute("data-ready", "false");

  startButton.textContent = "분석 중…";
  startButton.disabled = true;

  let index = 0;
  setActiveStep(index);

  timerId = window.setInterval(() => {
    index += 1;
    if (index >= steps.length) {
      window.clearInterval(timerId);
      finishAnalysis();
      return;
    }
    setActiveStep(index);
  }, 1100);
}

function finishAnalysis() {
  isRunning = false;
  startButton.textContent = "분석 완료";
  startButton.disabled = false;
  progressBar.style.width = "100%";
  statusLive.textContent = "분석 완료";

  const fileInput = document.getElementById("script-file");
  const file = fileInput.files[0] || null;
  const formValues = getFormValues();
  const analysisData = buildAnalysisData(formValues, file);

  summaryGrid.setAttribute("data-ready", "true");
  setSummaryValues(analysisData);

  const jsonBlob = new Blob([JSON.stringify(analysisData, null, 2)], {
    type: "application/json",
  });
  const pdfBlob = createPdfBlob();

  enableDownloads(pdfBlob, jsonBlob);
}

if (scrollButton) {
  scrollButton.addEventListener("click", () => {
    const target = document.getElementById("input");
    if (target) {
      target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  });
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

window.addEventListener("beforeunload", (event) => {
  if (isRunning) {
    event.preventDefault();
    event.returnValue = "";
  }
});

