"""
Export sinks. Each receives a batch of *anonymized* event dicts.

Failures are logged and swallowed — telemetry must never break a request.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional, Protocol

import httpx

logger = logging.getLogger("datadive.telemetry.sinks")
telemetry_logger = logging.getLogger("datadive.telemetry")


class Sink(Protocol):
    name: str

    async def emit(self, events: List[Dict[str, Any]]) -> None: ...

    async def close(self) -> None: ...


class LogSink:
    """One JSON line per event on logger `datadive.telemetry` — for log shippers."""
    name = "log"

    async def emit(self, events: List[Dict[str, Any]]) -> None:
        for e in events:
            telemetry_logger.info(json.dumps(e, separators=(",", ":"), default=str))

    async def close(self) -> None:
        return None


class WebhookSink:
    """POST batches to a collector endpoint (your own lambda, Segment-style HTTP API, …)."""
    name = "webhook"

    def __init__(self, url: str, token: str = "", client: Optional[httpx.AsyncClient] = None):
        self.url = url
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.client = client or httpx.AsyncClient(timeout=5.0, headers=headers)
        self._own_client = client is None

    async def emit(self, events: List[Dict[str, Any]]) -> None:
        resp = await self.client.post(self.url, content=json.dumps({"source": "data-dive", "events": events}, default=str))
        resp.raise_for_status()

    async def close(self) -> None:
        if self._own_client:
            await self.client.aclose()


class OtlpSink:
    """
    OpenTelemetry log records over OTLP/HTTP. Each event becomes one LogRecord whose
    attributes are the event fields, so any OTel-compatible backend (Grafana, Datadog,
    Honeycomb, …) can slice by feature/action.
    """
    name = "otlp"

    def __init__(self, endpoint: str, headers: str = ""):
        try:
            from opentelemetry._logs import set_logger_provider
            from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
            from opentelemetry.sdk._logs import LoggerProvider
            from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
            from opentelemetry.sdk.resources import Resource
        except ImportError as exc:  # pragma: no cover - depends on optional packages
            raise RuntimeError(
                "OTLP sink requires 'opentelemetry-sdk' and 'opentelemetry-exporter-otlp-proto-http'"
            ) from exc

        hdrs = dict(kv.split("=", 1) for kv in headers.split(",") if "=" in kv) if headers else None
        self._provider = LoggerProvider(resource=Resource.create({"service.name": "data-dive-api"}))
        self._provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter(endpoint=endpoint, headers=hdrs)))
        set_logger_provider(self._provider)
        self._logger = self._provider.get_logger("datadive.usage")

    async def emit(self, events: List[Dict[str, Any]]) -> None:
        import time

        from opentelemetry._logs import SeverityNumber

        for e in events:
            attrs = {}
            for k, v in e.items():
                if k == "properties":
                    for pk, pv in (v or {}).items():
                        attrs[f"props.{pk}"] = pv if isinstance(pv, (str, int, float, bool)) else json.dumps(pv)
                elif v is not None:
                    attrs[k] = v if isinstance(v, (str, int, float, bool)) else str(v)
            # Keyword form works across OTel SDK versions (LogRecord moved between modules).
            self._logger.emit(
                timestamp=time.time_ns(),
                severity_number=SeverityNumber.INFO,
                severity_text="INFO",
                body=f"{e.get('name')} {e.get('feature')}/{e.get('action') or ''}".strip(),
                attributes=attrs,
                event_name="usage_event",
            )

    async def close(self) -> None:
        self._provider.shutdown()


def build_sinks(settings) -> List[Sink]:
    sinks: List[Sink] = []
    for name in settings.telemetry_sink_list:
        try:
            if name == "log":
                sinks.append(LogSink())
            elif name == "webhook" and settings.telemetry_webhook_url:
                sinks.append(WebhookSink(settings.telemetry_webhook_url, settings.telemetry_webhook_token))
            elif name == "otlp" and settings.telemetry_otlp_endpoint:
                sinks.append(OtlpSink(settings.telemetry_otlp_endpoint, settings.telemetry_otlp_headers))
            elif name == "db":
                continue  # handled by the repository
            else:
                logger.warning("Telemetry sink '%s' not configured or unknown — skipped", name)
        except Exception:
            logger.exception("Failed to initialise telemetry sink '%s'", name)
    return sinks
