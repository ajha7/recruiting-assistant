"""Smoke test of the Streamlit page with the agent stubbed out."""
from pathlib import Path

from streamlit.testing.v1 import AppTest

import agent

APP = str(Path(__file__).parent.parent / "app.py")


def test_sample_button_and_typed_question(monkeypatch):
    seen = []

    async def fake_roles():
        return [{"role_id": "R1", "title": "Senior Backend Engineer"}, {"role_id": "R2", "title": "ML Engineer"}]

    async def fake_ask(question, role_id=None, role_title=None, history=()):
        seen.append((question, role_id, role_title, list(history)))
        return {"answer": f"answer to: {question}", "stopped": "done",
                "tool_calls": [{"name": "list_roles", "args": {}, "result": "{}", "is_error": False}]}

    monkeypatch.setattr(agent, "fetch_roles", fake_roles)
    monkeypatch.setattr(agent, "ask", fake_ask)
    at = AppTest.from_file(APP).run()
    assert not at.exception
    at.sidebar.button[0].click().run()
    assert seen[0][1:3] == ("R2", "ML Engineer")
    at.chat_input[0].set_value("Status of Priya Nandakumar?").run()
    assert seen[1][1] is None and seen[1][3] == [(seen[0][0], f"answer to: {seen[0][0]}")]
    assert not at.exception and len(at.chat_message) == 4
