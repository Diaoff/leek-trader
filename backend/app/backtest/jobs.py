from __future__ import annotations

import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.backtest.service import BacktestService
from app.core.db import SessionLocal
from app.schemas.backtest import BacktestRunRequest


class BacktestJobRegistry:
    _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest")
    _lock = threading.Lock()

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "artifacts" / "backtest_jobs"
        self.root.mkdir(parents=True, exist_ok=True)

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = f"backtest-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        status = {
            "job_id": job_id,
            "status": "queued",
            "progress_step": 0,
            "progress_total": 4,
            "progress_pct": 0.0,
            "progress_label": "排队中",
            "progress_details": [],
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "result": None,
            "error": None,
            "payload": payload,
        }
        self._write_status(status)
        self._executor.submit(self._run_job, job_id, payload)
        return status

    def get(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return self._normalize_job_payload(payload) if isinstance(payload, dict) else None

    def latest(self, user_id: int | None = None) -> dict[str, Any] | None:
        jobs: list[dict[str, Any]] = []
        for path in self.root.glob("backtest-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                normalized = self._normalize_job_payload(payload)
                if user_id is not None and int((normalized.get("payload") or {}).get("user_id") or 0) != user_id:
                    continue
                jobs.append(normalized)
        if not jobs:
            return None
        return max(jobs, key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""))

    def _run_job(self, job_id: str, payload: dict[str, Any]) -> None:
        self._update(
            job_id,
            status="running",
            progress_step=0,
            progress_total=4,
            progress_pct=0.0,
            progress_label="开始回测",
            progress_details=[],
            started_at=datetime.now(UTC).isoformat(),
        )

        def progress(step: int, total: int, label: str, details: list[str] | None = None) -> None:
            pct = round((step / max(total, 1)) * 100, 2)
            self._update(job_id, progress_step=step, progress_total=total, progress_pct=pct, progress_label=label, progress_details=details or [])

        try:
            request = BacktestRunRequest.model_validate(payload)
            with SessionLocal() as db:
                result = BacktestService().run_single_symbol_backtest(
                    db,
                    tenant_id=payload.get("tenant_id"),
                    user_id=payload.get("user_id"),
                    progress_callback=progress,
                    **request.model_dump(),
                )
            self._update(
                job_id,
                status="succeeded",
                progress_step=4,
                progress_total=4,
                progress_pct=100.0,
                progress_label="回测完成",
                progress_details=[f"样本：{result.get('bars', 0)} 根", f"交易：{result.get('trade_count', 0)} 笔"],
                finished_at=datetime.now(UTC).isoformat(),
                result=result,
                error=None,
            )
        except Exception as error:
            self._update(
                job_id,
                status="failed",
                progress_pct=100.0,
                progress_label="回测失败",
                progress_details=[str(error)],
                finished_at=datetime.now(UTC).isoformat(),
                error=str(error),
            )

    def _update(self, job_id: str, **updates: Any) -> None:
        current = self.get(job_id) or {"job_id": job_id}
        current.update(updates)
        current["updated_at"] = datetime.now(UTC).isoformat()
        self._write_status(current)

    def _write_status(self, payload: dict[str, Any]) -> None:
        with self._lock:
            path = self._path(str(payload["job_id"]))
            temp_path = path.with_suffix(".tmp")
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            temp_path.replace(path)

    def _path(self, job_id: str) -> Path:
        safe_job_id = "".join(ch for ch in job_id if ch.isalnum() or ch in {"-", "_"})
        return self.root / f"{safe_job_id}.json"

    @staticmethod
    def _normalize_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        details = normalized.get("progress_details")
        if isinstance(details, list):
            normalized["progress_details"] = [str(item) for item in details]
        return normalized
