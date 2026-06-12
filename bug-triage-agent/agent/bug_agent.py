"""
Bug Triage Agent - Core Logic
Đánh giá Priority và Severity của bug dựa trên mô tả người dùng
"""

import json
import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from openai import OpenAI


# ─── Enums & Data Models ──────────────────────────────────────────────────────

class Priority(str, Enum):
    P1 = "P1"  # Critical - fix immediately
    P2 = "P2"  # High - fix this sprint
    P3 = "P3"  # Medium - fix next sprint
    P4 = "P4"  # Low - backlog


class Severity(str, Enum):
    CRITICAL = "Critical"   # System down / data loss
    HIGH     = "High"       # Major feature broken
    MEDIUM   = "Medium"     # Feature degraded
    LOW      = "Low"        # Minor / cosmetic


class Environment(str, Enum):
    PRODUCTION  = "production"
    STAGING     = "staging"
    DEVELOPMENT = "development"
    ALL         = "all"


class Frequency(str, Enum):
    ALWAYS    = "always"     # 100%
    OFTEN     = "often"      # ~70%
    SOMETIMES = "sometimes"  # ~30%
    RARE      = "rare"       # ~5%


@dataclass
class BugReport:
    description: str
    environment: Optional[str] = None
    frequency: Optional[str] = None
    affected_users: Optional[str] = None   # e.g. "all users", "admin only"
    component: Optional[str] = None        # e.g. "auth", "payment"
    reporter: Optional[str] = None


@dataclass
class TriageResult:
    priority: str
    priority_score: int       # 0–100
    priority_label: str
    severity: str
    severity_score: int       # 0–100
    severity_label: str
    reason: str
    factors: list[str]
    actions: list[str]
    confidence: int           # 0–100, how confident the agent is
    raw_response: str = ""


# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Bạn là một Senior QA Engineer và Engineering Manager có 10+ năm kinh nghiệm.
Nhiệm vụ của bạn là phân tích bug reports và đánh giá:

## Thang đo Priority (P1–P4)
- **P1 (Khẩn cấp)**: Production bị ảnh hưởng, dữ liệu có nguy cơ mất mát, bảo mật bị xâm phạm, hoặc >50% user không thể sử dụng tính năng core. Cần fix trong vài giờ.
- **P2 (Cao)**: Tính năng quan trọng bị broken cho một nhóm user đáng kể, hoặc có workaround nhưng UX rất tệ. Fix trong sprint hiện tại.
- **P3 (Trung bình)**: Tính năng phụ bị ảnh hưởng, có workaround ổn, ảnh hưởng nhỏ. Fix sprint tiếp theo.
- **P4 (Thấp)**: Cosmetic, edge case hiếm gặp, hoặc cải tiến nhỏ. Backlog.

## Thang đo Severity
- **Critical**: Hệ thống không hoạt động, mất dữ liệu, lỗ hổng bảo mật nghiêm trọng
- **High**: Tính năng chính bị broken hoàn toàn, không có workaround
- **Medium**: Tính năng bị suy giảm, có workaround
- **Low**: Lỗi nhỏ, cosmetic, không ảnh hưởng workflow chính

## Các yếu tố cần xem xét
1. Phạm vi ảnh hưởng (bao nhiêu user/% bị ảnh hưởng)
2. Môi trường (production > staging > dev)
3. Tần suất tái hiện (100% > thỉnh thoảng > hiếm khi)
4. Tính năng core hay phụ
5. Rủi ro dữ liệu / bảo mật
6. Có workaround không
7. Thời điểm (cuối tháng, release sắp tới...)

Luôn trả về JSON hợp lệ, không có markdown fences."""


# ─── Agent Class ──────────────────────────────────────────────────────────────

class BugTriageAgent:
    """AI Agent phân tích và đánh giá bug reports sử dụng VNG Cloud AI Platform."""

    def __init__(
        self,
        model: str = "minimax/minimax-m2.5",
        max_tokens: int = 2000,
        temperature: float = 1.0,
        top_p: float = 0.95,
    ):
        self.client = OpenAI(
            api_key=os.environ["VNGCLOUD_API_KEY"],
            base_url="https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1",
        )
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.top_p = top_p

    def _build_prompt(self, report: BugReport) -> str:
        """Tạo prompt từ BugReport."""
        lines = [f"Bug Description:\n{report.description}"]

        if report.environment:
            lines.append(f"Environment: {report.environment}")
        if report.frequency:
            freq_map = {
                "always":    "Luôn luôn xảy ra (100%)",
                "often":     "Thường xuyên (~70%)",
                "sometimes": "Đôi khi (~30%)",
                "rare":      "Hiếm khi (~5%)",
            }
            lines.append(f"Tần suất: {freq_map.get(report.frequency, report.frequency)}")
        if report.affected_users:
            lines.append(f"Người dùng bị ảnh hưởng: {report.affected_users}")
        if report.component:
            lines.append(f"Component: {report.component}")

        context = "\n".join(lines)

        return f"""{context}

---
Hãy phân tích bug report trên và trả về JSON với cấu trúc sau (chỉ JSON thuần túy):
{{
  "priority": "P1" | "P2" | "P3" | "P4",
  "priority_score": <0-100>,
  "priority_label": "<Khẩn cấp | Cao | Trung bình | Thấp>",
  "severity": "Critical" | "High" | "Medium" | "Low",
  "severity_score": <0-100>,
  "severity_label": "<mô tả ngắn về mức độ nghiêm trọng>",
  "reason": "<giải thích 2-3 câu tại sao đánh giá như vậy>",
  "factors": ["<yếu tố 1>", "<yếu tố 2>", ...],
  "actions": ["<hành động đề xuất 1>", "<hành động 2>", "<hành động 3>"],
  "confidence": <0-100, mức độ chắc chắn của đánh giá>
}}"""

    def _parse_response(self, raw: str) -> dict:
        """Parse JSON từ response của model."""
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            raise ValueError(f"Không tìm thấy JSON trong response: {raw[:200]}")
        return json.loads(match.group())

    def analyze(self, report: BugReport) -> TriageResult:
        """
        Phân tích bug report và trả về TriageResult.

        Args:
            report: BugReport object chứa thông tin bug

        Returns:
            TriageResult với đánh giá đầy đủ
        """
        prompt = self._build_prompt(report)

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            presence_penalty=0,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": prompt},
            ],
        )

        raw = response.choices[0].message.content
        data = self._parse_response(raw)

        return TriageResult(
            priority       = data.get("priority", "P3"),
            priority_score = int(data.get("priority_score", 50)),
            priority_label = data.get("priority_label", ""),
            severity       = data.get("severity", "Medium"),
            severity_score = int(data.get("severity_score", 50)),
            severity_label = data.get("severity_label", ""),
            reason         = data.get("reason", ""),
            factors        = data.get("factors", []),
            actions        = data.get("actions", []),
            confidence     = int(data.get("confidence", 70)),
            raw_response   = raw,
        )

    def analyze_from_dict(self, data: dict) -> TriageResult:
        """Tiện ích tạo BugReport từ dict và phân tích."""
        report = BugReport(
            description    = data.get("description", ""),
            environment    = data.get("environment"),
            frequency      = data.get("frequency"),
            affected_users = data.get("affected_users"),
            component      = data.get("component"),
            reporter       = data.get("reporter"),
        )
        return self.analyze(report)
