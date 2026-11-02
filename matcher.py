"""Match website communities to CRM accounts and propose reviewable changes.
Rules (see README/writeup for the full reasoning):
- Street address (normalised) is the primary key; name+city is the fallback
  (Ashtabula uses a PO Box in the CRM, so street cannot match there).
- A website location's survivor is the CRM account at that address whose
  parent is Bellhaven, or whose name matches the website name. Other CRM
  accounts at the same address are duplicates of the survivor.
- If no survivor exists at an address, the location has no CRM account yet:
  propose creating one under Bellhaven. Do NOT guess a survivor among
  unrelated accounts at the same address (Kettering) or in the same city
  at a different address (Union Square).
- Parent moves follow the billing SOP exactly: if lifetime_revenue > 0 AND
  outstanding_ar > 0, do NOT re-parent; leave the old account alone except
  for chow_current_account, and create a new account under Bellhaven.
  Otherwise re-parent the existing account directly.
- Website care labels map to CRM care types: Short-Term Rehabilitation &
  Nursing -> Skilled Nursing, Memory Support -> Memory Care. Those are
  equivalents, not changes.
- Bellhaven-parent accounts matched to no website location are proposed
  Inactive (not on the current website), with the evidence stated.
Usage: BELLHAVEN_TOKEN=... python matcher.py
  Reads website_communities.json and crm_accounts.json (fetched live if
  BELLHAVEN_TOKEN is set, otherwise uses the local snapshot).
  Writes proposals.json. Nothing writes to the CRM here.
"""
import json, re, os, urllib.request

BELLHAVEN_PARENT_ID = "0015QAPLGS3FVYEEEM"
BELLHAVEN_PARENT_NAME = "Bellhaven Senior Living (Parent Account)"
BASE = "https://analyst-assessment-production.up.railway.app"
CARE_MAP = {"Short-Term Rehabilitation & Nursing": "Skilled Nursing",
            "Memory Support": "Memory Care", "Assisted Living": "Assisted Living"}

