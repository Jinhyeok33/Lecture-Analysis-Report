"""
Generate a polished lecture-analysis PDF report from analysis JSON.
"""

from __future__ import annotations

import argparse
import html
import io
import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

PAGE_W, PAGE_H = A4

# Color system (vivid orange mood)
C_PRIMARY = colors.HexColor("#FF7A00")
C_PRIMARY_DARK = colors.HexColor("#E65E00")
C_ACCENT = colors.HexColor("#FFA347")
C_SURFACE = colors.HexColor("#FFF5EA")
C_SURFACE_ALT = colors.HexColor("#FFE8CF")
C_BORDER = colors.HexColor("#EBC79E")
C_TEXT = colors.HexColor("#241A12")
C_MUTED = colors.HexColor("#6B4E37")
C_SUCCESS = colors.HexColor("#3F8F57")
C_WARNING = colors.HexColor("#C6842F")
C_DANGER = colors.HexColor("#BF5147")
C_WHITE = colors.white

CHART_BG = "#FFF7EE"
CHART_GRID = "#E2C6A8"
CHART_REF = "#C48D57"
CHART_TEXT = "#6B4E37"
CHART_LINE = "#FF7A00"
CHART_LINE_SOFT = "#FFD7AF"
CHART_RING_DARK = "#E65E00"
CHART_RING_LIGHT = "#FFD7AF"

CATEGORY_ORDER = [
    "lecture_structure",
    "concept_clarity",
    "practice_linkage",
    "interaction",
]

CATEGORY_LABELS = {
    "lecture_structure": "강의 구조",
    "concept_clarity": "개념 명확성",
    "practice_linkage": "실습 연계",
    "interaction": "상호작용",
}

SUBITEM_LABELS = {
    "learning_objective_intro": "학습 목표 안내",
    "previous_lesson_linkage": "이전 수업 연계",
    "explanation_sequence": "설명 순서",
    "key_point_emphasis": "핵심 포인트 강조",
    "closing_summary": "마무리 요약",
    "concept_definition": "개념 정의",
    "analogy_example_usage": "비유/예시 활용",
    "prerequisite_check": "선수 개념 확인",
    "example_appropriateness": "예시 적절성",
    "practice_transition": "실습 전환",
    "error_handling": "오류 대응",
    "participation_induction": "참여 유도",
    "question_response_sufficiency": "질문 응답 충분성",
}

SUBITEM_DESCRIPTIONS = {
    "learning_objective_intro": "수업 시작 학습 목표 안내를 확인합니다.",
    "previous_lesson_linkage": "이전 수업 연계와 내용 설명을 확인합니다.",
    "explanation_sequence": "설명 순서와 내용 요약을 확인합니다.",
    "key_point_emphasis": "핵심 포인트 강조와 반복 표현을 확인합니다.",
    "closing_summary": "마무리 요약과 핵심 내용 정리를 확인합니다.",
    "concept_definition": "개념 정의 설명의 명확성을 확인합니다.",
    "analogy_example_usage": "비유 예시 활용과 내용 설명을 확인합니다.",
    "prerequisite_check": "선수 개념 확인과 수업 연계를 확인합니다.",
    "example_appropriateness": "예시 적절성과 수업 내용 연계를 확인합니다.",
    "practice_transition": "실습 전환과 설명 순서를 확인합니다.",
    "error_handling": "오류 대응 설명과 내용 정리를 확인합니다.",
    "participation_induction": "참여 유도 질문과 응답 내용을 확인합니다.",
    "question_response_sufficiency": "질문 응답 내용과 충분성을 확인합니다.",
}


FONT_CANDIDATES = [
    {
        "regular_name": "MalgunGothic",
        "bold_name": "MalgunGothicBold",
        "regular_path": "C:/Windows/Fonts/malgun.ttf",
        "bold_path": "C:/Windows/Fonts/malgunbd.ttf",
        "matplotlib_family": "Malgun Gothic",
    },
    {
        "regular_name": "NanumGothic",
        "bold_name": "NanumGothicBold",
        "regular_path": "C:/Windows/Fonts/NanumGothic.ttf",
        "bold_path": "C:/Windows/Fonts/NanumGothicBold.ttf",
        "matplotlib_family": "NanumGothic",
    },
    {
        "regular_name": "NanumGothic",
        "bold_name": "NanumGothicBold",
        "regular_path": "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "bold_path": "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
        "matplotlib_family": "NanumGothic",
    },
]


def _register_font(name: str, path: Path) -> bool:
    if name in pdfmetrics.getRegisteredFontNames():
        return True
    try:
        pdfmetrics.registerFont(TTFont(name, str(path)))
        return True
    except Exception:
        return False


