"""One way to configure logging, for processes that run in two places.

Every module here runs both as a local script and inside Lambda, and
`logging.basicConfig` only works in the first case. The Lambda runtime
installs its own handler on the root logger before any of our code imports,
and `basicConfig` is documented to do nothing - including not setting the
level - when the root logger already has a handler. The root level stays at
WARNING, every `log.info` is dropped, and CloudWatch shows only START, END
and REPORT. Nothing errors; the logs are simply not there.

This bit us for real: the first scheduled ingestion ran seven times faster
than the first manual one and there was no way to say where the time went.

The fix is two lines rather than a branch. `basicConfig` installs a handler
when there is none, which covers running locally and gives a readable format.
The explicit `setLevel` applies in both worlds, which is what was missing.
"""

from __future__ import annotations

import logging
import os

LOCAL_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging() -> None:
    """Make `log.info` actually appear, locally and in Lambda."""
    level = os.environ.get("LOG_LEVEL", "INFO").upper()

    # No-op under Lambda, where a handler already exists. Locally this is what
    # creates the handler, so the format belongs here and not in the Lambda
    # path - the runtime prefixes its own timestamp and request id.
    logging.basicConfig(level=level, format=LOCAL_FORMAT)

    # The line that was missing. Unlike basicConfig, this always takes effect.
    logging.getLogger().setLevel(level)

    # yfinance logs every download at INFO and drowns out everything else.
    logging.getLogger("yfinance").setLevel(logging.WARNING)
