#!/usr/bin/env python3
"""
Micromedex CKO JSON API Tester — CLI Tool

Architecture: ALL requests POST to one endpoint:
  http://<host>:<port>/ckoapp/librarian/PFActionId/ckoapp.JsonRequest

The RequestType field in the JSON body routes to the correct CKO service.

Usage: python cli.py <command> [options]

Commands:
  status      Test connection and show CKO data-set versions
  lookup      Resolve a drug name to a GCR code via LUSRequest (GNGCRRT/PRDGCRRT)
  validate    Validate drug code(s) for specific CKO services (ValidationRequest)
  mas-check   MAS Validate Profile — check drug codes exist in MAS database
  screen      MAS Drug Screening — full interaction/warning screening (MasRequest)
  drugnotes   Get patient-friendly DrugNotes for a drug (DrugNotesRequest)
  drugpoints  Get clinical DrugPoints monograph (DrugPointsRequest)
  raw         Send an arbitrary JSON request body from a file or stdin

Environment variables:
  CKO_URL       Required. Full endpoint URL, e.g. https://www.micromedexsolutions.com/ckoapp/librarian/PFActionId/ckoapp.JsonRequest
  CKO_USERNAME  Required. Micromedex username
  CKO_PASSWORD  Required. Micromedex password
"""

import os
import sys
import json
import argparse
import textwrap
from typing import Optional, Any, Dict

# ──────────────────────────────────────────────────────────────
# HTTP CLIENT — prefer requests, fall back to urllib
# ──────────────────────────────────────────────────────────────
try:
    import requests as _requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    import urllib.request
    import urllib.error

# ──────────────────────────────────────────────────────────────
# TERMINAL COLORS
# ──────────────────────────────────────────────────────────────
USE_COLOR = sys.stdout.isatty()

def _c(text, code):  return f"\033[{code}m{text}\033[0m" if USE_COLOR else text
def bold(t):   return _c(t, "1")
def red(t):    return _c(t, "91")
def orange(t): return _c(t, "33")
def yellow(t): return _c(t, "93")
def blue(t):   return _c(t, "94")
def green(t):  return _c(t, "92")
def gray(t):   return _c(t, "90")
def cyan(t):   return _c(t, "96")

SEV_COLOR = {
    "CONTRAINDICATED": red,
    "MAJOR": orange,
    "MODERATE": yellow,
    "MINOR": blue,
    "UNKNOWN": gray,
}

# ──────────────────────────────────────────────────────────────
# ENDPOINT CONFIGURATION
# ──────────────────────────────────────────────────────────────
class APIError(Exception):
    def __init__(self, message, status=None, data=None):
        super().__init__(message)
        self.status = status
        self.data = data


def get_endpoint() -> str:
    url = os.environ.get("CKO_URL", "").strip()
    if not url:
        raise APIError(
            "CKO_URL environment variable is not set.\n"
            "Example: export CKO_URL=https://www.micromedexsolutions.com/ckoapp/librarian/PFActionId/ckoapp.JsonRequest"
        )
    return url


def get_auth():
    """Return (username, password) tuple for HTTP Basic Auth, or (None, None)."""
    user = os.environ.get("CKO_USERNAME", "").strip()
    pwd  = os.environ.get("CKO_PASSWORD", "")
    return (user or None, pwd or None)


