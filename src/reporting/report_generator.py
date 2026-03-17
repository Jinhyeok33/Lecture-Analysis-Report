"""
Report Generator: analysis.json → analysis.pdf

강의 분석 결과를 시각적인 PDF 리포트로 변환합니다.

PDF 구성:
  1. 커버 페이지  (강의 기본 정보)
  2. 언어 표현 품질 분석  (NLP 정량 지표 + 반복 표현 차트)
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
import numpy as np

matplotlib.use("Agg")

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
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
)

# ──────────────────────────────────────────────────────────────────────────────
# 전역 설정
# ──────────────────────────────────────────────────────────────────────────────

PAGE_W, PAGE_H = A4

_FONT_REGULAR = "Helvetica"
_FONT_BOLD = "Helvetica-Bold"

# 색상 팔레트
C_PRIMARY = colors.HexColor("#1E3A8A")   # 진한 파랑
C_ACCENT = colors.HexColor("#2563EB")    # 밝은 파랑
C_SUCCESS = colors.HexColor("#059669")   # 초록
C_WARNING = colors.HexColor("#D97706")   # 주황
C_DANGER = colors.HexColor("#DC2626")    # 빨강
C_LIGHT_BG = colors.HexColor("#EFF6FF")  # 연한 파랑 배경
C_GRAY_BG = colors.HexColor("#F8FAFC")   # 연한 회색 배경
C_BORDER = colors.HexColor("#CBD5E1")    # 테두리
C_TEXT = colors.HexColor("#1E293B")      # 본문 텍스트
C_SUBTEXT = colors.HexColor("#475569")   # 보조 텍스트
C_WHITE = colors.white


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
    """한국어 폰트를 등록하고 (regular, bold) 폰트명 튜플을 반환합니다."""
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

    # regular 선택: Bold 아닌 것 우선
    regular = next((n for n in registered if "Bold" not in n), list(registered)[0])
    bold = next((n for n in registered if "Bold" in n), regular)

    _FONT_REGULAR = regular
    _FONT_BOLD = bold
    return regular, bold


def setup_matplotlib_korean():
    """matplotlib 한국어 폰트를 설정합니다."""
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


def score_hex(score: float) -> str:
    if score >= 4.0:
        return "#059669"
    elif score >= 3.0:
        return "#D97706"
    else:
        return "#DC2626"


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


def cat_avg(cat_scores: dict) -> float:
    vals = list(cat_scores.values())
    return round(sum(vals) / len(vals), 2) if vals else 0.0


# ──────────────────────────────────────────────────────────────────────────────
# 스타일 팩토리
# ──────────────────────────────────────────────────────────────────────────────


def make_styles(reg: str, bold: str) -> dict:
    def ps(name, **kw):
        return ParagraphStyle(name, **kw)

    return {
        "cover_title": ps(
            "CoverTitle",
            fontName=bold,
            fontSize=26,
            textColor=C_WHITE,
            alignment=TA_CENTER,
            leading=34,
        ),
        "cover_sub": ps(
            "CoverSub",
            fontName=reg,
            fontSize=12,
            textColor=colors.HexColor("#93C5FD"),
            alignment=TA_CENTER,
            spaceAfter=4,
        ),
        "section": ps(
            "Section",
            fontName=bold,
            fontSize=14,
            textColor=C_PRIMARY,
            spaceBefore=12,
            spaceAfter=6,
            leading=20,
        ),
        "subsection": ps(
            "Subsection",
            fontName=bold,
            fontSize=11,
            textColor=C_TEXT,
            spaceBefore=8,
            spaceAfter=4,
            leading=16,
        ),
        "body": ps(
            "Body",
            fontName=reg,
            fontSize=10,
            textColor=C_TEXT,
            spaceAfter=4,
            leading=16,
        ),
        "small": ps(
            "Small",
            fontName=reg,
            fontSize=9,
            textColor=C_SUBTEXT,
            spaceAfter=3,
            leading=14,
        ),
        "evidence": ps(
            "Evidence",
            fontName=reg,
            fontSize=9,
            textColor=C_SUBTEXT,
            leading=14,
            leftIndent=16,
            spaceAfter=4,
        ),
        "badge_label": ps(
            "BadgeLabel",
            fontName=reg,
            fontSize=9,
            textColor=C_SUBTEXT,
            alignment=TA_CENTER,
        ),
        "badge_value": ps(
            "BadgeValue",
            fontName=bold,
            fontSize=18,
            textColor=C_PRIMARY,
            alignment=TA_CENTER,
        ),
        "badge_unit": ps(
            "BadgeUnit",
            fontName=reg,
            fontSize=8,
            textColor=C_SUBTEXT,
            alignment=TA_CENTER,
        ),
        "table_header": ps(
            "TableHeader",
            fontName=bold,
            fontSize=9,
            textColor=C_WHITE,
            alignment=TA_CENTER,
        ),
        "table_body": ps(
            "TableBody", fontName=reg, fontSize=9, textColor=C_TEXT, leading=14
        ),
        "table_center": ps(
            "TableCenter",
            fontName=reg,
            fontSize=9,
            textColor=C_TEXT,
            alignment=TA_CENTER,
            leading=14,
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 차트 생성
# ──────────────────────────────────────────────────────────────────────────────


def chart_radar(summary_scores: dict) -> io.BytesIO:
    """4개 카테고리 평균 점수 레이더 차트."""
    cat_map = {
        "lecture_structure": "강의 구조",
        "concept_clarity": "개념 명확성",
        "practice_linkage": "실습 연계",
        "interaction": "상호작용",
    }
    labels = list(cat_map.values())
    values = [cat_avg(summary_scores.get(k, {})) for k in cat_map]

    N = len(labels)
    angles = [n / N * 2 * math.pi for n in range(N)]
    angles += angles[:1]
    values_plot = values + [values[0]]

    fig, ax = plt.subplots(figsize=(5, 5), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F0F7FF")

    # 그리드
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(labels, fontsize=11, color="#1E293B")
    ax.set_ylim(0, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_yticklabels(["1", "2", "3", "4", "5"], fontsize=7, color="#94A3B8")
    ax.grid(color="#CBD5E1", linewidth=0.8, linestyle="--", alpha=0.7)
    ax.spines["polar"].set_color("#CBD5E1")

    # 기준선 3.0
    ref = [3.0] * N + [3.0]
    ax.plot(angles, ref, "--", linewidth=1, color="#94A3B8", alpha=0.6, label="기준 (3.0)")

    # 데이터
    ax.plot(angles, values_plot, "o-", linewidth=2.5, color="#2563EB", markersize=7)
    ax.fill(angles, values_plot, alpha=0.20, color="#2563EB")

    # 점수 레이블
    for angle, val in zip(angles[:-1], values):
        ax.text(
            angle, val + 0.35, f"{val:.2f}",
            ha="center", va="center", fontsize=9,
            color=score_hex(val), fontweight="bold",
        )

    plt.tight_layout(pad=0.5)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_repeat_expressions(repeat_expr: dict, top_n: int = 8) -> io.BytesIO | None:
    """반복 표현 사용 횟수 가로 막대 차트."""
    if not repeat_expr:
        return None

    items = sorted(repeat_expr.items(), key=lambda x: x[1], reverse=True)[:top_n]
    labels = [item[0] for item in items]
    values = [item[1] for item in items]
    max_v = max(values) if values else 1

    bar_colors = [
        "#DC2626" if v >= max_v * 0.7 else "#F97316" if v >= max_v * 0.4 else "#FCD34D"
        for v in values
    ]

    fig, ax = plt.subplots(figsize=(8, max(3, len(labels) * 0.5 + 0.8)))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")

    # 뒤집힌 순서로 표시 (가장 높은 값이 위)
    bars = ax.barh(
        list(range(len(labels))), values[::-1],
        color=bar_colors[::-1], height=0.55,
        edgecolor="white", linewidth=0.5,
    )
    ax.invert_yaxis()
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=11)

    for bar, val in zip(bars, values[::-1]):
        ax.text(
            bar.get_width() + max_v * 0.02,
            bar.get_y() + bar.get_height() / 2,
            f"{val}회", va="center", ha="left", fontsize=9, color="#475569",
        )

    ax.set_xlabel("사용 횟수", fontsize=9, color="#475569")
    ax.set_xlim(0, max_v * 1.25)
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")
    ax.tick_params(axis="x", labelsize=8, colors="#94A3B8")
    ax.tick_params(axis="y", labelsize=10, colors="#1E293B")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_category_scores(summary_scores: dict) -> io.BytesIO | None:
    """카테고리별 세부 항목 점수 가로 막대 차트."""
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
        "lecture_structure": ("강의 구조", "#2563EB"),
        "concept_clarity": ("개념 명확성", "#7C3AED"),
        "practice_linkage": ("실습 연계", "#059669"),
        "interaction": ("상호작용", "#D97706"),
    }

    all_items: list[tuple[str, float, str]] = []  # (label, score, color)
    for cat_key, (cat_name, color) in cat_display.items():
        for item_key, score in summary_scores.get(cat_key, {}).items():
            label = f"[{cat_name}]  {label_map.get(item_key, item_key)}"
            all_items.append((label, score, color))

    if not all_items:
        return None

    labels = [x[0] for x in all_items]
    values = [x[1] for x in all_items]
    bar_colors = [x[2] for x in all_items]

    fig_h = max(4.5, len(labels) * 0.48 + 1.2)
    fig, ax = plt.subplots(figsize=(9, fig_h))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("#F8FAFC")

    y_pos = list(range(len(labels)))
    bars = ax.barh(y_pos, values, color=bar_colors, height=0.55,
                   edgecolor="white", linewidth=0.5, alpha=0.85)
    ax.invert_yaxis()
    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=9)

    # 기준선 3.0
    ax.axvline(x=3.0, color="#94A3B8", linestyle="--", linewidth=1.5, alpha=0.7)
    ax.text(3.03, len(labels) - 0.5, "기준 3.0", fontsize=8, color="#94A3B8")

    # 점수 레이블
    for bar, val in zip(bars, values):
        ax.text(
            min(val + 0.08, 5.3),
            bar.get_y() + bar.get_height() / 2,
            f"{val:.1f}", va="center", ha="left", fontsize=9,
            color=score_hex(val), fontweight="bold",
        )

    ax.set_xlim(0, 5.6)
    ax.set_xlabel("점수 (5점 만점)", fontsize=9, color="#475569")
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.tick_params(axis="x", labelsize=8, colors="#94A3B8")
    ax.tick_params(axis="y", labelsize=9, colors="#1E293B")
    for spine in ["top", "right"]:
        ax.spines[spine].set_visible(False)
    ax.spines["left"].set_color("#CBD5E1")
    ax.spines["bottom"].set_color("#CBD5E1")

    legend_patches = [
        mpatches.Patch(color=c, label=n, alpha=0.85)
        for _, (n, c) in cat_display.items()
    ]
    ax.legend(handles=legend_patches, loc="lower right", fontsize=8,
              framealpha=0.9, edgecolor="#CBD5E1")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


def chart_speech_style(speech_style_ratio: dict) -> io.BytesIO | None:
    """발화 스타일 도넛 차트."""
    formal = speech_style_ratio.get("formal", 0)
    informal = speech_style_ratio.get("informal", 0)
    if formal == 0 and informal == 0:
        return None

    fig, ax = plt.subplots(figsize=(3.5, 3.5))
    fig.patch.set_facecolor("white")

    wedges, _ = ax.pie(
        [formal, informal],
        colors=["#2563EB", "#F97316"],
        startangle=90,
        wedgeprops=dict(width=0.55, edgecolor="white", linewidth=2),
    )
    ax.text(0, 0, f"{formal*100:.0f}%\n격식체",
            ha="center", va="center", fontsize=12, fontweight="bold", color="#1E293B")

    ax.legend(["격식체", "비격식체"], loc="lower center", bbox_to_anchor=(0.5, -0.12),
              fontsize=9, frameon=False, ncol=2)

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    buf.seek(0)
    return buf


# ──────────────────────────────────────────────────────────────────────────────
# PDF 페이지 콜백
# ──────────────────────────────────────────────────────────────────────────────


def _make_page_callback(reg_font: str):
    """페이지 번호 및 푸터를 추가하는 canvas 콜백을 반환합니다."""
    def on_page(canvas, doc):
        canvas.saveState()
        canvas.setFont(reg_font, 8)
        canvas.setFillColor(C_SUBTEXT)
        canvas.drawString(2 * cm, 1.3 * cm, "EduInsight AI  |  강의 분석 리포트")
        canvas.drawRightString(
            PAGE_W - 2 * cm, 1.3 * cm, f"{doc.page}"
        )
        # 얇은 구분선
        canvas.setStrokeColor(C_BORDER)
        canvas.setLineWidth(0.5)
        canvas.line(2 * cm, 1.7 * cm, PAGE_W - 2 * cm, 1.7 * cm)
        canvas.restoreState()

    return on_page


# ──────────────────────────────────────────────────────────────────────────────
# PDF 섹션 빌더
# ──────────────────────────────────────────────────────────────────────────────


def _metric_badge(label: str, value: str, unit: str, s: dict) -> Table:
    """지표 뱃지 카드를 Table로 생성합니다."""
    data = [
        [Paragraph(label, s["badge_label"])],
        [Paragraph(value, s["badge_value"])],
        [Paragraph(unit, s["badge_unit"])],
    ]
    t = Table(data, colWidths=[3.2 * cm])
    t.setStyle(
        TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT_BG),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ])
    )
    return t


def build_cover(data: dict, s: dict, reg: str, bold: str) -> list:
    """커버 페이지 플로어블 리스트."""
    story = []
    meta = data.get("metadata", {})
    sessions = meta.get("sessions", [])
    subjects = list(dict.fromkeys(ss.get("subject", "") for ss in sessions))

    # ── 헤더 블록 ──
    header_data = [[
        Paragraph("강의 분석 리포트", s["cover_title"]),
    ], [
        Paragraph("EduInsight AI", s["cover_sub"]),
    ]]
    header_table = Table(header_data, colWidths=[16 * cm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_PRIMARY),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 30),
        ("BOTTOMPADDING", (0, 0), (0, 0), 8),
        ("BOTTOMPADDING", (0, 1), (0, 1), 30),
        ("LEFTPADDING", (0, 0), (-1, -1), 20),
        ("RIGHTPADDING", (0, 0), (-1, -1), 20),
    ]))
    story.append(Spacer(1, 2.5 * cm))
    story.append(header_table)
    story.append(Spacer(1, 1 * cm))

    # ── 강의 정보 테이블 ──
    def info_row(key, val):
        return [
            Paragraph(key, ParagraphStyle("IK", fontName=bold, fontSize=9,
                                          textColor=C_PRIMARY, alignment=TA_CENTER)),
            Paragraph(val or "-", ParagraphStyle("IV", fontName=reg, fontSize=10,
                                                 textColor=C_TEXT)),
        ]

    info_rows = [
        info_row("과 정 명", meta.get("course_name", "")),
        info_row("강의 일자", meta.get("date", "")),
        info_row("담당 강사", meta.get("instructor", "")),
        info_row("보조 강사", meta.get("sub_instructor", "")),
        info_row("강의 주제", " / ".join(filter(None, subjects))),
        info_row("강의 ID", data.get("lecture_id", "")),
    ]
    info_table = Table(info_rows, colWidths=[3.5 * cm, 12.5 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), C_LIGHT_BG),
        ("FONTNAME", (0, 0), (-1, -1), reg),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [colors.white, C_GRAY_BG]),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.8 * cm))

    # ── 세션 테이블 ──
    if sessions:
        session_rows = [[
            Paragraph("세션", s["table_header"]),
            Paragraph("시간", s["table_header"]),
            Paragraph("과 목", s["table_header"]),
            Paragraph("내 용", s["table_header"]),
        ]]
        for i, ss in enumerate(sessions):
            session_rows.append([
                Paragraph(str(i + 1), s["table_center"]),
                Paragraph(ss.get("time", ""), s["table_center"]),
                Paragraph(ss.get("subject", ""), s["table_body"]),
                Paragraph(ss.get("content", ""), s["table_body"]),
            ])
        sess_table = Table(session_rows, colWidths=[1.5 * cm, 3.5 * cm, 4 * cm, 7 * cm])
        sess_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
            ("FONTNAME", (0, 0), (-1, -1), reg),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_GRAY_BG]),
        ]))
        story.append(sess_table)

    story.append(PageBreak())
    return story


def build_language_quality(analysis: dict, s: dict, reg: str, bold: str) -> list:
    """섹션 1: 언어 표현 품질 분석."""
    story = []
    lq = analysis.get("language_quality", {})
    ccm = analysis.get("concept_clarity_metrics", {})
    im = analysis.get("interaction_metrics", {})

    story.append(Paragraph("1. 언어 표현 품질 분석", s["section"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_ACCENT, spaceAfter=10))

    # ── 지표 뱃지 ──
    repeat_ratio = lq.get("repeat_ratio", 0)
    incomplete_ratio = lq.get("incomplete_sentence_ratio", 0)
    speech_rate = ccm.get("speech_rate_wpm", 0)
    q_count = im.get("understanding_question_count", 0)

    badges = [
        ("반복 표현 비율", f"{repeat_ratio * 100:.1f}%", "발화 전체 대비"),
        ("문장 완결성", f"{(1 - incomplete_ratio) * 100:.1f}%", "완결 문장 비율"),
        ("발화 속도", f"{speech_rate}", "단어/분 (wpm)"),
        ("이해 확인 질문", f"{q_count}회", "총 질문 수"),
    ]
    badge_cells = [[_metric_badge(l, v, u, s) for l, v, u in badges]]
    badge_row = Table(badge_cells, colWidths=[3.3 * cm] * 4, hAlign="CENTER")
    badge_row.setStyle(TableStyle([
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(badge_row)
    story.append(Spacer(1, 0.5 * cm))

    # ── 반복 표현 차트 + 발화 스타일 도넛 ──
    repeat_expr = lq.get("repeat_expressions", {})
    speech_style = lq.get("speech_style_ratio", {})

    repeat_buf = chart_repeat_expressions(repeat_expr)
    style_buf = chart_speech_style(speech_style)

    if repeat_buf or style_buf:
        story.append(Paragraph("반복 표현 및 발화 스타일", s["subsection"]))

    if repeat_buf and style_buf:
        img_repeat = Image(repeat_buf, width=10.5 * cm, height=5.5 * cm)
        img_style = Image(style_buf, width=4.5 * cm, height=4.5 * cm)
        row = Table(
            [[img_repeat, Spacer(0.3 * cm, 1), img_style]],
            colWidths=[10.5 * cm, 0.5 * cm, 5 * cm],
        )
        row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        story.append(row)
    elif repeat_buf:
        story.append(Image(repeat_buf, width=14 * cm, height=6 * cm))
    elif style_buf:
        story.append(Image(style_buf, width=5 * cm, height=5 * cm))

    story.append(PageBreak())
    return story


def build_scores(analysis: dict, s: dict, reg: str, bold: str) -> list:
    """섹션 2: 강의 품질 종합 평가."""
    story = []
    ss = analysis.get("summary_scores", {})
    if not ss:
        return story

    story.append(Paragraph("2. 강의 품질 종합 평가", s["section"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_ACCENT, spaceAfter=10))

    cat_map = {
        "lecture_structure": "강의 구조",
        "concept_clarity": "개념 명확성",
        "practice_linkage": "실습 연계",
        "interaction": "상호작용",
    }
    avgs = {k: cat_avg(ss.get(k, {})) for k in cat_map}
    overall = round(sum(avgs.values()) / len(avgs), 2) if avgs else 0.0

    # ── 종합 점수 배너 ──
    banner_data = [[
        Paragraph("종합 점수", ParagraphStyle("BL", fontName=reg, fontSize=10,
                                              textColor=C_SUBTEXT, alignment=TA_CENTER)),
        Paragraph(f"{overall:.2f}", ParagraphStyle("BV", fontName=bold, fontSize=34,
                                                    textColor=C_PRIMARY, alignment=TA_CENTER)),
        Paragraph("/ 5.00", ParagraphStyle("BD", fontName=reg, fontSize=13,
                                            textColor=C_SUBTEXT, alignment=TA_CENTER)),
        Paragraph(score_label(overall),
                  ParagraphStyle("BS", fontName=bold, fontSize=14,
                                 textColor=colors.HexColor(score_hex(overall)),
                                 alignment=TA_CENTER)),
    ]]
    banner = Table(banner_data, colWidths=[3 * cm, 4 * cm, 2.2 * cm, 3 * cm],
                   hAlign="CENTER")
    banner.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), C_LIGHT_BG),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(banner)
    story.append(Spacer(1, 0.5 * cm))

    # ── 레이더 차트 + 카테고리 점수 테이블 ──
    radar_img = Image(chart_radar(ss), width=9 * cm, height=9 * cm)

    cat_rows = [[
        Paragraph("카테고리", s["table_header"]),
        Paragraph("평균 점수", s["table_header"]),
        Paragraph("평가", s["table_header"]),
    ]]
    for key, name in cat_map.items():
        avg = avgs.get(key, 0)
        cat_rows.append([
            Paragraph(name, s["table_body"]),
            Paragraph(f"{avg:.2f}",
                      ParagraphStyle("CV", fontName=bold, fontSize=11,
                                     textColor=colors.HexColor(score_hex(avg)),
                                     alignment=TA_CENTER)),
            Paragraph(score_label(avg),
                      ParagraphStyle("CL", fontName=reg, fontSize=9,
                                     textColor=colors.HexColor(score_hex(avg)),
                                     alignment=TA_CENTER)),
        ])
    cat_table = Table(cat_rows, colWidths=[4 * cm, 2.5 * cm, 2.5 * cm])
    cat_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), C_ACCENT),
        ("FONTNAME", (0, 0), (-1, -1), reg),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.5, C_BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, C_GRAY_BG]),
    ]))

    dual = Table(
        [[radar_img, Spacer(0.3 * cm, 1), cat_table]],
        colWidths=[9 * cm, 0.5 * cm, 8.5 * cm],
    )
    dual.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 0),
    ]))
    story.append(dual)
    story.append(Spacer(1, 0.5 * cm))

    # ── 세부 항목 점수 차트 ──
    story.append(Paragraph("카테고리별 세부 항목 점수", s["subsection"]))
    scores_buf = chart_category_scores(ss)
    if scores_buf:
        n_items = sum(len(v) for v in ss.values())
        chart_h = max(5, n_items * 0.55 + 1.5)
        story.append(Image(scores_buf, width=16 * cm, height=chart_h * cm))

    story.append(PageBreak())
    return story


def build_insights(analysis: dict, s: dict, reg: str, bold: str) -> list:
    """섹션 3: 강의 개선 인사이트 (강점 / 개선 필요 사항 + 근거)."""
    story = []
    strengths = analysis.get("overall_strengths", [])
    issues = analysis.get("overall_issues", [])
    evidences = analysis.get("overall_evidences", [])

    story.append(Paragraph("3. 강의 개선 인사이트", s["section"]))
    story.append(HRFlowable(width="100%", thickness=2, color=C_ACCENT, spaceAfter=10))

    def section_header(text: str, bg: colors.Color) -> Table:
        t = Table(
            [[Paragraph(text, ParagraphStyle("SH", fontName=bold, fontSize=11,
                                             textColor=C_WHITE, alignment=TA_LEFT))]],
            colWidths=[16 * cm],
        )
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("TOPPADDING", (0, 0), (-1, -1), 9),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ]))
        return t

    def item_row(text: str, bg: colors.Color, evidence: str | None = None) -> Table:
        content = [[Paragraph(f"•  {text}", s["body"])]]
        if evidence:
            content.append([
                Paragraph(f"└ 근거:  {evidence}", s["evidence"])
            ])
        t = Table(content, colWidths=[16 * cm])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), bg),
            ("LEFTPADDING", (0, 0), (-1, -1), 16),
            ("RIGHTPADDING", (0, 0), (-1, -1), 14),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("BOX", (0, 0), (-1, -1), 0.5, C_BORDER),
        ]))
        return t

    # ── 강점 ──
    story.append(section_header("✓   강의 강점", C_SUCCESS))
    if strengths:
        for i, text in enumerate(strengths):
            bg = colors.white if i % 2 == 0 else colors.HexColor("#F0FDF4")
            story.append(item_row(text, bg))
    else:
        story.append(item_row("분석된 강점이 없습니다.", colors.white))

    story.append(Spacer(1, 0.6 * cm))

    # ── 개선 필요 사항 ──
    story.append(section_header("⚠   개선 필요 사항", C_DANGER))
    if issues:
        for i, text in enumerate(issues):
            bg = colors.white if i % 2 == 0 else colors.HexColor("#FFF5F5")
            ev = evidences[i] if i < len(evidences) else None
            story.append(item_row(text, bg, evidence=ev))
    else:
        story.append(item_row("분석된 개선 사항이 없습니다.", colors.white))

    # 근거 중 issue와 짝이 없는 것 별도 표시
    extra_evidences = evidences[len(issues):]
    if extra_evidences:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("추가 근거", s["subsection"]))
        for ev in extra_evidences:
            story.append(Paragraph(f"•  {ev}", s["small"]))

    return story


# ──────────────────────────────────────────────────────────────────────────────
# 진입점
# ──────────────────────────────────────────────────────────────────────────────


def generate_report(analysis_json_path: str, output_pdf_path: str) -> None:
    """analysis.json을 읽어 PDF 리포트를 생성합니다."""
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
    page_cb = _make_page_callback(reg)

    story: list = []
    story.extend(build_cover(data, styles, reg, bold))
    story.extend(build_language_quality(analysis, styles, reg, bold))
    story.extend(build_scores(analysis, styles, reg, bold))
    story.extend(build_insights(analysis, styles, reg, bold))

    doc.build(story, onFirstPage=page_cb, onLaterPages=page_cb)
    print(f"리포트 생성 완료: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="강의 분석 리포트 생성기 (analysis.json → PDF)")
    parser.add_argument("--input", required=True, help="analysis.json 파일 경로")
    parser.add_argument("--output", required=True, help="출력 PDF 파일 경로")
    args = parser.parse_args()

    generate_report(args.input, args.output)
