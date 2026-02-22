import logging
import os

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)


def init_telemetry(app_name="db-monitor"):
    """Initialize OpenTelemetry tracing and metrics."""

    # Check if telemetry is enabled
    otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    otel_debug = os.environ.get("OTEL_DEBUG", "false").lower() == "true"

    if not otlp_endpoint and not otel_debug:
        logger.info("OpenTelemetry is disabled (set OTEL_EXPORTER_OTLP_ENDPOINT to enable).")
        return

    logger.info(f"Initializing OpenTelemetry for {app_name}...")
    resource = Resource.create({"service.name": app_name})

    # --- Tracing ---
    tracer_provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(tracer_provider)

    if otlp_endpoint:
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    else:
        span_exporter = ConsoleSpanExporter()

    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))

    # --- Metrics ---
    if otlp_endpoint:
        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
    else:
        metric_exporter = ConsoleMetricExporter()

    metric_reader = PeriodicExportingMetricReader(metric_exporter)
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)


def get_meter():
    """Get the application meter for custom metrics."""
    return metrics.get_meter("db-monitor.metrics")


def get_tracer():
    """Get the application tracer for custom spans."""
    return trace.get_tracer("db-monitor.tracer")
