from app.services.catalog_privacy import (
    FICTIONAL_DEMO_URL_HASH_PREFIX,
    is_fictional_demo_hash,
)


def test_fictional_demo_hash_prefix():
    assert is_fictional_demo_hash(f"{FICTIONAL_DEMO_URL_HASH_PREFIX}northhaven")
    assert not is_fictional_demo_hash("ingested-abc")
    assert not is_fictional_demo_hash("")
    assert not is_fictional_demo_hash(None)
