"""
Bug Triage Agent - REST API Server
FastAPI server để expose agent qua HTTP endpoints

Run: uvicorn api_server:app --reload --port 8000
Docs: http://localhost:8000/docs
"""

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from pathlib import Path
from typing import Optional
import uuid
import time
from datetime import datetime

from bug_agent import BugTriageAgent, BugReport, TriageResult

# ─── App setup ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Bug Triage Agent API",
    description="AI Agent phân tích Priority và Severity của bug reports",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

agent = BugTriageAgent()

# In-memory store cho batch jobs (dùng Redis/DB trong production)
job_store: dict[str, dict] = {}

# Serve static UI
STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# ─── Pydantic schemas ─────────────────────────────────────────────────────────

class BugReportRequest(BaseModel):
    description: str = Field(
        ...,
        description="Mô tả chi tiết về bug",
        examples=["Người dùng không thể đăng nhập bằng Google OAuth trên iOS Safari"]
    )
    environment: Optional[str] = Field(
        None,
        description="Môi trường xảy ra bug",
        examples=["production", "staging", "development"]
    )
    frequency: Optional[str] = Field(
        None,
        description="Tần suất tái hiện",
        examples=["always", "often", "sometimes", "rare"]
    )
    affected_users: Optional[str] = Field(
        None,
        description="Mô tả người dùng bị ảnh hưởng",
        examples=["all users", "admin only", "~500 users"]
    )
    component: Optional[str] = Field(
        None,
        description="Component/module bị lỗi",
        examples=["auth", "payment", "dashboard"]
    )
    reporter: Optional[str] = Field(
        None,
        description="Tên người báo cáo",
        examples=["john@company.com"]
    )
    platform: Optional[str] = Field(
        None,
        description="Platform xảy ra bug",
        examples=["iOS", "Android", "Web", "iOS, Android"]
    )
    app_version: Optional[str] = Field(
        None,
        description="Phiên bản ứng dụng",
        examples=["2.4.1", "3.0.0-beta"]
    )
    screenshots: Optional[list[str]] = Field(
        None,
        description="Danh sách ảnh màn hình dạng base64 data URL",
        max_length=4,
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "description": "Toàn bộ trang checkout không load được sau khi user thêm sản phẩm vào giỏ hàng. Lỗi 500 xuất hiện, ảnh hưởng 100% user trên production.",
                "environment": "production",
                "frequency": "always",
                "affected_users": "all users",
                "component": "checkout"
            }
        }
    }


class RootCause(BaseModel):
    cause: str
    check: str = ""


class TestCases(BaseModel):
    must_have: list[str] = []
    should_have: list[str] = []
    regression: list[str] = []


class TriageResponse(BaseModel):
    request_id: str
    timestamp: str
    priority: str
    priority_score: int
    priority_label: str
    priority_reason: str = ""
    severity: str
    severity_score: int
    severity_label: str
    severity_reason: str = ""
    reason: str
    factors: list[str]
    actions: list[str]
    root_causes: list[RootCause] = []
    test_cases: TestCases = TestCases()
    confidence: int
    processing_time_ms: int


class BatchRequest(BaseModel):
    reports: list[BugReportRequest] = Field(..., max_length=20)


class BatchJobResponse(BaseModel):
    job_id: str
    status: str
    total: int
    message: str


class BatchJobStatus(BaseModel):
    job_id: str
    status: str  # pending | processing | done | failed
    total: int
    completed: int
    results: Optional[list[TriageResponse]] = None
    error: Optional[str] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
def root():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/health", tags=["Health"])
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


