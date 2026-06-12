#!/usr/bin/env python3
"""
Bug Triage Agent - CLI Interface
Usage: python cli.py
       python cli.py --json '{"description": "...", "environment": "production"}'
       python cli.py --file bug_report.json
"""

import argparse
import json
import sys
from pathlib import Path

from bug_agent import BugTriageAgent, BugReport, Priority, Severity

# ─── Color helpers (ANSI) ────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"

RED    = "\033[91m"
YELLOW = "\033[93m"
BLUE   = "\033[94m"
GREEN  = "\033[92m"
CYAN   = "\033[96m"
WHITE  = "\033[97m"
GRAY   = "\033[90m"

def color_priority(p: str) -> str:
    return {
        "P1": f"{RED}{BOLD}",
        "P2": f"{YELLOW}{BOLD}",
        "P3": f"{BLUE}{BOLD}",
        "P4": f"{GREEN}{BOLD}",
    }.get(p, WHITE)

def color_severity(s: str) -> str:
    return {
        "Critical": f"{RED}{BOLD}",
        "High":     f"{YELLOW}{BOLD}",
        "Medium":   f"{BLUE}{BOLD}",
        "Low":      f"{GREEN}{BOLD}",
    }.get(s, WHITE)

def bar(score: int, width: int = 20) -> str:
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled)


# ─── Pretty print result ─────────────────────────────────────────────────────

def print_result(result, report: BugReport):
    print(f"\n{CYAN}{'─' * 56}{RESET}")
    print(f"{BOLD}  🐛  Bug Triage Report{RESET}")
    print(f"{CYAN}{'─' * 56}{RESET}\n")

    # Priority & Severity
    pc = color_priority(result.priority)
    sc = color_severity(result.severity)

    print(f"  {BOLD}PRIORITY{RESET}   {pc}{result.priority}{RESET}  {DIM}{result.priority_label}{RESET}")
    print(f"  {GRAY}Score:     {bar(result.priority_score)} {result.priority_score}/100{RESET}\n")

    print(f"  {BOLD}SEVERITY{RESET}   {sc}{result.severity}{RESET}  {DIM}{result.severity_label}{RESET}")
    print(f"  {GRAY}Score:     {bar(result.severity_score)} {result.severity_score}/100{RESET}\n")

    print(f"  {BOLD}CONFIDENCE{RESET} {bar(result.confidence, 10)} {result.confidence}%\n")

    # Reason
    print(f"{CYAN}{'─' * 56}{RESET}")
    print(f"  {BOLD}Lý do đánh giá{RESET}\n")
    # Word wrap at 52 chars
    words = result.reason.split()
    line, lines = [], []
    for w in words:
        if sum(len(x) + 1 for x in line) + len(w) > 52:
            lines.append(" ".join(line))
            line = [w]
        else:
            line.append(w)
    if line:
        lines.append(" ".join(line))
    for l in lines:
        print(f"  {l}")

    # Factors
    print(f"\n{CYAN}{'─' * 56}{RESET}")
    print(f"  {BOLD}Yếu tố ảnh hưởng{RESET}\n")
    for f in result.factors:
        print(f"  {YELLOW}•{RESET} {f}")

    # Actions
    print(f"\n{CYAN}{'─' * 56}{RESET}")
    print(f"  {BOLD}Hành động đề xuất{RESET}\n")
    for i, a in enumerate(result.actions, 1):
        print(f"  {GREEN}{i}.{RESET} {a}")

    print(f"\n{CYAN}{'─' * 56}{RESET}\n")


# ─── Interactive mode ─────────────────────────────────────────────────────────

