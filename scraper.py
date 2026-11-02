"""Scrape every Bellhaven community from the public website.
Usage: python scraper.py  -> writes website_communities.json
No API token needed; this reads only the public site.
"""
import urllib.request, re, json, html, sys
BASE = "https://analyst-assessment-production.up.railway.app"

def get(url):
    with urllib.request.urlopen(url) as r:
        return r.read().decode()

def main():
    slugs = []
    # Homepage features one community not in the paginated list; crawl it too.
    home = get(f"{BASE}/")
    slugs += re.findall(r'href="/communities/([^"]+)"', home)
    page = 1
    while True:
        txt = get(f"{BASE}/communities?page={page}")
        found = re.findall(r'href="/communities/([^"]+)"', txt)
        found = [s for s in found if s not in slugs]
        if not found:
            break
        slugs += found
        page += 1
        if page > 10:
            break
    print(f"{len(slugs)} community pages found")
    out = []
    for s in slugs:
        txt = get(f"{BASE}/communities/{s}")
        name = html.unescape(re.search(r"<h1>(.*?)</h1>", txt).group(1))
        addr = re.search(r"<dt>Address</dt><dd>(.*?)</dd>", txt, re.S).group(1)
        addr = html.unescape(addr.replace("<br>", "\n"))
        street, cityline = [x.strip() for x in addr.split("\n")]
        m = re.match(r"(.+),\s*([A-Z]{2})\s+(\d{5})", cityline)
        city, state, zipc = m.groups()
        badges = [html.unescape(b) for b in re.findall(r'class="badge">([^<]+)</span>', txt)]
        phone_m = re.search(r"<dt>Phone</dt><dd>(.*?)</dd>", txt)
        out.append({"slug": s, "name": name, "street": street, "city": city,
                    "state": state, "zip": zipc, "care_offerings": badges,
                    "phone": phone_m.group(1) if phone_m else "",
                    "url": f"{BASE}/communities/{s}"})
    out.sort(key=lambda x: x["name"])
    json.dump(out, open("website_communities.json", "w"), indent=2)
    for c in out:
        print(f"{c['name']} | {c['street']}, {c['city']}, {c['state']} {c['zip']} | {', '.join(c['care_offerings'])}")
if __name__ == "__main__":
    main()
