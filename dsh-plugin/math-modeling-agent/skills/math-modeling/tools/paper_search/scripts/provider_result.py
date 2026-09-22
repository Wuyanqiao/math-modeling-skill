"""Provider outcomes distinguish a successful empty search from service failure."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


class ProviderError(Exception):
    def __init__(self, kind, code=None):
        self.kind = kind
        self.code = code
        super().__init__(kind)


@dataclass
class ProviderResult:
    provider: str
    status: str
    papers: list = field(default_factory=list)
    error: dict | None = None
    retrieved_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def metadata(self) -> dict[str, Any]:
        return {"provider": self.provider, "status": self.status,
                "count": len(self.papers), "error": self.error,
                "retrieved_at": self.retrieved_at}


def capture(provider, search, *args, **kwargs):
    try:
        papers = search(*args, **kwargs)
        return ProviderResult(provider, "ok" if papers else "empty", papers)
    except ProviderError as exc:
        return ProviderResult(provider, "failed", error={"kind": exc.kind, "code": exc.code})
    except Exception as exc:
        # Exception text may contain a URL, email or authorization data.
        return ProviderResult(provider, "failed", error={"kind": type(exc).__name__, "code": None})
