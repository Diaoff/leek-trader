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
from app.schemas.backtest import BacktestOptimizationRequest, BacktestRunRequest, PortfolioBacktestRequest


class BacktestJobRegistry:
    _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="backtest")
    _lock = threading.Lock()

    def __init__(self, root: Path | None = None, *, prefix: str = "backtest", job_kind: str = "single") -> None:
        self.root = root or Path(__file__).resolve().parents[3] / "artifacts" / f"{prefix}_jobs"
        self.prefix = prefix
        self.job_kind = job_kind
        self.root.mkdir(parents=True, exist_ok=True)

    def submit(self, payload: dict[str, Any]) -> dict[str, Any]:
        job_id = f"{self.prefix}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        total = self._initial_progress_total(payload)
        status = {
            "job_id": job_id,
            "status": "queued",
            "progress_step": 0,
            "progress_total": total,
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
        for path in self.root.glob(f"{self.prefix}-*.json"):
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

    def history(self, user_id: int | None = None, *, limit: int = 20) -> list[dict[str, Any]]:
        jobs: list[dict[str, Any]] = []
        for path in self.root.glob(f"{self.prefix}-*.json"):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(payload, dict):
                continue
            normalized = self._normalize_job_payload(payload)
            if user_id is not None and int((normalized.get("payload") or {}).get("user_id") or 0) != user_id:
                continue
            if normalized.get("status") != "succeeded" or not isinstance(normalized.get("result"), dict):
                continue
            jobs.append(self._history_item(normalized))
        jobs.sort(key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""), reverse=True)
        return jobs[:limit]

    def _run_job(self, job_id: str, payload: dict[str, Any]) -> None:
        self._update(
            job_id,
            status="running",
            progress_step=0,
            progress_total=self._initial_progress_total(payload),
            progress_pct=0.0,
            progress_label=self._start_label(),
            progress_details=[],
            started_at=datetime.now(UTC).isoformat(),
        )

        def progress(step: int, total: int, label: str, details: list[str] | None = None) -> None:
            pct = round((step / max(total, 1)) * 100, 2)
            self._update(job_id, progress_step=step, progress_total=total, progress_pct=pct, progress_label=label, progress_details=details or [])

        try:
            with SessionLocal() as db:
                result = self._execute_payload(db, payload, progress)
            self._update(
                job_id,
                status="succeeded",
                progress_step=self._finished_step(result),
                progress_total=self._finished_step(result),
                progress_pct=100.0,
                progress_label=self._finish_label(),
                progress_details=self._finish_details(result),
                finished_at=datetime.now(UTC).isoformat(),
                result=result,
                error=None,
            )
        except Exception as error:
            self._update(
                job_id,
                status="failed",
                progress_pct=100.0,
                progress_label=self._failure_label(),
                progress_details=[str(error)],
                finished_at=datetime.now(UTC).isoformat(),
                error=str(error),
            )

    def _execute_payload(self, db, payload: dict[str, Any], progress: Any) -> dict[str, Any]:
        if self.job_kind == "portfolio":
            request = PortfolioBacktestRequest.model_validate(payload)
            return BacktestService().run_portfolio_backtest(
                db,
                tenant_id=payload.get("tenant_id"),
                user_id=payload.get("user_id"),
                progress_callback=progress,
                **request.model_dump(),
            )
        if self.job_kind == "optimization":
            request = BacktestOptimizationRequest.model_validate(payload)
            return BacktestService().run_parameter_optimization(
                db,
                tenant_id=payload.get("tenant_id"),
                user_id=payload.get("user_id"),
                progress_callback=progress,
                **request.model_dump(),
            )
        request = BacktestRunRequest.model_validate(payload)
        return BacktestService().run_single_symbol_backtest(
            db,
            tenant_id=payload.get("tenant_id"),
            user_id=payload.get("user_id"),
            progress_callback=progress,
            **request.model_dump(),
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
            temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str), encoding="utf-8")
            temp_path.replace(path)

    def _path(self, job_id: str) -> Path:
        safe_job_id = "".join(ch for ch in job_id if ch.isalnum() or ch in {"-", "_"})
        return self.root / f"{safe_job_id}.json"

    def _initial_progress_total(self, payload: dict[str, Any]) -> int:
        if self.job_kind == "portfolio":
            return len(payload.get("symbols") or []) + 2
        if self.job_kind == "optimization":
            total = 1
            for values in (payload.get("parameter_grid") or {}).values():
                total *= len(values or [])
            if payload.get("out_of_sample"):
                total += 1
            return max(total, 1)
        return 4

    def _start_label(self) -> str:
        return {"portfolio": "开始组合回测", "optimization": "开始参数扫描"}.get(self.job_kind, "开始回测")

    def _finish_label(self) -> str:
        return {"portfolio": "组合回测完成", "optimization": "参数扫描完成"}.get(self.job_kind, "回测完成")

    def _failure_label(self) -> str:
        return {"portfolio": "组合回测失败", "optimization": "参数扫描失败"}.get(self.job_kind, "回测失败")

    def _finished_step(self, result: dict[str, Any]) -> int:
        if self.job_kind == "portfolio":
            return int(result.get("bars") or 1)
        if self.job_kind == "optimization":
            return int(result.get("combinations") or 1) + (1 if result.get("out_of_sample") else 0)
        return 4

    def _finish_details(self, result: dict[str, Any]) -> list[str]:
        if self.job_kind == "portfolio":
            return [f"标的：{len(result.get('symbols') or [])} 个", f"交易：{result.get('trade_count', 0)} 笔"]
        if self.job_kind == "optimization":
            return [f"组合：{result.get('combinations', 0)} 组", f"最佳：{(result.get('best_candidate') or {}).get('metric_value', '--')}"]
        return [f"样本：{result.get('bars', 0)} 根", f"交易：{result.get('trade_count', 0)} 笔"]

    @staticmethod
    def _normalize_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        details = normalized.get("progress_details")
        if isinstance(details, list):
            normalized["progress_details"] = [str(item) for item in details]
        return normalized

    @staticmethod
    def _history_item(job: dict[str, Any]) -> dict[str, Any]:
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        best = result.get("best_candidate") if isinstance(result.get("best_candidate"), dict) else {}
        payload = job.get("payload") if isinstance(job.get("payload"), dict) else {}
        return {
            "job_id": job.get("job_id"),
            "created_at": job.get("created_at"),
            "updated_at": job.get("updated_at"),
            "symbol": result.get("symbol") or payload.get("symbol") or "",
            "strategy_type": result.get("strategy_type") or payload.get("strategy_type") or "",
            "strategy_id": result.get("strategy_id") or payload.get("strategy_id"),
            "strategy_name": result.get("strategy_name"),
            "target_metric": result.get("target_metric") or payload.get("target_metric") or "total_return_pct",
            "best_parameters": best.get("merged_parameters") or best.get("parameters") or {},
            "best_result": best.get("metrics") or {},
            "out_of_sample": result.get("out_of_sample"),
            "payload": payload,
        }
