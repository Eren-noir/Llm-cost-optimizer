-- Initial schema for LLM Cost Optimization Platform
-- Run against PostgreSQL 14+

CREATE EXTENSION IF NOT EXISTS "pgcrypto"; -- for gen_random_uuid()

CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE budget_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    monthly_budget_usd NUMERIC(10,4) NOT NULL,
    min_quality_threshold SMALLINT NOT NULL CHECK (min_quality_threshold BETWEEN 0 AND 100),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'active'
);

CREATE TABLE models (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider_id UUID NOT NULL REFERENCES providers(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    context_limit INTEGER NOT NULL,
    capabilities JSONB NOT NULL DEFAULT '{}',
    estimated_quality SMALLINT NOT NULL CHECK (estimated_quality BETWEEN 0 AND 100),
    status VARCHAR(20) NOT NULL DEFAULT 'active',
    UNIQUE (provider_id, model_name)
);

CREATE TABLE pricing_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    model_id UUID NOT NULL REFERENCES models(id) ON DELETE CASCADE,
    input_price_per_1k NUMERIC(10,6) NOT NULL,
    output_price_per_1k NUMERIC(10,6) NOT NULL,
    effective_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    effective_to TIMESTAMPTZ NULL
);
CREATE INDEX idx_pricing_history_model_time ON pricing_history(model_id, effective_from);

CREATE TABLE requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('manual', 'comparison', 'auto')),
    prompt_text TEXT NOT NULL,
    estimated_complexity VARCHAR(20) CHECK (estimated_complexity IN ('simple','medium','complex')),
    model_id UUID NOT NULL REFERENCES models(id),
    status VARCHAR(20) NOT NULL CHECK (status IN ('success','failed','fallback_used')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_requests_user_time ON requests(user_id, created_at);

CREATE TABLE responses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID UNIQUE NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    response_text TEXT NOT NULL,
    finish_reason VARCHAR(50),
    raw_response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE usage_metrics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID UNIQUE NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    input_tokens_estimated INTEGER,
    output_tokens_estimated INTEGER,
    input_tokens_actual INTEGER NOT NULL,
    output_tokens_actual INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    estimated_cost_usd NUMERIC(10,6) NOT NULL,
    actual_cost_usd NUMERIC(10,6) NOT NULL
);

CREATE TABLE quality_evaluations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID UNIQUE NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    quality_score SMALLINT NOT NULL CHECK (quality_score BETWEEN 0 AND 100),
    evaluation_method VARCHAR(20) NOT NULL CHECK (evaluation_method IN ('rubric','llm_judge','human')),
    evaluator_notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE optimization_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id UUID UNIQUE NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    routing_strategy VARCHAR(50) NOT NULL,
    candidates_considered JSONB NOT NULL,
    chosen_model_id UUID NOT NULL REFERENCES models(id),
    chosen_reason TEXT NOT NULL,
    fallback_triggered BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
