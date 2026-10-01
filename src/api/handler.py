"""Lambda entry point.

Mangum translates between API Gateway's event format and ASGI, which is what
turns the FastAPI application into a Lambda handler without restructuring it
(ADR-13). There is no second application for the cloud - this file is the whole
adapter.
"""

from mangum import Mangum

from src.api.main import app

handler = Mangum(app, lifespan="off")
