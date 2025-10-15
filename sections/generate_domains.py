import streamlit as st
import pandas as pd

def generate_domains_section(manager):
    st.header("Generate Domains")
    st.markdown("Generate domain name ideas using Gemini AI based on keywords and TLDs. View registrar pricing in the 'Registrar Pricing' section.")
    prompt = st.text_input("Enter keywords for domain generation", "AI startup", help="E.g., 'tech blog', 'e-commerce'")
    tlds = st.multiselect("Select TLDs", [".com", ".ai", ".org", ".net"], default=[".com", ".ai"], help="Select top-level domains")
    num_suggestions = st.number_input("Number of suggestions", min_value=1, max_value=20, value=10, step=1)
    
    if st.button("Generate Domains", help="Generate domain name suggestions"):
        if not prompt:
            st.error("Please enter keywords for domain generation.")
            return
        with st.spinner("Generating domains..."):
            generated_domains = manager.generate_domains(prompt, tlds, num_suggestions)
            if generated_domains:
                st.session_state.generated_domains = generated_domains
                st.success("Domain generation complete! Available domains saved to database. See below or check Search History/Registrar Pricing sections.")
    
    if "generated_domains" in st.session_state and st.session_state.generated_domains:
        st.subheader("Generated Domains")
        df = pd.DataFrame(st.session_state.generated_domains)
        st.dataframe(df[["domain", "availability"]], use_container_width=True)