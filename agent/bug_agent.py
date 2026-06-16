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
    platform: Optional[str] = None         # e.g. "iOS", "Android", "Web"
    app_version: Optional[str] = None      # e.g. "2.4.1"
    screenshots: Optional[list[str]] = None  # base64 data URLs


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
    # ── Mở rộng ──
    priority_reason: str = ""                  # lý do riêng cho priority
    severity_reason: str = ""                  # lý do riêng cho severity
    root_causes: list[dict] = None             # [{"cause": str, "check": str}]
    test_cases: dict = None                    # {"must_have":[], "should_have":[], "regression":[]}
    raw_response: str = ""

    def __post_init__(self):
        if self.root_causes is None:
            self.root_causes = []
        if self.test_cases is None:
            self.test_cases = {"must_have": [], "should_have": [], "regression": []}


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

## Phân tích nguyên nhân (root cause) để trace bug
Dựa vào mô tả, hãy liệt kê các NGUYÊN NHÂN KHẢ DĨ THƯỜNG GẶP có thể gây ra loại bug này, sắp xếp
theo khả năng từ cao đến thấp. Với mỗi nguyên nhân, đề xuất CÁCH KIỂM TRA/XÁC MINH cụ thể (xem log gì,
kiểm tra config nào, query DB ra sao, reproduce thế nào...) để dev khoanh vùng nhanh. Suy luận theo
triệu chứng: ví dụ lỗi 500 → kiểm tra exception/stacktrace ở server, DB connection, migration; lỗi UI
trắng trang → kiểm tra console JS, lỗi render, API trả về sai shape; lỗi chỉ trên 1 trình duyệt →
kiểm tra CSS/JS API tương thích; lỗi chập chờn → race condition, cache, timeout, dữ liệu biên.

## Đề xuất test case (để verify lại fix và chống tái phát)
- **must_have**: test case BẮT BUỘC phải pass để xác nhận bug đã được fix (happy path của tính năng bị lỗi + đúng kịch bản gây ra bug).
- **should_have**: test case NÊN CÓ để tăng độ tin cậy (các biến thể, edge case liên quan, môi trường/nền tảng khác nhau).
- **regression**: test case nên đưa vào bộ regression / automation để bug KHÔNG LẶP LẠI về sau (bao gồm cả edge case biên đã gây lỗi).
Mỗi test case viết ngắn gọn, rõ ràng dạng "Khi... thì...", có thể kèm input và kết quả mong đợi.

