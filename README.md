Domain Management Tool


Overview
The Domain Management Tool is a Python-based web application built using Streamlit for analyzing and managing domain names. It provides functionalities to check domain WHOIS information, DNS records, expiration dates, RDAP data, DNSSEC validation, threat intelligence, and domain availability. Additionally, it supports generating domain name ideas using the Gemini AI API and displays registrar pricing for available domains. All search results are stored in a local SQLite database (domains.db) for easy retrieval and management.
Features

Analyze Domains: Perform WHOIS lookups, DNS record checks (A, MX, TXT), expiration checks, RDAP lookups, DNSSEC validation, threat intelligence, and availability checks.
Generate Domains: Generate domain name ideas based on keywords and top-level domains (TLDs) using the Gemini AI API.
Search History: View and manage search history for user-entered and generated domains, with filtering by domain, date, and check type.
DNS Records: Display DNS records (A, MX, TXT) for user-entered domains with filtering options.
Domain Status: Monitor website status (Live/Not Live) and expiration alerts, with automatic updates every 3 minutes and manual refresh capabilities.
Registrar Pricing: View static pricing for available generated domains from registrars like Namecheap, GoDaddy, Cloudflare, Porkbun, and IONOS.
Database Storage: Store all search results in a local SQLite database (domains.db) for persistence and easy access.
Interactive UI: Built with Streamlit, featuring a responsive interface with navigation buttons, expandable sections, and data tables.

Requirements

Python 3.8+
Required Python packages (install via pip):pip install streamlit pandas python-whois dnspython requests sqlite3 domaintools google-generativeai

Note: domaintools and google-generativeai are optional but required for threat intelligence and domain generation features, respectively.
A valid Gemini AI API key for domain generation (replace GEMINI_API_KEY in the code).
Valid DomainTools credentials (DOMAINTOOLS_USERNAME and DOMAINTOOLS_API_KEY) for threat intelligence (optional).
Internet connection for WHOIS, DNS, RDAP, and website status checks.

Installation

Clone or download the repository to your local machine.

Install the required Python packages:pip install -r requirements.txt


Create a requirements.txt file with the following:streamlit


pandas

python-whois

dnspython

requests

sqlite3

domaintools

google-generativeai


Update the following variables in the code with your credentials:

GEMINI_API_KEY: Your Gemini AI API key (required for domain generation).

DOMAINTOOLS_USERNAME and DOMAINTOOLS_API_KEY: Your DomainTools credentials (optional, for threat intelligence).



Ensure you have an active internet connection for external API calls.

Usage

Run the Streamlit application:streamlit run domain_management_tool.py


Open your browser and navigate to the URL provided by Streamlit (typically http://localhost:8501).
Use the sidebar navigation to access different sections:
Dashboard: View all user-entered domains with registrar, expiration, and website status.
Analyze Domains: Input domains and select checks (WHOIS, DNS, etc.) to analyze.
Generate Domains: Enter keywords and TLDs to generate domain name ideas.
Search History: View and delete search history for user-entered and generated domains.
DNS Records: View DNS records for user-entered domains.
Domain Status: Check website status and expiration alerts.
Registrar Pricing: View pricing for available generated domains.


Results are automatically saved to domains.db. Download analysis results as JSON from the "Analyze Domains" section.

Database

The tool uses a SQLite database (domains.db) to store search results.
Table structure:
searches: Stores search data with columns id, domain, search_timestamp, results_json, and source (either User-Entered or Generated).


The database is created automatically on the first run and persists between sessions.

Notes

Gemini AI: Requires a valid API key from Google AI. Without it, domain generation will not work.
DomainTools: Threat intelligence requires valid credentials from DomainTools. If not configured, threat intelligence checks will be skipped.
Registrar Pricing: Pricing data is static and included for .com and .ai TLDs. Visit registrar websites for real-time pricing.
Website Status: Status checks run every 3 minutes in the background for Dashboard and Domain Status sections. Use the "Refresh Status" button for manual updates.
DNSSEC: If a domain lacks DNSSEC records, a warning is displayed with instructions to contact the registrar.
Limitations:
WHOIS and RDAP lookups may fail for some domains due to registrar restrictions or rate limits.
Threat intelligence requires the domaintools library and valid credentials.
Domain generation requires the google-generativeai library and a valid Gemini AI API key.



File Structure

domain_management_tool.py: Main application script.
domains.db: SQLite database for storing search results (created automatically).
domain_results.json: Output file for analysis results (generated on demand).

Example Usage

Analyze Domains:
Enter example.com and startzyai.com in the text area.
Select checks (e.g., WHOIS, DNS, Expiration).
Click "Analyze Domains" to view results in expandable sections.
Download results as domain_results.json.


Generate Domains:
Enter keywords like AI startup and select TLDs (e.g., .com, .ai).
Click "Generate Domains" to see available domain suggestions.
View pricing in the "Registrar Pricing" section.


View History:
Navigate to "Search History" to filter and view past searches.
Delete unwanted domains from the history.


Check Status:
Go to "Domain Status" to see which domains are live and if any are expiring soon (within 30 days).



Contributing
Contributions are welcome! Please submit a pull request or open an issue for bug reports or feature requests.
License
This project is licensed under the MIT License.
Contact
For questions or support, contact the project maintainer or open an issue on the repository.
