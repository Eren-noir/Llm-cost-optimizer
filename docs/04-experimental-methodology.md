# Experimental Methodology

## Research question

Can intelligent per-task model routing reduce LLM operating cost while maintaining an acceptable response-quality threshold?

## Experimental groups

1. **Fixed-model baseline:** all benchmark tasks are sent to the same selected reference model.
2. **Cheapest-eligible routing:** the baseline routing strategy selects the lowest-cost model whose configured quality estimate satisfies the quality threshold.
3. **Weighted routing:** cost and quality are combined using a normalized weighted score.

## Benchmark categories

The initial benchmark contains simple, medium, and complex tasks in `benchmarks/tasks.json`. The dataset should be expanded before final experiments so each category has enough observations for meaningful analysis.

## Metrics

For every successful request record:

- model/provider
- task category
- input tokens
- output tokens
- total tokens
- actual cost
- estimated cost
- latency
- quality score

Report at least:

- total cost
- mean cost per task
- mean quality
- mean latency
- cost per successful task
- percentage cost savings relative to the baseline
- quality difference relative to the baseline
- model-selection frequency

## Quality evaluation

The deterministic rubric is a low-cost failure detector and should not be treated as a factual correctness score. For final research results, use the optional LLM judge and/or human evaluation on a representative sample. Programming tasks should additionally be evaluated with executable tests where practical.

## Cost comparison

For a baseline cost `B` and optimized cost `O`:

`Savings (%) = ((B - O) / B) × 100`

A positive percentage indicates lower optimized cost. If the optimized system is cheaper but quality falls below the predefined acceptable threshold, the result must not be described as a successful quality-constrained optimization.

## Reproducibility

Record the experiment date, provider/model identifiers, pricing snapshot, benchmark version, routing strategy, quality threshold, and relevant API configuration. Provider pricing can change, so historical results must remain tied to the pricing snapshot used during the experiment.

## Important rule

Do not invent or manually edit experimental results. Results must be generated from actual controlled runs and preserved as raw data before aggregation.
