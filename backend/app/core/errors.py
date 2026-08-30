"""
Common application-level exceptions and their FastAPI handlers.

Provider adapters (Phase 5) will map provider-specific errors onto these
types, so the router and API layer only ever need to handle this small,
uniform set - see docs/02-architecture.md, "Cross-Cutting Concerns".
"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for all handled application errors."""

    status_code = 500
    default_message = "An unexpected error occurred."

    def __init__(self, message: str | None = None):
        self.message = message or self.default_message
        super().__init__(self.message)


class ProviderTimeoutError(AppError):
    status_code = 504
    default_message = "The LLM provider timed out."


class ProviderRateLimitError(AppError):
    status_code = 429
    default_message = "The LLM provider rate limit was exceeded."


class ProviderUnavailableError(AppError):
    status_code = 503
    default_message = "The LLM provider is currently unavailable."


class InvalidProviderCredentialsError(AppError):
    status_code = 401
    default_message = "Invalid or missing provider API credentials."


class NoEligibleModelError(AppError):
    status_code = 422
    default_message = "No model meets the required quality threshold within budget."


class BudgetExceededError(AppError):
    status_code = 402
    default_message = "This request would exceed the configured budget."


def register_error_handlers(app: FastAPI) -> None:
    """Wire AppError subclasses to consistent JSON error responses."""

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": exc.__class__.__name__, "message": exc.message},
        )
