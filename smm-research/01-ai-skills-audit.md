# 01 — Installed SMM Skills Audit

Observed: 2026-10-27. Scope: Facebook/Instagram SMM research for the "Study in Dubai — Job Guarantee or 50% Fee Back" campaign.
No tools were installed, no paid API was called, no ad account or page was connected or modified.

## 1. What is installed and relevant

| Skill / tool | Source | Relevance | Needs | Used in this research? |
|---|---|---|---|---|
| `competitor-ad-teardown` | kelpi-ai/meta-ads-skills (project `.claude/skills`, pinned in `skills-lock.json`, uncommitted) | Meta Ad Library angle mining (proven angle = 3+ variations or 90+ days running) | Public Ad Library only | **Yes**: its doctrine (variation count + longevity as the only honest signals) drives `03`, `07` and `09` |
| `angle-writer`, `pain-to-promise`, `copy-formulas` | kelpi-ai | Angle and copy generation | none | **Yes**: method for `12` concepts (different who / pain / promise per angle; PAS/BAB formulas) |
| `audience-builder` | kelpi-ai | Interest/lookalike research | Meta Ads MCP (not connected) | Doctrine only (broad-first; interest categories retired Jan 2026, per skill text). No live size estimates |
| `buyer-language-miner` | kelpi-ai | Verbatim buyer language | Public sources | Partly: comment questions from organic research (`04`, `05`) |
| `lead-gen-builder` | kelpi-ai | Instant-form design with qualifying friction | Meta Ads MCP for creation | Method only (form questions in `10`); nothing created |
| `media-buyer`, `creative-director`, `budget-pacer`, `daily-auditor`, `performance-analyst`, `fatigue-detector`, `pixel-conversions`, `catalog-commerce` | kelpi-ai | Account build/optimisation | Meta Ads MCP with **write** access | **Not used**: no account connected; out of scope (no live changes). `budget-pacer` 20%-step scaling rule referenced in `13` |
| `facebook-skills:*` (fb-hook-extractor, fb-content-planner, fb-post-writer, fb-humanizer, fb-audience-insights, fb-page-optimizer, fb-engagement-drafter, fb-repurposer) | plugin, names match sergebulaev/facebook-skills | Organic FB post writing/planning | Publora API to publish, Apify for page stats (both paid/external) | Method only for `11` calendar and post drafts. **Nothing published** |
| `facebook-marketing` | user skill | Page posts via Publora | Publora API | Not used (publishing excluded) |
| `marketing-skills:*` (ad-creative, social, competitors, customer-research, video, marketing-psychology, offers) | marketingskills plugin 2.12.2 | General frameworks | none | Frameworks informed `08`, `10` |
| `dataslayer-marketing-skills:*` | plugin | Pulls GA4/Ads/Meta data via Dataslayer MCP | Dataslayer MCP + account | Not used: no EduSphere ad account data exists yet |
| `browser-use` (CDP) | user skill | Drive local Chrome | Chrome remote debugging | **Blocked**: remote debugging not enabled (`DevToolsActivePort not found`) |
| Python Playwright + Chromium (local) | already on machine | Headless browser | none | **Yes**: primary collector for the public Meta Ad Library (JSON embedded in page + GraphQL responses) |
| WebSearch / WebFetch | Claude Code | Public web | none | **Yes**: offer terms, regulations, organic research |
| MCP servers | Canva, Figma, Hugging Face (unauthenticated), Gmail, Postman, Shopify, Claude Docs; `definite` failed to connect | none relevant to Meta research | n/a | Not used |

**No Meta Ads MCP / Meta Marketing API / Ad Library API token is connected.** That matters less than it seems: the official Ad Library API
returns only political/issue ads and ads delivered in the EU/UK, so it would not return ordinary commercial ads shown only in India anyway.

## 2. Collector actually built and used (no install)

