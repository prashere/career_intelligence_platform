"""Structured tracing for the ingestion pipeline."""

from __future__ import annotations

import time
from typing import Any

try:
    import structlog

    log = structlog.get_logger(component="ingestion")
except ImportError:  # pragma: no cover - minimal test envs
    import logging

    log = logging.getLogger("ingestion")

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import IngestionTraceEvent, TraceLevel


class IngestionTracer:
    """Records LangSmith-style trace events for a single ingestion run."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        run_id: str,
        source_id: str | None,
        source_name: str | None = None,
        enabled: bool = True,
    ) -> None:
        self._session = session
        self._run_id = run_id
        self._source_id = source_id
        self._source_name = source_name
        self._enabled = enabled
        self._seq = 0
        self._logger = (
            log.bind(run_id=run_id, source_id=source_id, source=source_name)
            if hasattr(log, "bind")
            else log
        )

    def _log(self, level: TraceLevel, message: str, **fields: Any) -> None:
        log_fn = {
            TraceLevel.debug: self._logger.debug,
            TraceLevel.info: self._logger.info,
            TraceLevel.warn: self._logger.warning,
            TraceLevel.error: self._logger.error,
        }[level]
        if hasattr(log, "bind"):
            log_fn(message, **fields)
        else:
            extra = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
            log_fn("%s %s", message, extra)

    async def emit(
        self,
        stage: str,
        event: str,
        message: str,
        *,
        level: TraceLevel = TraceLevel.info,
        duration_ms: int | None = None,
        **payload: Any,
    ) -> None:
        if not self._enabled:
            return

        self._seq += 1
        row = IngestionTraceEvent(
            run_id=self._run_id,
            source_id=self._source_id,
            seq=self._seq,
            stage=stage,
            level=level,
            event=event,
            message=message,
            payload=payload or {},
            duration_ms=duration_ms,
        )
        self._session.add(row)

        self._log(
            level,
            message,
            stage=stage,
            event_name=event,
            duration_ms=duration_ms,
            **payload,
        )

    class _StageTimer:
        def __init__(self, tracer: "IngestionTracer", name: str) -> None:
            self._tracer = tracer
            self._name = name
            self._t0 = 0.0

        async def __aenter__(self) -> None:
            self._t0 = time.perf_counter()
            await self._tracer.stage_start(self._name)

        async def __aexit__(self, exc_type, exc, tb) -> None:
            ms = int((time.perf_counter() - self._t0) * 1000)
            level = TraceLevel.error if exc else TraceLevel.info
            msg = f"{self._name} failed: {exc}" if exc else f"{self._name} finished"
            await self._tracer.emit(
                "run",
                "stage_end",
                msg,
                level=level,
                duration_ms=ms,
                stage_detail=self._name,
            )

    def stage(self, name: str) -> _StageTimer:
        return self._StageTimer(self, name)

    async def stage_start(self, name: str, message: str | None = None) -> None:
        await self.emit("run", "stage_start", message or f"{name} started", stage_detail=name)

    async def strategy_attempt(
        self,
        kind: str,
        *,
        ok: bool,
        item_count: int = 0,
        filtered_count: int = 0,
        error: str | None = None,
        skipped: bool = False,
        skip_reason: str | None = None,
        requires_browser: bool = False,
        sample_urls: list[str] | None = None,
    ) -> None:
        level = TraceLevel.info if ok else TraceLevel.warn if skipped else TraceLevel.error
        msg = f"Strategy {kind}: {'ok' if ok else skip_reason or error or 'failed'}"
        await self.emit(
            "discover",
            "strategy_attempt",
            msg,
            level=level,
            kind=kind,
            ok=ok,
            item_count=item_count,
            filtered_count=filtered_count,
            error=error,
            skipped=skipped,
            skip_reason=skip_reason,
            requires_browser=requires_browser,
            sample_urls=(sample_urls or [])[:5],
        )

    async def item_event(
        self,
        stage: str,
        event: str,
        message: str,
        *,
        level: TraceLevel = TraceLevel.debug,
        url: str | None = None,
        title: str | None = None,
        reason: str | None = None,
        **extra: Any,
    ) -> None:
        await self.emit(
            stage,
            event,
            message,
            level=level,
            url=url,
            title=(title or "")[:200] if title else None,
            reason=reason,
            **extra,
        )
