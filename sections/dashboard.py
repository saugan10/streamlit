import streamlit as st
import pandas as pd
from utils import update_website_status

def dashboard_section(manager):
    st.header("Dashboard")
    st.markdown("View all user-entered domains with registrar, expiration date, and website status. Expand each domain for detailed results. Use the Refresh button to update statuses.")
    history = manager.get_search_history(source_filter="User-Entered")
    if history:
        st.write(f"Total user-entered domains: {len(history)}")
        # Initialize status updates for all domains
        domains = [item["domain"] for item in history]
        if domains and "dashboard_status_thread_started" not in st.session_state:
            st.session_state.dashboard_status_thread_started = True
            update_website_status(manager, domains, 180)
        
        # Refresh button for manual status update
        if st.button("Refresh Status", help="Manually re-check website status for all listed domains"):
            with st.spinner("Refreshing domain statuses..."):
                for domain in domains:
                    status = manager.check_website_status(domain)
                    st.session_state.status_updates[domain] = status
            st.success("Status refresh complete!")
            st.rerun()

        # Prepare dashboard data
        dashboard_data = []
        for item in history:
            domain = item["domain"]
            status = st.session_state.status_updates.get(domain, manager.check_website_status(domain))
            dashboard_data.append({
                "domain": domain,
                "registrar": item["registrar"],
                "expiration_alert": item["expiration_alert"],
                "website_status": status["status"],
                "status_code": status["status_code"],
                "status_error": status["error"],
                "last_checked": status.get("last_checked", "N/A"),
                "expires_soon": manager._is_expiring_soon(item["expiration_alert"]),
                "results_json": item["results_json"]
            })
        
        # Display dashboard
        df = pd.DataFrame(dashboard_data)
        df_display = df[["domain", "registrar", "expiration_alert", "website_status", "status_code", "last_checked", "expires_soon"]]
        df_display["expires_soon"] = df_display["expires_soon"].apply(lambda x: "⚠️ Expiring Soon" if x else "Safe")
        st.dataframe(df_display, use_container_width=True)

        # Expandable details for each domain
        for item in dashboard_data:
            with st.expander(f"Details for {item['domain']}"):
                st.write(f"**Search Timestamp**: {item['results_json'][0].get('search_timestamp', 'N/A')}")
                st.write(f"**Registrar**: {item['registrar']}")
                st.write(f"**Expiration Date**: {item['expiration_alert']}")
                st.write(f"**Website Status**: {item['website_status']}")
                st.write(f"**HTTP Status Code**: {item['status_code'] or 'N/A'}")
                st.write(f"**Status Error**: {item['status_error'] or 'N/A'}")
                st.write(f"**Last Checked**: {item['last_checked']}")
                st.markdown("**Full Results**:")
                st.json(item["results_json"])
    else:
        st.info("No user-entered domains available. Run an analysis in the 'Analyze Domains' section.")