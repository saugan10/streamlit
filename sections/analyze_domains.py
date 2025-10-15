import streamlit as st
import pandas as pd

def analyze_domains_section(manager):
    st.header("Analyze Domains")
    st.subheader("Input and Options")
    domains_input = st.text_area("Enter domains (one per line)", "example.com\nstartzyai.com", help="Enter one domain per line, e.g., example.com")
    domains = domains_input.split("\n")

    st.subheader("Select Checks")
    checks = {
        "WHOIS Lookup": "whois",
        "DNS Records": "dns",
        "Expiration Check": "expiration",
        "RDAP Lookup": "rdap",
        "Security (DNSSEC & Threat Intel)": "security",
        "Availability Check": "availability"
    }
    cols = st.columns(2)
    for i, (label, key) in enumerate(checks.items()):
        with cols[i % 2]:
            if st.checkbox(label, value=True, help=f"Enable {label.lower()}"):
                if key not in st.session_state.checks:
                    st.session_state.checks.append(key)
            else:
                if key in st.session_state.checks:
                    st.session_state.checks.remove(key)

    st.subheader("DNS Record Types")
    dns_types = st.multiselect("Select DNS Record Types", ["A", "MX", "TXT"], default=["A", "MX", "TXT"], help="Select DNS record types to check")

    if st.button("Analyze Domains", help="Run analysis for selected domains and checks"):
        if not domains_input.strip():
            st.error("Please enter at least one domain.")
            return
        with st.spinner("Analyzing domains..."):
            manager.manage_domains(domains, check_dns_types=dns_types)
            filename = manager.save_results()
            st.session_state.results = manager.results
            st.session_state.filename = filename
        st.success("Analysis complete! Results saved to database. See below or check Dashboard/Search History/DNS Records/Domain Status sections.")

    if "results" in st.session_state and st.session_state.results:
        st.header("Analysis Results")
        st.markdown("Expand each section to view detailed results. Errors (e.g., missing DNSSEC records) are shown in the tables.")

        with st.expander("WHOIS Lookup", expanded=True):
            whois_results = [r for r in st.session_state.results if "registrar" in r]
            if whois_results:
                df = pd.DataFrame(whois_results)
                df_display = df[["domain", "registrar", "creation_date", "expiration_date", "name_servers", "status", "error"]]
                df_display["name_servers"] = df_display["name_servers"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                df_display["status"] = df_display["status"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                st.dataframe(df_display, use_container_width=True)
            else:
                st.info("No WHOIS results available.")

        with st.expander("Expiration Check", expanded=True):
            exp_results = [r for r in st.session_state.results if "expiration_alert" in r]
            if exp_results:
                df = pd.DataFrame(exp_results)
                st.dataframe(df[["domain", "expiration_alert", "error"]], use_container_width=True)
            else:
                st.info("No expiration check results available.")

        with st.expander("RDAP Lookup", expanded=True):
            rdap_results = [r for r in st.session_state.results if "rdap_registrar" in r]
            if rdap_results:
                df = pd.DataFrame(rdap_results)
                df_display = df[["domain", "rdap_registrar", "rdap_status", "error"]]
                df_display["rdap_status"] = df_display["rdap_status"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                st.dataframe(df_display, use_container_width=True)
            else:
                st.info("No RDAP results available.")

        with st.expander("Security (DNSSEC & Threat Intelligence)", expanded=True):
            dnssec_results = [r for r in st.session_state.results if "dnssec_valid" in r]
            threat_results = [r for r in st.session_state.results if "threat_info" in r]
            if dnssec_results:
                st.subheader("DNSSEC Validation")
                df = pd.DataFrame(dnssec_results)
                st.dataframe(df[["domain", "dnssec_valid", "error"]], use_container_width=True)
                if any("DNSSEC not enabled" in r.get("error", "") for r in dnssec_results):
                    st.warning("Some domains lack DNSSEC records. Contact your registrar to enable DNSSEC if desired.")
            else:
                st.info("No DNSSEC results available.")
            if threat_results:
                st.subheader("Threat Intelligence")
                df = pd.DataFrame(threat_results)
                df_display = df[["domain", "threat_info", "error"]]
                df_display["threat_info"] = df_display["threat_info"].apply(
                    lambda x: f"Risk Score: {x['risk_score']}, Profile: {x['threat_profile']}" if isinstance(x, dict) else x
                )
                st.dataframe(df_display, use_container_width=True)
                if any("DomainTools credentials missing" in r.get("error", "") for r in threat_results):
                    st.warning("Threat intelligence requires valid DomainTools credentials in the code. See https://www.domaintools.com/ for details.")
            else:
                st.info("No threat intelligence results available.")

        with st.expander("Availability Check", expanded=True):
            avail_results = [r for r in st.session_state.results if "availability" in r]
            if avail_results:
                df = pd.DataFrame(avail_results)
                st.dataframe(df[["domain", "availability"]], use_container_width=True)
            else:
                st.info("No availability check results available.")

        st.subheader("Download Results")
        with open(st.session_state.filename, "rb") as f:
            st.download_button(
                label="Download Results (JSON)",
                data=f,
                file_name="domain_results.json",
                mime="application/json",
                help="Download all analysis results as a JSON file"
            )