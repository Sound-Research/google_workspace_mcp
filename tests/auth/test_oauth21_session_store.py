from auth.oauth21_session_store import OAuth21SessionStore


def test_oauth_state_persists_across_store_instances(tmp_path):
    state_file = tmp_path / "oauth_states.json"
    store_a = OAuth21SessionStore(oauth_state_file=str(state_file))
    store_b = OAuth21SessionStore(oauth_state_file=str(state_file))

    store_a.store_oauth_state(
        "shared-state",
        session_id="session-123",
        code_verifier="verifier-123",
    )

    state_info = store_b.validate_and_consume_oauth_state(
        "shared-state",
        session_id="session-123",
    )

    assert state_info["session_id"] == "session-123"
    assert state_info["code_verifier"] == "verifier-123"


def test_consume_latest_oauth_state_reads_from_shared_file(tmp_path):
    state_file = tmp_path / "oauth_states.json"
    store_a = OAuth21SessionStore(oauth_state_file=str(state_file))
    store_b = OAuth21SessionStore(oauth_state_file=str(state_file))

    store_a.store_oauth_state(
        "latest-state",
        session_id=None,
        code_verifier="latest-verifier",
    )

    state_info = store_b.consume_latest_oauth_state()

    assert state_info is not None
    assert state_info["code_verifier"] == "latest-verifier"
    assert store_a.consume_latest_oauth_state() is None
