"""
Report Generator: analysis.json → analysis.pdf

강의 분석 결과를 시각적인 PDF 리포트로 변환합니다.

PDF 구성:
  1. 커버 페이지        (강의 기본 정보 + 종합 점수 요약)
  2. 언어 표현 품질 분석  (NLP 정량 지표 + 반복 표현 차트 + 발화 스타일)
  3. 강의 품질 종합 평가  (레이더 차트 + 카테고리별 세부 점수)
  4. 강의 개선 인사이트   (강점 / 개선 필요 사항 + 근거)
"""

import io
import json
import math
import argparse
from pathlib import Path

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

matplotlib.use("Agg")

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    KeepTogether,
)

# ──────────────────────────────────────────────────────────────────────────────
# 전역 설정
# ──────────────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4
CONTENT_W = PAGE_W - 4 * cm  # 좌우 마진 2cm씩

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

# ── 색상 팔레트 ──
# Primary tones
C_PRIMARY = colors.HexColor("#1B3A5C")       # 딥 네이비
C_PRIMARY_LIGHT = colors.HexColor("#2E5C8A")  # 밝은 네이비
C_ACCENT = colors.HexColor("#E8792F")         # 오렌지 액센트
C_ACCENT_LIGHT = colors.HexColor("#F5A623")   # 밝은 오렌지

# Semantic
C_SUCCESS = colors.HexColor("#2E7D4F")
C_SUCCESS_BG = colors.HexColor("#E8F5E9")
C_WARNING = colors.HexColor("#E8792F")
C_WARNING_BG = colors.HexColor("#FFF3E0")
C_DANGER = colors.HexColor("#C0392B")
C_DANGER_BG = colors.HexColor("#FDECEA")

# Neutrals
C_TEXT = colors.HexColor("#1A1A2E")
C_TEXT_SECONDARY = colors.HexColor("#5A6678")
C_BORDER = colors.HexColor("#D0D5DD")
C_LIGHT_BG = colors.HexColor("#F8F9FC")
C_CARD_BG = colors.HexColor("#FFFFFF")
C_WHITE = colors.white

# Chart palette
CH_BG = "#FAFBFE"
CH_GRID = "#E0E4EC"
CH_PRIMARY = "#2E5C8A"
CH_ACCENT = "#E8792F"
CH_SUCCESS = "#2E7D4F"
CH_DANGER = "#C0392B"
CH_LIGHT = "#B0C4DE"
CH_FILL = "#D6E4F0"

CAT_COLORS = {
    "lecture_structure": "#2E5C8A",
    "concept_clarity": "#E8792F",
    "practice_linkage": "#2E7D4F",
    "interaction": "#8E44AD",
}


# ──────────────────────────────────────────────────────────────────────────────
# 폰트 등록
# ──────────────────────────────────────────────────────────────────────────────

FONT_CANDIDATES = [
    ("MalgunGothic", "C:/Windows/Fonts/malgun.ttf"),
    ("MalgunGothicBold", "C:/Windows/Fonts/malgunbd.ttf"),
    ("NanumGothic", "C:/Windows/Fonts/NanumGothic.ttf"),
    ("NanumGothicBold", "C:/Windows/Fonts/NanumGothicBold.ttf"),
    ("NanumGothic", "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"),
    ("NanumGothicBold", "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"),
]


def register_korean_fonts() -> tuple[str, str]:
    global _FONT_REGULAR, _FONT_BOLD

    registered: dict[str, str] = {}
    for name, path in FONT_CANDIDATES:
        if Path(path).exists() and name not in registered:
            try:
                pdfmetrics.registerFont(TTFont(name, path))
                registered[name] = path
            except Exception:
                pass

    if not registered:
        print("[경고] 한국어 폰트를 찾을 수 없습니다. Helvetica로 대체됩니다.")
        return "Helvetica", "Helvetica-Bold"

    regular = next((n for n in registered if "Bold" not in n), list(registered)[0])
    bold = next((n for n in registered if "Bold" in n), regular)

    _FONT_REGULAR = regular
    _FONT_BOLD = bold
    return regular, bold


def setup_matplotlib_korean():
    matplotlib.rcParams["font.family"] = "sans-serif"
    matplotlib.rcParams["font.sans-serif"] = [
        "Malgun Gothic",
        "NanumGothic",
        "AppleGothic",
        "DejaVu Sans",
    ]
    matplotlib.rcParams["axes.unicode_minus"] = False


# ──────────────────────────────────────────────────────────────────────────────
# 점수 유틸리티
# ──────────────────────────────────────────────────────────────────────────────


def score_color(score: float) -> colors.Color:
    if score >= 4.0:
        return C_SUCCESS
    elif score >= 3.0:
        return C_WARNING
    else:
        return C_DANGER


def score_hex(score: float) -> str:
    if score >= 4.0:
        return CH_SUCCESS
    elif score >= 3.0:
        return CH_ACCENT
    else:
        return CH_DANGER


def score_bg(score: float) -> colors.Color:
    if score >= 4.0:
        return C_SUCCESS_BG
    elif score >= 3.0:
        return C_WARNING_BG
    else:
        return C_DANGER_BG


def score_label(score: float) -> str:
    if score >= 4.5:
        return "매우 우수"
    elif score >= 4.0:
        return "우수"
    elif score >= 3.5:
        return "양호"
    elif score >= 3.0:
        return "보통"
    elif score >= 2.0:
        return "미흡"
    else:
        return "개선 필요"


def to_number(value, default: float = 0.0) -> float:
    try:
        num = float(value)
        if math.isnan(num):
            return default
        return num
    except (TypeError, ValueError):
        return default


