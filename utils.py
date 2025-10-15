import streamlit as st
import pandas as pd
import threading
import json

def update_website_status(manager, domains, interval=180):
    """Update website status for domains every 'interval' seconds."""
    if not domains:
        return
    if "status_updates" not in st.session_state:
        st.session_state.status_updates = {}
    
    for domain in domains:
        status = manager.check_website_status(domain)
        st.session_state.status_updates[domain] = status
    
    # Schedule the next update
    threading.Timer(interval, update_website_status, args=[manager, domains, interval]).start()

def format_suggestions(suggestions, recommended):
    if suggestions is None or not isinstance(suggestions, list) or not suggestions:
        return json.dumps([{
            "registrar": "N/A",
            "first_year": "N/A",
            "renewal": "N/A",
            "whois_privacy": "N/A",
            "recommended": "",
            "url": "N/A"
        }])
    suggestions_df = pd.DataFrame(suggestions)
    suggestions_df["recommended"] = suggestions_df["registrar"].apply(lambda x: "✅" if x == recommended else "")
    return suggestions_df[["registrar", "first_year", "renewal", "whois_privacy", "recommended", "url"]].to_json(orient="records")