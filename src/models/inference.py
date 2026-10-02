"""SageMaker inference handlers.

SageMaker looks for these four functions by name inside the serving container.
Together they define the endpoint's contract:

    model_fn   load the artifact once, when the container starts
    input_fn   deserialise the request body
    predict_fn produce the prediction
    output_fn  serialise the response

The features are built here, server side, using the SAME pipeline as training
(ADR-11). The caller sends a date, never a feature vector - a caller cannot hold
60 days of history, and any divergence in how features are computed would be
train/serve skew that stays invisible until the model quietly degrades.
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd

CONTENT_TYPE_JSON = "application/json"


def model_fn(model_dir: str):
    """Called once per container start. Everything expensive belongs here."""
    from src.models.train import METADATA_FILENAME, MODEL_FILENAME

    path = Path(model_dir)
    model = joblib.load(path / MODEL_FILENAME)
    metadata = json.loads((path / METADATA_FILENAME).read_text())
    return {"model": model, "metadata": metadata}


def input_fn(request_body: str, content_type: str = CONTENT_TYPE_JSON) -> dict:
    """Parse and validate the request. Reject early and clearly."""
    if content_type != CONTENT_TYPE_JSON:
        raise ValueError(f"Unsupported content type: {content_type}")

    payload = json.loads(request_body)

    as_of = payload.get("date")
    if as_of is None:
        raise ValueError("Request must contain a 'date' field, e.g. {\"date\": \"2026-09-25\"}")

    try:
        as_of = pd.Timestamp(as_of)
    except Exception as exc:
        raise ValueError(f"'date' is not a valid date: {payload['date']}") from exc

    return {"as_of": as_of}


def predict_fn(request: dict, bundle: dict) -> dict:
    """Build features for the requested date and predict the following day."""
    from src.data.fetch import fetch_all
    from src.features.pipeline import make_inference_row

    model = bundle["model"]
    metadata = bundle["metadata"]
    as_of = request["as_of"]

    # A year of history is ample for the longest rolling window (20 days).
    frames = fetch_all(period="1y")
    row = make_inference_row(frames, as_of)

    # Column order is part of the model contract. Passing a DataFrame rather
    # than an array means scikit-learn verifies that contract against the names
    # it was fitted with, instead of trusting that this line got it right.
    X = row[metadata["feature_columns"]]
    value = float(model.predict(X)[0])

    last_close = float(frames["gold"]["close"].loc[: row.index[-1]].iloc[-1])
    feature_date = row.index[-1]

    result = {
        "feature_date": str(feature_date.date()),
        "current_price": round(last_close, 2),
        "target": metadata["target"],
    }

    if metadata["target"] == "return":
        result |= {
            "predicted_return": round(value, 6),
            "predicted_price": round(last_close * (1 + value), 2),
            "direction": "up" if value > 0 else "down",
            "confidence": "low",
            "note": ("Point forecasts of daily returns do not beat a naive baseline "
                     "on this data. Treat this value as informational."),
        }
    else:
        result |= {
            "predicted_volatility": round(value, 6),
            "predicted_move_usd": round(last_close * value, 2),
            "note": "Expected absolute move for the next trading day, in return units.",
        }

    return result


def output_fn(prediction: dict, accept: str = CONTENT_TYPE_JSON) -> str:
    if accept != CONTENT_TYPE_JSON:
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps(prediction)
