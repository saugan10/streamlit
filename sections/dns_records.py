import streamlit as st

def dns_records_section(manager):
    st.header("DNS Records")
    st.markdown("Select a domain to view its DNS records (A, MX, TXT).")
    st.subheader("Filter DNS Records")
    col1, col2 = st.columns(2)
    with col1:
        dns_domain_filter = st.text_input("Filter by Domain", key="dns_domain_filter", help="Enter part of a domain, e.g., 'startzyai'")
    with col2:
        dns_date_filter = st.date_input("Filter by Date", value=None, key="dns_date_filter", help="Select a date to filter DNS records")
    dns_records_by_domain = manager.get_dns_records(
        domain_filter=dns_domain_filter if dns_domain_filter else None,
        date_filter=dns_date_filter if dns_date_filter else None
    )
    if dns_records_by_domain:
        domains = sorted(dns_records_by_domain.keys())
        st.write(f"Total domains with DNS records: {len(domains)}")
        selected_domain = st.selectbox(
            "Select a domain to view DNS records",
            options=domains,
            format_func=lambda x: x,
            key="dns_select"
        )
        if selected_domain:
            st.subheader(f"DNS Records for {selected_domain}")
            st.write(f"Search Timestamp: {dns_records_by_domain[selected_domain]['search_timestamp']}")
            records = dns_records_by_domain[selected_domain]['records']
            if records:
                for record in records:
                    st.markdown(f"**{record['record_type']} Records**")
                    st.write(f"Records: {record['records']}")
                    st.write(f"Error: {record['error']}")
                    st.markdown("---")
            else:
                st.info(f"No DNS records found for {selected_domain}.")
    else:
        st.info("No DNS records available. Run an analysis with DNS checks in the 'Analyze Domains' section.")