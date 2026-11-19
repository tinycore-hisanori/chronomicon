"""Property tests for the Python password oracle (rom-builder, Requirement 12)."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from tests.password_ref import ALPHABET, data_len, decode, encode

_states = st.binary(min_size=1, max_size=8)


# Feature: rom-builder, Property 4: Password round trip and shape (oracle)
# **Validates: Requirements 12.3, 12.4, 12.5, 12.6**
@given(state=_states)
def test_password_round_trip_and_shape(state: bytes) -> None:
    n = len(state)
    pw = encode(state)

    assert len(pw) == -(-8 * n // 5) + 1
    assert len(pw) == data_len(n) + 1
    assert all(c in ALPHABET for c in pw)

    values = [ALPHABET.index(c) for c in pw]
    assert values[-1] == sum(values[:-1]) % 32

    assert decode(pw, n) == state
