# One image, three Lambda functions.
#
# The API, the daily ingestion job and the drift check all import the same
# feature pipeline. Building three images would mean three copies of pandas,
# three cold-start profiles to tune and three chances for the feature code to
# diverge between them. Instead the image is built once and each function
# overrides CMD with its own handler — Terraform sets `image_config.command`.
#
#   src.api.handler.handler            API behind API Gateway
#   src.data.ingest.handler            EventBridge: daily ingestion
#   src.monitoring.handler.handler     EventBridge: daily drift check
#
# arm64 on purpose: Lambda on Graviton is about 20 % cheaper per GB-second than
# x86 at the same performance for this workload. Build on an Apple Silicon Mac
# and it is also the native architecture, so no emulation.

FROM public.ecr.aws/lambda/python:3.13-arm64

# Dependencies first, in their own layer. Every pin in requirements-api.txt
# resolves to a prebuilt aarch64 wheel, so no compiler is installed here — the
# base image ships one, but nothing needs it and leaving it untouched keeps the
# layer small and the build reproducible.
COPY requirements-api.txt ${LAMBDA_TASK_ROOT}/

RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements-api.txt

# Application code last: it changes on every commit, the dependencies above do
# not. Keeping this order means a code change rebuilds one small layer instead
# of reinstalling pandas.
COPY src/ ${LAMBDA_TASK_ROOT}/src/

# Strip bytecode caches and the vendored test suites that ship inside scipy,
# sklearn and pandas. Worth roughly 40 MB, which is 40 MB less to pull on every
# cold start. Done in Python because the Lambda base image is minimal and has
# no `find`.
RUN python -c "\
import pathlib, shutil; \
root = pathlib.Path('${LAMBDA_TASK_ROOT}'); \
[shutil.rmtree(d, ignore_errors=True) for d in root.rglob('__pycache__')]; \
[shutil.rmtree(d, ignore_errors=True) for d in root.rglob('tests') if d.is_dir()]; \
[f.unlink(missing_ok=True) for f in root.rglob('*.pyc')]"

# Where the model artifact is unpacked at runtime. /tmp is the only writable
# path in a Lambda, and it survives between invocations of a warm container.
ENV MODEL_CACHE_DIR=/tmp \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Default: the API. Overridden per function by Terraform.
CMD ["src.api.handler.handler"]
