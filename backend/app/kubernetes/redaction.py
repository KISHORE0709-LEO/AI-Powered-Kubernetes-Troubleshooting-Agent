import re

SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(password|passwd|secret|token|api[_-]?key|authorization|client[_-]?secret)"
    r"(\s*[:=]\s*)(['\"]?)[^\s,;'\"]+"
)
BEARER_PATTERN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")


def redact_sensitive_text(value: str) -> str:
    value = SECRET_ASSIGNMENT_PATTERN.sub(r"\1\2[REDACTED]", value)
    return BEARER_PATTERN.sub("Bearer [REDACTED]", value)
