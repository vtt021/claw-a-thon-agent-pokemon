# 🐛 Bug Triage Agent

AI Agent sử dụng **VNG Cloud AI Platform** (model Qwen) để tự động đánh giá **Priority** và **Severity** của bug reports.

> Ghi chú: project ban đầu chạy trên Claude (Anthropic), sau đó đã chuyển sang VNG Cloud AI Platform qua client tương thích OpenAI.

## Cấu trúc project

```
bug-triage-agent/
├── agent/
│   ├── bug_agent.py     # Core agent logic
│   ├── cli.py           # CLI interface
│   └── api_server.py    # FastAPI REST server
├── examples/
│   └── sample_bugs.json # Bug reports mẫu
├── requirements.txt
└── README.md
```

## Setup

### 1. Cài dependencies

```bash
pip install -r requirements.txt
```

### 2. Cấu hình API key

```bash
export VNGCLOUD_API_KEY="vn-..."
```

Hoặc tạo file `.env`:
```
VNGCLOUD_API_KEY=vn-...
```

> Agent gọi endpoint `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` (xem `agent/bug_agent.py`).
> Đổi model bằng tham số `--model` (CLI) hoặc khi khởi tạo `BugTriageAgent(model=...)`.

---

## Cách dùng

### CLI - Interactive mode

```bash
cd agent
python cli.py
```

Agent sẽ hỏi từng trường thông tin, sau đó in kết quả ra terminal có màu sắc.

### CLI - JSON input

```bash
python cli.py --json '{"description": "Login bị lỗi 500 trên production", "environment": "production", "frequency": "always"}'
```

### CLI - JSON output (để pipe vào tool khác)

```bash
python cli.py --json '{"description": "..."}' --output json
```

### CLI - Batch từ file

```bash
python cli.py --file ../examples/sample_bugs.json
```

---

### REST API

#### Khởi động server

```bash
cd agent
uvicorn api_server:app --reload --port 8000
```

API docs tự động tại: **http://localhost:8000/docs**

#### Phân tích 1 bug

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "description": "Toàn bộ hệ thống login ngừng hoạt động sau deploy",
    "environment": "production",
    "frequency": "always",
    "affected_users": "all users"
  }'
```

Response:
```json
{
  "request_id": "...",
  "timestamp": "2024-01-15T10:30:00",
  "priority": "P1",
  "priority_score": 95,
  "priority_label": "Khẩn cấp",
  "priority_reason": "Ảnh hưởng 100% user trên production.",
  "severity": "Critical",
  "severity_score": 92,
  "severity_label": "Hệ thống ngừng hoạt động hoàn toàn",
  "severity_reason": "Tính năng login core ngừng, không có workaround.",
  "reason": "...",
  "factors": ["Production environment", "100% users affected", "Core auth feature"],
  "actions": ["Rollback ngay lập tức", "..."],
  "root_causes": [
    {"cause": "Deploy gần đây gây regression ở auth", "check": "So sánh diff release, xem log deploy"},
    {"cause": "Service xác thực / DB token down", "check": "Kiểm tra health check, connection pool"}
  ],
  "test_cases": {
    "must_have":   ["Login bằng tài khoản hợp lệ phải thành công"],
    "should_have": ["Login sai mật khẩu trả lỗi đúng", "Login trên iOS Safari"],
    "regression":  ["Smoke test login tự động sau mỗi deploy"]
  },
  "confidence": 95,
  "processing_time_ms": 1240
}
```

> Các trường mới: `priority_reason` / `severity_reason` (lý do phân loại riêng),
> `root_causes` (nguyên nhân thường gặp + cách kiểm tra để trace bug),
> `test_cases` (test case **must_have** / **should_have** / **regression** chống tái phát).

#### Batch analysis

```bash
# Tạo batch job
curl -X POST http://localhost:8000/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"reports": [{"description": "Bug 1..."}, {"description": "Bug 2..."}]}'

# Kiểm tra kết quả
curl http://localhost:8000/analyze/batch/{job_id}
```

---

## Tích hợp vào code Python

```python
from agent.bug_agent import BugTriageAgent, BugReport

agent = BugTriageAgent()

report = BugReport(
    description    = "User không thể reset password, email không gửi được",
    environment    = "production",
    frequency      = "always",
    affected_users = "all users who forgot password",
    component      = "auth",
)

result = agent.analyze(report)

print(f"Priority: {result.priority} ({result.priority_label}) — {result.priority_reason}")
print(f"Severity: {result.severity} ({result.severity_label}) — {result.severity_reason}")
print(f"Reason: {result.reason}")
print(f"Actions: {result.actions}")

print("\nNguyên nhân để trace bug:")
for rc in result.root_causes:
    print(f"  - {rc['cause']}  (kiểm tra: {rc['check']})")

print("\nTest case đề xuất:")
for group in ("must_have", "should_have", "regression"):
    for tc in result.test_cases.get(group, []):
        print(f"  [{group}] {tc}")
```

---

## Thang đo

### Priority
| Level | Ý nghĩa | Thời gian fix |
|-------|---------|---------------|
| P1    | Khẩn cấp — production down, data loss, security breach | Vài giờ |
| P2    | Cao — tính năng quan trọng broken | Trong sprint |
| P3    | Trung bình — tính năng phụ ảnh hưởng | Sprint tiếp theo |
| P4    | Thấp — cosmetic, edge case | Backlog |

### Severity
| Level    | Ý nghĩa |
|----------|---------|
| Critical | System down, mất dữ liệu, lỗ hổng bảo mật |
| High     | Tính năng core broken, không có workaround |
| Medium   | Tính năng bị suy giảm, có workaround |
| Low      | Lỗi nhỏ, cosmetic |
