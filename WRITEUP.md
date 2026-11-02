# Bellhaven CRM sync: writeup

## Matching approach

I scraped all 35 Bellhaven communities from the public website and compared them with 121 CRM accounts. Street address, normalised for direction and suffix abbreviations, was the primary match key. Name plus city was the fallback, which mattered for Ashtabula, where the CRM record holds a PO Box instead of a street address. Scraping the paginated community list alone finds only 34 communities. The homepage features a 35th, Bellhaven Meadows of Findlay, so the scraper also crawls homepage links.

Website care labels were mapped to CRM types rather than treated as mismatches: Short-Term Rehabilitation and Nursing to Skilled Nursing, and Memory Support to Memory Care. Phone numbers were not used as a match key, because website and CRM phones did not line up consistently. Spelling-only name variants, such as Centre and Center, were not proposed as changes, to keep the review queue free of cosmetic noise.

This produced 27 proposals, all reviewed and approved: 7 new accounts, 3 direct re-parents to Bellhaven, 7 renames or field fixes, 5 duplicates marked inactive with duplicate_of_account pointing at the survivor, and 3 Bellhaven-parent accounts no longer on the website marked inactive. A fresh re-run after approval produced 0 new proposals.

## The billing rule and the judgment calls

Marietta and Tiffin both had revenue history and outstanding AR, so they were not re-parented. Instead, a new Bellhaven account was created for each, and the old account was linked to it with chow_current_account, leaving the old parent, revenue, and AR untouched. Lima, Findlay, and Zanesville had no outstanding AR, so they were re-parented directly.

Where the data could not confidently pick a survivor, I did not guess. Kettering has three different accounts at the same address and none under Bellhaven, so a new Bellhaven account was created and the others were left alone. Union Square has a same-city account at a different address under another parent, so it was treated as a different facility and a new account was created. Sandusky was marked inactive rather than Needs Review, because it is not on the website and a Millstone account sits at the same address, which looks like a sale; its revenue and AR history remain on the record.

## How I used AI tools

I used an AI assistant throughout, as a working partner rather than an autopilot. It helped explore the API, write the scraper, matcher, and review app, and check each proposal against its evidence. Every write to the CRM went through the review app only after a human approval, and every approved change was then verified by reading the account back from the API. No LLM calls are inside the pipeline itself.

## What I would build next

First, I would add a second reviewer check for inactive and CHOW cases, since those are the hardest to undo. Next, I would track website changes over time, so a community disappearing from the site for one day does not immediately inactivate a record. Finally, I would add contact-level matching, so administrator and phone changes from the website can be proposed with the same evidence and approval flow.
