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

# Deployment status, marked on the node rather than left to the reader.
#
# The architecture below is the design, agreed before any of it was built, and
# it is unchanged. What changes month to month is how much of it is actually
# provisioned - and a diagram that does not say which is which quietly claims
# more than it should. Nodes carrying PLANNED are designed and not yet
# deployed; everything else is live and can be curled.
#
# This is cheaper to maintain than two diagrams, and it is the honest answer
# to "does this run?", which is the first question anyone asks.
PLANNED = "\n(planned)"

# Edges into something planned are drawn faintly, so an incomplete path is
# visible at a glance instead of having to be traced node by node.
PLANNED_EDGE = Edge(color="#cbd5e1", style="dashed")


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
            training = SagemakerTrainingJob("SageMaker\nTraining Job" + PLANNED)
            mlflow = Mlflow("MLflow\nTracking\n(local, ADR-9)")
            registry = S3("S3 /model\n+ Model Registry")

        with Cluster("Serving (online)"):
            gateway = APIGateway("API Gateway")
            facade = Lambda("predict\n(facade)")
            endpoint = SagemakerModel("SageMaker\nServerless Endpoint" + PLANNED)

        with Cluster("Observability"):
            logs = Cloudwatch("CloudWatch\nMetrics + Logs")
            drift = Lambda("drift-check\n(PSI / KS test)" + PLANNED)
            alarm = CloudwatchAlarm("Alarm" + PLANNED)
            sns = SimpleNotificationServiceSns("SNS\n(e-mail)" + PLANNED)

        with Cluster("Delivery"):
            actions = GithubActions("GitHub Actions" + PLANNED)
            ecr = ECR("ECR")

        config = SystemsManagerParameterStore("Parameter Store\n(config)" + PLANNED)

        # Ingestion -> storage
        schedule >> TRIGGER >> fetch >> DATA >> raw

        # Training path
        raw >> PLANNED_EDGE >> training
        training >> PLANNED_EDGE >> mlflow
        training >> PLANNED_EDGE >> registry
        registry >> PLANNED_EDGE >> endpoint

        # Inference path
        users >> DATA >> gateway >> DATA >> facade
        facade >> PLANNED_EDGE >> endpoint

        # Observability and the retraining loop
        facade >> DATA >> logs
        endpoint >> PLANNED_EDGE >> logs
        logs >> PLANNED_EDGE >> drift
        drift >> PLANNED_EDGE >> alarm >> PLANNED_EDGE >> sns
        drift >> PLANNED_EDGE >> training

        # Cross-cutting
        config >> PLANNED_EDGE >> facade
        actions >> PLANNED_EDGE >> ecr
        ecr >> DATA >> facade


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
        schedule = EventbridgeScheduler("EventBridge Scheduler\n(23:30 UTC, Mon-Fri)")
        fetch = Lambda("fetch")
        raw = S3("S3 /raw")

        with Cluster("SageMaker Training Job"):
            prep = SagemakerTrainingJob("preprocess\n+ features" + PLANNED)
            train = SagemakerTrainingJob("train Random Forest\n+ evaluate" + PLANNED)

        mlflow = Mlflow("MLflow\nparams, metrics,\nartifacts\n(local, ADR-9)")
        registry = S3("Model Registry\n(versioned)" + PLANNED)
        approved = SagemakerModel("approved model\n-> endpoint update" + PLANNED)

        schedule >> TRIGGER >> fetch >> DATA >> raw
        raw >> PLANNED_EDGE >> prep >> PLANNED_EDGE >> train
        train >> PLANNED_EDGE >> mlflow
        train >> PLANNED_EDGE >> registry
        registry >> PLANNED_EDGE >> approved


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
        facade = Lambda("predict\nvalidate + build features\n+ run the model")
        artifact = S3("S3 /models/current\nmodel.tar.gz")
        endpoint = SagemakerModel("SageMaker\nServerless Inference" + PLANNED)
        logs = Cloudwatch("CloudWatch\nlatency, errors,\npredictions")

        # What runs today: the facade loads the artifact once per cold start
        # and predicts in-process. SAGEMAKER_ENDPOINT is the switch (ADR-15).
        client >> DATA >> gateway >> DATA >> facade
        artifact >> Edge(color="#2563eb", label="once per cold start") >> facade
        facade >> Edge(color="#16a34a", label="prediction") >> gateway
        gateway >> Edge(color="#16a34a") >> client
        facade >> Edge(style="dotted", color="#6b7280") >> logs

        # The designed production path, one environment variable away.
        facade >> PLANNED_EDGE >> endpoint


if __name__ == "__main__":
    overview()
    training_path()
    inference_path()
    print("Rendered 3 diagrams into", __file__.rsplit("/", 1)[0])
