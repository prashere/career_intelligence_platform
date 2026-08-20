"""Hard caps for source discovery runs."""

MAX_ROUNDS = 3
MAX_QUERIES_PER_ROUND = 8
MAX_CANDIDATES_EVALUATED = 20
TARGET_RECURRING_CONFIDENCE = 0.55
TARGET_RECURRING_COUNT = 5
HIGH_CONFIDENCE_THRESHOLD = 0.55

QUERY_CATEGORIES = (
    "aggregator",
    "institutional",
    "government_ngo",
    "professional_association",
)

MAX_FETCH_BYTES = 2_000_000
FETCH_TIMEOUT_S = 35.0
