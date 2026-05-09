from __future__ import annotations

import csv
import hashlib
import json
from dataclasses import dataclass
from datetime import date, timedelta
from io import StringIO
from typing import Any

from sqlalchemy.orm import Session

from app.market.history_storage import MarketDailyBarStorage
from app.market.quality_service import MarketDataQualityReport, MarketDataQualityService
from app.market.symbols import normalize_a_share_symbol
from app.quant.features import (
    RL_DATASET_FIELDS,
    RL_DATASET_SCHEMA_VERSION,
    RL_FACTOR_FIELDS,
    RL_FEATURE_DESCRIPTIONS,
    RL_LIQUIDITY_FIELDS,
    RL_NULLABLE_FIELDS,
    RL_PRICE_FIELDS,
    daily_bar_to_rl_record,
    normalization_hints,
)


@dataclass(slots=True)
class RLDatasetResult:
    status: str
    source: str
    adjustflag: str
    symbols: list[str]
    start_date: str | None
    end_date: str | None
    count: int
    fields: list[str]
    records: list[dict[str, Any]]
    manifest: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "source": self.source,
            "adjustflag": self.adjustflag,
            "symbols": self.symbols,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "count": self.count,
            "fields": self.fields,
            "manifest": self.manifest,
            "records": self.records,
        }


@dataclass(slots=True)
class RLDatasetSplitResult:
    schema_version: str
    source: str
    adjustflag: str
    symbols: list[str]
    train: RLDatasetResult
    test: RLDatasetResult
    split_date: str
    gap_days: int
    feature_groups: dict[str, list[str]]
    manifest: dict[str, Any]
    leakage_checks: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "adjustflag": self.adjustflag,
            "symbols": self.symbols,
            "train": self.train.to_dict(),
            "test": self.test.to_dict(),
            "split_date": self.split_date,
            "gap_days": self.gap_days,
            "feature_groups": self.feature_groups,
            "manifest": self.manifest,
            "leakage_checks": self.leakage_checks,
        }


