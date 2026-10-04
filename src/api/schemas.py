"""Request and response models.

These exist for three reasons at once: FastAPI validates against them,
the OpenAPI specification is generated from them, and they are the written
contract between this service and its callers. One definition, three jobs.
"""

from __future__ import annotations

from datetime import date as date_type

from pydantic import BaseModel, Field


class PredictRequest(BaseModel):
    """A prediction request carries a date and nothing else.

    The caller does not send features. It cannot: the model uses rolling
    windows spanning up to twenty trading days, which no API consumer holds.
    Features are built server side with the training pipeline (ADR-11).
    """

    date: date_type | None = Field(
        default=None,
        description="Build features as of this trading day and forecast the next one. "
                    "Defaults to the most recent day with complete data.",
        examples=["2026-09-30"],
    )


class PredictResponse(BaseModel):
    feature_date: str = Field(description="The last trading day that went into the features.")
    current_price: float = Field(description="Gold close on feature_date, in USD.")
    target: str = Field(description="What the model predicts: 'return' or 'volatility'.")
    predicted_volatility: float | None = Field(
        default=None, description="Expected absolute move of the next day, in return units."
    )
    predicted_move_usd: float | None = Field(
        default=None, description="The same figure expressed in USD."
    )
    predicted_return: float | None = Field(
        default=None, description="Signed return forecast. Only for the 'return' target."
    )
    predicted_price: float | None = Field(default=None)
    direction: str | None = Field(default=None)
    note: str | None = Field(default=None, description="How far this number may be trusted.")
    served_by: str = Field(description="'sagemaker' or 'local' — where the model ran.")
    latency_ms: int


class HealthResponse(BaseModel):
    status: str
    target: str | None = None
    model_loaded: bool
    serving_mode: str
    training_window: list[str] | None = None
    n_features: int | None = None


class ModelCardResponse(BaseModel):
    """The machine-readable half of the model card."""

    target: str
    feature_columns: list[str]
    n_training_rows: int
    training_window: list[str]
    hyperparameters: dict
    evaluation: dict | None = None


class BaselineResponse(BaseModel):
    """How the model compares with doing nothing clever."""

    target: str
    metric: str
    model_score: float
    baseline_score: float
    improvement_pct: float
    verdict: str
