import whois
import dns.resolver
import dns.dnssec
import dns.exception
import json
import requests
from datetime import datetime, timedelta
import streamlit as st
import pandas as pd
import sqlite3
import threading
import time
try:
    import domaintools
except ImportError:
    domaintools = None
try:
    import google.generativeai as genai
except ImportError:
    genai = None

GEMINI_API_KEY = "AIzaSyALF3iUDdh8nV7i9ZoF3mUc7YcCywxuZkM"  # Replace with your Gemini AI API key
DOMAINTOOLS_USERNAME = "your_domaintools_username"  # Replace with your DomainTools username or ""
DOMAINTOOLS_API_KEY = "your_domaintools_api_key"  # Replace with your DomainTools API key or ""

class DomainManager:
    def __init__(self, db_file="domains.db"):
        self.results = []
        self.db_file = db_file
        try:
            self.conn = sqlite3.connect(db_file, check_same_thread=False)
            self.cursor = self.conn.cursor()
            self.cursor.execute("""
                CREATE TABLE IF NOT EXISTS searches (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    domain TEXT NOT NULL,
                    search_timestamp TEXT NOT NULL,
                    results_json TEXT,
                    source TEXT DEFAULT 'User-Entered'
                )
            """)
            self.cursor.execute("PRAGMA table_info(searches)")
            columns = [col[1] for col in self.cursor.fetchall()]
            if 'source' not in columns:
                self.cursor.execute("ALTER TABLE searches ADD COLUMN source TEXT DEFAULT 'User-Entered'")
                self.conn.commit()
                st.write("Added 'source' column to searches table")
            self.conn.commit()
            st.write(f"Database initialized at {db_file}")
        except sqlite3.Error as e:
            st.error(f"Database initialization failed: {str(e)}")
            self.conn = None
            self.cursor = None

    def store_search(self, domain, results, source="User-Entered"):
        if not self.conn:
            st.error("Database connection not available. Search not saved.")
            return
        try:
            search_timestamp = datetime.now().isoformat()
            results_json = json.dumps(results)
            self.cursor.execute(
                "INSERT INTO searches (domain, search_timestamp, results_json, source) VALUES (?, ?, ?, ?)",
                (domain, search_timestamp, results_json, source)
            )
            self.conn.commit()
            st.write(f"Saved search for {domain} ({source}) at {search_timestamp}")
        except sqlite3.Error as e:
            st.error(f"Failed to save search for {domain}: {str(e)}")

    def delete_domains(self, domains):
        if not self.conn:
            st.error("Database connection not available. Deletion failed.")
            return
        try:
            for domain in domains:
                self.cursor.execute("DELETE FROM searches WHERE domain = ?", (domain,))
            self.conn.commit()
            st.success(f"Deleted {len(domains)} domain(s) from search history.")
        except sqlite3.Error as e:
            st.error(f"Failed to delete domains: {str(e)}")

    def get_alerts_log(self):
        return []

    def get_search_history(self, domain_filter=None, date_filter=None, check_filter=None, source_filter="User-Entered"):
        if not self.conn:
            return []
        try:
            query = "SELECT id, domain, search_timestamp, results_json, source FROM searches WHERE source = ?"
            params = [source_filter]
            if domain_filter:
                query += " AND domain LIKE ?"
                params.append(f"%{domain_filter}%")
            if date_filter:
                query += " AND date(search_timestamp) = ?"
                params.append(date_filter.strftime("%Y-%m-%d"))
            if source_filter == "all":
                query = query.replace("source = ?", "1=1")
                params.pop(0)
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            history = []
            for row in rows:
                result = {
                    "id": row[0],
                    "domain": row[1],
                    "search_timestamp": row[2],
                    "results_json": json.loads(row[3]),
                    "source": row[4]
                }
                results = result["results_json"]
                result["registrar"] = next((r["registrar"] for r in results if "registrar" in r), "N/A")
                result["expiration_alert"] = next((r["expiration_alert"] for r in results if "expiration_alert" in r), "N/A")
                result["dnssec_valid"] = next((r["dnssec_valid"] for r in results if "dnssec_valid" in r), "N/A")
                result["availability"] = next((r["availability"] for r in results if "availability" in r), "N/A")
                result["error_summary"] = ", ".join([r.get("error", "") for r in results if r.get("error")])
                if check_filter and check_filter != "all":
                    if not any(check_filter in r for r in results):
                        continue
                history.append(result)
            return history
        except sqlite3.Error as e:
            st.error(f"Failed to retrieve search history: {str(e)}")
            return []

    def get_available_generated_domains(self, domain_filter=None, date_filter=None):
        if not self.conn:
            return []
        try:
            query = "SELECT id, domain, search_timestamp, results_json, source FROM searches WHERE source = 'Generated' AND results_json LIKE '%\"availability\": \"Available\"%'"
            params = []
            if domain_filter:
                query += " AND domain LIKE ?"
                params.append(f"%{domain_filter}%")
            if date_filter:
                query += " AND date(search_timestamp) = ?"
                params.append(date_filter.strftime("%Y-%m-%d"))
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            history = []
            for row in rows:
                result = {
                    "id": row[0],
                    "domain": row[1],
                    "search_timestamp": row[2],
                    "results_json": json.loads(row[3]),
                    "source": row[4]
                }
                results = result["results_json"]
                result["availability"] = next((r["availability"] for r in results if "availability" in r), "N/A")
                # Add registrar_suggestions
                if result["availability"] == "Available":
                    pricing, recommended = self.get_registrar_pricing(result["domain"])
                    suggestions_df = pd.DataFrame(pricing)
                    suggestions_df["recommended"] = suggestions_df["registrar"].apply(lambda x: "✅" if x == recommended else "")
                    result["registrar_suggestions"] = suggestions_df[["registrar", "first_year", "renewal", "whois_privacy", "recommended", "url"]]
                else:
                    result["registrar_suggestions"] = pd.DataFrame([{
                        "registrar": "N/A",
                        "first_year": "N/A",
                        "renewal": "N/A",
                        "whois_privacy": "N/A",
                        "recommended": "",
                        "url": "N/A"
                    }])
                history.append(result)
            return history
        except sqlite3.Error as e:
            st.error(f"Failed to retrieve available generated domains: {str(e)}")
            return []

    def get_dns_records(self, domain_filter=None, date_filter=None):
        if not self.conn:
            return []
        try:
            query = "SELECT id, domain, search_timestamp, results_json, source FROM searches WHERE source = 'User-Entered' AND results_json LIKE '%\"record_type\":%'"
            params = []
            if domain_filter:
                query += " AND domain LIKE ?"
                params.append(f"%{domain_filter}%")
            if date_filter:
                query += " AND date(search_timestamp) = ?"
                params.append(date_filter.strftime("%Y-%m-%d"))
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            dns_records_by_domain = {}
            for row in rows:
                domain = row[1]
                search_timestamp = row[2]
                results = json.loads(row[3])
                if domain not in dns_records_by_domain:
                    dns_records_by_domain[domain] = {
                        "id": row[0],
                        "search_timestamp": search_timestamp,
                        "records": []
                    }
                for record in results:
                    if "record_type" in record:
                        dns_records_by_domain[domain]["records"].append({
                            "record_type": record["record_type"],
                            "records": ", ".join(record["records"]) if record["records"] else "N/A",
                            "error": record["error"] or "N/A"
                        })
            return dns_records_by_domain
        except sqlite3.Error as e:
            st.error(f"Failed to retrieve DNS records: {str(e)}")
            return {}

    def get_domain_status(self, domain_filter=None, date_filter=None):
        if not self.conn:
            return []
        try:
            query = "SELECT id, domain, search_timestamp, results_json FROM searches WHERE source = 'User-Entered'"
            params = []
            if domain_filter:
                query += " AND domain LIKE ?"
                params.append(f"%{domain_filter}%")
            if date_filter:
                query += " AND date(search_timestamp) = ?"
                params.append(date_filter.strftime("%Y-%m-%d"))
            self.cursor.execute(query, params)
            rows = self.cursor.fetchall()
            status_list = []
            for row in rows:
                domain = row[1]
                search_timestamp = row[2]
                results = json.loads(row[3])
                expiration_alert = next((r["expiration_alert"] for r in results if "expiration_alert" in r), "N/A")
                status = self.check_website_status(domain)
                status_info = {
                    "id": row[0],
                    "domain": domain,
                    "search_timestamp": row[2],
                    "website_status": status["status"],
                    "status_code": status["status_code"],
                    "status_error": status["error"],
                    "last_checked": status.get("last_checked", "N/A"),
                    "expiration_alert": expiration_alert,
                    "expires_soon": self._is_expiring_soon(expiration_alert)
                }
                status_list.append(status_info)
            return status_list
        except sqlite3.Error as e:
            st.error(f"Failed to retrieve domain status: {str(e)}")
            return []

    def check_website_status(self, domain):
        try:
            url = f"https://{domain}"
            response = requests.get(url, timeout=5)
            status = "Live" if response.status_code == 200 else "Not Live"
            return {
                "status": status,
                "status_code": response.status_code,
                "error": None,
                "last_checked": datetime.now().isoformat()
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "Not Live",
                "status_code": None,
                "error": str(e),
                "last_checked": datetime.now().isoformat()
            }

    def _is_expiring_soon(self, expiration_alert):
        if expiration_alert == "N/A":
            return False
        try:
            exp_date = datetime.strptime(expiration_alert, "%Y-%m-%d %H:%M:%S")
            return exp_date <= datetime.now() + timedelta(days=30)
        except ValueError:
            try:
                exp_date = datetime.strptime(expiration_alert, "%Y-%m-%d")
                return exp_date <= datetime.now() + timedelta(days=30)
            except ValueError:
                return False

    def get_registrar_pricing(self, domain):
        tld = domain.split('.')[-1]
        pricing_data = {
            ".com": [
                {"registrar": "Namecheap", "first_year": 11.28, "renewal": 16.98, "whois_privacy": "Free", "url": "https://www.namecheap.com"},
                {"registrar": "GoDaddy", "first_year": 11.99, "renewal": 19.99, "whois_privacy": "Paid", "url": "https://www.godaddy.com"},
                {"registrar": "Cloudflare", "first_year": 9.15, "renewal": 9.15, "whois_privacy": "Not Included", "url": "https://www.cloudflare.com"},
                {"registrar": "Porkbun", "first_year": 11.06, "renewal": 11.06, "whois_privacy": "Free", "url": "https://porkbun.com"},
                {"registrar": "IONOS", "first_year": 1.00, "renewal": 20.00, "whois_privacy": "Free with hosting", "url": "https://www.ionos.com"}
            ],
            ".ai": [
                {"registrar": "Namecheap", "first_year": 68.88, "renewal": 68.88, "whois_privacy": "Free", "url": "https://www.namecheap.com"},
                {"registrar": "GoDaddy", "first_year": 79.99, "renewal": 79.99, "whois_privacy": "Paid", "url": "https://www.godaddy.com"},
                {"registrar": "Cloudflare", "first_year": 48.00, "renewal": 48.00, "whois_privacy": "Not Included", "url": "https://www.cloudflare.com"},
                {"registrar": "Porkbun", "first_year": 60.00, "renewal": 60.00, "whois_privacy": "Free", "url": "https://porkbun.com"},
                {"registrar": "IONOS", "first_year": 60.00, "renewal": 60.00, "whois_privacy": "Free with hosting", "url": "https://www.ionos.com"}
            ]
        }
        prices = pricing_data.get(tld, pricing_data[".com"])
        recommended = min(prices, key=lambda x: x["first_year"] + x["renewal"])
        return prices, recommended["registrar"]

    def check_whois(self, domain):
        try:
            w = whois.whois(domain)
            creation_date = str(w.creation_date) if w.creation_date and isinstance(w.creation_date, (str, datetime)) else "N/A"
            expiration_date = str(w.expiration_date) if w.expiration_date and isinstance(w.expiration_date, (str, datetime)) else "N/A"
            creation_date = creation_date if creation_date.isprintable() else "N/A"
            expiration_date = expiration_date if expiration_date.isprintable() else "N/A"
            whois_info = {
                "domain": domain,
                "registrar": w.registrar or "N/A",
                "creation_date": creation_date,
                "expiration_date": expiration_date,
                "name_servers": w.name_servers if w.name_servers and isinstance(w.name_servers, list) else [],
                "status": w.status if w.status and isinstance(w.status, list) else [],
                "error": None
            }
        except Exception as e:
            whois_info = {
                "domain": domain,
                "registrar": "N/A",
                "creation_date": "N/A",
                "expiration_date": "N/A",
                "name_servers": [],
                "status": [],
                "error": f"WHOIS lookup failed: {str(e)}"
            }
        return whois_info

    def check_dns(self, domain, record_type="A"):
        try:
            answers = dns.resolver.resolve(domain, record_type)
            records = [str(r) for r in answers]
            dns_info = {
                "domain": domain,
                "record_type": record_type,
                "records": records,
                "error": None
            }
        except Exception as e:
            dns_info = {
                "domain": domain,
                "record_type": record_type,
                "records": [],
                "error": str(e)
            }
        return dns_info

    def is_domain_available(self, domain):
        whois_info = self.check_whois(domain)
        if whois_info["error"] or whois_info["registrar"] == "N/A":
            return "Available"
        return "Not Available"

    def save_results(self, filename="domain_results.json"):
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=4)
        return filename

    def check_expiration(self, domain, whois_info):
        expiration_date = whois_info.get("expiration_date")
        if not expiration_date or expiration_date == "N/A":
            return {"domain": domain, "expiration_alert": "N/A", "error": "No expiration date available"}

        if isinstance(expiration_date, list):
            expiration_date = str(expiration_date[0]) if expiration_date else "N/A"
        elif isinstance(expiration_date, str) and expiration_date.startswith("[datetime.datetime"):
            try:
                date_str = expiration_date.split("datetime.datetime(")[1].split(")")[0]
                year, month, day, *_ = map(int, date_str.split(", "))
                expiration_date = f"{year}-{month:02d}-{day:02d}"
            except (IndexError, ValueError) as e:
                return {"domain": domain, "expiration_alert": "N/A", "error": f"Failed to parse expiration date: {str(e)}"}

        try:
            try:
                exp_date = datetime.strptime(expiration_date, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                exp_date = datetime.strptime(expiration_date, "%Y-%m-%d")
            return {"domain": domain, "expiration_alert": str(exp_date), "error": None}
        except ValueError as e:
            return {"domain": domain, "expiration_alert": "N/A", "error": f"Invalid expiration date format: {str(e)}"}

    def rdap_lookup(self, domain):
        try:
            response = requests.get(f"https://rdap.verisign.com/com/v1/domain/{domain}")
            rdap_data = response.json()
            return {
                "domain": domain,
                "rdap_registrar": rdap_data.get("entities", [{}])[0].get("vcardArray", [{}])[1][0][3] if rdap_data.get("entities") else "N/A",
                "rdap_status": rdap_data.get("status", []),
                "error": None
            }
        except Exception as e:
            return {"domain": domain, "rdap_registrar": "N/A", "rdap_status": [], "error": str(e)}

    def validate_dnssec(self, domain):
        try:
            dnskey_answers = dns.resolver.resolve(domain, "DNSKEY")
            ds_answers = dns.resolver.resolve(domain, "DS")
            dns.dnssec.validate(dnskey_answers, ds_answers.rrset, {domain: dnskey_answers.rrset})
            return {"domain": domain, "dnssec_valid": True, "error": None}
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return {"domain": domain, "dnssec_valid": False, "error": "DNSSEC not enabled (no DNSKEY or DS records found)"}
        except dns.dnssec.ValidationFailure:
            return {"domain": domain, "dnssec_valid": False, "error": "DNSSEC validation failed"}
        except Exception as e:
            return {"domain": domain, "dnssec_valid": False, "error": str(e)}

    def check_threat_intel(self, domain):
        if not domaintools:
            return {"domain": domain, "threat_info": None, "error": "domaintools_api library not installed"}
        
        if not DOMAINTOOLS_USERNAME or not DOMAINTOOLS_API_KEY:
            st.warning(f"Skipping threat intelligence for {domain}: DomainTools credentials missing")
            return {"domain": domain, "threat_info": None, "error": "DomainTools credentials missing"}
        
        try:
            api = domaintools.API(DOMAINTOOLS_USERNAME, DOMAINTOOLS_API_KEY)
            response = api.domain_profile(domain)
            risk_score = response.get('risk', {}).get('score', 'N/A')
            threat_info = {
                "risk_score": risk_score,
                "threat_profile": response.get('threat_profile', 'N/A')
            }
            return {"domain": domain, "threat_info": threat_info, "error": None}
        except Exception as e:
            return {"domain": domain, "threat_info": None, "error": str(e)}

    def generate_domains(self, prompt, tlds=[".com"], num_suggestions=10):
        if not genai:
            st.error("Gemini AI library not installed. Install google-generativeai to use this feature.")
            return []
        
        if not GEMINI_API_KEY:
            st.error("Gemini AI API key missing. See https://ai.google.dev for details.")
            return []
        
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel("gemini-1.5-flash")
            response = model.generate_content(
                f"Generate {num_suggestions} domain name ideas for: {prompt}, using TLDs: {', '.join(tlds)}. "
                f"Return each domain on a new line, in the format 'name.tld'."
            )
            domains = [line.strip() for line in response.text.split("\n") if line.strip() and any(line.endswith(tld) for tld in tlds)]
            results = []
            for domain in domains[:num_suggestions]:
                availability = self.is_domain_available(domain)
                if availability == "Available":
                    results.append({"domain": domain, "availability": availability})
                    self.store_search(domain, [{"domain": domain, "availability": availability}], source="Generated")
            return results
        except Exception as e:
            st.error(f"Failed to generate domains: {str(e)}")
            return []

    def manage_domains(self, domains, check_dns_types=["A", "MX", "TXT"], check_expiration=True, check_security=True):
        self.results = []
        for domain in domains:
            domain = domain.strip()
            if not domain:
                continue

            domain_results = []
            if "whois" in st.session_state.checks:
                whois_info = self.check_whois(domain)
                domain_results.append(whois_info)

            if "dns" in st.session_state.checks:
                for record_type in check_dns_types:
                    dns_info = self.check_dns(domain, record_type)
                    domain_results.append(dns_info)

            if "expiration" in st.session_state.checks and check_expiration:
                exp_info = self.check_expiration(domain, self.check_whois(domain))
                domain_results.append(exp_info)

            if "rdap" in st.session_state.checks:
                rdap_info = self.rdap_lookup(domain)
                domain_results.append(rdap_info)

            if "security" in st.session_state.checks and check_security:
                dnssec_info = self.validate_dnssec(domain)
                domain_results.append(dnssec_info)
                threat_info = self.check_threat_intel(domain)
                domain_results.append(threat_info)

            if "availability" in st.session_state.checks:
                availability = self.is_domain_available(domain)
                domain_results.append({"domain": domain, "availability": availability})

            self.results.extend(domain_results)
            self.store_search(domain, domain_results, source="User-Entered")

    def __del__(self):
        if hasattr(self, 'conn') and self.conn:
            self.conn.close()

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
        st.header("Dashboard")
        st.markdown("View all user-entered domains with registrar, expiration date, and website status. Expand each domain for detailed results. Use the Refresh button to update statuses.")
        history = manager.get_search_history(source_filter="User-Entered")
        if history:
            st.write(f"Total user-entered domains: {len(history)}")
            # Initialize status updates for all domains
            domains = [item["domain"] for item in history]
            if domains and "dashboard_status_thread_started" not in st.session_state:
                st.session_state.dashboard_status_thread_started = True
                threading.Timer(0, update_website_status, args=[manager, domains, 180]).start()
            
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
            st.dataframe(df_display, width='stretch')

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

    elif section == "Analyze Domains":
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
                    st.dataframe(df_display, width='stretch')
                else:
                    st.info("No WHOIS results available.")

            with st.expander("Expiration Check", expanded=True):
                exp_results = [r for r in st.session_state.results if "expiration_alert" in r]
                if exp_results:
                    df = pd.DataFrame(exp_results)
                    st.dataframe(df[["domain", "expiration_alert", "error"]], width='stretch')
                else:
                    st.info("No expiration check results available.")

            with st.expander("RDAP Lookup", expanded=True):
                rdap_results = [r for r in st.session_state.results if "rdap_registrar" in r]
                if rdap_results:
                    df = pd.DataFrame(rdap_results)
                    df_display = df[["domain", "rdap_registrar", "rdap_status", "error"]]
                    df_display["rdap_status"] = df_display["rdap_status"].apply(lambda x: ", ".join(x) if isinstance(x, list) else x)
                    st.dataframe(df_display, width='stretch')
                else:
                    st.info("No RDAP results available.")

            with st.expander("Security (DNSSEC & Threat Intelligence)", expanded=True):
                dnssec_results = [r for r in st.session_state.results if "dnssec_valid" in r]
                threat_results = [r for r in st.session_state.results if "threat_info" in r]
                if dnssec_results:
                    st.subheader("DNSSEC Validation")
                    df = pd.DataFrame(dnssec_results)
                    st.dataframe(df[["domain", "dnssec_valid", "error"]], width='stretch')
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
                    st.dataframe(df_display, width='stretch')
                    if any("DomainTools credentials missing" in r.get("error", "") for r in threat_results):
                        st.warning("Threat intelligence requires valid DomainTools credentials in the code. See https://www.domaintools.com/ for details.")
                else:
                    st.info("No threat intelligence results available.")

            with st.expander("Availability Check", expanded=True):
                avail_results = [r for r in st.session_state.results if "availability" in r]
                if avail_results:
                    df = pd.DataFrame(avail_results)
                    st.dataframe(df[["domain", "availability"]], width='stretch')
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

    elif section == "Generate Domains":
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
            st.dataframe(df[["domain", "availability"]], width='stretch')

    elif section == "Search History":
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
                width='stretch'
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
                width='stretch'
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

    elif section == "DNS Records":
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

    elif section == "Domain Status":
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
                threading.Timer(0, update_website_status, args=[manager, domains, 180]).start()
            
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
            st.dataframe(df_display, width='stretch')
            
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

    elif section == "Registrar Pricing":
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
                width='stretch'
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
                        width='stretch'
                    )
        else:
            st.info("No available generated domains. Generate domains in the 'Generate Domains' section.")

if __name__ == "__main__":
    main()