"""Streamlit UI: pick a role, ask a question, watch the tool calls happen, inspect every one afterwards."""
import asyncio
import json
import time

import streamlit as st

import agent

SAMPLES = [
    ("Top 3 for the ML Engineer role", "R2", "Who are the top 3 candidates for this role, and why?"),
    ("Why is the backend role stuck?", "R1",
     "This role has been open for 4 months. Where is our process losing candidates?"),
    ("What is pending or overdue?", None, "Which tasks are pending or overdue?"),
]

st.set_page_config(page_title="Recruiting Assistant", page_icon="🧭")
st.title("Recruiting Assistant")


@st.cache_data
def load_roles():
    return asyncio.run(agent.fetch_roles())


def describe(event):
    """One line of live progress for an agent.ask() event."""
    if event["type"] == "model":
        return "Thinking..." if event["round"] == 1 else f"Reading the results (round {event['round']})..."
    a = event["args"]
    labels = {
        "list_roles": "Listing roles",
        "search_applications": "Searching applications" + (f" in {a['role_id']}" if a.get("role_id") else "")
                               + (f" for '{a['name_contains']}'" if a.get("name_contains") else ""),
        "get_candidate_profile": f"Opening the profile for {a.get('application_id')}",
        "get_pipeline_funnel": f"Building the funnel for {a.get('role_id')}",
        "get_pending_tasks": "Checking pending and overdue tasks",
    }
    return f"{labels.get(event['name'], event['name'])}  `{event['name']}`"


def show_question(turn):
    with st.chat_message("user"):
        st.write(turn["question"])
        st.caption(f"Role: {turn['role_id'] or 'all roles'}")


def show_answer(turn):
    st.markdown(turn["answer"])
    if turn["stopped"] == "cap":
        st.warning("Stopped at the tool-step limit. The answer above may be incomplete.")
    with st.expander(f"Tool calls ({len(turn['tool_calls'])})"):
        for call in turn["tool_calls"]:
            st.markdown(f"**{call['name']}** `{json.dumps(call['args'])}`" + (" (error)" if call["is_error"] else ""))
            st.code(call["result"], language="json")


roles = {r["role_id"]: r["title"] for r in load_roles()}
role_id = st.sidebar.selectbox("Role", [None, *roles], format_func=lambda r: "All roles" if r is None
                               else f"{r}: {roles[r]}")
st.sidebar.caption("Try a sample question:")
pending = None
for label, sample_role, question in SAMPLES:
    if st.sidebar.button(label):
        pending = (question, sample_role)
typed = st.chat_input("Ask about roles, candidates, the pipeline or pending work")
if typed:
    pending = (typed, role_id)

if "log" not in st.session_state:
    st.session_state.log = []  # each turn: question, role_id, role_title + what agent.ask returned

for turn in st.session_state.log:
    show_question(turn)
    with st.chat_message("assistant"):
        show_answer(turn)

if pending:
    question, ask_role = pending
    turn = {"question": question, "role_id": ask_role, "role_title": roles.get(ask_role)}
    show_question(turn)
    with st.chat_message("assistant"):
        started = time.monotonic()
        with st.status("Working on it...", expanded=True) as status:
            try:
                out = asyncio.run(agent.ask(question, ask_role, roles.get(ask_role),
                                            history=st.session_state.log[-5:],
                                            on_event=lambda event: st.write(describe(event))))
                n = len(out["tool_calls"])
                status.update(label=f"Done in {time.monotonic() - started:.0f}s with {n} tool call{'s' * (n != 1)}",
                              state="complete", expanded=False)
            except Exception as exc:  # show setup problems (missing key or model) instead of a stack trace
                out = {"answer": f"Something went wrong: {exc}", "tool_calls": [], "stopped": "error", "messages": []}
                status.update(label="Something went wrong", state="error", expanded=False)
        turn.update(out)
        show_answer(turn)
    st.session_state.log.append(turn)
