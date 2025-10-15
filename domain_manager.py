import whois
import dns.resolver
import dns.dnssec
import dns.exception
import json
import time  
import requests
from datetime import datetime, timedelta
import pandas as pd
import sqlite3
import streamlit as st
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
            # Try resolving A record (IPv4 address)
            answers = dns.resolver.resolve(domain, 'A', raise_on_no_answer=False)
            if answers:
                return {
                    "status": "Live",
                    "status_code": None,  # No HTTP status
                    "error": None,
                    "last_checked": datetime.now().isoformat(),
                    "method": "DNS"
                }
            else:
                return {
                    "status": "Not Live",
                    "status_code": None,
                    "error": "No A record found",
                    "last_checked": datetime.now().isoformat(),
                    "method": "DNS"
                }
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return {
                "status": "Not Live",
                "status_code": None,
                "error": "Domain does not resolve (NXDOMAIN or no answer)",
                "last_checked": datetime.now().isoformat(),
                "method": "DNS"
            }
        except dns.resolver.DNSException as e:
            return {
                "status": "Not Live",
                "status_code": None,
                "error": f"DNS lookup failed: {str(e)}",
                "last_checked": datetime.now().isoformat(),
                "method": "DNS"
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
            model = genai.GenerativeModel("gemini-2.0-flash")
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