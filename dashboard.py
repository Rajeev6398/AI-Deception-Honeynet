import streamlit as st
import json
import pandas as pd
import os
import time

# Page Configuration
st.set_page_config(
    page_title="AI Deception Honeynet - SOC Dashboard",
    page_icon="🛡️",
    layout="wide"
)

st.title("🛡️ AI-Powered Deception Honeynet | SOC Monitoring Center")
st.markdown("---")

# Function to load logs
def load_logs():
    log_file = "attack_logs.json"
    if not os.path.exists(log_file):
        return pd.DataFrame()
    
    data = []
    with open(log_file, "r") as f:
        for line in f:
            try:
                data.append(json.loads(line.strip()))
            except Exception:
                continue
    return pd.DataFrame(data)

df = load_logs()

# Metric Cards
col1, col2, col3, col4 = st.columns(4)

total_attacks = len(df) if not df.empty else 0
unique_ips = df['ip'].nunique() if not df.empty and 'ip' in df.columns else 0
top_user = df['username'].mode()[0] if not df.empty and 'username' in df.columns else "N/A"
top_pass = df['password'].mode()[0] if not df.empty and 'password' in df.columns else "N/A"

with col1:
    st.metric("🚨 Total Intrusion Attempts", total_attacks)
with col2:
    st.metric("🌐 Unique Attacker IPs", unique_ips)
with col3:
    st.metric("👤 Top Target Username", top_user)
with col4:
    st.metric("🔑 Top Tried Password", top_pass)

st.markdown("---")

if not df.empty:
    col_left, col_right = st.columns(2)
    
    with col_left:
        st.subheader("📊 Most Targeted Usernames")
        if 'username' in df.columns:
            st.bar_chart(df['username'].value_counts())
            
    with col_right:
        st.subheader("🔑 Top Wordlist Passwords Used")
        if 'password' in df.columns:
            st.bar_chart(df['password'].value_counts())

    st.markdown("---")
    st.subheader("📜 Real-Time Raw Attack Telemetry Logs")
    
    # Display latest logs first
    st.dataframe(df.sort_index(ascending=False), use_container_width=True)

else:
    st.info("ℹ️ No attack logs recorded yet. Launch an SSH attack on port 2222 to view live threat telemetry!")

# Auto-refresh option
time.sleep(2)
st.rerun()
