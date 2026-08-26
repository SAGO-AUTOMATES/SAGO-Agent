"""Error Classifier and Recovery Action Resolver for LLM and Provider APIs.

Classifies API exceptions and response errors into structured failure categories
with deterministic recovery recommendations (retry, backoff, compress context,
rotate credentials, fallback provider, abort).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

logger = logging.getLogger("sago.llm.error_classifier")


class FailReason(StrEnum):
    """Categorized LLM / API failure reasons."""

    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    BILLING = "billing"
    TIMEOUT = "timeout"
    CONTEXT_OVERFLOW = "context_overflow"
    SERVER_ERROR = "server_error"
    BAD_REQUEST = "bad_request"
    CONTENT_FILTER = "content_filter"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RecoveryAction:
    """Recommended recovery strategy for a classified failure."""

    retry: bool
    backoff: bool = False
    should_compress: bool = False
    should_fallback_provider: bool = False
    should_rotate_credential: bool = False
    max_retries: int = 3
    reason: FailReason = FailReason.UNKNOWN
    user_message: str = ""


RECOVERY_MATRIX: dict[FailReason, RecoveryAction] = {
    FailReason.RATE_LIMIT: RecoveryAction(
        retry=True,
        backoff=True,
        max_retries=3,
        reason=FailReason.RATE_LIMIT,
        user_message="Rate limit encountered; backing off and retrying...",
    ),
    FailReason.AUTH: RecoveryAction(
        retry=False,
        should_rotate_credential=True,
        should_fallback_provider=True,
        max_retries=0,
        reason=FailReason.AUTH,
        user_message="Authentication failed. Please check API key or credential rotation.",
    ),
    FailReason.BILLING: RecoveryAction(
        retry=False,
        should_fallback_provider=True,
        max_retries=0,
        reason=FailReason.BILLING,
        user_message="Provider quota/credits exhausted. Switching to fallback provider.",
    ),
    FailReason.TIMEOUT: RecoveryAction(
        retry=True,
        backoff=True,
        max_retries=2,
        reason=FailReason.TIMEOUT,
        user_message="Request timed out; attempting retry with backoff...",
    ),
    FailReason.CONTEXT_OVERFLOW: RecoveryAction(
        retry=True,
        backoff=False,
        should_compress=True,
        max_retries=2,
        reason=FailReason.CONTEXT_OVERFLOW,
        user_message="Context window exceeded; compacting conversation and retrying...",
    ),
    FailReason.SERVER_ERROR: RecoveryAction(
        retry=True,
        backoff=True,
        should_fallback_provider=True,
        max_retries=3,
        reason=FailReason.SERVER_ERROR,
        user_message="Remote provider 5xx server error; retrying or falling back.",
    ),
    FailReason.BAD_REQUEST: RecoveryAction(
        retry=False,
        max_retries=0,
        reason=FailReason.BAD_REQUEST,
        user_message="Bad request format sent to model API.",
    ),
    FailReason.CONTENT_FILTER: RecoveryAction(
        retry=False,
        max_retries=0,
        reason=FailReason.CONTENT_FILTER,
        user_message="Prompt or completion triggered provider content safety filter.",
    ),
    FailReason.NETWORK_ERROR: RecoveryAction(
        retry=True,
        backoff=True,
        max_retries=3,
        reason=FailReason.NETWORK_ERROR,
        user_message="Network connectivity error; retrying...",
    ),
    FailReason.UNKNOWN: RecoveryAction(
        retry=True,
        backoff=True,
        max_retries=1,
        reason=FailReason.UNKNOWN,
        user_message="Encountered unrecognized API error.",
    ),
}


def classify_error(
    status_code: int | str | None = None,
    message: str = "",
    exception: Exception | None = None,
) -> FailReason:
    """Classify an API error into a structured FailReason.

    Args:
        status_code: HTTP status code if available (or error message if called positionally).
        message: Error message string.
        exception: Original exception object if available.

    Returns:
        Categorized FailReason enum.
    """
    # Support calling classify_error("error message string")
    if isinstance(status_code, str) and not message:
        message = status_code
        status_code = None

    if status_code is not None:
        try:
            status_code = int(status_code)
        except Exception:
            status_code = None

    if exception is not None:
        exc_status = getattr(exception, "status_code", None)
        if exc_status is not None and status_code is None:
            try:
                status_code = int(exc_status)
            except Exception:
                pass
        if not message:
            message = str(exception)

    msg = (message or "").lower()

    if (
        status_code == 429
        or "rate limit" in msg
        or "too many requests" in msg
        or "resource_exhausted" in msg
    ):
        return FailReason.RATE_LIMIT

    if (
        status_code in (401, 403)
        or "unauthorized" in msg
        or "invalid api key" in msg
        or "authentication" in msg
        or "permission_denied" in msg
    ):
        return FailReason.AUTH

    if (
        status_code == 402
        or "insufficient_quota" in msg
        or "quota exceeded" in msg
        or "billing" in msg
        or "credit" in msg
    ):
        return FailReason.BILLING

    if status_code == 408 or "timeout" in msg or "timed out" in msg or "deadline exceeded" in msg:
        return FailReason.TIMEOUT

    if (
        "context_length_exceeded" in msg
        or "contextwindowexceeded" in msg
        or "maximum context length" in msg
        or "context window" in msg
        or "too many tokens" in msg
        or "prompt is too long" in msg
    ):
        return FailReason.CONTEXT_OVERFLOW

    if "content_filter" in msg or "safety filter" in msg or "harmful" in msg or "moderation" in msg:
        return FailReason.CONTENT_FILTER

    if status_code is not None and status_code >= 500:
        return FailReason.SERVER_ERROR

    if status_code == 400 or "invalid_request_error" in msg:
        return FailReason.BAD_REQUEST

    if "connecterror" in msg or "connection refused" in msg or "network" in msg or "dns" in msg:
        return FailReason.NETWORK_ERROR

    return FailReason.UNKNOWN


def get_recovery_action(
    status_code: int | None = None,
    message: str = "",
    exception: Exception | None = None,
) -> RecoveryAction:
    """Get the recommended RecoveryAction for an error.

    Args:
        status_code: HTTP status code.
        message: Error message.
        exception: Original exception.

    Returns:
        RecoveryAction instance with action flags.
    """
    reason = classify_error(status_code=status_code, message=message, exception=exception)
    action = RECOVERY_MATRIX.get(reason, RECOVERY_MATRIX[FailReason.UNKNOWN])
    logger.debug(
        "Classified error '%s' (status=%s) -> %s (retry=%s, compress=%s, fallback=%s)",
        message[:100],
        status_code,
        reason.value,
        action.retry,
        action.should_compress,
        action.should_fallback_provider,
    )
    return action
