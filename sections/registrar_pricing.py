import streamlit as st
import pandas as pd
import json
from utils import format_suggestions

def registrar_pricing_section(manager):
    st.header("Registrar Pricing")
    st.markdown("View registrar pricing for available generated domains. Prices are static; visit registrar websites for real-time pricing.")
    st.subheader("Filter Registrar Pricing")
    col1, col2 = st.columns(2)
    with col1:
        pricing_domain_filter = st.text_input("Filter by Domain", key="pricing_domain_filter", help="Enter part of a domain, e.g., 'aistartup'")
    with col2:
        pricing_date_filter = st.date_input("Filter by Date", value=None, key="pricing_date_filter", help="Select a date to filter generated domains")
    generated_history = manager.get_available_generated_domains(
        domain_filter=pricing_domain_filter if pricing_domain_filter else None,
        date_filter=pricing_date_filter if pricing_date_filter else None
    )
    if generated_history:
        st.write(f"Total available generated domains: {len(generated_history)}")
        df = pd.DataFrame(generated_history)
        df["registrar_suggestions"] = df.apply(
            lambda row: format_suggestions(*manager.get_registrar_pricing(row["domain"])) if row["availability"] == "Available" else json.dumps([{
                "registrar": "N/A",
                "first_year": "N/A",
                "renewal": "N/A",
                "whois_privacy": "N/A",
                "recommended": "",
                "url": "N/A"
            }]),
            axis=1
        )
        df["registrar_suggestions_display"] = df["registrar_suggestions"].apply(
            lambda x: "\n".join([f"{item['registrar']}: ${item['first_year']}/${item['renewal']} ({item['whois_privacy']}) {'✅' if item['recommended'] else ''}" for item in json.loads(x)])
        )
        st.dataframe(
            df[["domain", "search_timestamp", "availability", "registrar_suggestions_display"]],
            use_container_width=True
        )
        
        selected_pricing_id = st.selectbox(
            "Select a domain to view pricing details",
            options=df["id"].tolist(),
            format_func=lambda x: f"ID {x}: {df[df['id'] == x]['domain'].iloc[0]}",
            key="pricing_select"
        )
        if selected_pricing_id:
            selected_result = next((item for item in generated_history if item["id"] == selected_pricing_id), None)
            if selected_result:
                st.subheader(f"Pricing for {selected_result['domain']}")
                st.write(f"Search Timestamp: {selected_result['search_timestamp']}")
                st.dataframe(
                    selected_result["registrar_suggestions"],
                    use_container_width=True
                )
    else:
        st.info("No available generated domains. Generate domains in the 'Generate Domains' section.")