def cat_avg(cat_scores: dict) -> float:
    if not isinstance(cat_scores, dict):
        return 0.0
    vals = [to_number(v, 0.0) for v in cat_scores.values()]
    return round(sum(vals) / len(vals), 2) if vals else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 스타일 팩토리
# ──────────────────────────────────────────────────────────────────────────────


def make_styles(reg: str, bold: str) -> dict:
    def ps(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        # Cover
        "cover_title": ps(
            "CoverTitle", fontName=bold, fontSize=28, textColor=C_WHITE,
            alignment=TA_CENTER, leading=38,
        ),
        "cover_sub": ps(
            "CoverSub", fontName=reg, fontSize=13, textColor=colors.HexColor("#B0C4DE"),
            alignment=TA_CENTER, spaceAfter=4,
        ),
        # Section headers
        "section_title": ps(
            "SectionTitle", fontName=bold, fontSize=15, textColor=C_PRIMARY,
            spaceBefore=4, spaceAfter=8, leading=22,
        ),
        "section_desc": ps(
            "SectionDesc", fontName=reg, fontSize=9, textColor=C_TEXT_SECONDARY,
            spaceAfter=12, leading=14,
        ),
        "subsection": ps(
            "Subsection", fontName=bold, fontSize=11, textColor=C_PRIMARY,
            spaceBefore=10, spaceAfter=6, leading=16,
        ),
        # Body
        "body": ps(
            "Body", fontName=reg, fontSize=9.5, textColor=C_TEXT,
            spaceAfter=4, leading=15, alignment=TA_JUSTIFY,
        ),
        "body_bold": ps(
            "BodyBold", fontName=bold, fontSize=9.5, textColor=C_TEXT,
            spaceAfter=4, leading=15,
        ),
        "small": ps(
            "Small", fontName=reg, fontSize=8.5, textColor=C_TEXT_SECONDARY,
            spaceAfter=3, leading=13,
        ),
        "evidence": ps(
            "Evidence", fontName=reg, fontSize=8.5, textColor=C_TEXT_SECONDARY,
            leading=13, leftIndent=12, spaceAfter=4,
        ),
        # Badges
        "badge_label": ps(
            "BadgeLabel", fontName=reg, fontSize=8, textColor=C_TEXT_SECONDARY,
            alignment=TA_CENTER, leading=12,
        ),
        "badge_value": ps(
            "BadgeValue", fontName=bold, fontSize=20, textColor=C_PRIMARY,
            alignment=TA_CENTER, leading=26,
        ),
        "badge_unit": ps(
            "BadgeUnit", fontName=reg, fontSize=7.5, textColor=C_TEXT_SECONDARY,
            alignment=TA_CENTER, leading=11,
        ),
        # Tables
        "th": ps(
            "TH", fontName=bold, fontSize=9, textColor=C_WHITE,
            alignment=TA_CENTER, leading=14,
        ),
        "td": ps(
            "TD", fontName=reg, fontSize=9, textColor=C_TEXT, leading=14,
        ),
        "td_center": ps(
            "TDCenter", fontName=reg, fontSize=9, textColor=C_TEXT,
            alignment=TA_CENTER, leading=14,
        ),
        # Insights
        "insight_title": ps(
            "InsightTitle", fontName=bold, fontSize=10.5, textColor=C_WHITE,
            alignment=TA_LEFT, leading=16,
        ),
        "insight_item": ps(
            "InsightItem", fontName=reg, fontSize=9.5, textColor=C_TEXT,
            leading=15, spaceAfter=2,
        ),
        "insight_evidence": ps(
            "InsightEvidence", fontName=reg, fontSize=8.5,
            textColor=C_TEXT_SECONDARY, leading=13, leftIndent=14, spaceAfter=6,
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 차트 생성 (aspect ratio 엄격 유지)
# ──────────────────────────────────────────────────────────────────────────────

# 모든 차트는 (fig_w_inch, fig_h_inch) 와 Image(width_cm, height_cm) 비율을 일치시킴


def chart_radar(summary_scores: dict, fig_w=5.0, fig_h=5.0) -> io.BytesIO:
    """4개 카테고리 평균 점수 레이더 차트."""
    cat_map = {
        "lecture_structure": "강의 구조",
        "concept_clarity": "개념 명확성",
        "practice_linkage": "실습 연계",
        "interaction": "상호작용",
    }
    labels = list(cat_map.values())
    cat_keys = list(cat_map.keys())
    values = [cat_avg(summary_scores.get(k, {})) for k in cat_keys]

    N = len(labels)
    angles = [n / N * 2 * math.pi for n in range(N)]
    angles += angles[:1]
    values_plot = values + [values[0]]

    fig, ax = plt.subplots(figsize=(fig_w, fig_h), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F0F4FA")

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11, fontweight="bold", color="#1A1A2E")
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=7, color="#8A95A8")
    ax.grid(color="#C8D0DC", linewidth=0.6, linestyle="-", alpha=0.7)
    ax.spines["polar"].set_color("#C8D0DC")

    # 기준선 3.0
    ref = [3.0] * (N + 1)
    ax.plot(angles, ref, "--", linewidth=1.2, color="#A0AAB8", alpha=0.7, label="기준 (3.0)")

    # 데이터
    ax.plot(angles, values_plot, "o-", linewidth=2.5, color=CH_PRIMARY,
            markersize=8, markerfacecolor="white", markeredgewidth=2.5,
            markeredgecolor=CH_PRIMARY, zorder=5)
    ax.fill(angles, values_plot, alpha=0.15, color=CH_PRIMARY)

    for angle, val, cat_key in zip(angles[:-1], values, cat_keys):
        color = CAT_COLORS.get(cat_key, CH_PRIMARY)
        offset = 0.45
        ax.text(
            angle, val + offset, f"{val:.1f}",
            ha="center", va="center", fontsize=10,
            color=color, fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white", edgecolor=color,
                      alpha=0.9, linewidth=0.8),
        )

    plt.tight_layout(pad=1.0)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_repeat_expressions(repeat_expr: dict, top_n: int = 8) -> io.BytesIO | None:
    """반복 표현 가로 막대 차트."""
    if not repeat_expr:
        return None

    items = sorted(repeat_expr.items(), key=lambda x: x[1], reverse=True)[:top_n]
    labels = [item[0] for item in items]
    values = [item[1] for item in items]
    max_v = max(values) if values else 1

    fig_h = max(2.5, len(labels) * 0.45 + 0.8)
    fig, ax = plt.subplots(figsize=(5.5, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    bar_colors = []
    for v in values:
        ratio = v / max_v
        if ratio >= 0.7:
            bar_colors.append(CH_DANGER)
        elif ratio >= 0.4:
            bar_colors.append(CH_ACCENT)
        else:
            bar_colors.append(CH_LIGHT)

    y = list(range(len(labels)))
    bars = ax.barh(y, values, color=bar_colors, height=0.55,
                   edgecolor="white", linewidth=0.5, zorder=3)

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10, color="#1A1A2E")
    ax.invert_yaxis()

    for bar, val in zip(bars, values):
        ax.text(
            bar.get_width() + max_v * 0.03,
            bar.get_y() + bar.get_height() / 2,
            f"{val}회", va="center", ha="left", fontsize=9, color="#5A6678",
            fontweight="bold",
        )

    ax.set_xlim(0, max_v * 1.25)
    ax.set_xlabel("사용 횟수", fontsize=8, color="#5A6678")
    ax.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(CH_GRID)
    ax.tick_params(axis="x", labelsize=7, colors="#8A95A8")
    ax.tick_params(axis="y", length=0)
    ax.grid(axis="x", color=CH_GRID, linewidth=0.5, alpha=0.5, zorder=0)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_speech_style(speech_style_ratio: dict) -> io.BytesIO | None:
    """발화 스타일 도넛 차트."""
    formal = speech_style_ratio.get("formal", 0)
    informal = speech_style_ratio.get("informal", 0)
    if formal == 0 and informal == 0:
        return None

    fig, ax = plt.subplots(figsize=(3.0, 3.0))
    fig.patch.set_facecolor("white")

    wedge_colors = [CH_PRIMARY, "#D6E4F0"]
    wedges, _ = ax.pie(
        [formal, informal],
        colors=wedge_colors,
        startangle=90,
        wedgeprops=dict(width=0.45, edgecolor="white", linewidth=2.5),
        counterclock=False,
    )
    ax.text(0, 0.08, f"{formal * 100:.0f}%", ha="center", va="center",
            fontsize=18, fontweight="bold", color=CH_PRIMARY)
    ax.text(0, -0.22, "격식체", ha="center", va="center",
            fontsize=9, color="#5A6678")

    ax.legend(["격식체", "비격식체"], loc="lower center",
              bbox_to_anchor=(0.5, -0.08), fontsize=8, frameon=False, ncol=2,
              handlelength=1.2, columnspacing=1.0)

    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_category_detail(summary_scores: dict) -> io.BytesIO | None:
    """카테고리별 세부 항목 점수 가로 막대 차트 (그룹별 구분)."""
    label_map = {
        "learning_objective_intro": "학습 목표 안내",
        "previous_lesson_linkage": "전날 복습 연계",
        "explanation_sequence": "설명 순서",
        "key_point_emphasis": "핵심 강조",
        "closing_summary": "마무리 요약",
        "concept_definition": "개념 정의",
        "analogy_example_usage": "비유·예시 활용",
        "prerequisite_check": "선행 개념 확인",
        "example_appropriateness": "예시 적절성",
        "practice_transition": "실습 연계",
        "error_handling": "오류 대응",
        "participation_induction": "참여 유도",
        "question_response_sufficiency": "질문 응답 충분성",
    }
    cat_display = {
        "lecture_structure": "강의 구조",
        "concept_clarity": "개념 명확성",
        "practice_linkage": "실습 연계",
        "interaction": "상호작용",
    }

    groups: list[tuple[str, list[tuple[str, float, str]]]] = []
    for cat_key, cat_name in cat_display.items():
        color = CAT_COLORS.get(cat_key, CH_PRIMARY)
        items = []
        for item_key, score in summary_scores.get(cat_key, {}).items():
            items.append((label_map.get(item_key, item_key), to_number(score, 0.0), color))
        if items:
            groups.append((cat_name, items))

    if not groups:
        return None

    # 각 그룹 사이에 빈 줄 삽입
    all_labels = []
    all_values = []
    all_colors = []
    group_label_positions = []

    y_pos = 0
    for g_name, items in reversed(groups):
        start_y = y_pos
        for label, score, color in reversed(items):
            all_labels.append(label)
            all_values.append(score)
            all_colors.append(color)
            y_pos += 1
        group_label_positions.append((g_name, (start_y + y_pos - 1) / 2, items[0][2]))
        y_pos += 0.6  # 그룹 간 간격

    n = len(all_labels)
    y_positions = []
    idx = 0
    y_cur = 0
    group_idx = 0
    items_in_group = 0
    group_sizes = [len(g[1]) for g in reversed(groups)]

    for i in range(n):
        y_positions.append(y_cur)
        y_cur += 1
        items_in_group += 1
        if group_idx < len(group_sizes) and items_in_group >= group_sizes[group_idx]:
            y_cur += 0.6
            items_in_group = 0
            group_idx += 1

    fig_h = max(4.0, y_cur * 0.42 + 1.0)
    fig, ax = plt.subplots(figsize=(7.0, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # 배경 줄무늬
    for i, yp in enumerate(y_positions):
        if i % 2 == 0:
            ax.axhspan(yp - 0.35, yp + 0.35, color="#F8F9FC", zorder=0)

    bars = ax.barh(y_positions, all_values, color=all_colors, height=0.5,
                   edgecolor="white", linewidth=0.5, alpha=0.85, zorder=3)

    ax.set_yticks(y_positions)
    ax.set_yticklabels(all_labels, fontsize=9, color="#1A1A2E")

    # 기준선
    ax.axvline(x=3.0, color="#A0AAB8", linestyle="--", linewidth=1.2, alpha=0.6, zorder=2)

    for bar, val in zip(bars, all_values):
        txt_color = score_hex(val)
        ax.text(
            val + 0.08, bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}", va="center", ha="left", fontsize=9,
            color=txt_color, fontweight="bold", zorder=4,
        )

    ax.set_xlim(0, 5.5)
    ax.set_xlabel("점수 (5점 만점)", fontsize=8, color="#5A6678")
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.tick_params(axis="x", labelsize=7, colors="#8A95A8")
    ax.tick_params(axis="y", length=0)
    for spine in ["top", "right", "left"]:
        ax.spines[spine].set_visible(False)
    ax.spines["bottom"].set_color(CH_GRID)

    # 범례
    legend_patches = [
        mpatches.Patch(color=CAT_COLORS[k], label=v, alpha=0.85)
        for k, v in cat_display.items()
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8,
              framealpha=0.95, edgecolor=CH_GRID, fancybox=True)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ──────────────────────────────────────────────────────────────────────────────
# PDF 페이지 콜백
# ──────────────────────────────────────────────────────────────────────────────


def _make_page_callback(reg_font: str):
    def on_first_page(canvas, doc):
        # 커버 페이지에는 푸터 없음
        pass

    def on_later_pages(canvas, doc):
        canvas.saveState()
        # 상단 얇은 네이비 라인
        canvas.setStrokeColor(colors.HexColor("#1B3A5C"))
        canvas.setLineWidth(1.5)
        canvas.line(2 * cm, PAGE_H - 1.5 * cm, PAGE_W - 2 * cm, PAGE_H - 1.5 * cm)
        # 하단 푸터
        canvas.setFont(reg_font, 7.5)
        canvas.setFillColor(colors.HexColor("#8A95A8"))
        canvas.drawString(2 * cm, 1.2 * cm, "EduInsight AI  ·  강의 분석 리포트")
        canvas.drawRightString(PAGE_W - 2 * cm, 1.2 * cm, f"{doc.page}")
        canvas.setStrokeColor(colors.HexColor("#D0D5DD"))
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 1.5 * cm, PAGE_W - 2 * cm, 1.5 * cm)
        canvas.restoreState()

    return on_first_page, on_later_pages


# ──────────────────────────────────────────────────────────────────────────────
# 공통 위젯
# ──────────────────────────────────────────────────────────────────────────────


def _section_header(title: str, description: str, s: dict) -> list:
    """섹션 제목 + 설명 + 구분선."""
    elements = [
        Paragraph(title, s["section_title"]),
        HRFlowable(width="100%", thickness=2, color=C_ACCENT, spaceAfter=4),
    ]
    if description:
        elements.append(Paragraph(description, s["section_desc"]))
    return elements


def _metric_card(label: str, value: str, unit: str, accent_color: colors.Color,
                 s: dict, bold: str) -> Table:
    """지표 카드 (라벨, 값, 단위)."""
    data = [
        [Paragraph(label, s["badge_label"])],
        [Paragraph(value, ParagraphStyle(
            f"MV_{label}", fontName=bold, fontSize=22, textColor=accent_color,
            alignment=TA_CENTER, leading=28,
        ))],
        [Paragraph(unit, s["badge_unit"])],
    ]
    t = Table(data, colWidths=[3.8 * cm])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT_BG),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ("TOPPADDING", (0, 0), (0, 0), 10),
        ("TOPPADDING", (0, 1), (0, 1), 4),
        ("TOPPADDING", (0, 2), (0, 2), 2),
        ("BOTTOMPADDING", (0, 2), (0, 2), 10),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("BOTTOMPADDING", (0, 1), (0, 1), 2),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
    ]))
    return t