def register_korean_fonts() -> tuple[str, str, list[str]]:
    for candidate in FONT_CANDIDATES:
        reg_path = Path(candidate["regular_path"])
        if not reg_path.exists():
            continue

        reg_name = candidate["regular_name"]
        bold_name = candidate["bold_name"]

        if not _register_font(reg_name, reg_path):
            continue

        bold_path = Path(candidate["bold_path"])
        if bold_path.exists():
            _register_font(bold_name, bold_path)
        else:
            bold_name = reg_name

        return reg_name, bold_name, [candidate["matplotlib_family"]]

    print("[경고] 한글 폰트를 찾지 못해 기본 폰트를 사용합니다.")
    return "Helvetica", "Helvetica-Bold", ["DejaVu Sans"]


def setup_matplotlib_fonts(font_families: list[str]) -> None:
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = font_families + [
        "AppleGothic",
        "Arial Unicode MS",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False


def as_text(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text if text else fallback


def esc(value: Any, fallback: str = "-") -> str:
    return html.escape(as_text(value, fallback)).replace("\n", "<br/>")


def as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def average(values: list[float]) -> float:
    valid = [v for v in values if isinstance(v, (int, float))]
    if not valid:
        return 0.0
    return round(sum(valid) / len(valid), 2)


def score_color_hex(score: float) -> str:
    if score >= 4.0:
        return "#2C9A5E"
    if score >= 3.0:
        return "#C9892D"
    return "#C94F4F"


def score_grade(score: float) -> str:
    if score >= 4.5:
        return "매우 우수"
    if score >= 4.0:
        return "우수"
    if score >= 3.5:
        return "양호"
    if score >= 3.0:
        return "보통"
    if score >= 2.0:
        return "개선 필요"
    return "위험"


def pct(value: float) -> str:
    return f"{value * 100:.1f}%"


def category_averages(summary_scores: dict[str, dict[str, float]]) -> dict[str, float]:
    return {
        key: average([as_float(v) for v in summary_scores.get(key, {}).values()])
        for key in CATEGORY_ORDER
    }


def overall_score(cat_avgs: dict[str, float]) -> float:
    scores = [v for v in cat_avgs.values() if v > 0]
    return average(scores)


def flatten_scores(summary_scores: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cat_key in CATEGORY_ORDER:
        cat_name = CATEGORY_LABELS.get(cat_key, cat_key)
        for item_key, value in summary_scores.get(cat_key, {}).items():
            score = as_float(value)
            rows.append(
                {
                    "category_key": cat_key,
                    "category": cat_name,
                    "item_key": item_key,
                    "item": SUBITEM_LABELS.get(item_key, item_key),
                    "score": score,
                }
            )
    return rows


def make_styles(reg: str, bold: str) -> dict[str, ParagraphStyle]:
    def ps(name: str, **kwargs: Any) -> ParagraphStyle:
        return ParagraphStyle(name, **kwargs)

    return {
        "cover_title": ps(
            "CoverTitle",
            fontName=bold,
            fontSize=27,
            leading=34,
            textColor=C_WHITE,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "cover_sub": ps(
            "CoverSub",
            fontName=reg,
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#FFE5CF"),
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "section_title": ps(
            "SectionTitle",
            fontName=bold,
            fontSize=16,
            leading=22,
            textColor=C_WHITE,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "section_sub": ps(
            "SectionSub",
            fontName=reg,
            fontSize=10,
            leading=15,
            textColor=colors.HexColor("#FFE5CF"),
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "title": ps(
            "Title",
            fontName=bold,
            fontSize=13,
            leading=18,
            textColor=C_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "body": ps(
            "Body",
            fontName=reg,
            fontSize=10.5,
            leading=16,
            textColor=C_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "small": ps(
            "Small",
            fontName=reg,
            fontSize=9,
            leading=14,
            textColor=C_MUTED,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "bullet": ps(
            "Bullet",
            fontName=reg,
            fontSize=10.2,
            leading=16,
            textColor=C_TEXT,
            leftIndent=12,
            firstLineIndent=-8,
            wordWrap="CJK",
        ),
        "evidence": ps(
            "Evidence",
            fontName=reg,
            fontSize=9.2,
            leading=14,
            textColor=C_MUTED,
            leftIndent=16,
            wordWrap="CJK",
        ),
        "metric_label": ps(
            "MetricLabel",
            fontName=reg,
            fontSize=9,
            leading=12,
            textColor=C_MUTED,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "metric_value": ps(
            "MetricValue",
            fontName=bold,
            fontSize=21,
            leading=26,
            textColor=C_PRIMARY,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "metric_help": ps(
            "MetricHelp",
            fontName=reg,
            fontSize=8.5,
            leading=12,
            textColor=C_MUTED,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "table_header": ps(
            "TableHeader",
            fontName=bold,
            fontSize=9,
            leading=12,
            textColor=C_WHITE,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "table_cell": ps(
            "TableCell",
            fontName=reg,
            fontSize=9.3,
            leading=13.5,
            textColor=C_TEXT,
            alignment=TA_LEFT,
            wordWrap="CJK",
        ),
        "table_center": ps(
            "TableCenter",
            fontName=reg,
            fontSize=9.2,
            leading=13,
            textColor=C_TEXT,
            alignment=TA_CENTER,
            wordWrap="CJK",
        ),
        "table_number": ps(
            "TableNumber",
            fontName=bold,
            fontSize=9.3,
            leading=13,
            textColor=C_TEXT,
            alignment=TA_RIGHT,
            wordWrap="CJK",
        ),
    }


def page_callback(reg_font: str):
    def on_page(canvas, doc) -> None:
        canvas.saveState()
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.7)
        canvas.line(
            doc.leftMargin,
            doc.bottomMargin - 0.22 * cm,
            PAGE_W - doc.rightMargin,
            doc.bottomMargin - 0.22 * cm,
        )

        canvas.setFont(reg_font, 8.5)
        canvas.setFillColor(C_MUTED)
        canvas.drawString(doc.leftMargin, doc.bottomMargin - 0.7 * cm, "EduInsight AI | 강의 분석 리포트")
        canvas.drawRightString(PAGE_W - doc.rightMargin, doc.bottomMargin - 0.7 * cm, str(doc.page))
        canvas.restoreState()

    return on_page


def section_header(title: str, subtitle: str, styles: dict[str, ParagraphStyle], width: float) -> Table:
    table = Table(
        [
            [Paragraph(esc(title), styles["section_title"])],
            [Paragraph(esc(subtitle), styles["section_sub"])],
        ],
        colWidths=[width],
    )
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
                ("TOPPADDING", (0, 0), (-1, 0), 12),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 12),
                ("LEFTPADDING", (0, 0), (-1, -1), 14),
                ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ]
        )
    )
    return table


def metric_card(
    label: str,
    value: str,
    caption: str,
    styles: dict[str, ParagraphStyle],
    width: float,
    bg: colors.Color = C_SURFACE,
) -> Table:
    card = Table(
        [
            [Paragraph(esc(label), styles["metric_label"])],
            [Paragraph(esc(value), styles["metric_value"])],
            [Paragraph(esc(caption), styles["metric_help"])],
        ],
        colWidths=[width],
    )
    card.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), bg),
                ("BOX", (0, 0), (-1, -1), 0.8, C_BORDER),
                ("TOPPADDING", (0, 0), (-1, 0), 9),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                ("TOPPADDING", (0, 1), (-1, 1), 2),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 2),
                ("TOPPADDING", (0, 2), (-1, 2), 2),
                ("BOTTOMPADDING", (0, 2), (-1, 2), 8),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    return card


def fig_to_buffer(fig, dpi: int = 220) -> io.BytesIO:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def fit_image(buf: io.BytesIO, max_width: float, max_height: float, h_align: str = "CENTER") -> Image:
    buf.seek(0)
    img_reader = ImageReader(buf)
    orig_w, orig_h = img_reader.getSize()
    scale = min(max_width / orig_w, max_height / orig_h)
    scale = max(0.01, min(scale, 1.6))
    image = Image(buf, width=orig_w * scale, height=orig_h * scale)
    image.hAlign = h_align
    return image

def chart_radar(cat_avgs: dict[str, float]) -> io.BytesIO | None:
    labels = [CATEGORY_LABELS[key] for key in CATEGORY_ORDER]
    values = [cat_avgs.get(key, 0.0) for key in CATEGORY_ORDER]
    if not any(v > 0 for v in values):
        return None

    n = len(labels)
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    values_closed = values + values[:1]
    angles_closed = angles + angles[:1]

    fig, ax = plt.subplots(figsize=(5.5, 5.0), subplot_kw={"polar": True})
    ax.set_facecolor(CHART_BG)

    ax.set_xticks(angles)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=8, color=CHART_TEXT)
    ax.grid(color=CHART_GRID, linestyle="--", linewidth=0.8)
    ax.spines["polar"].set_color(CHART_GRID)

    base_line = [3.0] * n + [3.0]
    ax.plot(angles_closed, base_line, color=CHART_REF, linewidth=1.2, linestyle="--")

    ax.plot(angles_closed, values_closed, color=CHART_LINE, linewidth=2.4, marker="o")
    ax.fill(angles_closed, values_closed, color=CHART_LINE, alpha=0.24)

    for angle, value in zip(angles, values):
        ax.text(
            angle,
            min(value + 0.45, 5.25),
            f"{value:.2f}",
            ha="center",
            va="center",
            fontsize=8.5,
            color=score_color_hex(value),
            fontweight="bold",
        )

    fig.tight_layout()
    return fig_to_buffer(fig)


def chart_repeat_expressions(repeat_expr: dict[str, Any], top_n: int = 10) -> io.BytesIO | None:
    if not repeat_expr:
        return None

    items = sorted(((as_text(k), int(v)) for k, v in repeat_expr.items()), key=lambda x: x[1], reverse=True)[:top_n]
    if not items:
        return None

    labels = [item[0] for item in items]
    values = [item[1] for item in items]
    max_value = max(values)

    fig_h = max(3.8, len(items) * 0.5 + 1.6)
    fig, ax = plt.subplots(figsize=(7.4, fig_h))
    ax.set_facecolor(CHART_BG)

    y = np.arange(len(labels))
    bar_colors = [CHART_LINE if idx == 0 else CHART_LINE_SOFT for idx in range(len(labels))]
    bars = ax.barh(y, values, color=bar_colors, edgecolor="white", linewidth=0.7)
    ax.invert_yaxis()

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlim(0, max_value * 1.22)
    ax.set_xlabel("등장 횟수", fontsize=9, color=CHART_TEXT)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width() + max_value * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{value}회",
            va="center",
            fontsize=9,
            color=CHART_TEXT,
        )

    ax.tick_params(axis="x", labelsize=8, colors=CHART_TEXT)
    ax.tick_params(axis="y", labelsize=10, colors=CHART_TEXT)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(CHART_GRID)
    ax.spines["bottom"].set_color(CHART_GRID)

    fig.tight_layout()
    return fig_to_buffer(fig)


def chart_speech_style(speech_ratio: dict[str, Any]) -> io.BytesIO | None:
    formal = as_float(speech_ratio.get("formal", 0.0))
    informal = as_float(speech_ratio.get("informal", 0.0))
    if formal == 0 and informal == 0:
        return None

    fig, ax = plt.subplots(figsize=(4.1, 4.1))
    ax.pie(
        [formal, informal],
        colors=[CHART_RING_DARK, CHART_RING_LIGHT],
        startangle=90,
        wedgeprops={"width": 0.48, "edgecolor": "white", "linewidth": 2},
    )
    ax.text(0, 0, f"{formal * 100:.0f}%\n격식체", ha="center", va="center", fontsize=12, fontweight="bold")
    ax.legend(["격식체", "비격식체"], loc="lower center", bbox_to_anchor=(0.5, -0.16), ncol=2, frameon=False, fontsize=9)
    fig.tight_layout()
    return fig_to_buffer(fig)


def chart_subitem_scores(summary_scores: dict[str, dict[str, float]]) -> io.BytesIO | None:
    rows = flatten_scores(summary_scores)
    if not rows:
        return None

    labels = [f"{row['category']} · {row['item']}" for row in rows]
    scores = [row["score"] for row in rows]
    colors_map = [score_color_hex(v) for v in scores]

    fig_h = max(4.8, min(10.2, len(rows) * 0.45 + 1.8))
    fig, ax = plt.subplots(figsize=(8.6, fig_h))
    ax.set_facecolor(CHART_BG)

    y = np.arange(len(labels))
    bars = ax.barh(y, scores, color=colors_map, alpha=0.85, edgecolor="white", linewidth=0.6)
    ax.invert_yaxis()

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.3)
    ax.set_xlim(0, 5.4)
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.axvline(3.0, color=CHART_REF, linestyle="--", linewidth=1.1)

    for bar, score in zip(bars, scores):
        ax.text(
            min(score + 0.07, 5.25),
            bar.get_y() + bar.get_height() / 2,
            f"{score:.1f}",
            va="center",
            fontsize=8.3,
            color=score_color_hex(score),
            fontweight="bold",
        )

    ax.tick_params(axis="x", labelsize=8, colors=CHART_TEXT)
    ax.tick_params(axis="y", labelsize=8.2, colors=CHART_TEXT)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color(CHART_GRID)
    ax.spines["bottom"].set_color(CHART_GRID)

    fig.tight_layout()
    return fig_to_buffer(fig)

def build_cover(data: dict[str, Any], analysis: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> list:
    story: list = []

    meta = data.get("metadata", {})
    sessions = meta.get("sessions", []) if isinstance(meta.get("sessions", []), list) else []
    language = analysis.get("language_quality", {})
    interaction_metrics = analysis.get("interaction_metrics", {})
    summary_scores = analysis.get("summary_scores", {})

    cat_avgs = category_averages(summary_scores)
    overall = overall_score(cat_avgs)

    hero = Table(
        [
            [Paragraph("EduInsight AI 강의 분석 리포트", styles["cover_title"])],
            [Paragraph(esc(meta.get("course_name", "강의 정보 없음")), styles["cover_sub"])],
            [
                Paragraph(
                    esc(f"{as_text(meta.get('date'))} | 강사: {as_text(meta.get('instructor'))}"),
                    styles["cover_sub"],
                )
            ],
        ],
        colWidths=[width],
    )
    hero.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY_DARK),
                ("TOPPADDING", (0, 0), (-1, 0), 22),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 4),
                ("TOPPADDING", (0, 1), (-1, 2), 0),
                ("BOTTOMPADDING", (0, 1), (-1, 2), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 16),
                ("RIGHTPADDING", (0, 0), (-1, -1), 16),
            ]
        )
    )
    story.append(hero)
    story.append(Spacer(1, 0.45 * cm))

    repeat_ratio = as_float(language.get("repeat_ratio", 0.0))
    complete_ratio = max(0.0, 1.0 - as_float(language.get("incomplete_sentence_ratio", 0.0)))
    q_count = int(as_float(interaction_metrics.get("understanding_question_count", 0)))

    card_width = (width - 1.2 * cm) / 4
    cards = [
        metric_card("종합 점수", f"{overall:.2f}", "5점 만점", styles, card_width, C_SURFACE),
        metric_card("반복 표현", pct(repeat_ratio), "전체 발화 대비", styles, card_width, C_SURFACE),
        metric_card("문장 완결률", pct(complete_ratio), "완결 문장 비율", styles, card_width, C_SURFACE),
        metric_card("이해 확인 질문", f"{q_count}회", "수업 중 질문 수", styles, card_width, C_SURFACE),
    ]
    cards_table = Table([cards], colWidths=[card_width] * 4)
    cards_table.setStyle(
        TableStyle(
            [
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(cards_table)
    story.append(Spacer(1, 0.45 * cm))

    info_rows = [
        [Paragraph("강의명", styles["table_header"]), Paragraph(esc(meta.get("course_name")), styles["table_cell"])],
        [Paragraph("강의일", styles["table_header"]), Paragraph(esc(meta.get("date")), styles["table_cell"])],
        [Paragraph("주강사", styles["table_header"]), Paragraph(esc(meta.get("instructor")), styles["table_cell"])],
        [Paragraph("보조강사", styles["table_header"]), Paragraph(esc(meta.get("sub_instructor")), styles["table_cell"])],
        [Paragraph("강의 ID", styles["table_header"]), Paragraph(esc(data.get("lecture_id")), styles["table_cell"])],
        [Paragraph("세션 수", styles["table_header"]), Paragraph(esc(str(len(sessions))), styles["table_cell"])],
    ]
    info_table = Table(info_rows, colWidths=[3.2 * cm, width - 3.2 * cm])
    info_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), C_PRIMARY),
                ("ROWBACKGROUNDS", (1, 0), (1, -1), [colors.white, C_SURFACE]),
                ("GRID", (0, 0), (-1, -1), 0.7, C_BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(info_table)

    if sessions:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("세션 구성", styles["title"]))
        story.append(Spacer(1, 0.12 * cm))

        session_widths = [1.2 * cm, 2.8 * cm, 4.0 * cm, max(4.5 * cm, width - 8.0 * cm)]
        session_rows = [
            [
                Paragraph("번호", styles["table_header"]),
                Paragraph("시간", styles["table_header"]),
                Paragraph("주제", styles["table_header"]),
                Paragraph("내용", styles["table_header"]),
            ]
        ]
        for idx, session in enumerate(sessions, start=1):
            session_rows.append(
                [
                    Paragraph(str(idx), styles["table_center"]),
                    Paragraph(esc(session.get("time")), styles["table_center"]),
                    Paragraph(esc(session.get("subject")), styles["table_cell"]),
                    Paragraph(esc(session.get("content")), styles["table_cell"]),
                ]
            )

        session_table = Table(session_rows, colWidths=session_widths, repeatRows=1)
        session_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_SURFACE]),
                    ("GRID", (0, 0), (-1, -1), 0.7, C_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(session_table)

    story.append(PageBreak())
    return story


def build_language_section(analysis: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> list:
    story: list = []

    language = analysis.get("language_quality", {})
    concept = analysis.get("concept_clarity_metrics", {})
    interaction = analysis.get("interaction_metrics", {})

    story.append(section_header("1. 언어 표현 품질 분석", "반복 표현, 문장 완결성, 화법 비율을 기반으로 전달 품질을 진단합니다.", styles, width))
    story.append(Spacer(1, 0.25 * cm))

    repeat_ratio = as_float(language.get("repeat_ratio", 0.0))
    complete_ratio = max(0.0, 1.0 - as_float(language.get("incomplete_sentence_ratio", 0.0)))
    speech_rate = int(as_float(concept.get("speech_rate_wpm", 0.0)))
    question_count = int(as_float(interaction.get("understanding_question_count", 0.0)))

    card_width = (width - 0.9 * cm) / 3
    quality_cards = [
        metric_card("반복 표현 비율", pct(repeat_ratio), "낮을수록 전달 안정", styles, card_width),
        metric_card("문장 완결률", pct(complete_ratio), "높을수록 명료함", styles, card_width),
        metric_card("발화 속도", f"{speech_rate} 단어/분", "권장 범위: 140~180", styles, card_width),
    ]
    card_table = Table([quality_cards], colWidths=[card_width] * 3)
    card_table.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(card_table)
    story.append(Spacer(1, 0.25 * cm))

    story.append(
        Paragraph(
            esc(
                f"이해 확인 질문은 총 {question_count}회로 집계되었습니다. "
                f"반복 표현 비율은 {pct(repeat_ratio)}, 문장 완결률은 {pct(complete_ratio)}입니다."
            ),
            styles["body"],
        )
    )
    story.append(Spacer(1, 0.18 * cm))
    story.append(HRFlowable(width="100%", thickness=0.7, color=C_BORDER))
    story.append(Spacer(1, 0.25 * cm))

    repeat_chart = chart_repeat_expressions(language.get("repeat_expressions", {}))
    style_chart = chart_speech_style(language.get("speech_style_ratio", {}))

    chart_cells = []
    if repeat_chart:
        left_block = [Paragraph("상위 반복 표현", styles["title"]), Spacer(1, 0.08 * cm), fit_image(repeat_chart, width * 0.66, 9.2 * cm)]
        chart_cells.append(left_block)
    else:
        chart_cells.append([Paragraph("반복 표현 데이터가 없습니다.", styles["small"])])

    if style_chart:
        right_block = [Paragraph("화법 비율", styles["title"]), Spacer(1, 0.08 * cm), fit_image(style_chart, width * 0.30, 5.6 * cm)]
        chart_cells.append(right_block)
    else:
        chart_cells.append([Paragraph("화법 비율 데이터가 없습니다.", styles["small"])])

    layout = Table([chart_cells], colWidths=[width * 0.68, width * 0.32])
    layout.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(layout)

    repeat_expr = language.get("repeat_expressions", {})
    items = sorted(((as_text(k), int(v)) for k, v in repeat_expr.items()), key=lambda x: x[1], reverse=True)[:8]
    if items:
        story.append(Spacer(1, 0.25 * cm))
        story.append(Paragraph("반복 표현 상세", styles["title"]))
        total = max(1, sum(v for _, v in items))
        rows = [[Paragraph("표현", styles["table_header"]), Paragraph("횟수", styles["table_header"]), Paragraph("비중", styles["table_header"])]]
        for expr, count in items:
            rows.append(
                [
                    Paragraph(esc(expr), styles["table_cell"]),
                    Paragraph(f"{count}회", styles["table_center"]),
                    Paragraph(pct(count / total), styles["table_center"]),
                ]
            )

        tbl = Table(rows, colWidths=[width * 0.56, width * 0.20, width * 0.24], repeatRows=1)
        tbl.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_SURFACE]),
                    ("GRID", (0, 0), (-1, -1), 0.7, C_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        story.append(tbl)

    story.append(PageBreak())
    return story

def build_scores_section(analysis: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> list:
    story: list = []

    summary_scores = analysis.get("summary_scores", {})
    if not summary_scores:
        return story

    cat_avgs = category_averages(summary_scores)
    overall = overall_score(cat_avgs)

    story.append(
        section_header(
            "2. 종합 점수 분석",
            "항목 점수와 종합 점수를 함께 확인합니다.",
            styles,
            width,
        )
    )
    story.append(Spacer(1, 0.28 * cm))

    top_cards = [
        metric_card("종합 점수", f"{overall:.2f}", f"등급: {score_grade(overall)}", styles, (width - 0.6 * cm) / 2),
        metric_card("항목 점수", f"{overall - 3.0:+.2f}", "기준점(3.00) 대비", styles, (width - 0.6 * cm) / 2, C_SURFACE_ALT),
    ]
    top_tbl = Table([top_cards], colWidths=[(width - 0.6 * cm) / 2, (width - 0.6 * cm) / 2])
    top_tbl.setStyle(TableStyle([("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.append(top_tbl)
    story.append(Spacer(1, 0.25 * cm))

    radar = chart_radar(cat_avgs)
    cat_rows = [
        [
            Paragraph("항목", styles["table_header"]),
            Paragraph("점수", styles["table_header"]),
            Paragraph("내용", styles["table_header"]),
        ]
    ]
    for key in CATEGORY_ORDER:
        value = cat_avgs.get(key, 0.0)
        cat_rows.append(
            [
                Paragraph(CATEGORY_LABELS.get(key, key), styles["table_cell"]),
                Paragraph(
                    f"{value:.2f}",
                    ParagraphStyle(
                        "tmp",
                        parent=styles["table_center"],
                        textColor=colors.HexColor(score_color_hex(value)),
                        fontName=styles["table_center"].fontName,
                    ),
                ),
                Paragraph(
                    score_grade(value),
                    ParagraphStyle("tmp2", parent=styles["table_center"], textColor=colors.HexColor(score_color_hex(value))),
                ),
            ]
        )

    def _styled_cat_table(total_width: float) -> Table:
        table = Table(
            cat_rows,
            colWidths=[total_width * 0.52, total_width * 0.20, total_width * 0.28],
            repeatRows=1,
        )
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_SURFACE]),
                    ("GRID", (0, 0), (-1, -1), 0.7, C_BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ]
            )
        )
        return table

    if radar:
        right_width = width * 0.40
        cat_table = _styled_cat_table(right_width)
        radar_img = fit_image(radar, width * 0.57, 8.2 * cm)
        radar_layout = Table([[radar_img, cat_table]], colWidths=[width * 0.60, right_width])
        radar_layout.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
        story.append(KeepTogether([radar_layout]))
    else:
        story.append(_styled_cat_table(width * 0.64))

    story.append(Spacer(1, 0.24 * cm))
    story.append(Paragraph("항목 점수", styles["title"]))

    subitem_chart = chart_subitem_scores(summary_scores)
    if subitem_chart:
        story.append(fit_image(subitem_chart, width, 9.6 * cm))

    rows = flatten_scores(summary_scores)
    if rows:
        # split tables away from charts to prevent clipping
        story.append(PageBreak())
        story.append(
            section_header(
                "2-1. 항목 점수",
                "항목 점수와 항목 설명을 함께 확인합니다.",
                styles,
                width,
            )
        )
        story.append(Spacer(1, 0.2 * cm))

        detail_rows = [
            [
                Paragraph("항목", styles["table_header"]),
                Paragraph("내용", styles["table_header"]),
                Paragraph("점수", styles["table_header"]),
                Paragraph("요약", styles["table_header"]),
            ]
        ]
        for row in rows:
            score = row["score"]
            detail_rows.append(
                [
                    Paragraph(esc(row["category"]), styles["table_cell"]),
                    Paragraph(esc(row["item"]), styles["table_cell"]),
                    Paragraph(f"{score:.1f}", ParagraphStyle("td_num", parent=styles["table_number"], textColor=colors.HexColor(score_color_hex(score)))),
                    Paragraph(score_grade(score), ParagraphStyle("td_grade", parent=styles["table_center"], textColor=colors.HexColor(score_color_hex(score)))),
                ]
            )

        detail_table = Table(detail_rows, colWidths=[width * 0.20, width * 0.44, width * 0.12, width * 0.24], repeatRows=1, splitByRow=1)
        detail_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_SURFACE]),
                    ("GRID", (0, 0), (-1, -1), 0.7, C_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(detail_table)

        story.append(PageBreak())
        story.append(
            section_header(
                "2-2. 항목 설명",
                "세부 평가 항목의 의미를 확인하고 다음 수업 액션을 정리합니다.",
                styles,
                width,
            )
        )
        story.append(Spacer(1, 0.2 * cm))
        story.append(Paragraph("항목 설명", styles["title"]))
        story.append(Paragraph("설명을 확인하고 다음 수업 액션을 정리합니다.", styles["small"]))
        story.append(Spacer(1, 0.1 * cm))

        guide_rows = [[Paragraph("항목", styles["table_header"]), Paragraph("설명", styles["table_header"])]]
        for row in rows:
            guide_rows.append(
                [
                    Paragraph(esc(row["item"]), styles["table_cell"]),
                    Paragraph(esc(SUBITEM_DESCRIPTIONS.get(row["item_key"], "설명 없음")), styles["table_cell"]),
                ]
            )

        guide_table = Table(guide_rows, colWidths=[width * 0.29, width * 0.71], repeatRows=1, splitByRow=1)
        guide_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_SURFACE_ALT]),
                    ("GRID", (0, 0), (-1, -1), 0.7, C_BORDER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ]
            )
        )
        story.append(guide_table)

    return story