@app.post("/analyze", response_model=TriageResponse, tags=["Triage"])
def analyze_bug(request: BugReportRequest):
    """
    Phân tích một bug report và trả về đánh giá Priority + Severity.

    - **description**: Bắt buộc. Mô tả chi tiết về bug.
    - **environment**: Môi trường xảy ra (production/staging/development).
    - **frequency**: Tần suất tái hiện (always/often/sometimes/rare).
    - **affected_users**: Phạm vi ảnh hưởng.
    - **component**: Module/component bị lỗi.
    """
    start = time.time()

    report = BugReport(
        description    = request.description,
        environment    = request.environment,
        frequency      = request.frequency,
        affected_users = request.affected_users,
        component      = request.component,
        reporter       = request.reporter,
        platform       = request.platform,
        app_version    = request.app_version,
        screenshots    = request.screenshots,
    )

    try:
        result: TriageResult = agent.analyze(report)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    elapsed_ms = int((time.time() - start) * 1000)

    return TriageResponse(
        request_id        = str(uuid.uuid4()),
        timestamp         = datetime.utcnow().isoformat(),
        priority          = result.priority,
        priority_score    = result.priority_score,
        priority_label    = result.priority_label,
        priority_reason   = result.priority_reason,
        severity          = result.severity,
        severity_score    = result.severity_score,
        severity_label    = result.severity_label,
        severity_reason   = result.severity_reason,
        reason            = result.reason,
        factors           = result.factors,
        actions           = result.actions,
        root_causes       = result.root_causes,
        test_cases        = result.test_cases,
        confidence        = result.confidence,
        processing_time_ms = elapsed_ms,
    )


@app.post("/analyze/batch", response_model=BatchJobResponse, tags=["Triage"])
def analyze_batch(request: BatchRequest, background_tasks: BackgroundTasks):
    """
    Phân tích nhiều bug reports cùng lúc (tối đa 20).
    Trả về job_id để theo dõi tiến trình.
    """
    job_id = str(uuid.uuid4())
    job_store[job_id] = {
        "status": "pending",
        "total": len(request.reports),
        "completed": 0,
        "results": [],
    }

    background_tasks.add_task(_process_batch, job_id, request.reports)

    return BatchJobResponse(
        job_id  = job_id,
        status  = "pending",
        total   = len(request.reports),
        message = f"Batch job đã được tạo. Dùng GET /analyze/batch/{job_id} để kiểm tra.",
    )


@app.get("/analyze/batch/{job_id}", response_model=BatchJobStatus, tags=["Triage"])
def get_batch_status(job_id: str):
    """Kiểm tra trạng thái và kết quả của một batch job."""
    if job_id not in job_store:
        raise HTTPException(status_code=404, detail=f"Job {job_id} không tồn tại")

    job = job_store[job_id]
    return BatchJobStatus(
        job_id    = job_id,
        status    = job["status"],
        total     = job["total"],
        completed = job["completed"],
        results   = job.get("results") if job["status"] == "done" else None,
        error     = job.get("error"),
    )


# ─── Background task ─────────────────────────────────────────────────────────

def _process_batch(job_id: str, reports: list[BugReportRequest]):
    job_store[job_id]["status"] = "processing"

    results = []
    for req in reports:
        start = time.time()
        try:
            report = BugReport(
                description    = req.description,
                environment    = req.environment,
                frequency      = req.frequency,
                affected_users = req.affected_users,
                component      = req.component,
            )
            result = agent.analyze(report)
            elapsed_ms = int((time.time() - start) * 1000)

            results.append(TriageResponse(
                request_id         = str(uuid.uuid4()),
                timestamp          = datetime.utcnow().isoformat(),
                priority           = result.priority,
                priority_score     = result.priority_score,
                priority_label     = result.priority_label,
                priority_reason    = result.priority_reason,
                severity           = result.severity,
                severity_score     = result.severity_score,
                severity_label     = result.severity_label,
                severity_reason    = result.severity_reason,
                reason             = result.reason,
                factors            = result.factors,
                actions            = result.actions,
                root_causes        = result.root_causes,
                test_cases         = result.test_cases,
                confidence         = result.confidence,
                processing_time_ms = elapsed_ms,
            ).model_dump())
        except Exception as e:
            results.append({"error": str(e), "description": req.description[:80]})

        job_store[job_id]["completed"] += 1

    job_store[job_id]["status"]  = "done"
    job_store[job_id]["results"] = results