def _score_pill(score: float, bold: str) -> Paragraph:
    """점수에 따라 색상 변하는 pill 텍스트."""
    hex_c = score_hex(score)
    return Paragraph(
        f"{score:.1f}",
        ParagraphStyle(f"Pill_{score}", fontName=bold, fontSize=11,
                       textColor=colors.HexColor(hex_c), alignment=TA_CENTER),
    )


# ──────────────────────────────────────────────────────────────────────────────
# 페이지 1: 커버
# ──────────────────────────────────────────────────────────────────────────────


def build_cover(data: dict, s: dict, reg: str, bold: str) -> list:
    story = []
    meta = data.get("metadata", {})
    sessions = meta.get("sessions", [])
    subjects = list(dict.fromkeys(ss.get("subject", "") for ss in sessions))
    analysis = data.get("analysis", {})
    ss_scores = analysis.get("summary_scores", {})

    # ── 상단 여백 ──
    story.append(Spacer(1, 1.5 * cm))

    # ── 네이비 헤더 블록 ──
    header_data = [
        [Paragraph("강의 분석 리포트", s["cover_title"])],
        [Paragraph("EduInsight AI", s["cover_sub"])],
    ]
    header_table = Table(header_data, colWidths=[CONTENT_W])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (0, 0), 36),
        ("BOTTOMPADDING", (0, 0), (0, 0), 6),
        ("BOTTOMPADDING", (0, 1), (0, 1), 32),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
        ("ROUNDEDCORNERS", [6, 6, 6, 6]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.8 * cm))

    # ── 강의 정보 테이블 ──
    def info_row(key, val):
        return [
            Paragraph(key, ParagraphStyle(
                f"IK_{key}", fontName=bold, fontSize=9,
                textColor=C_PRIMARY, alignment=TA_CENTER, leading=14)),
            Paragraph(val or "-", ParagraphStyle(
                f"IV_{key}", fontName=reg, fontSize=9.5,
                textColor=C_TEXT, leading=14)),
        ]

    info_rows = [
        info_row("과정명", meta.get("course_name", "")),
        info_row("강의 일자", meta.get("date", "")),
        info_row("담당 강사", meta.get("instructor", "")),
        info_row("보조 강사", meta.get("sub_instructor", "")),
        info_row("강의 주제", " / ".join(filter(None, subjects))),
        info_row("강의 ID", data.get("lecture_id", "")),
    ]
    key_col_w = 3.2 * cm
    val_col_w = CONTENT_W - key_col_w
    info_table = Table(info_rows, colWidths=[key_col_w, val_col_w])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), C_LIGHT_BG),
        ("FONTNAME", (0, 0), (-1, -1), reg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, C_BORDER),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.6 * cm))

    # ── 세션 테이블 ──
    if sessions:
        sess_header = [
            Paragraph("세션", s["th"]),
            Paragraph("시간", s["th"]),
            Paragraph("과목", s["th"]),
            Paragraph("강의 내용", s["th"]),
        ]
        session_rows = [sess_header]
        for i, ss in enumerate(sessions):
            session_rows.append([
                Paragraph(str(i + 1), s["td_center"]),
                Paragraph(ss.get("time", ""), s["td_center"]),
                Paragraph(ss.get("subject", ""), s["td"]),
                Paragraph(ss.get("content", ""), s["td"]),
            ])
        col_ws = [1.5 * cm, 3.2 * cm, 4.2 * cm, CONTENT_W - 1.5 * cm - 3.2 * cm - 4.2 * cm]
        sess_table = Table(session_rows, colWidths=col_ws)
        sess_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
            ("FONTNAME", (0, 0), (-1, -1), reg),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, C_BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT_BG]),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        story.append(sess_table)
        story.append(Spacer(1, 0.6 * cm))

    # ── 종합 점수 미리보기 (커버 하단) ──
    cat_map = {
        "lecture_structure": "강의 구조",
        "concept_clarity": "개념 명확성",
        "practice_linkage": "실습 연계",
        "interaction": "상호작용",
    }
    if ss_scores:
        avgs = {k: cat_avg(ss_scores.get(k, {})) for k in cat_map}
        overall = round(sum(avgs.values()) / len(avgs), 2) if avgs else 0.0

        # 종합 점수 배너
        sc = score_color(overall)
        overall_data = [[
            Paragraph("종합 점수", ParagraphStyle(
                "OL", fontName=reg, fontSize=9, textColor=C_TEXT_SECONDARY,
                alignment=TA_CENTER)),
            Paragraph(f"{overall:.2f}", ParagraphStyle(
                "OV", fontName=bold, fontSize=30, textColor=sc,
                alignment=TA_CENTER, leading=36)),
            Paragraph(f"/ 5.00  ·  {score_label(overall)}", ParagraphStyle(
                "OD", fontName=bold, fontSize=11, textColor=sc,
                alignment=TA_CENTER)),
        ]]
        overall_banner = Table(overall_data, colWidths=[3 * cm, 4.5 * cm, 5 * cm],
                               hAlign="CENTER")
        overall_banner.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), score_bg(overall)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 12),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
            ("BOX", (0, 0), (-1, -1), 0.5, sc),
            ("ROUNDEDCORNERS", [6, 6, 6, 6]),
        ]))
        story.append(overall_banner)
        story.append(Spacer(1, 0.3 * cm))

        # 카테고리 미니 점수
        cat_cells = []
        for key, name in cat_map.items():
            avg = avgs[key]
            cell = Table(
                [[Paragraph(name, ParagraphStyle(
                    f"CM_{key}", fontName=reg, fontSize=8,
                    textColor=C_TEXT_SECONDARY, alignment=TA_CENTER))],
                 [Paragraph(f"{avg:.2f}", ParagraphStyle(
                    f"CS_{key}", fontName=bold, fontSize=14,
                    textColor=colors.HexColor(score_hex(avg)), alignment=TA_CENTER))]],
                colWidths=[3.5 * cm],
            )
            cell.setStyle(TableStyle([
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            cat_cells.append(cell)

        cat_row = Table([cat_cells], colWidths=[3.8 * cm] * 4, hAlign="CENTER")
        cat_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ]))
        story.append(cat_row)

    story.append(PageBreak())
    return story