`scratchpad/adlib/scrape2.py`: headless Chromium opens
`facebook.com/ads/library/?active_status=active&ad_type=all&country=IN&q=<term>&search_type=keyword_unordered`, scrolls 10×,
and parses the ad objects Meta embeds in the page (`ad_archive_id`, `page_name`, `publisher_platform`, `start_date`, `collation_count`,
`snapshot.body/title/cta_type/display_format/link_url/page_like_count`, cards, images, videos). Logged out, no login wall was hit.
Fields Meta returns as null for India commercial ads (`spend`, `reach_estimate`, `impressions`) were recorded as "not disclosed".

## 3. Missing capabilities and gaps

| Gap | Effect | Free fix | Paid fix (needs approval) |
|---|---|---|---|
| Instagram organic feed is login-walled for anonymous visitors | Post-level IG data partial (see `04`) | Enable a logged-in, human-supervised browser session (user's own account, read-only) | Apify Instagram scraper (pay-per-result) |
| Video ad content (audio, pacing, subtitles) | Only cover frames + metadata analysed (see `07`) | Download `video_sd_url` and transcribe locally (e.g. Whisper on CPU) | Hosted transcription API |
| Ad delivery data (spend, reach, demographics) | Not available for India commercial ads | none | none: Meta does not publish it |
| Chrome CDP for `browser-use` | Could not use the logged-in browser | User enables `chrome://inspect/#remote-debugging` | n/a |
| Meta Ads MCP | Audience size estimates, form/campaign drafts impossible | n/a | Pipeboard / Meta official MCP; **write scopes must stay off** for this phase |

## 4. Recommendations

1. **Keep** the installed kelpi-ai set; commit `skills-lock.json` + `.claude/skills/*` only if the team wants them versioned (currently uncommitted).
2. **Optional add:** `Hiberius/competitor-ad-intelligence` (MIT, no network code, scores a CSV you supply) can re-score `03-facebook-ad-library-analysis.csv` on longevity/variation/recency. Low risk, but not required: `09` already scores on the same signals.
3. **Do not install** `tenfoldmarc/ad-spy-skill` (no licence, runs an unpinned `npx` package), `vnklab/claude-smm-skills` (no licence on GitHub, prompt-only), `mardab96/meta-ads-skills` (own-account exports only).
4. **Apify-based** skills (apify/awesome-skills, sergebulaev/facebook-skills page scraping) are a **paid** fallback for Instagram/Facebook organic coverage. Ask for approval before any use.

---

## Appendix — Candidate repository verification (read-only, 2026-10-27)

Verified with `gh api` and raw file reads only; nothing cloned, installed or executed.


Observed 2026-10-27. Read-only: `gh api repos/<r>`, `gh api repos/<r>/commits`, `gh api repos/<r>/git/trees/main?recursive=1`, and `curl` of raw.githubusercontent.com files. Nothing was installed, cloned or run. Classification per project constitution: all of this is UNVERIFIED third-party evidence, not approval.

Task context: India-market research of "Study in Dubai" education advertisers on FB/IG (Ad Library + public organic). Already in place: 16 kelpi-ai skills, plus a working headless-Playwright scraper of the public Ad Library.

Note on the official Meta Ad Library API: it returns only political/issue ads and ads delivered in the EU/UK. Ordinary commercial ads shown only in India are visible only through the public Ad Library web UI. None of the 8 repos uses that API for commercial ads.

### Summary table

| Repo | Exists | License (SPDX) | Last commit (default branch) | Stars | Data source | Paid? | Verdict |
|---|---|---|---|---|---|---|---|
| apify/awesome-skills | Yes, not archived | Apache-2.0 | 2026-09-22 (1eb0cd0c) | 282 | Apify actors (`apify/facebook-ads-scraper`, `brilliant_gum/facebook-ads-library-scraper`, ...) | Yes, Apify pay-per-result | OPTIONAL (only as a paid fallback) |
| tenfoldmarc/ad-spy-skill | Yes, not archived | none (all rights reserved) | 2026-09-09 (232a2534) | 0 | Public Ad Library scraping through `npx agent-browser` | No (OpenAI Whisper API optional) | NOT RECOMMENDED |
| realbrianhanson/fb-ad-intel | Yes, not archived | none (all rights reserved) | 2026-08-11 (e3efc276) | 3 | Public Ad Library through a browser tool (Claude in Chrome) | No | OPTIONAL (borrow the ideas, don't install) |
| kelpi-ai/meta-ads-skills | Yes, not archived | MIT | 2026-07-02 (c046a258) | 4 | Manual/web Ad Library read; Meta Ads MCP (Pipeboard or Meta official) for account skills | No for teardown; account skills need an MCP | Already installed; keep `competitor-ad-teardown` |
| mardab96/meta-ads-skills | Yes, not archived | MIT | 2026-08-14 (388095b0) | 6 | Your own Meta Ads exports (CSV) | No | NOT RECOMMENDED for this task |
| Hiberius/competitor-ad-intelligence | Yes, not archived | MIT | 2026-09-08 (d9b1944a) | 1 | None: no collection code; scores a CSV you supply | No | RECOMMEND |
| sergebulaev/facebook-skills | Yes, not archived | MIT | 2026-10-15 (f3fb266c); pushed_at 2026-10-21 | 71 | Apify actors (`apify~facebook-pages-scraper`, `danek~facebook-comments-ppr`); Publora for posting | Optional Apify, Publora, Pixfaro | OPTIONAL (already installed; limited to organic Page stats) |
| vnklab/claude-smm-skills | Yes, not archived | none per GitHub API (README says "MIT") | 2026-04-06 (361e5f40) | 8 | None (prompt-only content skills) | No | NOT RECOMMENDED |

---

### 1. apify/awesome-skills
- **Exists:** Yes. https://github.com/apify/awesome-skills. archived=false, default branch `main`.
- **License:** Apache-2.0 (GitHub API).
- **Maintenance:** last commit 2026-09-22T19:50:55Z `1eb0cd0c` "chore: regenerate marketplace.json, AGENTS.md and README [bot]". Open issues 62 (the API count includes PRs). Stars 282, forks 96.
- **What it does:** a community catalog of about 28 Apify skills (`skills/*/SKILL.md`). The relevant one is `skills/apify-ads-intelligence/SKILL.md` (author Sameh Jarour), which covers competitor-ads, keyword-ads, top-creatives, landing-page-audit and cross-platform-audit across Meta, Google, TikTok, LinkedIn and X. Also of interest: `apify-influencer-brand-collabs` (Instagram branded content) and `apify-easy-competitive-intelligence`.
- **Data access:** Apify Store actors run through the Apify CLI (`apify actors call`). For Meta it uses primary `apify/facebook-ads-scraper` with fallback `brilliant_gum/facebook-ads-library-scraper`. These actors scrape the public Ad Library on Apify's side. It does not use the official Meta API.
- **Credentials/cost:** needs `APIFY_TOKEN` or `apify login`. The SKILL.md warns that "`apify/facebook-ads-scraper` charges per ad" and to "Warn the user before runs of 500+ ads". The repo gives no price figures (not verified).
- **Risk:** the SKILL.md says "The `--user-agent` flag is critical for telemetry — never omit it", so usage is attributed to Apify. It runs third-party community actors (for example `brilliant_gum`, `dz_omar`), which are unknown code on Apify's infrastructure. Some skills ship shell/cron scripts (for example `apify-ai-search-visibility-tracker/reference/scripts/install_cron.sh`). No ad-account write access.
- **Install:** `npx skills add apify/awesome-skills` (`-s <name>` for one skill). The repo also ships a Claude plugin marketplace (`.claude-plugin/marketplace.json`).
- **Value:** OPTIONAL. Only useful as a paid fallback if the existing Playwright scraper gets blocked. It duplicates what is already working and costs money per ad.

### 2. tenfoldmarc/ad-spy-skill
- **Exists:** Yes. https://github.com/tenfoldmarc/ad-spy-skill. archived=false.
- **License:** none (GitHub API `license: null`, and no LICENSE file in the tree), so all rights are reserved.
- **Maintenance:** last commit 2026-09-09T21:52:31Z `232a2534`. 0 open issues, 0 stars, 0 forks. Files: README.md, SKILL.md, scrape.sh, transcribe.py.
- **What it does:** the `/ad-spy` commands (`add`, `remove`, `list`, `angles`, `setup`). It saves competitor page IDs, scrapes their active ads, downloads media, transcribes videos (Whisper), ranks ads by run length, flags likely retargeting ads and writes angle briefs. It is tied into the author's other skills (/ad-copy, /ad-image-gen, ...) through a shared profile at `~/.claude/ad-profiles/`.
- **Data access:** scrapes the public Ad Library. `scrape.sh` opens `facebook.com/ads/library/?...view_all_page_id=` with `npx agent-browser`, scrolls, extracts the card DOM with JS `eval`, then uses `curl` to download fbcdn media. It takes a country parameter (default ALL). No login.
- **Credentials/cost:** none required. The OpenAI Whisper API (`OPENAI_API_KEY`, sent to api.openai.com) is optional; local whisper is free.
- **Risk:** `npx agent-browser` downloads and runs an unpinned npm package at run time. The skill runs bash, ffmpeg and curl. It asks the agent to install global npm/pip packages. The scraping is automated. It is Mac/Linux oriented ("Windows works with WSL"), and this machine is Windows.
- **Install:** paste "Install this skill for me: https://github.com/tenfoldmarc/ad-spy-skill", or `git clone ... ~/.claude/skills/ad-spy`.
- **Value:** NOT RECOMMENDED. It duplicates the existing Playwright scraper, has no license, has an unpinned npx dependency, needs bash/WSL, and has 0 adoption.

### 3. realbrianhanson/fb-ad-intel
- **Exists:** Yes. https://github.com/realbrianhanson/fb-ad-intel. archived=false.
- **License:** none (API `null`, and no LICENSE file).
- **Maintenance:** single commit 2026-08-11T05:29:33Z `e3efc276`. 0 open issues, 3 stars, 2 forks.
- **What it does:** one skill, `fb-ad-intel`. Given an Ad Library URL or page ID, the browser loads all cards (See-more/scroll loop). It extracts id, start date, variants, caption, headline, CTA, landing URL (decoded from `l.facebook.com/l.php?u=`) and media URLs. It then downloads the media, transcribes videos locally (faster-whisper/mlx-whisper) and builds a 4-tab .xlsx (`scripts/pipeline.py`, `scripts/build_xlsx.py`).
- **Data access:** the public Ad Library through the Claude in Chrome extension or the built-in browser. It uses `country=ALL` by default, and the URL is editable. No login: "No API keys. No accounts."
- **Credentials/cost:** none. Local Whisper models are downloaded on first use.
- **Risk:** `scripts/install.sh` creates a venv and pip-installs `static-ffmpeg openpyxl pillow faster-whisper` without pins. `pipeline.py` makes network calls only to the fbcdn media URLs it is given, with a spoofed Mac UA, and runs `ffprobe`. No telemetry was seen. It drives your logged-in Chrome when the Chrome extension is used. Use a logged-out profile to avoid tying the scraping to a personal FB account.
- **Install:** copy the folder to `~/.claude/skills/fb-ad-intel`, then say "Set up the fb-ad-intel skill".
- **Value:** OPTIONAL. Don't install it. Its landing-URL decoding, variant count and xlsx layout are worth copying as ideas into the existing scraper. Unlicensed, so reuse only the ideas, not the code.

### 4. kelpi-ai/meta-ads-skills (already installed)
- **Exists:** Yes. https://github.com/kelpi-ai/meta-ads-skills. archived=false.
- **License:** MIT.
- **Maintenance:** last commit 2026-07-02T09:04:51Z `c046a258` ("Add GROWTH-OS.md"). 0 open issues, 4 stars, 2 forks.
- **What it does:** 16 skills, matching the 16 pinned in skills-lock.json (angle-writer ... pixel-conversions). The relevant one, `competitor-ad-teardown`, is a prompt only. It groups a competitor's active ads by message, flags groups with 3+ variations and ads running 90+ days, and outputs gaps plus 3-5 angle hypotheses.
- **Data access:** competitor-ad-teardown has `mcp_access: "none"` (skill.meta.json) and works from the public Ad Library through web access. Account skills use a Meta Ads MCP, either Pipeboard-hosted `meta-ads.mcp.pipeboard.co` or Meta's official `mcp.facebook.com/ads`. `media-buyer`, `creative-director` and `budget-pacer` declare `mcp_access: "write"`.
- **Credentials/cost:** none for the teardown. Account skills need MCP auth to an ad account. Pipeboard pricing is not verified.
- **Risk:** the write-capable skills (media-buyer, creative-director, budget-pacer) can change an ad account if an MCP is connected. The README says "Read-only by default" and "Nothing writes without you." Not relevant unless an MCP is attached.
- **Install:** README says `npx skills add kelpi-ai/meta-ads-skills` (already done).
- **Value:** already installed. Keep `competitor-ad-teardown` as the analysis layer on top of the scraper output. Nothing more is needed from this repo.

### 5. mardab96/meta-ads-skills
- **Exists:** Yes. https://github.com/mardab96/meta-ads-skills. archived=false.
- **License:** MIT.
- **Maintenance:** last commit 2026-08-14T13:21:16Z `388095b0` "v2.0.0: 10 -> 20 skills". 1 open issue, 6 stars, 4 forks.
- **What it does:** 20 diagnostic skills for your own account: account health, creative fatigue, Advantage+, Pixel/CAPI, budget reallocation, placement, structure, offer-angle extraction, comment mining, weekly readout, attribution, modeled conversions, conversion lag, iOS gap, click-to-session, incrementality, margin, audience overlap, lookalike, learning phase. Four Python helpers live in `scripts/`.
- **Data access:** your own Meta Ads exports (CSV, screenshots). README: "They work with Meta Ads exports today", and they "do not require write access". No competitor data source.
- **Credentials/cost:** none.
- **Risk:** low. Local Python helpers only. By default the skills do not publish, change budgets or pause ads.
- **Install:** `git clone`, then `cp -r meta-ads-skills/*-meta-ads meta-ads-skills/scripts ~/.claude/skills/`.
- **Value:** NOT RECOMMENDED for this task. It analyzes your own account. Only `offer-angle-extraction` overlaps the competitor task, and it expects performance data the Ad Library lacks. It also overlaps kelpi's installed skills.

### 6. Hiberius/competitor-ad-intelligence
- **Exists:** Yes. https://github.com/Hiberius/competitor-ad-intelligence. archived=false.
- **License:** MIT.
- **Maintenance:** last commit 2026-09-08T19:25:07Z `d9b1944a`. 0 open issues, 1 star, 1 fork. Has CI (`.github/workflows/ci.yml`) and `tests/test_adscore.py`.
- **What it does:** a "Winner Score" over a competitor-ad corpus (`score = 0.35·longevity + 0.25·variants + 0.20·geo + 0.10·velocity + 0.10·recency`). It does lineage grouping so re-uploads don't fake short lifespans (token-set similarity 0.72), assigns stages (battle-tested 30+ days, gaining traction 14-29, new test under 14), uses a 9-category angle taxonomy, and runs `gaps` analysis against your own ads. Commands: `adscore.py lineage|score|gaps`.
- **Data access:** none built in. SKILL.md: "This skill ships no scraping code". It works on CSVs you supply. `references/sources-and-limits.md` correctly states that spend and impressions exist only for political/issue ads.
- **Credentials/cost:** none.
- **Risk:** very low. The `adscore.py` imports checked were only stdlib (argparse, csv, datetime, json, re, sys, collections), with no network or subprocess imports seen. The README badges say "No network calls" and "Zero dependencies".
- **Install:** `npx skills add Hiberius/competitor-ad-intelligence`.
- **Value:** RECOMMEND. It complements the existing scraper by scoring and de-duplicating the scraped corpus honestly, with no paid service, and the code is small enough to review before use. The scraper CSV needs mapping to its template columns (`templates/competitors.example.csv`).

### 7. sergebulaev/facebook-skills
- **Exists:** Yes. https://github.com/sergebulaev/facebook-skills. archived=false.
- **License:** MIT.
- **Maintenance:** last commit 2026-10-15T11:35:00Z `f3fb266c` "v1.0.31 ..."; pushed_at 2026-10-21. 1 open issue, 71 stars, 15 forks. Most active of the 8.
- **What it does:** 8 skills: fb-audience-insights, fb-content-planner, fb-engagement-drafter, fb-hook-extractor, fb-humanizer, fb-page-optimizer, fb-post-writer, fb-repurposer. These are exactly the 8 installed `facebook-skills:*` skills. The installed `facebook-marketing` skill describes Publora publishing, matching this repo. No local plugin files were found under `~/.claude/plugins` to confirm the origin byte-for-byte. Attribution is by name and description match only (not verified at file level).
- **Data access:** organic Facebook Pages only, not the Ad Library. Read side: Apify actors `apify~facebook-pages-scraper` (Page stats) and `danek~facebook-comments-ppr` (post commenters), via `api.apify.com/v2/acts/.../run-sync-get-dataset-items` (`lib/apify_client.py`), or the Apify MCP on claude.ai. Write side: Publora API, which publishes Page posts.
- **Credentials/cost:** all optional (`.env.example`): `PUBLORA_API_KEY` + `FACEBOOK_PLATFORM_ID` (Publora "sign up free"), `APIFY_TOKEN` (Apify, "free tier included"), `PIXFARO_TOKEN` (image API; README says "from `flux-schnell` at $0.004"). It works in draft-only mode with nothing set.
- **Risk:** the publishing path writes to your Facebook Page through a third party (Publora), but it has an approval flow (`lib/approval.py`). The README warns that the bare Apify MCP exposes `call-actor` ("run anything in the Apify Store at whatever that actor charges"). It also has `FB_SKILLS_CUSTOM_POSTER`, a user-configured command. The repo includes security checks (`scripts/check_security_boundaries.py`, `check_no_secrets.py`).
- **Install:** `/plugin marketplace add sergebulaev/facebook-skills` then `/plugin install facebook-skills@facebook-skills`. Codex: `codex plugin marketplace add sergebulaev/facebook-skills`.
- **Value:** OPTIONAL (already installed). `fb-hook-extractor` and `fb-audience-insights` help with organic competitor Pages, but reading data needs Apify. No Ad Library or Instagram coverage.

### 8. vnklab/claude-smm-skills
- **Exists:** Yes. https://github.com/vnklab/claude-smm-skills. archived=false.
- **License:** GitHub API reports `null`, and there is no LICENSE file in the tree. The README "License" section says "MIT — free to use, modify, distribute." That is an unverified README claim; it has no license file.
- **Maintenance:** single commit 2026-04-06T17:17:59Z `361e5f40` "Initial commit". 0 open issues, 8 stars, 1 fork. Untouched for about 7 months.
- **What it does:** 9 prompt-only content skills: sm-content-strategy, sm-content-calendar, sm-hook-generator, sm-caption-writer, sm-viral-formula, sm-audience-persona, sm-retention-architect, sm-engagement-scripts, sm-threads-writer. The README claims they are "built on official Meta/Instagram algorithm documentation" (not verified).
- **Data access:** none. No scripts and no data collection.
- **Credentials/cost:** none.
- **Risk:** low (Markdown only).
- **Install:** `git clone git@github.com:vnklab/claude-smm-skills.git`, then `cp -r claude-smm-skills/skills/* ~/.claude/skills/`.
- **Value:** NOT RECOMMENDED. Content creation, not competitor research. It overlaps the installed marketing-skills, facebook-skills and kelpi skills.
