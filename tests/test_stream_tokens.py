import time

from app import stream_tokens


def test_resolve_unknown_token_returns_none():
    assert stream_tokens.resolve_token("hic-var-olmayan-token") is None


def test_mint_then_resolve_returns_correct_camera_id():
    token = stream_tokens.mint_token(42)
    assert stream_tokens.resolve_token(token) == 42


def test_tokens_are_unique_per_call():
    t1 = stream_tokens.mint_token(1)
    t2 = stream_tokens.mint_token(1)
    assert t1 != t2


def test_expired_token_resolves_to_none():
    token = stream_tokens.mint_token(7)
    original_ttl = stream_tokens._TOKEN_TTL_SECONDS
    try:
        stream_tokens._TOKEN_TTL_SECONDS = 0.01
        time.sleep(0.05)
        assert stream_tokens.resolve_token(token) is None
    finally:
        stream_tokens._TOKEN_TTL_SECONDS = original_ttl
