# Controlled Benchmarking

This directory contains the reproducible research tooling for the LLM Cost Optimizer.

## Why the benchmark is two-stage

A fair routing experiment should not make an additional paid LLM call just to compare routing policies. The benchmark therefore has two stages:

1. **Collection:** send each benchmark task independently to every active model and record actual token usage, cost, quality and latency.
2. **Replay:** use the collected observations to determine which model each routing strategy would have selected from pre-request information, then measure the selected model's observed outcome.

This lets baseline and weighted strategies be compared on the **same task/model observations**.

## Run

Start the backend first, ensure the model registry is populated and provider API keys are configured, then run:

```bash
python experiments/run_benchmark.py --base-url http://localhost:8000
```

For a small smoke test:

```bash
python experiments/run_benchmark.py --task-limit 2
```

The command makes real provider calls and can incur API charges. It writes results locally under `benchmarks/results/`; generated results should not be committed unless intentionally selected as project evidence.

## Analyze

```bash
python experiments/analyze_results.py benchmarks/results/raw_results.json
```

The analyzer reports:

- total actual cost
- average quality
- average latency
- successful tasks
- tasks with no eligible model
- savings relative to the baseline
- model selected for each task

## Experimental controls

Keep the following constant across strategies:

- benchmark task set
- prompt text
- minimum quality threshold
- model registry and pricing snapshot
- provider configuration
- output-token policy

Run the benchmark more than once if resources permit and report the number of repetitions. Do not treat one run as proof of general performance.

## Interpretation

The baseline is the transparent **cheapest eligible** strategy. The weighted strategy combines normalized estimated cost, registry quality estimate and historical latency when that signal is available. The experiment evaluates whether the weighted strategy changes the cost/quality trade-off rather than assuming it will produce savings.

No experimental result is hard-coded into the source code or documentation.
