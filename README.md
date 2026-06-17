# 🐛 Bug Triage Agent — Trợ lý phân loại bug tự động

Bug Triage Agent giúp đội QA và dev đánh giá mức ưu tiên của bug nhanh và nhất quán: thay vì tranh luận thủ công "lỗi này gấp đến đâu", agent phân tích mô tả và đưa ra đánh giá có cơ sở trong vài giây. Chạy trên **VNG Cloud AI Platform** (model Qwen), dùng được qua **web, CLI hoặc REST API**.

> Ghi chú: project ban đầu chạy trên Claude (Anthropic), sau đó đã chuyển sang VNG Cloud AI Platform qua client tương thích OpenAI.

---

## Input

Mô tả bug, kèm thông tin tùy chọn như môi trường, tần suất tái hiện, phạm vi user ảnh hưởng, component, nền tảng, phiên bản và ảnh chụp màn hình.

## Output — agent trả về kết quả có cấu trúc gồm:

- **Priority (P1–P4)** kèm điểm số 0–100, nhãn mức độ và **lý do phân loại riêng** (vì sao ở mức này).
- **Severity (Critical–Low)** kèm điểm số 0–100, nhãn và **lý do riêng**, tách biệt với priority.
- **Các yếu tố ảnh hưởng** tới quyết định (môi trường, phạm vi user, tính năng core/phụ, rủi ro dữ liệu, có workaround hay không…).
- **Hành động đề xuất** — các bước nên làm tiếp theo (rollback, mở incident, báo on-call…).
- **Nguyên nhân thường gặp để trace bug** — danh sách nguyên nhân khả dĩ xếp theo khả năng cao→thấp, mỗi cái kèm **cách kiểm tra cụ thể** (xem log nào, query gì, reproduce ra sao).
- **Bộ test case đề xuất** chia 3 nhóm: `must_have` (bắt buộc để verify fix), `should_have` (nên test thêm các biến thể/edge case), `regression` (đưa vào automation để bug không tái phát).
- **Chỉ số độ tin cậy (0–100)** của toàn bộ đánh giá.
- **Metadata:** request_id, timestamp, thời gian xử lý (ms).

---

## Use case thực tế thường gặp

- **Tiếp nhận bug mới:** dán mô tả để gán nhãn P1–P4 ngay, tránh để lỗi nghiêm trọng lọt xuống cuối hàng đợi.
- **Dọn backlog tồn đọng:** dùng chế độ batch (file JSON hoặc API) chạy hàng loạt bug cũ rồi sắp xếp lại theo điểm priority.
- **Chuẩn hóa tiêu chí trong nhóm:** cả team dùng chung một thang đánh giá, giảm tranh cãi khi review.
- **Rút ngắn thời gian khoanh vùng:** dev đọc phần "nguyên nhân + cách kiểm tra" để biết xem log nào, query gì trước khi đào sâu.
- **Đảm bảo chất lượng khi đóng bug:** lấy test case gợi ý để verify fix và bổ sung test regression.
- **Tích hợp tự động:** gọi REST API từ hệ thống ticket (Jira, GitLab…) để mỗi bug mới tự động được chấm priority khi tạo.

## Use case ít gặp / nâng cao

- Phân tích bug từ ảnh chụp màn hình lỗi (vision) khi mô tả bằng chữ không rõ.
- Hỗ trợ viết postmortem: dùng phần nguyên nhân + yếu tố ảnh hưởng làm khung phân tích sự cố.
- Onboarding người mới: giúp thành viên mới hiểu cách đánh giá mức độ nghiêm trọng theo chuẩn của team.
- Đánh giá rủi ro trước release: batch-analyze các bug đang mở để quyết định có nên hoãn deploy không.
- Sinh nhanh checklist QA từ bộ test case gợi ý cho các tính năng vừa sửa.

## Hướng mở rộng phát triển

- Tích hợp sâu 2 chiều với Jira/Linear: tự động cập nhật field priority/severity và comment lý do vào ticket.
- Bot Slack/Teams: chấm bug ngay trong kênh chat khi có người báo lỗi.
- Lưu lịch sử và dashboard thống kê: theo dõi phân bố priority, thời gian xử lý, xu hướng bug theo component.
- Học từ phản hồi: cho phép team điều chỉnh đánh giá của agent và dùng dữ liệu đó để tinh chỉnh prompt/tiêu chí.
- Tự động gợi ý người phụ trách (auto-assign) dựa trên component và lịch sử.
- Phát hiện bug trùng lặp: so khớp mô tả với các bug đã có để gộp.
- Thay job_store in-memory bằng Redis/DB để chạy production đa-instance.

---

## Cấu trúc project

```
bug-triage-agent/
├── agent/
│   ├── bug_agent.py        # Core agent logic: prompt, gọi model, parse kết quả
│   ├── cli.py              # CLI interface (interactive / json / batch)
│   ├── api_server.py       # FastAPI REST server
│   └── static/
│       └── index.html      # Web UI (single-file)
├── examples/
│   └── sample_bugs.json    # Bug reports mẫu
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

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
PORT=8080
```

> Agent gọi endpoint `https://maas-llm-aiplatform-hcm.api.vngcloud.vn/v1` (xem `agent/bug_agent.py`).
> Đổi model bằng tham số `--model` (CLI) hoặc khi khởi tạo `BugTriageAgent(model=...)`.

---

## Cách dùng

### Giao diện Web

```bash
cd agent
uvicorn api_server:app --reload --port 8000
```

- Web UI: **http://localhost:8000**
- API docs (Swagger): **http://localhost:8000/docs**

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

#### Phân tích 1 bug — `POST /analyze`

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

#### Batch analysis

```bash
# Tạo batch job (tối đa 20 report)
curl -X POST http://localhost:8000/analyze/batch \
  -H "Content-Type: application/json" \
  -d '{"reports": [{"description": "Bug 1..."}, {"description": "Bug 2..."}]}'

# Kiểm tra trạng thái & kết quả
curl http://localhost:8000/analyze/batch/{job_id}
```

#### Health check

```bash
curl http://localhost:8000/health
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

---

## Chạy bằng Docker

```bash
export VNGCLOUD_API_KEY="vn-..."
docker compose up --build
```

Server chạy tại `http://localhost:8080` (đổi qua biến `PORT`). Hoặc build thủ công:

```bash
docker build -t bug-triage-agent .
docker run -p 8080:8080 -e VNGCLOUD_API_KEY="vn-..." bug-triage-agent
```

---

<p align="center"><sub>Made with 🐛 for Claw-a-thon</sub></p>
