"""LLM and upstream error types."""


class LLMServiceError(Exception):
    """Ollama or OpenAI returned an error response."""


class LLMRateLimitedError(Exception):
    """Local token bucket rate limit exceeded."""


class LLMTimeoutError(Exception):
    """LLM request timed out (generic)."""


class LLMUpstreamTimeoutError(LLMTimeoutError):
    """Upstream LLM read/connect timeout."""