Luôn trả về JSON hợp lệ, không có markdown fences."""


# ─── Agent Class ──────────────────────────────────────────────────────────────

class BugTriageAgent:
    """AI Agent phân tích và đánh giá bug reports sử dụng VNG Cloud AI Platform."""

    def __init__(
        self,
        model: str = "qwen/qwen3-5-27b",
        max_tokens: int = 4096,
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
  "priority_reason": "<1-2 câu giải thích vì sao priority ở mức này>",
  "severity": "Critical" | "High" | "Medium" | "Low",
  "severity_score": <0-100>,
  "severity_label": "<mô tả ngắn về mức độ nghiêm trọng>",
  "severity_reason": "<1-2 câu giải thích vì sao severity ở mức này>",
  "reason": "<giải thích tổng hợp 2-3 câu tại sao đánh giá như vậy>",
  "factors": ["<yếu tố 1>", "<yếu tố 2>", ...],
  "actions": ["<hành động đề xuất 1>", "<hành động 2>", "<hành động 3>"],
  "root_causes": [
    {{"cause": "<nguyên nhân khả dĩ, xếp theo khả năng cao→thấp>", "check": "<cách kiểm tra/xác minh cụ thể>"}}
  ],
  "test_cases": {{
    "must_have":   ["<test case bắt buộc để xác nhận đã fix>", ...],
    "should_have": ["<test case nên có, biến thể/edge case liên quan>", ...],
    "regression":  ["<test case đưa vào regression để chống tái phát>", ...]
  }},
  "confidence": <0-100, mức độ chắc chắn của đánh giá>
}}"""

    def _parse_response(self, raw: str) -> dict:
        """Parse JSON từ response của model."""
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        match = re.search(r"\{.*\}", clean, re.DOTALL)
        if not match:
            raise ValueError(f"Không tìm thấy JSON trong response: {raw[:200]}")
        return json.loads(match.group())

    @staticmethod
    def _normalize_root_causes(value) -> list[dict]:
        """Chuẩn hoá root_causes về list[{'cause','check'}], chịu được nhiều dạng input."""
        result = []
        if not value:
            return result
        if isinstance(value, dict):
            value = [value]
        for item in value:
            if isinstance(item, dict):
                cause = str(item.get("cause") or item.get("name") or item.get("reason") or "").strip()
                check = str(item.get("check") or item.get("how_to_check") or item.get("verify") or "").strip()
                if cause:
                    result.append({"cause": cause, "check": check})
            elif isinstance(item, str) and item.strip():
                result.append({"cause": item.strip(), "check": ""})
        return result

    @staticmethod
    def _normalize_test_cases(value) -> dict:
        """Chuẩn hoá test_cases về {'must_have','should_have','regression': [str,...]}."""
        out = {"must_have": [], "should_have": [], "regression": []}
        if not value:
            return out

        def _to_str_list(v) -> list[str]:
            items = v if isinstance(v, list) else [v]
            res = []
            for it in items:
                if isinstance(it, str) and it.strip():
                    res.append(it.strip())
                elif isinstance(it, dict):
                    txt = it.get("title") or it.get("name") or it.get("description") or it.get("case")
                    if txt:
                        expected = it.get("expected") or it.get("expected_result")
                        res.append(f"{txt} → {expected}" if expected else str(txt))
            return res

        if isinstance(value, dict):
            # các alias key thường gặp
            alias = {
                "must_have": ["must_have", "must", "must-have", "musthave", "bắt buộc"],
                "should_have": ["should_have", "should", "should-have", "shouldhave", "nên có"],
                "regression": ["regression", "regression_tests", "anti_regression", "chống tái phát"],
            }
            lowered = {str(k).lower(): val for k, val in value.items()}
            for canon, keys in alias.items():
                for k in keys:
                    if k in lowered:
                        out[canon].extend(_to_str_list(lowered[k]))
                        break
        elif isinstance(value, list):
            # nếu model trả phẳng -> coi tất cả là must_have
            out["must_have"].extend(_to_str_list(value))
        return out


    def analyze(self, report: BugReport) -> TriageResult:
        """
        Phân tích bug report và trả về TriageResult.

        Args:
            report: BugReport object chứa thông tin bug

        Returns:
            TriageResult với đánh giá đầy đủ
        """
        prompt = self._build_prompt(report)

        # Build user message — include screenshots as vision content if provided
        if report.screenshots:
            user_content = [{"type": "text", "text": prompt}]
            for img_data in report.screenshots[:4]:
                # Validate it's a data URL
                if img_data.startswith("data:image/"):
                    media_type = img_data.split(";")[0].split(":")[1]
                    b64 = img_data.split(",", 1)[1]
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:{media_type};base64,{b64}"},
                    })
        else:
            user_content = prompt

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            top_p=self.top_p,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_content},
            ],
        )

        raw = response.choices[0].message.content
        data = self._parse_response(raw)

        return TriageResult(
            priority        = data.get("priority", "P3"),
            priority_score  = int(data.get("priority_score", 50)),
            priority_label  = data.get("priority_label", ""),
            severity        = data.get("severity", "Medium"),
            severity_score  = int(data.get("severity_score", 50)),
            severity_label  = data.get("severity_label", ""),
            reason          = data.get("reason", ""),
            factors         = data.get("factors", []),
            actions         = data.get("actions", []),
            confidence      = int(data.get("confidence", 70)),
            priority_reason = data.get("priority_reason", ""),
            severity_reason = data.get("severity_reason", ""),
            root_causes     = self._normalize_root_causes(data.get("root_causes")),
            test_cases      = self._normalize_test_cases(data.get("test_cases")),
            raw_response    = raw,
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
            platform       = data.get("platform"),
            app_version    = data.get("app_version"),
            screenshots    = data.get("screenshots"),
        )
        return self.analyze(report)
