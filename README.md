# Intelligent Multi-LLM Cost Optimization and Model Routing Platform

A university capstone project that dynamically routes LLM requests across multiple providers (OpenAI, Anthropic Claude, Google Gemini) to minimize operating cost while satisfying a user-defined quality threshold.

## Problem

LLM-powered applications often use one model for every task, even when a cheaper model could handle simpler requests just as well. This project investigates whether intelligent, per-task model selection can reduce cost while maintaining acceptable response quality.

## Status

🚧 In early development — Phase 1 (Requirements) in progress.

## Project Structure (planned)

```
backend/     FastAPI backend: routing engine, provider adapters, cost engine
frontend/    React dashboard
docs/        Requirements, design docs, ERD, research write-up
benchmarks/  Task datasets used for evaluation
```

## Tech Stack

- Backend: Python + FastAPI
- Frontend: React
- Database: PostgreSQL
- LLM Providers: OpenAI, Anthropic, Google Gemini (official APIs)

## License

MIT (see LICENSE)
