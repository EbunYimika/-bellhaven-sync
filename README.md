# Bellhaven Senior Living CRM sync

Daily pipeline that keeps the CRM's Bellhaven ownership picture matching
the public Bellhaven website. Nothing writes to the CRM without a human
approval in the review app.

## Run it

```bash
python scraper.py          # 35 website communities -> website_communities.json
BELLHAVEN_TOKEN=... python matcher.py   # -> proposals.json (27 proposals on 2026-11-02)
BELLHAVEN_TOKEN=... python app.py       # review queue at http://127.0.0.1:8765
```

Daily schedule: see `.github-actions.yml` (copy to
`.github/workflows/bellhaven-sync.yml`); a cron entry
`0 7 * * *` runs scraper + matcher daily and stops at the review queue.

## Matching, in brief

- Street address (normalised) is the primary key; name + city is the
  fallback (Ashtabula's CRM record is a PO Box).
- The website is scraped from the paginated list **and** the homepage,
  which features Bellhaven Meadows of Findlay, a community missing from
  the paginated list. Scraping pagination alone finds only 34 of 35.
- Care labels map to CRM types: Short-Term Rehabilitation & Nursing ->
  Skilled Nursing, Memory Support -> Memory Care.
- Billing SOP: if lifetime_revenue > 0 AND outstanding_ar > 0, never
  re-parent. Leave the old account alone except for
  chow_current_account, and create a new account under Bellhaven
  (Marietta and Tiffin). Otherwise re-parent directly (Lima, Findlay,
  Zanesville).
- Duplicates at one address are marked Inactive with
  duplicate_of_account pointing at the surviving account.
- Re-running matcher.py is safe: on 2026-11-02, after all 27 proposals were
  approved, a fresh re-run produced 0 new proposals. Decided proposals
  are recorded in decisions.json, already-applied state is recognised
  (e.g. an account already Inactive as a duplicate is not re-proposed),
  and CHOW-preserved old records are never treated as duplicates.
