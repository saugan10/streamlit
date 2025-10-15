import streamlit as st
import pandas as pd
from utils import update_website_status

def domain_status_section(manager):
    st.header("Domain Status")
    st.markdown("Check the website status (Live/Not Live, updated every 3 minutes) and expiration alerts for user-entered domains. Domains expiring within 30 days are highlighted. Use the Refresh button to manually update statuses.")
    st.subheader("Filter Domain Status")
    col1, col2 = st.columns(2)
    with col1:
        status_domain_filter = st.text_input("Filter by Domain", key="status_domain_filter", help="Enter part of a domain, e.g., 'startzyai'")
    with col2:
        status_date_filter = st.date_input("Filter by Date", value=None, key="status_date_filter", help="Select a date to filter domain status")
    status_list = manager.get_domain_status(
        domain_filter=status_domain_filter if status_domain_filter else None,
        date_filter=status_date_filter if status_date_filter else None
    )
    if status_list:
        st.write(f"Total domains: {len(status_list)}")
        # Start background status updates
        domains = [item["domain"] for item in status_list]
        if domains and "status_update_thread_started" not in st.session_state:
            st.session_state.status_update_thread_started = True
            update_website_status(manager, domains, 180)
        
        # Refresh button for manual status update
        if st.button("Refresh Status", help="Manually re-check website status for all listed domains"):
            with st.spinner("Refreshing domain statuses..."):
                for domain in domains:
                    status = manager.check_website_status(domain)
                    st.session_state.status_updates[domain] = status
            st.success("Status refresh complete!")
            st.rerun()
        
        # Update status_list with latest status from session state
        for item in status_list:
            domain = item["domain"]
            if domain in st.session_state.status_updates:
                status = st.session_state.status_updates[domain]
                item["website_status"] = status["status"]
                item["status_code"] = status["status_code"]
                item["status_error"] = status["error"]
                item["last_checked"] = status.get("last_checked", item["last_checked"])
        
        df = pd.DataFrame(status_list)
        df_display = df[["id", "domain", "search_timestamp", "website_status", "status_code", "status_error", "last_checked", "expiration_alert", "expires_soon"]]
        df_display["expires_soon"] = df_display["expires_soon"].apply(lambda x: "⚠️ Expiring Soon" if x else "Safe")
        st.dataframe(df_display, use_container_width=True)
        
        selected_status_id = st.selectbox(
            "Select a domain to view details",
            options=df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {df[df['id'] == x]['domain'].iloc[0]}",
            key="status_select"
        )
        if selected_status_id:
            selected_status = next((item for item in status_list if item["id"] == selected_status_id), None)
            if selected_status:
                st.subheader(f"Status for {selected_status['domain']}")
                st.write(f"Search Timestamp: {selected_status['search_timestamp']}")
                st.markdown(f"**Website Status**: {selected_status['website_status']}")
                st.write(f"HTTP Status Code: {selected_status['status_code'] or 'N/A'}")
                st.write(f"Error: {selected_status['status_error'] or 'N/A'}")
                st.write(f"Last Checked: {selected_status['last_checked']}")
                st.markdown(f"**Expiration Date**: {selected_status['expiration_alert']}")
                st.write(f"Expires Soon: {'⚠️ Yes' if selected_status['expires_soon'] else 'No'}")
                if selected_status['expires_soon']:
                    st.warning(f"{selected_status['domain']} is expiring soon (within 30 days). Contact your registrar to renew.")
    else:
        st.info("No domain status available. Run an analysis with Expiration Check in the 'Analyze Domains' section.")