# ──────────────────────────────────────────────────────────────────────────────
# 페이지 2: 언어 표현 품질 분석
# ──────────────────────────────────────────────────────────────────────────────


def build_language_quality(analysis: dict, s: dict, reg: str, bold: str) -> list:
    story = []
    lq = analysis.get("language_quality", {})
    ccm = analysis.get("concept_clarity_metrics", {})
    im = analysis.get("interaction_metrics", {})

    story.extend(_section_header(
        "1. 언어 표현 품질 분석",
        "강의 중 사용된 언어의 품질을 반복 표현, 문장 완결성, 발화 속도 등의 지표로 분석합니다.",
        s,
    ))

    # ── 지표 카드 ──
    repeat_ratio = to_number(lq.get("repeat_ratio", 0), 0.0)
    incomplete_ratio = to_number(lq.get("incomplete_sentence_ratio", 0), 0.0)
    speech_rate = int(round(to_number(ccm.get("speech_rate_wpm", 0), 0.0)))
    q_count = int(round(to_number(im.get("understanding_question_count", 0), 0.0)))

    # 각 지표에 적절한 색상 지정
    repeat_color = C_DANGER if repeat_ratio > 0.15 else (C_WARNING if repeat_ratio > 0.1 else C_SUCCESS)
    complete_color = C_SUCCESS if (1 - incomplete_ratio) >= 0.9 else (C_WARNING if (1 - incomplete_ratio) >= 0.8 else C_DANGER)
    speed_color = C_WARNING if speech_rate > 180 else (C_SUCCESS if speech_rate >= 120 else C_DANGER)
    q_color = C_SUCCESS if q_count >= 15 else (C_WARNING if q_count >= 8 else C_DANGER)

    cards = [
        _metric_card("반복 표현 비율", f"{repeat_ratio * 100:.1f}%", "발화 전체 대비", repeat_color, s, bold),
        _metric_card("문장 완결성", f"{(1 - incomplete_ratio) * 100:.1f}%", "완결 문장 비율", complete_color, s, bold),
        _metric_card("발화 속도", f"{speech_rate}", "단어/분 (wpm)", speed_color, s, bold),
        _metric_card("이해 확인 질문", f"{q_count}회", "총 질문 수", q_color, s, bold),
    ]
    card_row = Table([cards], colWidths=[4.05 * cm] * 4, hAlign="CENTER")
    card_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(card_row)
    story.append(Spacer(1, 0.6 * cm))

    # ── 반복 표현 차트 + 발화 스타일 도넛 ──
    repeat_expr = lq.get("repeat_expressions", {})
    speech_style = lq.get("speech_style_ratio", {})

    repeat_buf = chart_repeat_expressions(repeat_expr)
    style_buf = chart_speech_style(speech_style)

    if repeat_buf or style_buf:
        story.append(Paragraph("반복 표현 분포 및 발화 스타일", s["subsection"]))
        story.append(Spacer(1, 2 * mm))

    if repeat_buf and style_buf:
        # figsize=(5.5, h) → 비율 유지
        repeat_items = sorted(repeat_expr.items(), key=lambda x: x[1], reverse=True)[:8]
        n_bars = len(repeat_items)
        fig_h_inch = max(2.5, n_bars * 0.45 + 0.8)
        ratio = fig_h_inch / 5.5
        img_w_repeat = 10.0 * cm
        img_h_repeat = img_w_repeat * ratio

        img_repeat = Image(repeat_buf, width=img_w_repeat, height=img_h_repeat)
        img_style = Image(style_buf, width=5.0 * cm, height=5.0 * cm)

        spacer_w = 0.5 * cm
        row = Table(
            [[img_repeat, Spacer(spacer_w, 1), img_style]],
            colWidths=[img_w_repeat, spacer_w, 5.5 * cm],
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(row)
    elif repeat_buf:
        story.append(Image(repeat_buf, width=14 * cm, height=7 * cm))
    elif style_buf:
        story.append(Image(style_buf, width=5 * cm, height=5 * cm))

    # ── 해석 요약 카드 ──
    story.append(Spacer(1, 0.5 * cm))
    interp_lines = []
    if repeat_ratio > 0.15:
        top_expr = sorted(repeat_expr.items(), key=lambda x: x[1], reverse=True)[:2]
        top_str = ", ".join(f"'{w}'({c}회)" for w, c in top_expr)
        interp_lines.append(
            f"반복 표현 비율이 <b>{repeat_ratio*100:.1f}%</b>로 높은 편입니다. "
            f"특히 {top_str} 등의 필러 표현이 빈번하게 사용되고 있어 청취 집중도에 영향을 줄 수 있습니다."
        )
    elif repeat_ratio > 0.1:
        interp_lines.append(
            f"반복 표현 비율이 <b>{repeat_ratio*100:.1f}%</b>로 보통 수준입니다."
        )
    else:
        interp_lines.append(
            f"반복 표현 비율이 <b>{repeat_ratio*100:.1f}%</b>로 양호합니다."
        )

    if (1 - incomplete_ratio) >= 0.9:
        interp_lines.append(
            f"문장 완결성은 <b>{(1 - incomplete_ratio)*100:.1f}%</b>로 우수하며, "
            "대부분의 발화가 완전한 문장 형태로 전달되고 있습니다."
        )
    else:
        interp_lines.append(
            f"문장 완결성이 <b>{(1 - incomplete_ratio)*100:.1f}%</b>로 개선이 필요합니다."
        )

    if speech_rate > 180:
        interp_lines.append(
            f"발화 속도가 <b>{speech_rate} wpm</b>으로 다소 빠른 편입니다. "
            "핵심 개념 설명 시 속도 조절이 도움이 될 수 있습니다."
        )
    elif speech_rate >= 120:
        interp_lines.append(
            f"발화 속도는 <b>{speech_rate} wpm</b>으로 적절한 범위입니다."
        )

    formal_pct = speech_style.get("formal", 0) * 100
    if formal_pct >= 85:
        interp_lines.append(
            f"격식체 비율이 <b>{formal_pct:.0f}%</b>로 높아 "
            "전문적이고 일관된 강의 어투를 유지하고 있습니다."
        )

    if interp_lines:
        interp_header = Paragraph("분석 해석", s["subsection"])
        interp_body_parts = []
        for line in interp_lines:
            interp_body_parts.append(
                Paragraph(f"·  {line}", s["body"])
            )
        story.append(interp_header)
        story.append(Spacer(1, 2 * mm))
        # 해석 카드
        interp_card_data = [[[p] for p in interp_body_parts]]
        flat_rows = [[p] for p in interp_body_parts]
        interp_table = Table(flat_rows, colWidths=[CONTENT_W - 1.2 * cm])
        interp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, -1), (0, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -2), 4),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        story.append(interp_table)

    story.append(PageBreak())
    return story


