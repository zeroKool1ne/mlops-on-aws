"""Architecture diagrams for the Gold/USD MLOps project.

Diagram-as-code: the picture is generated from this file, so it stays in sync
with the system and is versioned in git like any other source.

Usage:
    ../../.venv/bin/python architecture.py

Requires graphviz on the system (brew install graphviz).
Renders three PNGs next to this file:
    01_architecture_overview.png  - the whole system
    02_training_path.png          - offline path: how a model is produced
    03_inference_path.png         - online path: how a prediction is served
"""

from diagrams import Cluster, Diagram, Edge
from diagrams.aws.compute import ECR, Lambda
from diagrams.aws.integration import EventbridgeScheduler, SimpleNotificationServiceSns
from diagrams.aws.management import Cloudwatch, CloudwatchAlarm, SystemsManagerParameterStore
from diagrams.aws.ml import SagemakerModel, SagemakerTrainingJob
from diagrams.aws.network import APIGateway
from diagrams.aws.storage import S3
from diagrams.onprem.ci import GithubActions
from diagrams.onprem.client import Users
from diagrams.onprem.mlops import Mlflow

# Shared look. graphviz renders left-to-right so the flow reads like a sentence.
GRAPH_ATTR = {
    "fontsize": "16",
    "bgcolor": "transparent",
    "pad": "0.5",
    "splines": "spline",
}

# Edge styles carry meaning, not decoration:
#   solid  = data moves
#   dashed = a trigger fires (control, not data)
DATA = Edge(color="#2563eb")
TRIGGER = Edge(color="#ca8a04", style="dashed")


def overview() -> None:
    """The whole system on one page - the slide you present first."""
    with Diagram(
        "Gold/USD Forecasting - AWS Architecture",
        filename="01_architecture_overview",
        show=False,
        direction="LR",
        graph_attr=GRAPH_ATTR,
    ):
        users = Users("API consumer")

        with Cluster("Ingestion (daily, automated)"):
            schedule = EventbridgeScheduler("EventBridge\nScheduler")
            fetch = Lambda("fetch\n(yfinance)")

        with Cluster("Data Lake"):
            raw = S3("S3 /raw\n(Parquet)")

        with Cluster("Training (offline)"):
            training = SagemakerTrainingJob("SageMaker\nTraining Job")
            mlflow = Mlflow("MLflow\nTracking")
            registry = S3("S3 /model\n+ Model Registry")

        with Cluster("Serving (online)"):
            gateway = APIGateway("API Gateway")
            facade = Lambda("predict\n(facade)")
            endpoint = SagemakerModel("SageMaker\nServerless Endpoint")

        with Cluster("Observability"):
            logs = Cloudwatch("CloudWatch\nMetrics + Logs")
            drift = Lambda("drift-check\n(PSI / KS test)")
            alarm = CloudwatchAlarm("Alarm")
            sns = SimpleNotificationServiceSns("SNS\n(e-mail)")

        with Cluster("Delivery"):
            actions = GithubActions("GitHub Actions")
            ecr = ECR("ECR")

        config = SystemsManagerParameterStore("Parameter Store\n(config)")

        # Ingestion -> storage
        schedule >> TRIGGER >> fetch >> DATA >> raw

        # Training path
        raw >> DATA >> training
        training >> DATA >> mlflow
        training >> DATA >> registry
        registry >> DATA >> endpoint

        # Inference path
        users >> DATA >> gateway >> DATA >> facade >> DATA >> endpoint

        # Observability and the retraining loop
        facade >> DATA >> logs
        endpoint >> DATA >> logs
        logs >> DATA >> drift
        drift >> TRIGGER >> alarm >> TRIGGER >> sns
        drift >> Edge(color="#dc2626", style="dashed", label="drift detected") >> training

        # Cross-cutting
        config >> Edge(style="dotted", color="#6b7280") >> facade
        actions >> DATA >> ecr >> DATA >> facade


def training_path() -> None:
    """Offline path. Runs on a schedule or when drift is detected - never per request.

    This is the half that students most often blur into the serving path.
    """
    with Diagram(
        "Training Path (offline - daily or on drift)",
        filename="02_training_path",
        show=False,
        direction="LR",
        graph_attr=GRAPH_ATTR,
    ):
        schedule = EventbridgeScheduler("EventBridge\n(daily 06:00 UTC)")
        fetch = Lambda("fetch")
        raw = S3("S3 /raw")

        with Cluster("SageMaker Training Job"):
            prep = SagemakerTrainingJob("preprocess\n+ features")
            train = SagemakerTrainingJob("train XGBoost\n+ evaluate")

        mlflow = Mlflow("MLflow\nparams, metrics,\nartifacts")
        registry = S3("Model Registry\n(versioned)")
        approved = SagemakerModel("approved model\n-> endpoint update")

        schedule >> TRIGGER >> fetch >> DATA >> raw >> DATA >> prep >> DATA >> train
        train >> DATA >> mlflow
        train >> DATA >> registry
        registry >> Edge(label="beats baseline?", color="#16a34a") >> approved


def inference_path() -> None:
    """Online path. Runs per request, in milliseconds. No training happens here."""
    with Diagram(
        "Inference Path (online - per request)",
        filename="03_inference_path",
        show=False,
        direction="LR",
        graph_attr=GRAPH_ATTR,
    ):
        client = Users("Client")
        gateway = APIGateway("API Gateway\nPOST /predict")
        facade = Lambda("predict\nvalidate + build features")
        endpoint = SagemakerModel("SageMaker\nServerless Inference")
        logs = Cloudwatch("CloudWatch\nlatency, errors,\npredictions")

        client >> DATA >> gateway >> DATA >> facade >> DATA >> endpoint
        endpoint >> Edge(color="#16a34a", label="prediction") >> facade
        facade >> Edge(color="#16a34a") >> gateway >> Edge(color="#16a34a") >> client
        facade >> Edge(style="dotted", color="#6b7280") >> logs


if __name__ == "__main__":
    overview()
    training_path()
    inference_path()
    print("Rendered 3 diagrams into", __file__.rsplit("/", 1)[0])
