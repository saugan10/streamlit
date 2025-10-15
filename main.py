import streamlit as st
from domain_manager import DomainManager
from sections.dashboard import dashboard_section
from sections.analyze_domains import analyze_domains_section
from sections.generate_domains import generate_domains_section
from sections.search_history import search_history_section
from sections.dns_records import dns_records_section
from sections.domain_status import domain_status_section
from sections.registrar_pricing import registrar_pricing_section

def main():
    st.title("Domain Management Tool")
    st.markdown("Analyze domains, generate domain name ideas, view registrar pricing, manage search history, track DNS records, or check website status and expiration alerts. All searches are saved to a local SQLite database (domains.db).")
    st.markdown("**Note**: For threat intelligence, ensure valid DomainTools credentials are set in the code. For domain generation, ensure a valid Gemini AI API key is set in the code.")

    if "checks" not in st.session_state:
        st.session_state.checks = []
    if "status_updates" not in st.session_state:
        st.session_state.status_updates = {}
    if "selected_section" not in st.session_state:
        st.session_state.selected_section = "Dashboard"

    # Custom CSS for navigation buttons
    st.markdown("""
        <style>
        .nav-button {
            display: block;
            width: 100%;
            padding: 10px;
            margin: 5px 0;
            border: 2px solid #4CAF50;
            border-radius: 8px;
            background-color: #f0f2f6;
            color: #333;
            font-size: 16px;
            font-weight: bold;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        }
        .nav-button:hover {
            background-color: #4CAF50;
            color: white;
            transform: scale(1.05);
        }
        .nav-button.active {
            background-color: #4CAF50;
            color: white;
            border-color: #388E3C;
            box-shadow: 0 4px 8px rgba(0,0,0,0.2);
        }
        </style>
    """, unsafe_allow_html=True)

    # Sidebar navigation with styled buttons
    st.sidebar.title("Navigation")
    sections = ["Dashboard", "Analyze Domains", "Generate Domains", "Search History", "DNS Records", "Domain Status", "Registrar Pricing"]
    for section in sections:
        button_key = f"nav_{section.replace(' ', '_').lower()}"
        if st.sidebar.button(section, key=button_key):
            st.session_state.selected_section = section
        # Add custom CSS class for active state
        st.markdown(f"""
            <script>
            document.querySelectorAll('.nav-button').forEach(button => {{
                button.classList.remove('active');
                if (button.textContent === "{st.session_state.selected_section}") {{
                    button.classList.add('active');
                }}
            }});
            </script>
        """, unsafe_allow_html=True)

    manager = DomainManager()
    section = st.session_state.selected_section

    if section == "Dashboard":
        dashboard_section(manager)
    elif section == "Analyze Domains":
        analyze_domains_section(manager)
    elif section == "Generate Domains":
        generate_domains_section(manager)
    elif section == "Search History":
        search_history_section(manager)
    elif section == "DNS Records":
        dns_records_section(manager)
    elif section == "Domain Status":
        domain_status_section(manager)
    elif section == "Registrar Pricing":
        registrar_pricing_section(manager)

if __name__ == "__main__":
    main()