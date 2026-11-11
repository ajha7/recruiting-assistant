"""The agent loop, driven by a scripted fake model against the real MCP server."""
import asyncio
import json
from types import SimpleNamespace as NS

import pytest
from openai.types.chat import ChatCompletionMessage

import agent


def message(content=None, calls=(), refusal=None):
    return ChatCompletionMessage.model_validate({
        "role": "assistant", "content": content, "refusal": refusal,
        "tool_calls": [{"id": id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}
                       for id, name, args in calls] or None})


def reply(msg, finish="stop"):
    return NS(choices=[NS(message=msg, finish_reason=finish)])


def tool_reply(content, *calls):
    return reply(message(content, calls), "tool_calls")


class FakeClient:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.chat = NS(completions=self)

    async def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


@pytest.fixture(autouse=True)
def env(db_env, monkeypatch):
    monkeypatch.setenv("OPENAI_MODEL", "test-model")


def run(client, **kw):
    return asyncio.run(agent.ask("q", client=client, **kw))


def test_loop_calls_tools_and_returns_answer():
    client = FakeClient([
        tool_reply("looking", ("t1", "list_roles", {}), ("t2", "get_pending_tasks", {})),
        reply(message("Done. RANKING: APP-006")),
    ])
    out = run(client, role_id="R2", role_title="Machine Learning Engineer")
    assert out["stopped"] == "done" and out["answer"].startswith("Done")
    assert [c["name"] for c in out["tool_calls"]] == ["list_roles", "get_pending_tasks"]
    second = client.calls[1]["messages"]
    assert [m["role"] for m in second[-3:]] == ["assistant", "tool", "tool"]
    assert [m["tool_call_id"] for m in second[-2:]] == ["t1", "t2"]
    assert second[-3]["tool_calls"][0]["id"] == "t1"  # assistant turn appended unchanged
    first = client.calls[0]["messages"]
    assert first[0]["role"] == "system" and first[1]["content"].startswith("[Selected role: R2")
    assert "temperature" not in client.calls[0] and "tool_choice" not in client.calls[0]
    assert {t["function"]["name"] for t in client.calls[0]["tools"]} >= {"list_roles", "get_pending_tasks"}


def test_tool_errors_are_passed_back_to_the_model():
    client = FakeClient([
        tool_reply(None, ("t1", "get_candidate_profile", {"application_id": "APP-999"})),
        reply(message("not found")),
    ])
    out = run(client)
    assert out["tool_calls"][0]["is_error"] and "No application with id" in out["tool_calls"][0]["result"]
    last = client.calls[1]["messages"][-1]["content"]
    assert last.startswith("ERROR: ") and "No application with id" in last


def test_bad_tool_arguments_do_not_kill_the_loop():
    bad = ChatCompletionMessage.model_validate({"role": "assistant", "content": None, "tool_calls": [
        {"id": "t1", "type": "function", "function": {"name": "list_roles", "arguments": "{oops"}}]})
    out = run(FakeClient([reply(bad, "tool_calls"), reply(message("ok"))]))
    assert out["tool_calls"][0]["is_error"] and out["stopped"] == "done"


def test_iteration_cap_is_reported_not_silent():
    client = FakeClient([tool_reply("partial", ("t", "list_roles", {}))])
    out = run(client, max_iterations=2)
    assert out["stopped"] == "cap" and "2-step tool limit" in out["answer"] and "partial" in out["answer"]
    assert len(out["tool_calls"]) == 2


def test_refusal_is_graceful():
    out = run(FakeClient([reply(message(None, refusal="I can't help with that."))]))
    assert out["stopped"] == "refusal" and "declined" in out["answer"]


def test_older_history_is_replayed_as_text_with_its_role():
    older = {"question": "older q", "role_id": "R2", "role_title": "Machine Learning Engineer",
             "answer": "older a", "stopped": "done", "messages": [{"role": "user", "content": "unused"}]}
    failed = {"question": "failed q", "role_id": None, "role_title": None, "answer": "boom", "stopped": "error"}
    client = FakeClient([reply(message("ok"))])
    run(client, history=[older, failed])
    contents = [m["content"] for m in client.calls[0]["messages"][1:]]
    # Only the latest turn may be replayed in full; a failed latest turn falls back to text.
    assert contents == ["[Selected role: R2 - Machine Learning Engineer]\nolder q", "older a", "failed q", "boom", "q"]


def test_latest_turn_is_carried_forward_with_its_tool_results():
    first = FakeClient([tool_reply(None, ("t1", "get_candidate_profile", {"application_id": "APP-009"})),
                        reply(message("APP-009 has weak interviews."))])
    turn1 = run(first, role_id="R2", role_title="Machine Learning Engineer")
    assert [m["role"] for m in turn1["messages"]] == ["user", "assistant", "tool", "assistant"]
    turn1.update(question="q", role_id="R2", role_title="Machine Learning Engineer")

    second = FakeClient([reply(message("Because of FB-040."))])
    out = asyncio.run(agent.ask("why not APP-009?", history=[turn1], client=second))
    sent = second.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "tool", "assistant", "user"]
    assert '"application_id": "APP-009"' in sent[3]["content"]  # the profile is still in context
    assert out["tool_calls"] == [] and len(second.calls) == 1  # answered without re-fetching


def test_on_event_reports_each_step_as_it_starts():
    events = []
    client = FakeClient([tool_reply(None, ("t1", "list_roles", {}), ("t2", "get_pending_tasks", {"role_id": "R3"})),
                         reply(message("done"))])
    asyncio.run(agent.ask("q", client=client, on_event=events.append))
    assert events == [{"type": "model", "round": 1}, {"type": "tool", "name": "list_roles", "args": {}},
                      {"type": "tool", "name": "get_pending_tasks", "args": {"role_id": "R3"}},
                      {"type": "model", "round": 2}]


def test_missing_model_gives_clear_error(monkeypatch):
    monkeypatch.delenv("OPENAI_MODEL")
    with pytest.raises(RuntimeError, match="OPENAI_MODEL"):
        run(FakeClient([reply(message("x"))]))


def test_fetch_roles_goes_through_mcp():
    assert [r["role_id"] for r in asyncio.run(agent.fetch_roles())] == ["R1", "R2", "R3"]