# ──────────────────────────────────────────────────────────────────────────────
# 페이지 3: 강의 품질 종합 평가
# ──────────────────────────────────────────────────────────────────────────────


def build_scores(analysis: dict, s: dict, reg: str, bold: str) -> list:
    story = []
    ss = analysis.get("summary_scores", {})
    if not ss:
        return story

    story.extend(_section_header(
        "2. 강의 품질 종합 평가",
        "4개 카테고리(강의 구조, 개념 명확성, 실습 연계, 상호작용)에 대한 정량적 평가입니다.",
        s,
    ))

    cat_map = {
        "lecture_structure": "강의 구조",
        "concept_clarity": "개념 명확성",
        "practice_linkage": "실습 연계",
        "interaction": "상호작용",
    }
    avgs = {k: cat_avg(ss.get(k, {})) for k in cat_map}
    overall = round(sum(avgs.values()) / len(avgs), 2) if avgs else 0.0

    # ── 레이더 차트 + 카테고리 점수 테이블 ──
    radar_buf = chart_radar(ss)
    # figsize=(5,5) → 1:1 비율
    radar_w = 7 * cm
    radar_img = Image(radar_buf, width=radar_w, height=radar_w)

    # 카테고리 테이블
    cat_rows = [[
        Paragraph("카테고리", s["th"]),
        Paragraph("평균", s["th"]),
        Paragraph("평가", s["th"]),
    ]]
    for key, name in cat_map.items():
        avg = avgs.get(key, 0)
        cat_rows.append([
            Paragraph(name, ParagraphStyle(
                f"CN_{key}", fontName=reg, fontSize=9.5, textColor=C_TEXT, leading=14)),
            Paragraph(f"{avg:.2f}", ParagraphStyle(
                f"CV_{key}", fontName=bold, fontSize=11,
                textColor=colors.HexColor(score_hex(avg)), alignment=TA_CENTER)),
            Paragraph(score_label(avg), ParagraphStyle(
                f"CL_{key}", fontName=bold, fontSize=9,
                textColor=colors.HexColor(score_hex(avg)), alignment=TA_CENTER)),
        ])

    t_w = CONTENT_W - radar_w - 1.0 * cm
    cat_table = Table(cat_rows, colWidths=[t_w * 0.45, t_w * 0.28, t_w * 0.27])
    cat_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_PRIMARY),
        ("FONTNAME", (0, 0), (-1, -1), reg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("LINEBELOW", (0, 0), (-1, -2), 0.3, C_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [C_WHITE, C_LIGHT_BG]),
        ("ROUNDEDCORNERS", [4, 4, 4, 4]),
    ]))

    dual = Table(
        [[radar_img, Spacer(0.3 * cm, 1), cat_table]],
        colWidths=[radar_w, 0.5 * cm, t_w],
    )
    dual.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(dual)
    story.append(Spacer(1, 0.4 * cm))

    # ── 카테고리별 해석 카드 ──
    cat_interp_lines = []
    for key, name in cat_map.items():
        avg = avgs[key]
        label = score_label(avg)
        raw_items = ss.get(key, {})
        items = {k: to_number(v, 0.0) for k, v in raw_items.items()}
        if not items:
            continue
        best_item = max(items, key=items.get)
        worst_item = min(items, key=items.get)
        label_map_local = {
            "learning_objective_intro": "학습 목표 안내",
            "previous_lesson_linkage": "전날 복습 연계",
            "explanation_sequence": "설명 순서",
            "key_point_emphasis": "핵심 강조",
            "closing_summary": "마무리 요약",
            "concept_definition": "개념 정의",
            "analogy_example_usage": "비유·예시 활용",
            "prerequisite_check": "선행 개념 확인",
            "example_appropriateness": "예시 적절성",
            "practice_transition": "실습 연계",
            "error_handling": "오류 대응",
            "participation_induction": "참여 유도",
            "question_response_sufficiency": "질문 응답 충분성",
        }
        best_name = label_map_local.get(best_item, best_item)
        worst_name = label_map_local.get(worst_item, worst_item)
        hex_c = score_hex(avg)
        cat_interp_lines.append(
            f'<font color="{hex_c}"><b>{name}</b></font> ({avg:.2f}, {label}): '
            f'<b>{best_name}</b>({items[best_item]:.1f})이 가장 높고, '
            f'<b>{worst_name}</b>({items[worst_item]:.1f})이 가장 낮습니다.'
        )

    if cat_interp_lines:
        story.append(Paragraph("카테고리별 요약", s["subsection"]))
        story.append(Spacer(1, 2 * mm))
        interp_rows = [[Paragraph(f"·  {line}", s["body"])] for line in cat_interp_lines]
        interp_tbl = Table(interp_rows, colWidths=[CONTENT_W - 1.0 * cm])
        interp_tbl.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT_BG),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (0, 0), 10),
            ("TOPPADDING", (0, 1), (-1, -1), 4),
            ("BOTTOMPADDING", (0, -1), (0, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -2), 4),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
            ("ROUNDEDCORNERS", [4, 4, 4, 4]),
        ]))
        story.append(interp_tbl)
    story.append(Spacer(1, 0.3 * cm))

    # ── 세부 항목 점수 차트 ──
    detail_buf = chart_category_detail(ss)
    if detail_buf:
        n_items = sum(len(v) for v in ss.values() if isinstance(v, dict))
        # figsize=(7.0, fig_h) → 비율 유지
        fig_h_inch = max(4.0, (n_items + 2) * 0.42 + 1.0)
        ratio = fig_h_inch / 7.0
        img_w = 15 * cm
        img_h = img_w * ratio
        # KeepTogether: 제목과 차트가 같은 페이지에 표시되도록
        story.append(KeepTogether([
            Paragraph("카테고리별 세부 항목 점수", s["subsection"]),
            Spacer(1, 2 * mm),
            Image(detail_buf, width=img_w, height=img_h),
        ]))

    story.append(PageBreak())
    return story


