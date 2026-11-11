"""Streamlit UI: pick a role, ask a question, read the answer, inspect every tool call."""
import asyncio
import json

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
    st.session_state.log = []  # [{"question", "role_id", "answer", "tool_calls", "stopped"}]

if pending:
    question, ask_role = pending
    history = [(t["question"], t["answer"]) for t in st.session_state.log[-5:]]
    with st.spinner("Asking the recruiting tools..."):
        try:
            out = asyncio.run(agent.ask(question, ask_role, roles.get(ask_role), history))
        except Exception as exc:  # show setup problems (missing key or model) instead of a stack trace
            out = {"answer": f"Something went wrong: {exc}", "tool_calls": [], "stopped": "error"}
    st.session_state.log.append({"question": question, "role_id": ask_role, **out})

for turn in st.session_state.log:
    with st.chat_message("user"):
        st.write(turn["question"])
        st.caption(f"Role: {turn['role_id'] or 'all roles'}")
    with st.chat_message("assistant"):
        st.markdown(turn["answer"])
        if turn["stopped"] == "cap":
            st.warning("Stopped at the tool-step limit. The answer above may be incomplete.")
        with st.expander(f"Tool calls ({len(turn['tool_calls'])})"):
            for call in turn["tool_calls"]:
                st.markdown(f"**{call['name']}** `{json.dumps(call['args'])}`" + (" (error)" if call["is_error"] else ""))
                st.code(call["result"], language="json")