def build_insight_section(analysis: dict[str, Any], styles: dict[str, ParagraphStyle], width: float) -> list:
    story: list = []

    strengths = analysis.get("overall_strengths", []) if isinstance(analysis.get("overall_strengths", []), list) else []
    issues = analysis.get("overall_issues", []) if isinstance(analysis.get("overall_issues", []), list) else []
    evidences = analysis.get("overall_evidences", []) if isinstance(analysis.get("overall_evidences", []), list) else []

    story.append(
        section_header(
            "3. 개선 인사이트",
            "강점과 개선 필요 사항을 근거와 함께 명확히 구분해 제시합니다.",
            styles,
            width,
        )
    )
    story.append(Spacer(1, 0.26 * cm))

    strength_bg = C_SURFACE
    strength_bg_alt = C_SURFACE_ALT
    strength_border = C_BORDER
    issue_bg = C_SURFACE
    issue_bg_alt = C_SURFACE_ALT
    issue_border = C_BORDER

    section_label_style = ParagraphStyle(
        "InsightSectionLabel",
        parent=styles["title"],
        fontSize=11,
        leading=14,
        textColor=C_WHITE,
    )

    def insight_label(text: str, bg_color: colors.Color) -> Table:
        label = Table([[Paragraph(esc(text), section_label_style)]], colWidths=[width])
        label.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), bg_color),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ]
            )
        )
        return label

    story.append(insight_label("강의 강점", C_ACCENT))
    story.append(Spacer(1, 0.1 * cm))

    if strengths:
        for idx, value in enumerate(strengths, start=1):
            row = Table([[Paragraph(f"{idx}. {esc(value)}", styles["bullet"])]], colWidths=[width])
            row.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), strength_bg if idx % 2 else strength_bg_alt),
                        ("BOX", (0, 0), (-1, -1), 0.8, strength_border),
                        ("TOPPADDING", (0, 0), (-1, -1), 7),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(row)
            story.append(Spacer(1, 0.08 * cm))
    else:
        row = Table([[Paragraph("- 추출된 강점 정보가 없습니다.", styles["small"])]], colWidths=[width])
        row.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), strength_bg_alt),
                    ("BOX", (0, 0), (-1, -1), 0.8, strength_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(row)

    story.append(Spacer(1, 0.2 * cm))
    story.append(insight_label("개선 필요 사항", C_ACCENT))
    story.append(Spacer(1, 0.1 * cm))

    if issues:
        for idx, issue in enumerate(issues, start=1):
            blocks: list = [Paragraph(f"{idx}. {esc(issue)}", styles["bullet"])]
            if idx - 1 < len(evidences):
                blocks.append(Spacer(1, 0.06 * cm))
                blocks.append(Paragraph(f"근거: {esc(evidences[idx - 1])}", styles["evidence"]))

            row = Table([[blocks]], colWidths=[width])
            row.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), issue_bg if idx % 2 else issue_bg_alt),
                        ("BOX", (0, 0), (-1, -1), 0.8, issue_border),
                        ("TOPPADDING", (0, 0), (-1, -1), 8),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            story.append(row)
            story.append(Spacer(1, 0.09 * cm))
    else:
        row = Table([[Paragraph("- 추출된 개선 이슈 정보가 없습니다.", styles["small"])]], colWidths=[width])
        row.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), issue_bg_alt),
                    ("BOX", (0, 0), (-1, -1), 0.8, issue_border),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ]
            )
        )
        story.append(row)

    return story