def norm_street(s):
    s = s.lower()
    for a, b in [("northwest", "nw"), ("northeast", "ne"), ("southwest", "sw"), ("southeast", "se"),
                 ("north", "n"), ("south", "s"), ("east", "e"), ("west", "w"),
                 ("avenue", "ave"), ("boulevard", "blvd"), ("street", "st"), ("road", "rd"),
                 ("drive", "dr"), ("lane", "ln"), ("parkway", "pkwy")]:
        s = re.sub(rf"\b{a}\b", b, s)
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def norm_name(s):
    s = s.lower().strip()
    if s.startswith("the "):
        s = s[4:]
    s = s.replace("healthcare", "health care").replace("centre", "center")
    s = re.sub(r"[^a-z0-9 ]", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def fetch_crm():
    token = os.environ.get("BELLHAVEN_TOKEN", "")
    if not token:
        return json.load(open("crm_accounts.json"))
    out, page = [], 1
    while True:
        req = urllib.request.Request(
            f"{BASE}/api/v1/accounts?limit=200&page={page}",
            headers={"Authorization": f"Bearer {token}"})
        d = json.load(urllib.request.urlopen(req))
        out += d["data"]
        if page * 200 >= d["total"]:
            break
        page += 1
    json.dump(out, open("crm_accounts.json", "w"), indent=2)
    return out

def main():
    web = json.load(open("website_communities.json"))
    crm = fetch_crm()
    by_id = {a["account_id"]: a for a in crm}
    proposals, matched_crm_ids = [], set()

    def add(kind, account_id, website, changes, evidence):
        proposals.append({"id": f"P{len(proposals)+1:02d}", "kind": kind,
                          "account_id": account_id, "website_name": website["name"] if website else None,
                          "changes": changes, "evidence": evidence, "status": "pending"})

    for w in web:
        ns = norm_street(w["street"])
        at_addr = [a for a in crm if norm_street(a["billing_street"]) == ns]
        # Fallback: exact name + same city (Ashtabula PO Box case)
        if not at_addr:
            at_addr = [a for a in crm if norm_name(a["name"]) == norm_name(w["name"])
                       and a["billing_city"].lower() == w["city"].lower()]
        survivors = [a for a in at_addr
                     if a["parent_id"] == BELLHAVEN_PARENT_ID or norm_name(a["name"]) == norm_name(w["name"])]
        # Sole account at an address is that facility's record, even if its
        # name/parent are stale (e.g. Zanesville, previously Cedar Trail).
        # With several accounts and no Bellhaven/name match (Kettering), do
        # not guess: that case falls through to create_account below.
        if not survivors and len(at_addr) == 1:
            survivors = at_addr
        # Owosso: two identical Bellhaven copies; keep the one whose street
        # is written exactly as on the website, mark the other duplicate.
        if len(survivors) > 1:
            exact = [a for a in survivors if a["billing_street"] == w["street"]]
            if exact:
                survivors = [exact[0]]
        if not survivors:
            add("create_account", None, w,
                {"name": w["name"], "parent_id": BELLHAVEN_PARENT_ID,
                 "billing_street": w["street"], "billing_city": w["city"],
                 "billing_state": w["state"], "billing_zip": w["zip"],
                 "care_type": CARE_MAP.get(w["care_offerings"][0], w["care_offerings"][0]),
                 "phone": w["phone"],
                 "note": f"Created from Bellhaven website ({w['url']}); care offerings: {', '.join(w['care_offerings'])}."},
                f"No CRM account at {w['street']}, {w['city']} matches this website location by name or Bellhaven parent. "
                f"Other accounts at this address/city, if any, are left untouched because they cannot be confidently identified as this facility.")
            continue
        surv = survivors[0]
        matched_crm_ids.add(surv["account_id"])
        # Duplicate copies at the same address
        for other in at_addr:
            if other["account_id"] != surv["account_id"]:
                # CHOW-preserved old records are not duplicates: they stay
                # Active under their old parent, linked to the new account.
                if other["chow_current_account"]:
                    matched_crm_ids.add(other["account_id"])
                    continue
                if other["status"] == "Inactive" and other["duplicate_of_account"] == surv["account_id"]:
                    matched_crm_ids.add(other["account_id"])
                    continue
                matched_crm_ids.add(other["account_id"])
                add("mark_duplicate", other["account_id"], w,
                    {"status": "Inactive", "duplicate_of_account": surv["account_id"],
                     "note": f"Duplicate of {surv['name']} ({surv['account_id']}) at the same address. Website location is {w['name']}."},
                    f"Same normalised street address as the website location and as the surviving account {surv['name']}, "
                    f"but a different name/parent ({other['name']}, {other['parent_name'] or 'no parent'}).")
        # Survivor fixes
        changes, ev = {}, []
        if surv["parent_id"] != BELLHAVEN_PARENT_ID:
            if surv["lifetime_revenue"] > 0 and surv["outstanding_ar"] > 0:
                # CHOW: do not touch the old account's parent; create a new one
                # and link the old one to it. Handled as two proposals below.
                add("chow_link_old", surv["account_id"], w,
                    {"chow_current_account": "__NEW_ACCOUNT_ID__"},
                    f"Parent must change from {surv['parent_name']} to Bellhaven, but lifetime_revenue=${surv['lifetime_revenue']} "
                    f"and outstanding_ar=${surv['outstanding_ar']} (both > 0), so billing SOP forbids re-parenting. "
                    f"The old account is preserved and linked to the new account created below.")
                add("create_account", None, w,
                    {"name": w["name"], "parent_id": BELLHAVEN_PARENT_ID,
                     "billing_street": w["street"], "billing_city": w["city"],
                     "billing_state": w["state"], "billing_zip": w["zip"],
                     "care_type": CARE_MAP.get(w["care_offerings"][0], w["care_offerings"][0]),
                     "phone": surv["phone"],
                     "note": f"CHOW replacement for {surv['name']} ({surv['account_id']}), whose parent was {surv['parent_name']}. "
                              f"Created from Bellhaven website ({w['url']})."},
                    f"CHOW replacement for {surv['name']}: revenue and AR history stay on the old account, so a new Bellhaven account is created instead of re-parenting.")
                matched_crm_ids.add(surv["account_id"])
                continue
            changes["parent_id"] = BELLHAVEN_PARENT_ID
            ev.append(f"Parent is {surv['parent_name'] or 'none'}, website shows it as a Bellhaven community; "
                      f"revenue=${surv['lifetime_revenue']}, AR=${surv['outstanding_ar']}, so direct re-parenting is allowed (AR is zero).")
        if norm_name(surv["name"]) != norm_name(w["name"]):
            # Rename only when the normalised names genuinely differ.
            # Punctuation, leading "The", and Centre/Center or
            # Healthcare/Health Care spelling variants are not proposed
            # as changes, to keep the queue free of cosmetic noise.
            changes["name"] = w["name"]
            ev.append(f"CRM name '{surv['name']}' differs from website name '{w['name']}' at the same address.")
        if norm_street(surv["billing_street"]) != ns:
            changes["billing_street"] = w["street"]
            ev.append(f"CRM street is '{surv['billing_street']}', website street is '{w['street']}'.")
        if surv["billing_zip"] != w["zip"]:
            changes["billing_zip"] = w["zip"]
            ev.append(f"CRM zip is {surv['billing_zip']}, website zip is {w['zip']} (same street and city).")
        if changes:
            kind = "reparent" if "parent_id" in changes else "update_fields"
            add(kind, surv["account_id"], w, changes, " ".join(ev))

    # Bellhaven-parent accounts matched to no website location
    for a in crm:
        if a["parent_id"] == BELLHAVEN_PARENT_ID and a["account_id"] not in matched_crm_ids and a["status"] != "Inactive":
            add("mark_inactive_not_on_website", a["account_id"], None,
                {"status": "Inactive",
                 "note": f"Not on the current Bellhaven website (no website community in {a['billing_city']}, {a['billing_state']}, and no community at this address). Verify closure/sale before relying on this record."},
                f"Bellhaven-parent account with no matching website community: {a['name']}, {a['billing_street']}, {a['billing_city']}. "
                f"Lifetime revenue ${a['lifetime_revenue']}, AR ${a['outstanding_ar']} are preserved on the record; only its status changes.")

    # Never re-propose an already-decided proposal, even if the CRM state
    # alone would still suggest it (e.g. a rejected proposal).
    try:
        _dec = json.load(open("decisions.json"))
        _decided_keys = set()
        _old = json.load(open("proposals.json")) if os.path.exists("proposals.json") else []
        _old_by_id = {x["id"]: x for x in _old}
        for _pid, _d in _dec.items():
            _o = _old_by_id.get(_pid)
            if _o:
                _decided_keys.add((_o["kind"], _o["account_id"], _o["website_name"]))
        proposals = [x for x in proposals if (x["kind"], x["account_id"], x["website_name"]) not in _decided_keys]
    except Exception:
        pass
    json.dump(proposals, open("proposals.json", "w"), indent=2)
    from collections import Counter
    print(f"{len(proposals)} proposals: {Counter(p['kind'] for p in proposals)}")
    for p in proposals:
        print(f"{p['id']} {p['kind']} {p['account_id']} | {p['website_name']} | {p['changes']}")

if __name__ == "__main__":
    main()