class RLDatasetBuilder:
    def __init__(self, db: Session) -> None:
        self.db = db

    def build_dataset(
        self,
        *,
        symbols: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        exclude_suspended: bool = True,
    ) -> RLDatasetResult:
        normalized_symbols = self._normalize_symbols(symbols)
        records = self._collect_records(
            symbols=normalized_symbols,
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )
        all_records = self._collect_records(
            symbols=normalized_symbols,
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=False,
        )
        manifest = self._build_manifest(
            symbols=normalized_symbols,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            source=source,
            adjustflag=adjustflag,
            filters={"exclude_suspended": exclude_suspended},
            quality_records=all_records,
            options={},
        )
        return RLDatasetResult(
            status="ready" if records else "empty",
            source=source,
            adjustflag=adjustflag,
            symbols=normalized_symbols,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            count=len(records),
            fields=list(RL_DATASET_FIELDS),
            records=records,
            manifest=manifest,
        )

    def _collect_records(
        self,
        *,
        symbols: list[str],
        start_date: date | None,
        end_date: date | None,
        source: str,
        adjustflag: str,
        exclude_suspended: bool,
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        storage = MarketDailyBarStorage(self.db)
        for symbol in symbols:
            bars = storage.list_bars(
                symbol=symbol,
                source=source,
                adjustflag=adjustflag,
                start_date=start_date,
                end_date=end_date,
            ).bars
            for bar in bars:
                if exclude_suspended and bar.trade_status != 1:
                    continue
                records.append(daily_bar_to_rl_record(bar))
        records.sort(key=lambda record: (record["symbol"], record["trade_date"]))
        return records

    def build_split_dataset(
        self,
        *,
        symbols: list[str],
        split_date: date,
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
        exclude_suspended: bool = True,
        gap_days: int = 0,
    ) -> RLDatasetSplitResult:
        if gap_days < 0:
            raise ValueError("gap_days must be greater than or equal to 0")
        if start_date and split_date <= start_date:
            raise ValueError("split_date must be later than start_date")
        if end_date and split_date > end_date:
            raise ValueError("split_date must be earlier than or equal to end_date")
        train_end_date = split_date - timedelta(days=gap_days + 1)
        test_start_date = split_date
        train = self.build_dataset(
            symbols=symbols,
            start_date=start_date,
            end_date=train_end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )
        test = self.build_dataset(
            symbols=symbols,
            start_date=test_start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
            exclude_suspended=exclude_suspended,
        )
        normalized_symbols = self._normalize_symbols(symbols)
        leakage_checks = self._build_leakage_checks(
            symbols=normalized_symbols,
            train=train,
            test=test,
            split_date=split_date,
            train_end_date=train_end_date,
            test_start_date=test_start_date,
            gap_days=gap_days,
        )
        split_manifest = self._build_manifest(
            symbols=normalized_symbols,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            source=source,
            adjustflag=adjustflag,
            filters={"exclude_suspended": exclude_suspended},
            quality_records=[*train.records, *test.records],
            options={"split_date": split_date.isoformat(), "gap_days": gap_days},
        )
        return RLDatasetSplitResult(
            schema_version=RL_DATASET_SCHEMA_VERSION,
            source=source,
            adjustflag=adjustflag,
            symbols=normalized_symbols,
            train=train,
            test=test,
            split_date=split_date.isoformat(),
            gap_days=gap_days,
            feature_groups=self.feature_groups(),
            manifest=split_manifest,
            leakage_checks=leakage_checks,
        )

    def build_quality_report(
        self,
        *,
        symbols: list[str],
        start_date: date | None = None,
        end_date: date | None = None,
        source: str = "baostock",
        adjustflag: str = "2",
    ) -> MarketDataQualityReport:
        return MarketDataQualityService(self.db).build_daily_bar_quality_report(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            source=source,
            adjustflag=adjustflag,
        )

    @staticmethod
    def feature_metadata() -> dict[str, Any]:
        return {
            "schema_version": RL_DATASET_SCHEMA_VERSION,
            "fields": list(RL_DATASET_FIELDS),
            "nullable_fields": list(RL_NULLABLE_FIELDS),
            "feature_groups": RLDatasetBuilder.feature_groups(),
            "descriptions": dict(RL_FEATURE_DESCRIPTIONS),
            "normalization_hints": normalization_hints(),
        }

    @staticmethod
    def feature_groups() -> dict[str, list[str]]:
        return {
            "identity": ["symbol", "trade_date"],
            "price": list(RL_PRICE_FIELDS),
            "liquidity": list(RL_LIQUIDITY_FIELDS),
            "factor": list(RL_FACTOR_FIELDS),
        }

    def build_csv(self, **kwargs: Any) -> str:
        dataset = self.build_dataset(**kwargs)
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=RL_DATASET_FIELDS)
        writer.writeheader()
        writer.writerows(dataset.records)
        return output.getvalue()

    @staticmethod
    def _calendar_gap_days(trade_dates: list[date]) -> list[str]:
        if len(trade_dates) < 2:
            return []
        sorted_dates = sorted(set(trade_dates))
        gaps: list[str] = []
        for previous_date, current_date in zip(sorted_dates, sorted_dates[1:]):
            cursor = previous_date + timedelta(days=1)
            while cursor < current_date:
                gaps.append(cursor.isoformat())
                cursor += timedelta(days=1)
        return gaps

    def _build_manifest(
        self,
        *,
        symbols: list[str],
        start_date: str | None,
        end_date: str | None,
        source: str,
        adjustflag: str,
        filters: dict[str, Any],
        quality_records: list[dict[str, Any]],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        payload = {
            "schema_version": RL_DATASET_SCHEMA_VERSION,
            "symbols": symbols,
            "source": source,
            "adjustflag": adjustflag,
            "start_date": start_date,
            "end_date": end_date,
            "filters": filters,
            "options": options,
        }
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {
            "dataset_id": hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16],
            **payload,
            "quality_summary": self._quality_summary(quality_records),
            "normalization_hints": normalization_hints(),
        }

    def _quality_summary(self, records: list[dict[str, Any]]) -> dict[str, Any]:
        trade_dates_by_symbol: dict[str, list[date]] = {}
        for record in records:
            trade_dates_by_symbol.setdefault(str(record["symbol"]), []).append(date.fromisoformat(str(record["trade_date"])))
        null_counts = {field: sum(1 for record in records if record.get(field) is None) for field in RL_NULLABLE_FIELDS}
        return {
            "total_rows": len(records),
            "suspended_rows": sum(1 for record in records if record.get("trade_status") != 1),
            "st_rows": sum(1 for record in records if record.get("is_st") is True),
            "null_counts": {field: count for field, count in null_counts.items() if count > 0},
            "calendar_gap_count": sum(len(self._calendar_gap_days(trade_dates)) for trade_dates in trade_dates_by_symbol.values()),
        }

    @staticmethod
    def _build_leakage_checks(
        *,
        symbols: list[str],
        train: RLDatasetResult,
        test: RLDatasetResult,
        split_date: date,
        train_end_date: date,
        test_start_date: date,
        gap_days: int,
    ) -> dict[str, Any]:
        warnings: list[str] = []
        if train.count == 0 and test.count == 0:
            warnings.append("train and test partitions are both empty")
        elif train.count == 0:
            warnings.append("train partition is empty")
        elif test.count == 0:
            warnings.append("test partition is empty")
        train_symbols = {str(record["symbol"]) for record in train.records}
        test_symbols = {str(record["symbol"]) for record in test.records}
        coverage = {
            symbol: {
                "has_train": symbol in train_symbols,
                "has_test": symbol in test_symbols,
                "survivorship_bias_warning": symbol not in train_symbols or symbol not in test_symbols,
            }
            for symbol in symbols
        }
        if any(item["survivorship_bias_warning"] for item in coverage.values()):
            warnings.append("one or more symbols do not cover both train and test partitions; check survivorship bias")
        passed = train_end_date < split_date and test_start_date >= split_date
        if not passed:
            warnings.append("split boundaries may leak across train/test partitions")
        return {
            "status": "passed" if passed and not warnings else "warning",
            "train_end_date": train_end_date.isoformat(),
            "test_start_date": test_start_date.isoformat(),
            "split_date": split_date.isoformat(),
            "gap_days": gap_days,
            "checks": {
                "train_end_before_split": train_end_date < split_date,
                "test_start_on_or_after_split": test_start_date >= split_date,
            },
            "warnings": warnings,
            "symbol_coverage": coverage,
        }

    @staticmethod
    def _normalize_symbols(symbols: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for symbol in symbols:
            normalized_symbol = normalize_a_share_symbol(symbol)
            if not normalized_symbol or normalized_symbol in seen:
                continue
            seen.add(normalized_symbol)
            normalized.append(normalized_symbol)
        return normalized
