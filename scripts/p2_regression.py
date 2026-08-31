#!/usr/bin/env python3
"""Deterministic P2 reliability/operations contract tests without live CCTV."""
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)
        print(f"[FAIL] {message}")
    else:
        print(f"[OK] {message}")


def main() -> int:
    runtime = (ROOT / "dashboard" / "src" / "runtimeGuards.js").read_text(encoding="utf-8")
    check("SNAPSHOT_CACHE_TTL_MS = 15000" in runtime, "snapshot fallback policy is 15 seconds")
    check("SNAPSHOT_INFLIGHT" in runtime and "new Response" in runtime, "snapshot requests are deduplicated and cloned safely")
    check("SNAPSHOT_CACHE.set(key" in runtime, "snapshot success and failure responses are cached")

    supervisor = (ROOT / "ai_engine" / "main.py").read_text(encoding="utf-8")
    check("AI_SUPERVISOR_INTERVAL_SECS" in supervisor, "AI supervisor heartbeat interval is configurable")
    check("AI_RESTART_BASE_DELAY_SECS" in supervisor and "AI_RESTART_MAX_DELAY_SECS" in supervisor, "AI worker restart backoff is bounded")
    check("publish(\"supervisor\"" in supervisor and "heartbeat(" in supervisor, "AI supervisor publishes process health")
    health = (ROOT / "ai_engine" / "process_health.py").read_text(encoding="utf-8")
    check("expire(KEY_PREFIX + name" in health, "AI process health entries expire when heartbeat stops")

    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    for token in ("AI_SUPERVISOR_INTERVAL_SECS", "AI_RESTART_BASE_DELAY_SECS", "AI_RESTART_MAX_DELAY_SECS", "AI_HEALTH_TTL_SECS"):
        check(token in compose, f"Compose exposes P2 setting: {token}")

    worker = (ROOT / "ai_engine" / "anpr_worker.py").read_text(encoding="utf-8")
    check("ANPR_MAX_CONCURRENT_TRACKS" in worker and "if len(states) > MAX_TRACKS" in worker, "ANPR track state is bounded")

    operations = (ROOT / "api" / "routes" / "operations.py").read_text(encoding="utf-8")
    check("ai_processes" in operations and "redis_streams" in operations, "operations overview exposes AI and Redis health")
    check("process health" in operations.lower() and "queue" in operations.lower(), "operations API documents process and queue telemetry")

    workflow = (ROOT / ".github" / "workflows" / "p0-release-gate.yml").read_text(encoding="utf-8")
    check("scripts/p2_regression.py" in workflow, "existing three-check CI gate executes P2 regression")
    check(len(re.findall(r"^  p0-.*:$", workflow, flags=re.MULTILINE)) == 3, "CI still declares exactly three checks")

    if FAILURES:
        print(f"\n{len(FAILURES)} P2 regression gate(s) failed.")
        return 1
    print("\nAll P2 regression gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
