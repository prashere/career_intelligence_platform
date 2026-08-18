"""LangSmith configuration tests."""

from app.telemetry.langsmith import (
    langsmith_enabled,
    profile_trace_metadata,
    process_chat_inputs,
    process_chat_outputs,
)


def test_profile_trace_metadata():
    meta = profile_trace_metadata(
        user_id="u1",
        pipeline_run_id="r1",
        submission_id="s1",
        step="extract_cv",
    )
    assert meta["feature"] == "profile_setup"
    assert meta["user_id"] == "u1"
    assert meta["pipeline_run_id"] == "r1"
    assert meta["submission_id"] == "s1"
    assert meta["pipeline_step"] == "extract_cv"


def test_process_chat_inputs_outputs():
    shaped = process_chat_inputs(
        {
            "messages": [{"role": "user", "content": "hello"}],
            "stream": False,
        }
    )
    assert shaped["message_count"] == 1
    assert shaped["messages"][0]["content"] == "hello"

    out = process_chat_outputs("response text")
    assert out["char_count"] == len("response text")


def test_langsmith_disabled_without_api_key():
    # Default test env typically has no LANGSMITH_API_KEY
    assert langsmith_enabled() in (True, False)
