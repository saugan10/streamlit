import streamlit as st
import pandas as pd

def search_history_section(manager):
    st.header("Search History")
    st.markdown("View and manage user-entered and available generated domains. Delete domains from history as needed. DNS records and status checks are in the 'DNS Records' and 'Domain Status' sections.")
    
    st.subheader("User-Entered Domains")
    st.write(f"Total user-entered searches: {len(manager.get_search_history())}")
    st.subheader("Filter User-Entered Domains")
    col1, col2, col3 = st.columns(3)
    with col1:
        domain_filter = st.text_input("Filter by Domain", key="user_domain_filter", help="Enter part of a domain, e.g., 'startzyai'")
    with col2:
        date_filter = st.date_input("Filter by Date", value=None, key="user_date_filter", help="Select a date to filter searches")
    with col3:
        check_filter = st.selectbox(
            "Filter by Check Type",
            options=["all", "whois", "expiration", "rdap", "security", "availability"],
            key="user_check_filter",
            help="Filter by type of check performed"
        )
    history = manager.get_search_history(
        domain_filter=domain_filter if domain_filter else None,
        date_filter=date_filter if date_filter else None,
        check_filter=check_filter if check_filter else None
    )
    if history:
        df = pd.DataFrame(history)
        df_display = df[["id", "domain", "search_timestamp", "registrar", "expiration_alert", "dnssec_valid", "availability", "source"]]
        st.dataframe(
            df_display,
            use_container_width=True
        )
        
        st.subheader("Delete Domains from History")
        domains_to_delete = st.multiselect(
            "Select domains to delete",
            options=df["domain"].unique().tolist(),
            key="delete_domains",
            help="Select one or more domains to remove from search history"
        )
        if st.button("Delete Selected Domains", help="Remove selected domains from the database"):
            if domains_to_delete:
                manager.delete_domains(domains_to_delete)
                st.session_state.pop("user_select", None)
                st.rerun()
            else:
                st.warning("Please select at least one domain to delete.")
        
        selected_id = st.selectbox(
            "Select a search to view details",
            options=df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {df[df['id'] == x]['domain'].iloc[0]} ({df[df['id'] == x]['source'].iloc[0]})",
            key="user_select"
        )
        if selected_id:
            selected_result = next((item for item in history if item["id"] == selected_id), None)
            if selected_result:
                st.subheader(f"Details for Search ID {selected_id} ({selected_result['domain']})")
                with st.expander("Full Results", expanded=False):
                    st.json(selected_result["results_json"])
    else:
        st.info("No user-entered search history available. Run an analysis in the 'Analyze Domains' section.")

    st.subheader("Available Generated Domains")
    generated_history = manager.get_available_generated_domains()
    st.write(f"Total available generated domains: {len(generated_history)}")
    st.subheader("Filter Available Generated Domains")
    col1, col2 = st.columns(2)
    with col1:
        gen_domain_filter = st.text_input("Filter by Domain", key="gen_domain_filter", help="Enter part of a domain, e.g., 'aistartup'")
    with col2:
        gen_date_filter = st.date_input("Filter by Date", value=None, key="gen_date_filter", help="Select a date to filter generated domains")
    generated_history = manager.get_available_generated_domains(
        domain_filter=gen_domain_filter if gen_domain_filter else None,
        date_filter=gen_date_filter if gen_date_filter else None
    )
    if generated_history:
        df = pd.DataFrame(generated_history)
        df_display = df[["id", "domain", "search_timestamp", "availability", "source"]]
        st.dataframe(
            df_display,
            use_container_width=True
        )
        
        st.subheader("Delete Generated Domains")
        gen_domains_to_delete = st.multiselect(
            "Select generated domains to delete",
            options=df["domain"].unique().tolist(),
            key="delete_gen_domains",
            help="Select one or more generated domains to remove from history"
        )
        if st.button("Delete Selected Generated Domains", help="Remove selected generated domains from the database"):
            if gen_domains_to_delete:
                manager.delete_domains(gen_domains_to_delete)
                st.session_state.pop("gen_select", None)
                st.rerun()
            else:
                st.warning("Please select at least one generated domain to delete.")
        
        selected_gen_id = st.selectbox(
            "Select an available generated domain to view details",
            options=df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {df[df['id'] == x]['domain'].iloc[0]}",
            key="gen_select"
        )
        if selected_gen_id:
            selected_result = next((item for item in generated_history if item["id"] == selected_gen_id), None)
            if selected_result:
                st.subheader(f"Details for Search ID {selected_gen_id} ({selected_result['domain']})")
                with st.expander("Full Results", expanded=False):
                    st.json(selected_result["results_json"])
    else:
        st.info("No available generated domains. Generate domains in the 'Generate Domains' section.")