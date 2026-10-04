"""The FastAPI application.

One application serves three audiences (ADR-13):

    /              a demo page, so the project can be shown without a terminal
    /docs          the generated OpenAPI documentation
    /predict       the REST contract other software talks to

It runs unchanged under uvicorn on a laptop, inside the container, and as a
Lambda behind API Gateway. The only thing that differs is where the model runs,
and that is decided in `serving.py`.
"""

from __future__ import annotations

import logging
import time
from datetime import date as date_type

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse

from src.api import serving
from src.api.schemas import (
    BaselineResponse,
    HealthResponse,
    ModelCardResponse,
    PredictRequest,
    PredictResponse,
)
from src.logging_setup import configure_logging

log = logging.getLogger(__name__)
configure_logging()

DESCRIPTION = """
Forecasts the next trading day's **gold price volatility** from ten years of
market data — gold, the dollar index, oil, equities and the VIX.

Send a date, get a forecast. Features are built server side with the same
pipeline that trained the model, so the numbers the model sees in production
are computed exactly as they were in training.

Every figure is measured against a naive baseline. Where the model does not
beat that baseline, the response says so.
"""

app = FastAPI(
    title="Gold/USD Forecasting API",
    description=DESCRIPTION,
    version="1.0.0",
    license_info={"name": "MIT", "url": "https://opensource.org/licenses/MIT"},
    contact={"name": "Daniel Vasić", "url": "https://github.com/zeroKool1ne/mlops-on-aws"},
)


def _evaluation() -> dict | None:
    """Holdout metrics from the artifact, or None if they were not shipped.

    Lives next to the model in model.tar.gz, so the metrics travel with the
    weights they describe. A model card assembled from a file somewhere else
    is a model card that can disagree with the model.
    """
    import json
    from pathlib import Path

    try:
        path = Path(serving.MODEL_DIR) / "evaluation.json"
        if not path.exists() and serving.LOCAL_CACHE.exists():
            path = serving.LOCAL_CACHE / "evaluation.json"
        return json.loads(path.read_text()) if path.exists() else None
    except Exception:
        log.warning("evaluation artifact unreadable", exc_info=True)
        return None


@app.get("/health", response_model=HealthResponse, tags=["operations"],
         summary="Liveness and model status")
def health() -> HealthResponse:
    """Whether the service is up and whether it has a model to answer with.

    Deliberately returns 200 even when no model is loaded: the container is
    alive and should not be recycled by a health check, and the payload says
    plainly what is missing.
    """
    meta = serving.metadata()
    return HealthResponse(
        status="ok" if meta else "degraded",
        target=meta["target"] if meta else None,
        model_loaded=meta is not None,
        serving_mode=serving.serving_mode(),
        training_window=meta["training_window"] if meta else None,
        n_features=len(meta["feature_columns"]) if meta else None,
    )


@app.post("/predict", response_model=PredictResponse, tags=["inference"],
          summary="Forecast the next trading day")
def predict(request: PredictRequest) -> PredictResponse:
    """Build features as of the requested date and forecast the following day.

    Omit the date to use the most recent day with complete data — which is what
    a scheduled caller wants and saves it from having to know the market calendar.
    """
    as_of = request.date or date_type.today()

    started = time.perf_counter()
    try:
        result = serving.predict({"date": str(as_of)})
    except ValueError as exc:
        # Callable but unanswerable: a date before the data begins, or a
        # weekend with no complete feature row. The caller can fix this.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        log.exception("prediction failed")
        raise HTTPException(status_code=503, detail=f"Prediction unavailable: {exc}") from exc
    elapsed = int((time.perf_counter() - started) * 1000)

    return PredictResponse(**result, served_by=serving.serving_mode(), latency_ms=elapsed)


@app.get("/model", response_model=ModelCardResponse, tags=["operations"],
         summary="Model card, machine-readable")
def model_card() -> ModelCardResponse:
    """What the running model is: target, features, training window, metrics.

    The prose model card lives in `docs/model-card.md`. This endpoint is the
    part a monitoring system can read, and it comes from the artifact itself
    rather than from a document that can fall out of date.
    """
    meta = serving.metadata()
    if meta is None:
        raise HTTPException(status_code=503, detail="No model artifact available")

    evaluation = _evaluation()

    return ModelCardResponse(
        target=meta["target"],
        feature_columns=meta["feature_columns"],
        n_training_rows=meta["n_training_rows"],
        training_window=meta["training_window"],
        hyperparameters=meta["hyperparameters"],
        evaluation=evaluation,
    )


@app.get("/baseline", response_model=BaselineResponse, tags=["operations"],
         summary="Model versus the naive baseline")


@app.get("/baseline", response_model=BaselineResponse, tags=["operations"],
         summary="Model versus the naive baseline")
def baseline() -> BaselineResponse:
    """How much better than doing nothing clever — on data the model never saw.

    This is the number the project is actually about. A forecasting service
    that cannot state its margin over a naive baseline is asking to be trusted
    on the strength of having been built.

    RMSE rather than MAE, and the two disagree here: the model makes fewer
    large misses at the cost of a larger typical error. For a volatility
    forecast that is the trade worth making — the day the model calls quiet and
    the market is not is the day that costs money — so the promotion gate
    decides on RMSE. The disagreement is in `evaluation` on /model rather than
    hidden.
    """
    evaluation = _evaluation()
    if evaluation is None:
        raise HTTPException(
            status_code=503,
            detail="No evaluation artifact available. The model has not been scored "
                   "against a holdout in this deployment.",
        )

    improvement = evaluation["improvement_over_baseline_pct"]
    required = evaluation.get("min_improvement_required_pct", 0.0)

    if improvement < 0:
        verdict = "worse than the baseline — this model should not be promoted"
    elif improvement < required:
        verdict = (f"better than the baseline by {improvement:.2f} %, but under the "
                   f"{required:.1f} % promotion threshold")
    else:
        verdict = (f"beats the baseline by {improvement:.2f} % on "
                   f"{evaluation['n_holdout_rows']} untouched days")

    return BaselineResponse(
        target=evaluation["target"],
        metric="rmse",
        model_score=evaluation["model"]["rmse"],
        baseline_score=evaluation["baseline"]["rmse"],
        improvement_pct=improvement,
        verdict=verdict,
    )


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def demo() -> str:
    """A single page that calls the API in front of the audience.

    This is the demo surface from ADR-13: no terminal, no slides, one URL.
    """
    from src.api.page import render

    return render(serving.metadata(), serving.serving_mode())
