"""
cybops — Cyber Operations tools for the BulkClix MCP server.

Exposes all Shodan API tools (DNS, search, scan, network alerts, misc) as well as
Kali Linux penetration testing CLI wrappers (nmap, gobuster, nikto, sqlmap, hydra).
"""

# --- Shodan tools ---
from tools.cybops.dns import shodan_dns_resolve, shodan_dns_reverse, shodan_domain_info
from tools.cybops.search import shodan_search, shodan_count, shodan_search_tokens
from tools.cybops.scan import shodan_scan, shodan_scan_status, shodan_scans
from tools.cybops.network import shodan_create_alert, shodan_alerts, shodan_delete_alert
from tools.cybops.misc import (
    shodan_host,
    shodan_info,
    shodan_honeyscore,
    shodan_ports,
    shodan_protocols,
    shodan_services,
    shodan_myip,
)

# --- Kali Linux tools ---
from tools.cybops.kali import (
    kali_nmap,
    kali_gobuster,
    kali_nikto,
    kali_sqlmap,
    kali_hydra,
)

__all__ = [
    # Shodan — DNS
    "shodan_dns_resolve",
    "shodan_dns_reverse",
    "shodan_domain_info",
    # Shodan — Search
    "shodan_search",
    "shodan_count",
    "shodan_search_tokens",
    # Shodan — Scan
    "shodan_scan",
    "shodan_scan_status",
    "shodan_scans",
    # Shodan — Network Alerts
    "shodan_create_alert",
    "shodan_alerts",
    "shodan_delete_alert",
    # Shodan — Misc
    "shodan_host",
    "shodan_info",
    "shodan_honeyscore",
    "shodan_ports",
    "shodan_protocols",
    "shodan_services",
    "shodan_myip",
    # Kali Linux
    "kali_nmap",
    "kali_gobuster",
    "kali_nikto",
    "kali_sqlmap",
    "kali_hydra",
]
