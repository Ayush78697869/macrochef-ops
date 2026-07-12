"""MacroChef Ops Streamlit UI.  Run locally:  streamlit run src/app.py"""
import os
import sqlite3
import sys

# make `from src...` imports work no matter where streamlit is launched from
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

from src.agent import SYSTEM, run_agent
from src.llm import strip_think

st.set_page_config(page_title="MacroChef Ops", page_icon="🥗")
st.title("🥗 MacroChef Ops")
st.caption("Agentic meal planner over an Airtable-backed ops database (synthetic "
           "data) + the Dietary Guidelines for Americans. Plans validated by code.")

with st.sidebar:
    st.header("Plan for a client")
    con = sqlite3.connect(os.getenv("MACROCHEF_DB", "data/ops.sqlite"))
    clients = con.execute(
        "SELECT client_id, name, diet, allergies, calorie_target, "
        "protein_target_g FROM clients WHERE active = 1 ORDER BY name").fetchall()
    labels = [f"{c[1]} ({c[0]})" for c in clients]
    pick = st.selectbox("Client", labels)
    c = clients[labels.index(pick)]
    st.caption(f"Diet: {c[2]} · Allergies: {c[3] or 'none'} · "
               f"Targets: {c[4]:.0f} kcal / {c[5]:.0f}g protein")
    if st.button("Build tomorrow's plan", type="primary"):
        st.session_state.pending = f"Plan tomorrow's meals for client {c[0]}."
    st.divider()
    st.caption("All data is synthetic (Faker + generated meals). Plans are "
               "checked by code, not by the model: macros recomputed from the "
               "snapshot, allergens screened via keyword expansion.")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "system", "content": SYSTEM}]

# render history (skip the system prompt; tool calls shown via expanders)
for m in st.session_state.messages[1:]:
    role = m.get("role")
    if role == "user":
        st.chat_message("user").write(m["content"])
    elif role == "assistant":
        if m.get("tool_calls"):
            with st.chat_message("assistant"):
                with st.expander("🔧 tool calls"):
                    for tc in m["tool_calls"]:
                        st.code(f"{tc['function']['name']}({tc['function']['arguments']})",
                                language="text")
                if m.get("content"):
                    st.write(strip_think(m["content"]))
        elif m.get("content"):
            st.chat_message("assistant").write(strip_think(m["content"]))

user_msg = st.chat_input("Ask for a client's plan or a nutrition question...") \
    or st.session_state.pop("pending", None)

if user_msg:
    st.session_state.messages.append({"role": "user", "content": user_msg})
    with st.spinner("Planning (profile → search → compute → validate)..."):
        st.session_state.messages = run_agent(st.session_state.messages)
    st.rerun()