from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.core.auth import get_current_active_user, get_current_superuser
from app.core.db import get_db
from app.market.history_storage import MarketDailyBarStorage
from app.market.rl_dataset_service import RLDatasetBuilder
from app.market.rl_experiment_service import RLExperimentService
from app.market.symbols import normalize_a_share_symbol
from app.quant.simulator import RLEpisodeConfig, RLEpisodeSimulator
from app.models.user import User
from app.quant.training import RLModelRegistry, RLTrainingJobRegistry, RLTrainingService
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
    RLModelCompareRead,
    RLModelListRead,
    RLModelDeleteRead,
    RLModelRead,
    RLModelStatusUpdateRequest,
    RLTrainingJobRead,
    RLTrainingRequest,
    RLTrainingResolveRead,
    RLTrainingResolveRequest,
    RLTrainingScopeOptionsRead,
)
from app.strategy.strategies.rl_trading import RLTradingStrategy
from app.tasks.market_tasks import run_rl_batch_evaluation_task

router = APIRouter()


def _rl_model_service(db: Session, user_id: int) -> RLTrainingService:
    root = Path(__file__).resolve().parents[4] / "artifacts" / "rl_models" / f"user-{user_id}"
    return RLTrainingService(db, registry=RLModelRegistry(root))


def _rl_job_registry(user_id: int) -> RLTrainingJobRegistry:
    artifacts_root = Path(__file__).resolve().parents[4] / "artifacts"
    job_root = artifacts_root / "rl_training_jobs" / f"user-{user_id}"
    model_root = artifacts_root / "rl_models" / f"user-{user_id}"
    return RLTrainingJobRegistry(job_root, model_root=model_root)


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
        drawdown_penalty_coef=payload.drawdown_penalty_coef,
        turnover_penalty_coef=payload.turnover_penalty_coef,
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
def submit_rl_batch_evaluation(
    payload: RLBatchEvaluationRequest,
    current_user: User = Depends(get_current_superuser),
) -> RLBatchEvaluationTaskRead:
    task = run_rl_batch_evaluation_task.delay(payload.model_dump(mode="json"))
    return RLBatchEvaluationTaskRead(task_id=task.id, status="submitted")


@router.post("/rl/batch-evaluation/run-now", response_model=RLBatchEvaluationRead)
def run_rl_batch_evaluation_now(
    payload: RLBatchEvaluationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_superuser),
) -> RLBatchEvaluationRead:
    try:
        result = RLExperimentService(db).run_batch_evaluation(**payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RLBatchEvaluationRead(**result)


@router.get("/rl/training/scopes", response_model=RLTrainingScopeOptionsRead)
def list_rl_training_scopes(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLTrainingScopeOptionsRead:
    return RLTrainingScopeOptionsRead(**_rl_model_service(db, current_user.id).list_scope_options())


@router.post("/rl/training/resolve", response_model=RLTrainingResolveRead)
def resolve_rl_training_symbols(payload: RLTrainingResolveRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLTrainingResolveRead:
    payload_data = payload.model_dump()
    symbols = _rl_model_service(db, current_user.id).resolve_symbols(**payload_data)
    response_scope = "+".join(payload.scopes or [payload.scope])
    return RLTrainingResolveRead(
        scope=response_scope,
        count=len(symbols),
        symbols=[{"symbol": item.symbol, "name": item.name, "source": item.source} for item in symbols],
    )




@router.post("/rl/training/jobs", response_model=RLTrainingJobRead)
def submit_rl_training_job(payload: RLTrainingRequest, current_user: User = Depends(get_current_active_user)) -> RLTrainingJobRead:
    job = _rl_job_registry(current_user.id).submit(payload.model_dump(mode="json"))
    return RLTrainingJobRead(**job)


@router.get("/rl/training/jobs/latest", response_model=RLTrainingJobRead)
def get_latest_rl_training_job(current_user: User = Depends(get_current_active_user)) -> RLTrainingJobRead:
    job = _rl_job_registry(current_user.id).latest()
    if job is None:
        raise HTTPException(status_code=404, detail="rl training job not found")
    return RLTrainingJobRead(**job)


@router.get("/rl/training/jobs/{job_id}", response_model=RLTrainingJobRead)
def get_rl_training_job(job_id: str, current_user: User = Depends(get_current_active_user)) -> RLTrainingJobRead:
    job = _rl_job_registry(current_user.id).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="rl training job not found")
    return RLTrainingJobRead(**job)


@router.post("/rl/training/train", response_model=RLModelRead)
def train_rl_model(payload: RLTrainingRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLModelRead:
    try:
        model = _rl_model_service(db, current_user.id).train(**payload.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return RLModelRead(**model)


@router.get("/rl/models", response_model=RLModelListRead)
def list_rl_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLModelListRead:
    return RLModelListRead(models=[RLModelRead(**model) for model in _rl_model_service(db, current_user.id).list_models()])


@router.get("/rl/models/compare", response_model=RLModelCompareRead)
def compare_rl_models(db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLModelCompareRead:
    return RLModelCompareRead(models=_rl_model_service(db, current_user.id).compare_models())


@router.get("/rl/models/{model_id}", response_model=RLModelRead)
def get_rl_model(model_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLModelRead:
    model = _rl_model_service(db, current_user.id).get_model(model_id)
    if model is None:
        raise HTTPException(status_code=404, detail="rl model not found")
    return RLModelRead(**model)


@router.patch("/rl/models/{model_id}/status", response_model=RLModelRead)
def update_rl_model_status(model_id: str, payload: RLModelStatusUpdateRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLModelRead:
    try:
        model = _rl_model_service(db, current_user.id).update_model_status(model_id, payload.status)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if model is None:
        raise HTTPException(status_code=404, detail="rl model not found")
    return RLModelRead(**model)


@router.delete("/rl/models/{model_id}", response_model=RLModelDeleteRead)
def delete_rl_model(model_id: str, db: Session = Depends(get_db), current_user: User = Depends(get_current_active_user)) -> RLModelDeleteRead:
    deleted = _rl_model_service(db, current_user.id).delete_model(model_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="rl model not found")
    return RLModelDeleteRead(status="deleted", model_id=model_id)
