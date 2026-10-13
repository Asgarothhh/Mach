import structlog
from opentelemetry import trace
from prometheus_client import Histogram, Counter

# Настройка structlog (оставляем без изменений)
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

def get_logger(name: str):
    return structlog.get_logger(name)

# Инициализация OpenTelemetry трейсера[cite: 16]
tracer = trace.get_tracer("mts_voice_agent")

# Инициализация Prometheus метрик (без чувствительных лейблов)[cite: 16]
# Корзины (buckets) настроены для точного замера целевых 300-400 мс
LATENCY_BUCKETS = (0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.8, 1.0, 2.0, 5.0, float("inf"))

rag_latency_metric = Histogram(
    "voice_agent_rag_latency_seconds",
    "Latency of RAG retrieval stage",
    labelnames=["tenant_id", "status"],
    buckets=LATENCY_BUCKETS
)

llm_ttft_metric = Histogram(
    "voice_agent_llm_ttft_seconds",
    "Time To First Token from OpenRouter",
    labelnames=["model_id", "status"],
    buckets=LATENCY_BUCKETS
)

e2e_latency_metric = Histogram(
    "voice_agent_e2e_ttfa_seconds",
    "End-to-end Time To First Audio",
    labelnames=["tenant_id", "channel"],
    buckets=LATENCY_BUCKETS
)

error_counter = Counter(
    "voice_agent_errors_total",
    "Total number of processing errors",
    labelnames=["error_class"]
)