def load_analysis_json(path: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            parsed = json.loads(raw.decode(encoding))
            if isinstance(parsed, dict):
                return parsed
            raise ValueError("JSON 루트는 객체(dict)여야 합니다.")
        except UnicodeDecodeError:
            continue

    raise UnicodeDecodeError("analysis_json", raw, 0, len(raw), "지원하는 인코딩(utf-8/cp949/euc-kr)으로 읽지 못했습니다.")


def generate_report(analysis_json_path: str, output_pdf_path: str) -> None:
    data = load_analysis_json(analysis_json_path)

    reg_font, bold_font, mpl_fonts = register_korean_fonts()
    setup_matplotlib_fonts(mpl_fonts)
    styles = make_styles(reg_font, bold_font)

    out_path = Path(output_pdf_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=1.6 * cm,
        rightMargin=1.6 * cm,
        topMargin=1.6 * cm,
        bottomMargin=1.8 * cm,
        title="강의 분석 리포트",
        author="EduInsight AI",
    )

    analysis = data.get("analysis", {})

    story: list = []
    story.extend(build_cover(data, analysis, styles, doc.width))
    story.extend(build_language_section(analysis, styles, doc.width))
    story.extend(build_scores_section(analysis, styles, doc.width))
    story.append(PageBreak())
    story.extend(build_insight_section(analysis, styles, doc.width))

    cb = page_callback(reg_font)
    doc.build(story, onFirstPage=cb, onLaterPages=cb)
    print(f"리포트 생성 완료: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="강의 분석 JSON으로 PDF 리포트를 생성합니다.")
    parser.add_argument("--input", required=True, help="입력 analysis.json 파일 경로")
    parser.add_argument("--output", required=True, help="출력 PDF 파일 경로")
    args = parser.parse_args()

    generate_report(args.input, args.output)









