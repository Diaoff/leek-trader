from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.market.history_storage import MarketDailyBarStorage
from app.market.rl_dataset_service import RLDatasetBuilder
from app.market.rl_experiment_service import RLExperimentService
from app.market.symbols import normalize_a_share_symbol
from app.quant.simulator import RLEpisodeConfig, RLEpisodeSimulator
from app.schemas.market import (
    RLBatchEvaluationRead,
    RLBatchEvaluationRequest,
    RLBatchEvaluationTaskRead,
    RLDatasetFeatureMetadataRead,
    RLDatasetQualityRead,
    RLDatasetRead,
    RLDatasetRequest,
    RLDatasetSplitRead,
    RLDatasetSplitRequest,
    RLEpisodeSimulateRequest,
    RLEpisodeSimulationRead,
    RLStrategyPreviewRead,
    RLStrategyPreviewRequest,
)
from app.strategy.strategies.rl_trading import RLTradingStrategy
from app.tasks.market_tasks import run_rl_batch_evaluation_task

router = APIRouter()


@router.post("/rl/dataset", response_model=RLDatasetRead)
def build_rl_dataset(payload: RLDatasetRequest, db: Session = Depends(get_db)) -> RLDatasetRead:
    result = RLDatasetBuilder(db).build_dataset(**payload.model_dump())
    return RLDatasetRead(**result.to_dict())


@router.post("/rl/dataset.csv")
def build_rl_dataset_csv(payload: RLDatasetRequest, db: Session = Depends(get_db)) -> Response:
    csv_payload = RLDatasetBuilder(db).build_csv(**payload.model_dump())
    return Response(content=csv_payload, media_type="text/csv; charset=utf-8")


@router.post("/rl/dataset/split", response_model=RLDatasetSplitRead)
def build_rl_dataset_split(payload: RLDatasetSplitRequest, db: Session = Depends(get_db)) -> RLDatasetSplitRead:
    try:
        result = RLDatasetBuilder(db).build_split_dataset(**payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RLDatasetSplitRead(**result.to_dict())


@router.post("/rl/dataset/quality", response_model=RLDatasetQualityRead)
def inspect_rl_dataset_quality(payload: RLDatasetRequest, db: Session = Depends(get_db)) -> RLDatasetQualityRead:
    result = RLDatasetBuilder(db).build_quality_report(**payload.model_dump(exclude={"exclude_suspended"}))
    return RLDatasetQualityRead(**result.to_dict())


@router.get("/rl/dataset/features", response_model=RLDatasetFeatureMetadataRead)
def get_rl_dataset_features() -> RLDatasetFeatureMetadataRead:
    return RLDatasetFeatureMetadataRead(**RLDatasetBuilder.feature_metadata())


@router.post("/rl/episode/simulate", response_model=RLEpisodeSimulationRead)
def simulate_rl_episode(payload: RLEpisodeSimulateRequest, db: Session = Depends(get_db)) -> RLEpisodeSimulationRead:
    dataset = RLDatasetBuilder(db).build_dataset(
        symbols=payload.symbols,
        start_date=payload.start_date,
        end_date=payload.end_date,
        source=payload.source,
        adjustflag=payload.adjustflag,
        exclude_suspended=payload.exclude_suspended,
    )
    config = RLEpisodeConfig(
        initial_cash=payload.initial_cash,
        commission_rate=payload.commission_rate,
        slippage_rate=payload.slippage_rate,
        reward_mode=payload.reward_mode,
        max_position_pct=payload.max_position_pct,
        ma_short_window=payload.ma_short_window,
        ma_long_window=payload.ma_long_window,
    )
    result = RLEpisodeSimulator(config).simulate(
        dataset.records,
        policy_name=payload.policy,
        action_sequence=payload.action_sequence,
        action_encoding=payload.action_encoding,
    )
    return RLEpisodeSimulationRead(**result.to_dict())


@router.post("/rl/strategy-preview", response_model=RLStrategyPreviewRead)
def preview_rl_strategy(payload: RLStrategyPreviewRequest, db: Session = Depends(get_db)) -> RLStrategyPreviewRead:
    symbol = normalize_a_share_symbol(payload.symbol)
    dataset = RLDatasetBuilder(db).build_dataset(
        symbols=[symbol],
        start_date=payload.start_date,
        end_date=payload.end_date,
        source=payload.source,
        adjustflag=payload.adjustflag,
        exclude_suspended=payload.exclude_suspended,
    )
    storage_result = MarketDailyBarStorage(db).list_bars(
        symbol=symbol,
        source=payload.source,
        adjustflag=payload.adjustflag,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    strategy = RLTradingStrategy()
    bars = sorted(storage_result.bars, key=lambda item: item.trade_date)
    signal = strategy.evaluate(symbol, bars, payload.parameters) if bars else strategy.empty_signal(symbol)
    trajectory = strategy.replay(symbol, bars, payload.parameters) if bars else RLEpisodeSimulator().simulate(dataset.records).to_dict()
    return RLStrategyPreviewRead(
        status=trajectory.get("status", "empty"),
        symbol=symbol,
        signal=signal,
        trajectory=RLEpisodeSimulationRead(**trajectory),
    )


@router.post("/rl/batch-evaluation", response_model=RLBatchEvaluationTaskRead)
def submit_rl_batch_evaluation(payload: RLBatchEvaluationRequest) -> RLBatchEvaluationTaskRead:
    task = run_rl_batch_evaluation_task.delay(payload.model_dump(mode="json"))
    return RLBatchEvaluationTaskRead(task_id=task.id, status="submitted")


@router.post("/rl/batch-evaluation/run-now", response_model=RLBatchEvaluationRead)
def run_rl_batch_evaluation_now(payload: RLBatchEvaluationRequest, db: Session = Depends(get_db)) -> RLBatchEvaluationRead:
    try:
        result = RLExperimentService(db).run_batch_evaluation(**payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RLBatchEvaluationRead(**result)
