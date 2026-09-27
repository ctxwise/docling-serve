# OmniDocBench evaluator (pinned) + matplotlib for the charts
FROM python:3.10-slim
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ git && rm -rf /var/lib/apt/lists/*
ARG OMNIDOCBENCH_COMMIT=f133a71e9e91c3621c7ce8994200a7b394a06eb3
RUN git clone https://github.com/opendatalab/OmniDocBench.git /evalkit && git -C /evalkit checkout "$OMNIDOCBENCH_COMMIT"
WORKDIR /evalkit
RUN pip install --no-cache-dir -e . matplotlib==3.7.5 \
 && (python -c "import evaluate; evaluate.load('bleu'); evaluate.load('meteor')" || true)
