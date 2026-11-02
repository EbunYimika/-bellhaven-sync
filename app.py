"""Bellhaven review app (stdlib only, no dependencies).
Run:  BELLHAVEN_TOKEN=... python app.py
Then open http://127.0.0.1:8765
- Lists every proposal from proposals.json with its evidence and the
  current CRM values for that account.
- Approve writes to the CRM through the API; Reject writes nothing.
- Decisions are saved to decisions.json, so a re-run of matcher.py does
  not re-propose anything already decided (approved or rejected).
- CHOW pairs are linked: approving either the old-account link or the
  new-account create approves both, in the safe order (create first,
  then set chow_current_account on the old account to the new id).
"""
import json, os, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

BASE = "https://analyst-assessment-production.up.railway.app"
TOKEN = os.environ.get("BELLHAVEN_TOKEN", "")

def load_json(name, default):
    try:
        return json.load(open(name))
    except FileNotFoundError:
        return default

def save_json(name, data):
    json.dump(data, open(name, "w"), indent=2)

def api(method, path, body=None):
    req = urllib.request.Request(
        BASE + path, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body is not None else None)
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r) if r.headers.get_content_type() == "application/json" else {}
    except urllib.error.HTTPError as e:
        return {"error": e.read().decode()[:500], "status": e.code}

def proposals():
    props = load_json("proposals.json", [])
    dec = load_json("decisions.json", {})
    crm = {a["account_id"]: a for a in load_json("crm_accounts.json", [])}
    for p in props:
        p["decision"] = dec.get(p["id"], {}).get("decision", "pending")
        p["current"] = crm.get(p["account_id"]) if p["account_id"] else None
    return props

def chow_pair(props, p):
    """Return (link_proposal, create_proposal) for a CHOW website, if any."""
    if p["kind"] in ("chow_link_old", "create_account") and p["website_name"]:
        links = [x for x in props if x["website_name"] == p["website_name"] and x["kind"] == "chow_link_old"]
        creates = [x for x in props if x["website_name"] == p["website_name"] and x["kind"] == "create_account"
                   and "CHOW replacement" in json.dumps(x["changes"])]
        if links and creates:
            return links[0], creates[0]
    return None, None

def apply_proposal(p, props, dec):
    link, create = chow_pair(props, p)
    if link and create:
        # Safe order: create first, then link the old account to it.
        if dec.get(create["id"], {}).get("decision") != "approved":
            res = api("POST", "/api/v1/accounts", create["changes"])
            if "error" in res:
                return res
            new_id = res.get("account_id") or res.get("data", {}).get("account_id")
            dec[create["id"]] = {"decision": "approved", "result_account_id": new_id, "api_result": res}
        new_id = dec[create["id"]].get("result_account_id")
        changes = {k: (new_id if v == "__NEW_ACCOUNT_ID__" else v) for k, v in link["changes"].items()}
        res = api("PATCH", f"/api/v1/accounts/{link['account_id']}", changes)
        dec[link["id"]] = {"decision": "approved", "api_result": res}
        return {"chow_new_account_id": new_id, "link_result": res}
    if p["kind"] == "create_account":
        res = api("POST", "/api/v1/accounts", p["changes"])
        new_id = res.get("account_id") or res.get("data", {}).get("account_id")
        dec[p["id"]] = {"decision": "approved", "result_account_id": new_id, "api_result": res}
        return res
    res = api("PATCH", f"/api/v1/accounts/{p['account_id']}", p["changes"])
    dec[p["id"]] = {"decision": "approved", "api_result": res}
    return res

class H(BaseHTTPRequestHandler):
    def _send(self, body, ctype="text/html"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(200); self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        if self.path == "/api/proposals":
            return self._send(json.dumps(proposals()), "application/json")
        props = proposals()
        rows = ""
        for p in props:
            cur = p["current"]
            cur_txt = (f"{cur['name']} | {cur['billing_street']}, {cur['billing_city']} {cur['billing_zip']} | "
                       f"parent: {cur['parent_name'] or 'none'} | status: {cur['status']} | "
                       f"revenue: ${cur['lifetime_revenue']} AR: ${cur['outstanding_ar']}") if cur else "New account (no current CRM record)"
            btns = (f'<form method="post" action="/approve?id={p["id"]}" style="display:inline"><button>Approve</button></form> '
                    f'<form method="post" action="/reject?id={p["id"]}" style="display:inline"><button>Reject</button></form>') \
                   if p["decision"] == "pending" else f"<b>{p['decision'].upper()}</b>"
            rows += (f"<tr><td>{p['id']}</td><td>{p['kind']}</td><td>{p['website_name'] or '—'}</td>"
                     f"<td>{cur_txt}</td><td><pre>{json.dumps(p['changes'], indent=1)}</pre></td>"
                     f"<td>{p['evidence']}</td><td>{btns}</td></tr>")
        pending = sum(1 for p in props if p["decision"] == "pending")
        self._send(f"""<html><head><title>Bellhaven review queue</title>
        <style>body{{font-family:Verdana,sans-serif;margin:24px}} table{{border-collapse:collapse}} td,th{{border:1px solid #ccc;padding:8px;vertical-align:top}} pre{{white-space:pre-wrap}}</style></head>
        <body><h1>Bellhaven review queue</h1><p>{pending} pending of {len(props)} proposals. Nothing writes to the CRM until you click Approve.</p>
        <table><tr><th>ID</th><th>Kind</th><th>Website location</th><th>Current CRM record</th><th>Proposed change</th><th>Evidence</th><th>Decision</th></tr>{rows}</table></body></html>""")
    def do_POST(self):
        q = parse_qs(urlparse(self.path).query)
        pid = q.get("id", [None])[0]
        props = proposals(); dec = load_json("decisions.json", {})
        p = next((x for x in props if x["id"] == pid), None)
        if not p:
            return self._send("Unknown proposal", "text/plain")
        if self.path.startswith("/approve"):
            res = apply_proposal(p, props, dec)
            save_json("decisions.json", dec)
            self._send(f"Approved {pid}: {json.dumps(res)}", "text/plain")
        elif self.path.startswith("/reject"):
            dec[pid] = {"decision": "rejected"}
            save_json("decisions.json", dec)
            self._send(f"Rejected {pid}: nothing written to the CRM.", "text/plain")
        else:
            self._send("Unknown action", "text/plain")

if __name__ == "__main__":
    if not TOKEN:
        print("Set BELLHAVEN_TOKEN first.")
        raise SystemExit(1)
    print("Review app at http://127.0.0.1:8765")
    HTTPServer(("127.0.0.1", 8765), H).serve_forever()