# ──────────────────────────────────────────────────────────────────────────────
# 페이지 4: 강의 개선 인사이트
# ──────────────────────────────────────────────────────────────────────────────


def build_insights(analysis: dict, s: dict, reg: str, bold: str) -> list:
    story = []
    strengths = analysis.get("overall_strengths", [])
    issues = analysis.get("overall_issues", [])
    evidences = analysis.get("overall_evidences", [])

    story.extend(_section_header(
        "3. 강의 개선 인사이트",
        "분석 결과를 바탕으로 도출된 강의의 강점과 개선이 필요한 영역을 정리합니다.",
        s,
    ))

    # ── 강점 섹션 ──
    strength_header = Table(
        [[Paragraph("강점", s["insight_title"])]],
        colWidths=[CONTENT_W],
    )
    strength_header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_SUCCESS),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [6, 6, 0, 0]),
    ]))
    story.append(strength_header)

    if strengths:
        strength_rows = []
        for i, text in enumerate(strengths):
            bg = C_WHITE if i % 2 == 0 else C_SUCCESS_BG
            strength_rows.append([
                Paragraph(f"<b>{i+1}.</b>", ParagraphStyle(
                    f"SN_{i}", fontName=bold, fontSize=9.5, textColor=C_SUCCESS,
                    alignment=TA_CENTER, leading=15)),
                Paragraph(text, s["insight_item"]),
            ])
        strength_table = Table(strength_rows, colWidths=[1.2 * cm, CONTENT_W - 1.2 * cm])
        strength_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (0, -1), 6),
            ("LEFTPADDING", (1, 0), (1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#A8D5BA")),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#D4EDDA")),
            *[("BACKGROUND", (0, i), (-1, i), C_WHITE if i % 2 == 0 else C_SUCCESS_BG)
              for i in range(len(strength_rows))],
            ("ROUNDEDCORNERS", [0, 0, 6, 6]),
        ]))
        story.append(strength_table)
    else:
        story.append(Paragraph("분석된 강점이 없습니다.", s["small"]))

    story.append(Spacer(1, 0.6 * cm))

    # ── 개선 필요 사항 섹션 ──
    issue_header = Table(
        [[Paragraph("개선 필요 사항", s["insight_title"])]],
        colWidths=[CONTENT_W],
    )
    issue_header.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_DANGER),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("ROUNDEDCORNERS", [6, 6, 0, 0]),
    ]))
    story.append(issue_header)

    if issues:
        issue_rows = []
        for i, text in enumerate(issues):
            bg = C_WHITE if i % 2 == 0 else C_DANGER_BG
            ev = evidences[i] if i < len(evidences) else None

            content_parts = [Paragraph(text, s["insight_item"])]
            if ev:
                content_parts.append(Spacer(1, 2 * mm))
                content_parts.append(
                    Paragraph(
                        f'<font color="#8A95A8">근거:</font>  {ev}',
                        s["insight_evidence"],
                    )
                )

            # 내용을 하나의 셀로 묶기 (패딩 감안하여 폭 축소)
            inner = Table(
                [[p] for p in content_parts],
                colWidths=[CONTENT_W - 1.2 * cm - 20],
            )
            inner.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]))

            issue_rows.append([
                Paragraph(f"<b>{i+1}.</b>", ParagraphStyle(
                    f"IN_{i}", fontName=bold, fontSize=9.5, textColor=C_DANGER,
                    alignment=TA_CENTER, leading=15)),
                inner,
            ])

        issue_table = Table(issue_rows, colWidths=[1.2 * cm, CONTENT_W - 1.2 * cm])
        issue_table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (0, -1), 6),
            ("LEFTPADDING", (1, 0), (1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#F5C6CB")),
            ("LINEBELOW", (0, 0), (-1, -2), 0.3, colors.HexColor("#F8D7DA")),
            *[("BACKGROUND", (0, i), (-1, i), C_WHITE if i % 2 == 0 else C_DANGER_BG)
              for i in range(len(issue_rows))],
            ("ROUNDEDCORNERS", [0, 0, 6, 6]),
        ]))
        story.append(issue_table)
    else:
        story.append(Paragraph("분석된 개선 사항이 없습니다.", s["small"]))

    # 남은 근거
    extra_evidences = evidences[len(issues):]
    if extra_evidences:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("추가 근거", s["subsection"]))
        for ev in extra_evidences:
            story.append(Paragraph(f"·  {ev}", s["small"]))

    return story


# ──────────────────────────────────────────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────────────────────────────────────────


def generate_report(analysis_json_path: str, output_pdf_path: str) -> None:
    with open(analysis_json_path, encoding="utf-8") as f:
        data = json.load(f)

    setup_matplotlib_korean()
    reg, bold = register_korean_fonts()

    out = Path(output_pdf_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2.2 * cm,
        title="강의 분석 리포트",
        author="EduInsight AI",
    )

    styles = make_styles(reg, bold)
    analysis = data.get("analysis", {})
    on_first, on_later = _make_page_callback(reg)

    story: list = []
    story.extend(build_cover(data, styles, reg, bold))
    story.extend(build_language_quality(analysis, styles, reg, bold))
    story.extend(build_scores(analysis, styles, reg, bold))
    story.extend(build_insights(analysis, styles, reg, bold))

    doc.build(story, onFirstPage=on_first, onLaterPages=on_later)
    print(f"리포트 생성 완료: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="강의 분석 리포트 생성기 (analysis.json → PDF)")
    parser.add_argument("--input", required=True, help="analysis.json 파일 경로")
    parser.add_argument("--output", required=True, help="출력 PDF 파일 경로")
    args = parser.parse_args()

    generate_report(args.input, args.output)



