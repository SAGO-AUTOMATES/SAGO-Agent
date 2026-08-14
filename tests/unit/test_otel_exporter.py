"""Tests for OTelExporter and PrometheusExporter."""

from __future__ import annotations

import time

from sago.tracking.dev_tracer import DevTraceEvent, TraceEventType
from sago.tracking.otel_exporter import OTelExporter, PrometheusExporter


def test_otel_exporter_schema() -> None:
    events = [
        DevTraceEvent(
            timestamp=time.time(),
            event_type=TraceEventType.FUNCTION_CALL,
            source="test_source",
            action="execute_plan",
            data={"model": "gpt-4o", "tokens": 120},
            duration_ms=45.2,
            status="OK",
        )
    ]

    exporter = OTelExporter(service_name="test-sago")
    payload = exporter.export_traces(events)

    assert "resourceSpans" in payload
    assert len(payload["resourceSpans"]) == 1
    spans = payload["resourceSpans"][0]["scopeSpans"][0]["spans"]
    assert len(spans) == 1
    assert spans[0]["name"] == "test_source::execute_plan"
    assert spans[0]["status"]["code"] == 1


def test_prometheus_exporter_metrics() -> None:
    events = [
        DevTraceEvent(
            timestamp=time.time(),
            event_type=TraceEventType.TOOL_DISPATCH,
            source="tool_runner",
            action="run(write_file)",
            data={"tool_name": "write_file"},
            duration_ms=12.5,
            status="OK",
        )
    ]

    exporter = PrometheusExporter(namespace="sago_test")
    text = exporter.export_metrics(events)

    assert "sago_test_events_total" in text
    assert 'tool="write_file"' in text
    assert "sago_test_function_duration_ms" in text