def interactive_mode(agent: BugTriageAgent):
    print(f"\n{CYAN}{BOLD}🐛 Bug Triage Agent{RESET} {DIM}(gõ 'quit' để thoát){RESET}\n")

    env_options   = ["production", "staging", "development", "all", ""]
    freq_options  = ["always", "often", "sometimes", "rare", ""]

    while True:
        # Description
        print(f"{BOLD}Mô tả bug{RESET} {DIM}(bắt buộc){RESET}:")
        desc = input("  > ").strip()
        if desc.lower() in ("quit", "exit", "q"):
            print(f"\n{DIM}Goodbye!{RESET}\n")
            break
        if not desc:
            print(f"{RED}  ⚠ Vui lòng nhập mô tả bug{RESET}\n")
            continue

        # Optional fields
        print(f"\n{BOLD}Môi trường{RESET} {DIM}[production/staging/development/all] (Enter để bỏ qua){RESET}:")
        env = input("  > ").strip().lower() or None
        if env and env not in env_options:
            env = None

        print(f"\n{BOLD}Tần suất{RESET} {DIM}[always/often/sometimes/rare] (Enter để bỏ qua){RESET}:")
        freq = input("  > ").strip().lower() or None
        if freq and freq not in freq_options:
            freq = None

        print(f"\n{BOLD}Người dùng bị ảnh hưởng{RESET} {DIM}(VD: 'all users', 'admin only') (Enter để bỏ qua){RESET}:")
        affected = input("  > ").strip() or None

        print(f"\n{BOLD}Component{RESET} {DIM}(VD: auth, payment, dashboard) (Enter để bỏ qua){RESET}:")
        component = input("  > ").strip() or None

        report = BugReport(
            description    = desc,
            environment    = env,
            frequency      = freq,
            affected_users = affected,
            component      = component,
        )

        print(f"\n{DIM}Đang phân tích...{RESET}")
        try:
            result = agent.analyze(report)
            print_result(result, report)
        except Exception as e:
            print(f"{RED}  ✗ Lỗi: {e}{RESET}\n")

        again = input(f"Phân tích bug khác? {DIM}[Y/n]{RESET}: ").strip().lower()
        if again in ("n", "no", "quit"):
            print(f"\n{DIM}Goodbye!{RESET}\n")
            break
        print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Bug Triage Agent - Phân tích priority và severity của bug"
    )
    parser.add_argument(
        "--json", "-j",
        help='JSON string chứa bug report. VD: \'{"description": "...", "environment": "production"}\''
    )
    parser.add_argument(
        "--file", "-f",
        help="Đường dẫn đến file JSON chứa bug report"
    )
    parser.add_argument(
        "--output", "-o",
        choices=["pretty", "json"],
        default="pretty",
        help="Định dạng output (mặc định: pretty)"
    )
    parser.add_argument(
        "--model", "-m",
        default="claude-sonnet-4-6",
        help="Claude model (mặc định: claude-sonnet-4-6)"
    )

    args = parser.parse_args()
    agent = BugTriageAgent(model=args.model)

    # JSON string input
    if args.json:
        try:
            data = json.loads(args.json)
        except json.JSONDecodeError as e:
            print(f"{RED}✗ JSON không hợp lệ: {e}{RESET}", file=sys.stderr)
            sys.exit(1)

        result = agent.analyze_from_dict(data)

        if args.output == "json":
            print(json.dumps({
                "priority":       result.priority,
                "priority_score": result.priority_score,
                "priority_label": result.priority_label,
                "severity":       result.severity,
                "severity_score": result.severity_score,
                "severity_label": result.severity_label,
                "reason":         result.reason,
                "factors":        result.factors,
                "actions":        result.actions,
                "confidence":     result.confidence,
            }, ensure_ascii=False, indent=2))
        else:
            report = BugReport(**{k: v for k, v in data.items() if k in BugReport.__dataclass_fields__})
            print_result(result, report)
        return

    # File input
    if args.file:
        path = Path(args.file)
        if not path.exists():
            print(f"{RED}✗ File không tìm thấy: {args.file}{RESET}", file=sys.stderr)
            sys.exit(1)

        with open(path) as f:
            data = json.load(f)

        # Support single report or array of reports
        reports = data if isinstance(data, list) else [data]
        for i, item in enumerate(reports, 1):
            if len(reports) > 1:
                print(f"\n{BOLD}Bug #{i}{RESET}")
            result = agent.analyze_from_dict(item)
            if args.output == "json":
                print(json.dumps({
                    "priority": result.priority, "severity": result.severity,
                    "reason": result.reason, "actions": result.actions,
                }, ensure_ascii=False, indent=2))
            else:
                report = BugReport(**{k: v for k, v in item.items() if k in BugReport.__dataclass_fields__})
                print_result(result, report)
        return

    # Default: interactive mode
    interactive_mode(agent)


if __name__ == "__main__":
    main()