# ──────────────────────────────────────────────────────────────
# CORE HTTP — single POST to CKO endpoint
# ──────────────────────────────────────────────────────────────
def cko_request(body: Dict[str, Any], verbose: bool = False) -> Dict:
    """POST a CKO JSON request body to the single CKO endpoint using HTTP Basic Auth.
    Returns the parsed JSON response dict.
    """
    url = get_endpoint()
    user, pwd = get_auth()
    payload = json.dumps(body).encode("utf-8")

    if verbose:
        auth_display = f"{user}:***" if user else "(no credentials)"
        print(gray(f"POST {url}  auth={auth_display}"))
        print(gray(json.dumps(body, indent=2)))
        print()

    if HAS_REQUESTS:
        try:
            auth = (user, pwd) if user else None
            resp = _requests.post(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                auth=auth,
                timeout=30,
                verify=True
            )
            if resp.status_code == 401:
                raise APIError("Authentication failed (HTTP 401). Check CKO_USERNAME and CKO_PASSWORD.")
            if resp.status_code == 403:
                raise APIError("Access forbidden (HTTP 403). Credentials may lack permission.")
            data = resp.json()
        except _requests.exceptions.SSLError as e:
            raise APIError(f"SSL error: {e}\nTry setting verify=False if using a self-signed cert.")
        except _requests.exceptions.ConnectionError as e:
            raise APIError(f"Connection failed: {e}")
        except _requests.exceptions.Timeout:
            raise APIError("Request timed out after 30 seconds.")
        except APIError:
            raise
        except Exception as e:
            raise APIError(f"Request error: {e}")
    else:
        # urllib fallback with Basic Auth
        import base64
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        if user:
            creds = base64.b64encode(f"{user}:{pwd}".encode()).decode()
            req.add_header("Authorization", f"Basic {creds}")
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                data = json.loads(res.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise APIError("Authentication failed (HTTP 401). Check CKO_USERNAME and CKO_PASSWORD.")
            raise APIError(f"HTTP error {e.code}: {e}")
        except urllib.error.URLError as e:
            raise APIError(f"Connection failed: {e}")

    if verbose:
        print(gray("Response:"))
        print(gray(json.dumps(data, indent=2)))
        print()

    return data


def check_success(data: Dict, context: str = "") -> Dict:
    """Extract Response from CKO result, checking IS_SUCCESS."""
    resp = data.get("Response", {})
    if resp.get("IS_SUCCESS") == "FALSE":
        raise APIError(f"{context} — IS_SUCCESS: FALSE. Check drug codes or server config.")
    return resp


# ──────────────────────────────────────────────────────────────
# COMMANDS
# ──────────────────────────────────────────────────────────────

def cmd_status(args):
    """ServiceStatusRequest — test connection and show dataset versions."""
    print(f"Connecting to CKO at {get_endpoint()} ...")
    data = cko_request({"RequestType": "ServiceStatusRequest", "Request": {}}, verbose=args.verbose)
    resp = data.get("Response", {})

    if resp.get("IS_SUCCESS") != "TRUE":
        print(red("✗ Connection failed — IS_SUCCESS is not TRUE"))
        print(json.dumps(data, indent=2))
        sys.exit(1)

    print(green("✓ Connected to CKO successfully\n"))
    datasets = resp.get("DataSetList", {}).get("DataSet", [])
    if not datasets:
        print("No dataset information returned.")
        return

    print(bold("CKO Data Sets:"))
    for ds in datasets:
        dtype = ds.get("TYPE", "?")
        content_list = ds.get("ContentSetList", {}).get("ContentSet", [])
        if isinstance(content_list, dict):
            content_list = [content_list]
        print(f"\n  {cyan(dtype)}")
        for cs in content_list:
            ts  = cs.get("TIME_STAMP", "?")
            nm  = cs.get("NAME", "?")
            ver = cs.get("VERSION", "?")
            print(f"    {gray(ts)}  {nm}  v{ver}")


def cmd_lookup(args):
    """LUSRequest — resolve drug name to GCR/GFC codes."""
    lookup_type = args.type or "GNGCRRT"
    search_name = "key" if lookup_type in ("GNGCRRT", "PRDGCRRT") else "generic_name"

    body = {
        "RequestType": "LUSRequest",
        "Request": {
            "LookUpType": lookup_type,
            "SearchParameterList": {
                "OPERATOR": "OR",
                "SearchParameters": [{"NAME": search_name, "VALUE": args.query}]
            }
        }
    }

    print(f"Looking up {bold(args.query)} via {cyan(lookup_type)} ...")
    data = cko_request(body, verbose=args.verbose)
    resp = data.get("Response", {})

    if resp.get("SUCCESS") != "TRUE":
        print(red("✗ Lookup failed or drug not found."))
        if args.verbose:
            print(json.dumps(data, indent=2))
        sys.exit(1)

    records = resp.get("LookUpRecordList", [])
    header = resp.get("HEADER", "").split("|")
    size = resp.get("SIZE", 0)

    print(f"\n{green(f'Found {size} record(s)')} (showing up to {min(int(size or 0), args.limit or 20)}):\n")
    print(bold("  " + "  |  ".join(h.upper() for h in header)))
    print("  " + "-" * 80)

    shown = 0
    for item in records:
        if shown >= (args.limit or 20):
            break
        record = item.get("LookUpRecord", "")
        fields = record.split("|")
        # Highlight the first field (usually the code)
        fields_display = [cyan(fields[0])] + fields[1:] if fields else []
        print("  " + "  |  ".join(fields_display))
        shown += 1

    if shown < int(size or 0):
        print(gray(f"\n  ... and {int(size)-shown} more results."))


def cmd_validate_drug(args):
    """ValidationRequest — check which CKO services a drug code is valid for."""
    svc_map = {
        "drugpoints": "DRUGPOINTS",
        "psd": "PSD",
        "iv": "IVSCREENING",
        "labels": "WARNINGLABELS",
        "images": "IMAGESIMPRINTS",
        "drugnotes": "DRUGNOTES",
    }

    selected = args.services.split(",") if args.services else list(svc_map.keys())
    req_body: Dict[str, Any] = {"RequestType": "ValidationRequest", "Request": {}}

    for svc_key, svc_name in svc_map.items():
        req_body["Request"][svc_name] = "YES" if svc_key in selected else "NO"

    req_body["Request"]["NewDrugList"] = {
        "Drug": [{"CODE": args.code, "TYPE": args.code_type.upper()}]
    }

    print(f"Validating {bold(args.code)} ({args.code_type.upper()}) ...")
    data = cko_request(req_body, verbose=args.verbose)
    resp = data.get("Response", {})

    valid_total = resp.get("VALID_TOTAL", 0)
    invalid_total = resp.get("INVALID_TOTAL", 0)
    na_total = resp.get("NOTAPPLICABLE_TOTAL", 0)

    print(f"\n{bold('Validation Results')}  —  Valid: {green(str(valid_total))}  |  Invalid: {red(str(invalid_total))}  |  N/A: {gray(str(na_total))}\n")

    def print_drug_list(label, drugs):
        if not drugs:
            return
        print(f"  {bold(label)}:")
        for drug in drugs:
            code = drug.get("CODE", "?")
            dtype = drug.get("TYPE", "?")
            print(f"    {cyan(code)} ({dtype})")
            for svc in list(svc_map.values()):
                val = drug.get(svc, "")
                if val:
                    col = green if val == "VALID" else (red if val == "INVALID" else gray)
                    print(f"      {svc:<20} {col(val)}")
            print()

    new_drugs = resp.get("NewDrugList", {}).get("Drug", [])
    cur_drugs = resp.get("CurrentDrugList", {}).get("Drug", [])
    if isinstance(new_drugs, dict): new_drugs = [new_drugs]
    if isinstance(cur_drugs, dict): cur_drugs = [cur_drugs]

    print_drug_list("New Drugs", new_drugs)
    print_drug_list("Current Drugs", cur_drugs)


def cmd_mas_check(args):
    """MASValidationRequest — check drug codes exist in MAS database before screening."""
    new_drug_list = _parse_drug_list(args.new_drugs)
    cur_drug_list = _parse_drug_list(args.current_drugs) if args.current_drugs else []

    body: Dict[str, Any] = {"RequestType": "MASValidationRequest", "Request": {}}
    if new_drug_list:
        body["Request"]["NewDrugList"] = {"Drug": new_drug_list}
    if cur_drug_list:
        body["Request"]["CurrentDrugList"] = {"Drug": cur_drug_list}

    print(f"Validating {len(new_drug_list)} new + {len(cur_drug_list)} current drugs in MAS database ...")
    data = cko_request(body, verbose=args.verbose)
    resp = data.get("Response", {})

    warning_total = int(resp.get("WARNING_TOTAL", 0))
    if warning_total == 0:
        print(green("✓ All drugs found in MAS database — safe to run screening."))
    else:
        print(yellow(f"⚠ {warning_total} validation warning(s) — some drugs may not be in MAS database:\n"))
        warnings = resp.get("WarningList", {}).get("Warning", [])
        if isinstance(warnings, dict): warnings = [warnings]
        for w in warnings:
            print(f"  {red('•')} {w.get('WarningText','')}")


def cmd_screen(args):
    """MasRequest — full MAS drug interaction and safety screening."""
    new_drug_list = _parse_drug_list(args.new_drugs)
    cur_drug_list = _parse_drug_list(args.current_drugs) if args.current_drugs else []

    if not new_drug_list and not cur_drug_list:
        print(red("Error: provide at least one drug via --new-drugs or --current-drugs"))
        sys.exit(1)

    # Patient
    patient: Dict[str, Any] = {
        "GENDER": (args.gender or "MALE").upper(),
        "BD_YEAR": args.birth_year or "1970",
    }
    if args.birth_month: patient["BD_MONTH"] = args.birth_month
    if args.birth_day:   patient["BD_DAY"]   = args.birth_day
    patient["PREGNANT"]  = "TRUE" if args.pregnant else "FALSE"
    patient["LACTATING"] = "TRUE" if args.lactating else "FALSE"
    patient["SMOKER"]    = "TRUE" if args.smoker else "FALSE"

    # Filter
    sev = (args.severity or "MODERATE").upper()
    type_names = [
        "DRUG", "FOOD", "ETHANOL", "LAB", "TOBACCO", "ALLERGY",
        "TC_DUPLICATION", "ANTAGONISM", "INGREDIENT_DUPLICATION",
        "DISEASE", "PREGNANCY", "LACTATION", "PRECAUTION"
    ]
    if args.types:
        type_names = [t.strip().upper() for t in args.types.split(",")]

    body: Dict[str, Any] = {
        "RequestType": "MasRequest",
        "Request": {
            "CLASS": (args.cls or "PROFESSIONAL").upper(),
            "Patient": patient,
            "Filter": {
                "SEVERITY": sev,
                "TypeFilter": [{"NAME": n} for n in type_names]
            }
        }
    }
    if new_drug_list:
        body["Request"]["NewDrugList"] = {"Drug": new_drug_list}
    if cur_drug_list:
        body["Request"]["CurrentDrugList"] = {"Drug": cur_drug_list}

    print(f"Running MAS screening for {len(new_drug_list)} new + {len(cur_drug_list)} current drugs ...")
    print(f"Patient: {patient['GENDER']} born {patient['BD_YEAR']} | Filter: severity≥{sev}")
    print()

    data = cko_request(body, verbose=args.verbose)
    resp = data.get("Response", {})

    if resp.get("IS_SUCCESS") == "FALSE":
        print(red("✗ Screening failed — IS_SUCCESS: FALSE"))
        print(json.dumps(data, indent=2))
        sys.exit(1)

    # Summary
    summary = resp.get("Summary", {})
    interaction_total = summary.get("INTERACTION_TOTAL", 0)
    warning_total = summary.get("WARNING_TOTAL", 0)

    if warning_total == 0:
        print(green("✓ No warnings found for the screened drug combination."))
        return

    print(bold(f"Found {warning_total} warning(s) ({interaction_total} interactions):\n"))

    # Type summary
    type_summaries = summary.get("InteractionTypeSummaryList", {}).get("InteractionTypeSummary", [])
    if isinstance(type_summaries, dict): type_summaries = [type_summaries]
    if type_summaries:
        print(bold("  Summary by type:"))
        for ts in type_summaries:
            sev_col = SEV_COLOR.get(ts.get("MAX_SEVERITY","UNKNOWN"), gray)
            print(f"    {ts.get('TYPE','?'):<30} count={ts.get('TOTAL','?')}  max_severity={sev_col(ts.get('MAX_SEVERITY','?'))}")
        print()

    # Warnings
    warnings = resp.get("WarningList", {}).get("Warning", [])
    if isinstance(warnings, dict): warnings = [warnings]

    sev_order = {"CONTRAINDICATED": 0, "MAJOR": 1, "MODERATE": 2, "MINOR": 3, "UNKNOWN": 4}
    warnings_sorted = sorted(warnings, key=lambda w: sev_order.get(w.get("SEVERITY","UNKNOWN"), 4))

    for i, w in enumerate(warnings_sorted, 1):
        sev_val = w.get("SEVERITY", "UNKNOWN")
        sev_col = SEV_COLOR.get(sev_val, gray)
        wtype   = w.get("Type", "?")
        doc_rat = w.get("DOCUMENTATION_RATING", "")
        mon_id  = w.get("MONOGRAPH_ID", "")
        text    = w.get("WarningText", "")

        print(f"  {i:02d}. {sev_col(f'[{sev_val}]'):<30} {cyan(wtype)}")
        if doc_rat: print(f"      Documentation: {doc_rat}")
        if mon_id and mon_id != "0": print(f"      Monograph ID:   {mon_id}")
        print(f"      {textwrap.fill(text, width=80, subsequent_indent='      ')}")
        print()

    if args.json:
        print(gray("\n--- Full JSON Response ---"))
        print(json.dumps(data, indent=2))


def cmd_drugnotes(args):
    """DrugNotesRequest — patient-friendly medication instructions."""
    body = {
        "RequestType": "DrugNotesRequest",
        "Request": {
            "LANGUAGE": args.language or "English",
            "NewDrugList": {
                "Drug": [{"CODE": args.code, "TYPE": args.code_type.upper()}]
            }
        }
    }

    print(f"Fetching DrugNotes for {bold(args.code)} ({args.code_type.upper()}) in {args.language or 'English'} ...")
    data = cko_request(body, verbose=args.verbose)
    resp = data.get("Response", {})

    if resp.get("IS_SUCCESS") != "TRUE":
        print(red("✗ DrugNotes request failed."))
        print(json.dumps(data, indent=2))
        sys.exit(1)

    docs = resp.get("DocumentList", {}).get("Document", [])
    if isinstance(docs, dict): docs = [docs]

    if not docs:
        print(yellow("No DrugNotes documents returned for this drug."))
        return

    for doc in docs:
        code_val = doc.get("DRUG_CODE", "?")
        type_val = doc.get("DRUG_TYPE", "?")
        text     = doc.get("Text", "")

        print(bold(f"\n[{type_val}] {code_val}"))
        print("-" * 60)

        if args.html:
            print(text)
        else:
            # Strip basic HTML tags for plain-text output
            import re
            clean = re.sub(r'<[^>]+>', ' ', text or "")
            clean = re.sub(r'\s+', ' ', clean).strip()
            print(textwrap.fill(clean, width=80))


def cmd_drugpoints(args):
    """DrugPointsRequest — concise clinical monograph."""
    body = {
        "RequestType": "DrugPointsRequest",
        "Request": {
            "NewDrugList": {
                "Drug": [{"CODE": args.code, "TYPE": args.code_type.upper()}]
            }
        }
    }

    print(f"Fetching DrugPoints for {bold(args.code)} ({args.code_type.upper()}) ...")
    data = cko_request(body, verbose=args.verbose)
    resp = data.get("Response", {})

    if resp.get("IS_SUCCESS") != "TRUE":
        print(red("✗ DrugPoints request failed."))
        print(json.dumps(data, indent=2))
        sys.exit(1)

    print(green("✓ DrugPoints retrieved."))
    if args.json or args.verbose:
        print(json.dumps(data, indent=2))
    else:
        print(yellow("Use --json to see the full DrugPoints response."))


def cmd_raw(args):
    """Send an arbitrary JSON body from a file or stdin."""
    if args.file:
        with open(args.file) as f:
            body = json.load(f)
    else:
        print("Enter JSON request body (Ctrl+D when done):")
        raw = sys.stdin.read()
        body = json.loads(raw)

    data = cko_request(body, verbose=True)
    print(json.dumps(data, indent=2))


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────
def _parse_drug_list(drug_str: Optional[str]):
    """Parse comma-separated drug specs: CODE:TYPE or just CODE (defaults to GCR).

    Examples:
      104045                   → {CODE: 104045, TYPE: GCR}
      00056-0172-70:NDC        → {CODE: 00056-0172-70, TYPE: NDC}
      123456:GFC               → {CODE: 123456, TYPE: GFC}
    """
    if not drug_str:
        return []
    result = []
    for part in drug_str.split(","):
        part = part.strip()
        if ":" in part:
            code, dtype = part.rsplit(":", 1)
        else:
            code, dtype = part, "GCR"
        result.append({"CODE": code.strip(), "TYPE": dtype.strip().upper()})
    return result


# ──────────────────────────────────────────────────────────────
# ARGUMENT PARSER
# ──────────────────────────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(
        prog="cko-cli",
        description="Micromedex CKO JSON API Tester",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Environment variables:
          CKO_URL       Full endpoint URL (required)
                        e.g. https://www.micromedexsolutions.com/ckoapp/librarian/PFActionId/ckoapp.JsonRequest
          CKO_USERNAME  Micromedex username (required)
          CKO_PASSWORD  Micromedex password (required)

        Drug code formats:
          GCR   Numeric, e.g. 104045
          GFC   6-digit numeric, e.g. 123456
          NDC   5-4-2 dash-separated, e.g. 00056-0172-70

        Examples:
          python cli.py status
          python cli.py lookup --query warfarin --type GNGCRRT
          python cli.py screen --new-drugs "00056-0172-70:NDC" --current-drugs "55935-0084-01:NDC" --gender FEMALE --birth-year 1955
          python cli.py mas-check --new-drugs "104045:GCR,55935-0084-01:NDC"
          python cli.py drugnotes --code 123456 --code-type GFC --language Spanish
          python cli.py validate --code 00029-3211-13 --code-type NDC
        """)
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Print raw requests/responses")

    subs = parser.add_subparsers(dest="command", metavar="COMMAND")
    subs.required = True

    # status
    subs.add_parser("status", help="Test connection (ServiceStatusRequest)")

    # lookup
    p = subs.add_parser("lookup", help="Look up a drug name → GCR code (LUSRequest)")
    p.add_argument("--query", "-q", required=True, help="Drug name keyword to search for")
    p.add_argument("--type", "-t", default="GNGCRRT",
                   choices=["GNGCRRT", "PRDGCRRT", "GENERIC_NAME"],
                   help="LookUp type (default: GNGCRRT)")
    p.add_argument("--limit", type=int, default=20, help="Max results to show (default: 20)")

    # validate
    p = subs.add_parser("validate", help="Validate a drug code for CKO services (ValidationRequest)")
    p.add_argument("--code", "-c", required=True, help="Drug code, e.g. 00029-3211-13")
    p.add_argument("--code-type", default="NDC", choices=["NDC", "GFC", "GCR"],
                   help="Drug code type (default: NDC)")
    p.add_argument("--services", help="Comma-separated services to check: drugpoints,psd,iv,labels,images,drugnotes")

    # mas-check
    p = subs.add_parser("mas-check", help="MAS Validate Profile — check drug codes exist (MASValidationRequest)")
    p.add_argument("--new-drugs", required=True, metavar="CODE[:TYPE],...",
                   help="New drugs, e.g. 00056-0172-70:NDC,104045:GCR")
    p.add_argument("--current-drugs", metavar="CODE[:TYPE],...",
                   help="Current drugs the patient already takes")

    # screen
    p = subs.add_parser("screen", help="Full MAS drug screening (MasRequest)")
    p.add_argument("--new-drugs", required=True, metavar="CODE[:TYPE],...",
                   help="New drugs being prescribed, e.g. 00056-0172-70:NDC")
    p.add_argument("--current-drugs", metavar="CODE[:TYPE],...",
                   help="Current drugs patient already takes")
    p.add_argument("--gender", default="MALE", choices=["MALE","FEMALE"], help="Patient gender")
    p.add_argument("--birth-year", metavar="YYYY", help="Patient birth year")
    p.add_argument("--birth-month", metavar="M", help="Patient birth month (1-12)")
    p.add_argument("--birth-day", metavar="D", help="Patient birth day (1-31)")
    p.add_argument("--pregnant", action="store_true")
    p.add_argument("--lactating", action="store_true")
    p.add_argument("--smoker", action="store_true")
    p.add_argument("--cls", default="PROFESSIONAL",
                   choices=["PROFESSIONAL","CONSUMER"], metavar="CLASS",
                   help="Request class (default: PROFESSIONAL)")
    p.add_argument("--severity", default="MODERATE",
                   choices=["CONTRAINDICATED","MAJOR","MODERATE","MINOR"],
                   help="Minimum severity to report (default: MODERATE)")
    p.add_argument("--types", metavar="TYPE,...",
                   help="Comma-separated interaction types (default: all)")
    p.add_argument("--json", action="store_true", help="Print full JSON response")

    # drugnotes
    p = subs.add_parser("drugnotes", help="Get patient DrugNotes (DrugNotesRequest)")
    p.add_argument("--code", "-c", required=True, help="Drug code")
    p.add_argument("--code-type", default="GFC", choices=["GFC","NDC"],
                   help="Drug code type (default: GFC)")
    p.add_argument("--language", default="English", help="Language (default: English)")
    p.add_argument("--html", action="store_true", help="Output raw HTML instead of plain text")

    # drugpoints
    p = subs.add_parser("drugpoints", help="Get DrugPoints clinical monograph (DrugPointsRequest)")
    p.add_argument("--code", "-c", required=True, help="Drug code")
    p.add_argument("--code-type", default="NDC", choices=["NDC","GFC"],
                   help="Drug code type (default: NDC)")
    p.add_argument("--json", action="store_true", help="Print full JSON response")

    # raw
    p = subs.add_parser("raw", help="Send a raw JSON request from a file or stdin")
    p.add_argument("--file", "-f", help="Path to JSON file containing the request body (else reads stdin)")

    return parser


# ──────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────
COMMAND_MAP = {
    "status":     cmd_status,
    "lookup":     cmd_lookup,
    "validate":   cmd_validate_drug,
    "mas-check":  cmd_mas_check,
    "screen":     cmd_screen,
    "drugnotes":  cmd_drugnotes,
    "drugpoints": cmd_drugpoints,
    "raw":        cmd_raw,
}

def main():
    parser = build_parser()
    args = parser.parse_args()

    fn = COMMAND_MAP.get(args.command)
    if not fn:
        parser.print_help()
        sys.exit(1)

    try:
        fn(args)
    except APIError as e:
        print(red(f"\n✗ Error: {e}"))
        if args.verbose and e.data:
            print(json.dumps(e.data, indent=2))
        sys.exit(1)
    except KeyboardInterrupt:
        print()
        sys.exit(0)


if __name__ == "__main__":
    main()
