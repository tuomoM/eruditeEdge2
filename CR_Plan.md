# Search Engine Visibility Plan For Vocabulary Pages

## Goal

Make eruditeEdge vocabulary content discoverable, crawlable, indexable, and competitive for word-meaning searches such as `recalcitrant meaning`.

The product goal is:

- Anonymous visitors can browse vocabulary and view word pages.
- Search engines find canonical, content-rich `/words/<slug>` pages.
- Logged-in-only features and AI usage remain protected.
- Thin, duplicate, or internal app pages do not dilute the public vocabulary section.

## Adversarial Review Summary

Two review lenses were applied:

- Agent A: crawler and technical SEO. Routes, auth, status codes, robots, sitemap, canonical tags, metadata, rendering, and internal links.
- Agent B: content and query intent. Duplicate/thin content, page structure, schema, word-meaning search fit, and off-site discovery.

Current positives:

- Public word index exists at `/words` in `Views/vocabulary.py`.
- Public word pages exist at `/words/<word_slug>` in `Views/vocabulary.py`.
- `-meaning` URLs redirect to canonical word URLs in `Views/vocabulary.py`.
- Sitemap exists at `/sitemap.xml` in `Views/vocabulary.py`.
- Robots file exists at `/robots.txt` in `Views/vocabulary.py`.
- Public word pages have custom title, description, canonical, and JSON-LD hooks in `templates/public_word.html`.
- Anonymous `/vocabulary` and `/vocabulary/<id>/page` read access exists in `Views/vocabulary.py`.
- AI write/use routes remain auth and CSRF protected in `Views/vocabulary.py`.

## Reference Baseline

This plan follows current Google/Search Central guidance:

- Use unique, descriptive title text and useful snippets/meta descriptions.
- Make links crawlable with normal `<a href="...">` links.
- Make canonical URLs explicit and keep sitemap URLs aligned with canonical URLs.
- Keep important content available in the initial HTML where possible.
- Submit and monitor the sitemap in Google Search Console.
- Use structured data only when it truthfully represents visible page content.
- Prioritize helpful, original, people-first content over pages created only to manipulate rankings.

Primary references:

- Google SEO Starter Guide: `https://developers.google.com/search/docs/fundamentals/seo-starter-guide`
- Google helpful content guidance: `https://developers.google.com/search/docs/fundamentals/creating-helpful-content`
- Google sitemap guidance: `https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap`
- Google canonical guidance: `https://developers.google.com/search/docs/crawling-indexing/consolidate-duplicate-urls`
- Google link crawlability guidance: `https://developers.google.com/search/docs/crawling-indexing/links-crawlable`
- Google structured data guidelines: `https://developers.google.com/search/docs/appearance/structured-data/sd-policies`
- Schema.org `DefinedTerm`: `https://schema.org/DefinedTerm`

## Priority Findings

### P0: Main Anonymous Vocabulary UI Links To ID Pages Instead Of Canonical Word Pages

Evidence:

- `/vocabulary` is now public in `Views/vocabulary.py`.
- The public app list links to `/vocabulary/{{ entry.id }}/page` in `templates/vocabulary_list.html`.
- The ID detail page has no canonical block or SEO metadata in `templates/vocabulary_detail.html`.
- The canonical public SEO route is `/words/<slug>` in `Views/vocabulary.py`.

Risk:

Search engines can discover and index internal ID pages before or alongside `/words/<slug>`. This splits ranking signals, creates duplicate content, and makes search snippets worse because ID pages use the default site metadata from `templates/base.html:6`.

Remediation:

- For anonymous users, link vocabulary list rows to `/words/<slug>` instead of `/vocabulary/<id>/page`.
- For signed-in users, either keep current app links or also prefer `/words/<slug>` with an edit action shown separately.
- Add a canonical tag to `/vocabulary/<id>/page` pointing to `/words/<slug>`.
- Consider adding `noindex,follow` on `/vocabulary/<id>/page` for anonymous responses once `/words/<slug>` is fully feature-complete.

Tests:

- Anonymous `/vocabulary` contains `href="/words/recalcitrant"` and not the ID detail link for the entry.
- `/vocabulary/<id>/page` includes canonical `/words/recalcitrant`.
- `/words/recalcitrant` remains 200 and canonical to itself.

### P0: Landing/Header Does Not Link To The Canonical `/words` Index

Evidence:

- Anonymous nav links to `/vocabulary` in `templates/base.html`.
- Landing page is rendered for anonymous users at `app.py:40`, but current review found no direct `/words` crawl path in the main anonymous navigation.
- `/words` exists and has canonical metadata in `templates/public_words.html`.

Risk:

The canonical SEO section is discoverable through sitemap, but weaker through normal internal navigation. Search engines use internal links to discover, prioritize, and understand site architecture.

Remediation:

- Change anonymous nav from `Vocabulary` -> `/vocabulary` to `Words` or `Vocabulary` -> `/words`.
- Add a visible landing-page link to `/words`.
- Add a footer or secondary link from `/words` back to `/vocabulary` only if the app browsing UI remains useful.

Tests:

- Anonymous `/` contains `href="/words"`.
- Anonymous base nav contains `href="/words"`.
- Logged-in nav can keep `/vocabulary` for app workflow.

### P1: `/words` Has No Pagination Or Alphabetical Crawl Hubs

Evidence:

- `/words` renders every entry from `vocabulary_service.list_entries()` in `Views/vocabulary.py`.
- Repository list ordering is by word, part of speech, context in `Repositories/vocabulary_repository.py`.
- Template lists all entries in one page at `templates/public_words.html`.

Risk:

As the vocabulary grows, `/words` becomes too large and shallow. Search engines may crawl less efficiently, and users get a heavy page. Large all-entry pages can also look low quality.

Remediation:

- Add `/words/a`, `/words/b`, etc. alphabetical hubs.
- Add paginated `/words?page=2` or preferably crawlable letter pages.
- Keep `/words` as a concise hub linking to letter pages and a curated set of important words.
- Include letter pages in sitemap.

Tests:

- `/words/r` lists `recalcitrant`.
- `/words` links to `/words/r`.
- Sitemap includes `/words/r`.

### P1: Sitemap Includes Every Entry Without Content Quality Gating

Evidence:

- Sitemap loops over all `vocabulary_service.list_entries()` in `Views/vocabulary.py`.
- Public word pages render entries even if they have only a definition and no examples or synonyms in `templates/public_word.html`.
- `needs_attention` exists in the model and is selected in `Repositories/vocabulary_repository.py`, but sitemap does not filter by it.

Risk:

Indexing thin, uncertain, duplicate, or maintenance-needed entries can reduce perceived quality of the vocabulary section. A word-meaning page should answer the query immediately and substantively.

Remediation:

- Define `is_public_indexable_entry(entry)`:
  - has word, definition, and valid part of speech
  - has at least one example or at least two synonyms
  - `needs_attention` is empty
  - confidence is not obsolete if confidence data is present
- Use this gate in sitemap and optionally add `<meta name="robots" content="noindex,follow">` to public pages that do not pass.
- Keep non-indexable pages accessible to users if desired, but do not push them to search engines.

Tests:

- Thin entry is viewable but omitted from sitemap.
- Thin entry includes `noindex,follow`.
- Complete entry is included in sitemap and has no noindex tag.

### P1: Word Pages Need Stronger Search-Intent Content Above The Fold

Evidence:

- Metadata is generated in `Views/vocabulary.py`.
- Page heading is `{{ Word }} Meaning` in `templates/public_word.html`.
- Definition section starts in `templates/public_word.html`.
- There is no direct first-sentence answer pattern like `Recalcitrant means ...` before the first section heading.

Risk:

For queries like `recalcitrant meaning`, the page should immediately provide the answer in a snippet-friendly sentence. The current page is understandable, but not maximally optimized for definition snippets.

Remediation:

- Add an answer paragraph directly under the H1:
  - `Recalcitrant means stubbornly resistant to authority, control, or guidance.`
- Use consistent section names:
  - `Recalcitrant definition`
  - `How to use recalcitrant in a sentence`
  - `Recalcitrant synonyms`
  - `Is recalcitrant a GRE word?` when applicable
- For multiple senses, show one compact sense list near the top.

Tests:

- `/words/recalcitrant` contains `Recalcitrant means`.
- Examples section heading includes the word.
- Synonyms section heading includes the word.

### P1: Structured Data Is Too Minimal

Evidence:

- JSON-LD is emitted in `templates/public_word.html`.
- Structured data contains only `@context`, `@type`, `name`, and `description` in `Views/vocabulary.py`.

Risk:

Minimal schema is acceptable, but it leaves helpful signals unused. Search engines can better understand a definition page if schema aligns with the visible content and canonical URL.

Remediation:

- Expand JSON-LD to include:
  - `@type: DefinedTerm`
  - `name`
  - `description`
  - `url`
  - `inDefinedTermSet` for eruditeEdge vocabulary
  - `termCode` or additional fields only if semantically correct
- Add a surrounding `WebPage` object if needed:
  - page name
  - description
  - mainEntity as the `DefinedTerm`
- Keep JSON-LD truthful and matched to visible content.

Tests:

- JSON-LD parses as valid JSON.
- JSON-LD includes canonical URL and word definition.

### P2: Canonical URL Generation Depends On Request Host Configuration

Evidence:

- Sitemap and canonical URLs use `url_for(..., _external=True)` in `Views/vocabulary.py`.
- No `SERVER_NAME`, `PREFERRED_URL_SCHEME`, `BASE_URL`, or proxy handling was found in `config.py`.
- App creation has no `ProxyFix` or external URL configuration in `app.py`.

Risk:

Behind a production proxy, canonical and sitemap URLs may be generated with the wrong scheme or host unless the platform forwards headers in a way Flask trusts. Wrong canonical hosts can badly hurt indexing.

Remediation:

- Add explicit `PUBLIC_BASE_URL` config.
- Build canonical and sitemap URLs from `PUBLIC_BASE_URL` rather than request host.
- Alternatively configure `ProxyFix`, `PREFERRED_URL_SCHEME`, and `SERVER_NAME` carefully for the deployment environment.
- Add a production smoke check that `/sitemap.xml` contains the production domain and `https`.

Tests:

- With `PUBLIC_BASE_URL=https://eruditeedge.example`, sitemap uses that host.
- Word canonical uses that host even under a localhost test request.

### P2: Public Word Slugs Need Collision And Change Strategy

Evidence:

- Slug generation lowercases and replaces non-alphanumerics in `Views/vocabulary.py`.
- Slug lookup scans all entries and matches slug equality in `Views/vocabulary.py`.
- Sitemap deduplicates by slug and keeps only one URL in `Views/vocabulary.py`.
- Multiple entries for the same word are rendered on one page in `templates/public_word.html`.

Risk:

This works for same-word multiple senses, but collisions such as punctuation variants can merge unrelated entries. If a word changes spelling, old URLs 404 unless redirects are added.

Remediation:

- Keep one canonical page per spelling when senses are genuinely related.
- Add slug collision tests for punctuation, phrases, and duplicate senses.
- Consider storing a stable `public_slug` in the database later if URLs become important enough to preserve across edits.
- Add manual redirect support for changed slugs if production content changes.

Tests:

- `pro forma` resolves to `/words/pro-forma`.
- Duplicate senses render on one canonical page.
- Non-canonical casing or punctuation redirects correctly.

### P2: Public List And Public Word Pages Have No Social/Open Graph Metadata

Evidence:

- `templates/base.html` provides meta description and title blocks.
- No Open Graph or Twitter metadata blocks were found.

Risk:

This is not a direct ranking factor, but better previews improve sharing, click-through, and off-site discovery.

Remediation:

- Add base template blocks for `og:title`, `og:description`, `og:url`, `og:type`.
- Populate word pages with word-specific values.
- Use a simple static brand image unless a better asset is created.

Tests:

- `/words/recalcitrant` includes word-specific `og:title` and `og:url`.

## Codebase Action Plan

### Phase 1: Consolidate Canonical Crawl Paths

1. Add `canonical_word_url_for_entry(entry)` helper.
2. Add slug to entries used by `/vocabulary`.
3. Change anonymous `/vocabulary` links to `/words/<slug>`.
4. Add canonical tag to `/vocabulary/<id>/page` pointing to `/words/<slug>`.
5. Add optional `robots` block support in `base.html`.
6. Decide whether anonymous ID detail pages should be `noindex,follow`.

Acceptance checks:

- Anonymous users naturally navigate to `/words/<slug>`.
- ID pages no longer compete with canonical word pages.
- AI/practice buttons remain absent for anonymous users.

### Phase 2: Improve Word Page Content For Meaning Queries

1. Add a direct answer sentence below H1.
2. Include the word in section headings.
3. Add part-of-speech specific copy where natural:
   - `Recalcitrant is an adjective.`
4. Include GRE list/relevance when present.
5. Render cloze sentences only if they are useful and do not expose internal training-only content.
6. Add related-word links from linked synonyms.

Acceptance checks:

- A word page answers `<word> meaning` in the first visible paragraph.
- Page remains readable without login.
- No AI interaction is available anonymously.

### Phase 3: Add Index Quality Controls

1. Implement `is_public_indexable_entry(entry)`.
2. Use it in sitemap.
3. Add `noindex,follow` to non-indexable public word pages.
4. Add admin/reporting view or CLI command for entries excluded from indexing.
5. Fix excluded entries by adding examples, synonyms, and confidence cleanup.

Acceptance checks:

- Thin pages are not in sitemap.
- High-quality pages are in sitemap.
- The number of indexed pages is intentional, not accidental.

### Phase 4: Build Crawl Hubs

1. Add `/words/<letter>` alphabetical pages.
2. Change `/words` into a hub page linking to letters and featured collections.
3. Add collection pages for durable query classes:
   - `/words/gre-vocabulary`
   - `/words/rare-words`
   - `/words/formal-words`
   - `/words/literary-words`
4. Include hubs in sitemap.
5. Link from word pages back to relevant hubs.

Acceptance checks:

- No crawl path requires search forms or JavaScript.
- Every indexable word is reachable through static links.

### Phase 5: Harden Production URL Generation

1. Add `PUBLIC_BASE_URL`.
2. Generate sitemap, canonical, robots sitemap URL, and Open Graph URL from it.
3. Add tests for production absolute URLs.
4. Add deployment smoke check:
   - `/robots.txt`
   - `/sitemap.xml`
   - one known `/words/<slug>` page

Acceptance checks:

- Production sitemap uses `https://` and the real domain.
- No canonical URL points to localhost, Railway preview host, or internal host.

### Phase 6: Add SEO Regression Tests

Add tests for:

- Anonymous nav links to `/words`.
- Landing page links to `/words`.
- Anonymous `/vocabulary` links to `/words/<slug>`.
- ID detail page canonical points to `/words/<slug>`.
- `/words/<slug>` title contains `<Word> Meaning`.
- `/words/<slug>` meta description contains the word.
- `/words/<slug>` JSON-LD is valid and includes URL.
- `/words/<slug>-meaning` 301 redirects.
- Sitemap omits non-indexable entries.
- Robots points to production sitemap when `PUBLIC_BASE_URL` is configured.

## Outside-Code Action Plan

### Search Console And Indexing

1. Verify the production domain in Google Search Console.
2. Submit `/sitemap.xml`.
3. Inspect a few representative pages:
   - `/words/recalcitrant`
   - `/words/contumacious`
   - `/words/pro-forma`
4. Use URL Inspection after each major release to confirm:
   - page is crawlable
   - canonical selected by Google matches `/words/<slug>`
   - page is indexable
   - rendered HTML includes definition/examples

### Analytics

1. Add privacy-conscious analytics or server log review for:
   - organic landing pages
   - queries where Search Console shows impressions
   - pages crawled but not indexed
2. Track search queries containing:
   - `<word> meaning`
   - `<word> definition`
   - `<word> synonym`
   - `GRE <word>`

### Content Operations

1. Pick 50 to 100 priority words first, including `recalcitrant`.
2. Ensure each priority page has:
   - concise definition
   - at least two natural examples
   - synonyms
   - part of speech
   - frequency/use note
   - GRE relevance when applicable
3. Review pages manually for snippet quality.
4. Avoid publishing/indexing entries marked `needs_attention`.

### Authority And Links

1. Add public links from any personal/project pages to the vocabulary hub.
2. Create a few durable editorial pages:
   - `Advanced English vocabulary list`
   - `GRE vocabulary meanings`
   - `Rare English words with examples`
3. Link those editorial pages to individual word pages.
4. Share useful word collections where appropriate, without spam.

### Competitive Reality

Ranking for `recalcitrant meaning` is competitive. The realistic path is:

1. Get pages indexed correctly.
2. Win long-tail searches first:
   - `recalcitrant meaning with examples`
   - `recalcitrant GRE meaning`
   - `recalcitrant synonyms and usage`
3. Improve click-through and content quality over time.
4. Build enough internal and external authority for shorter head terms.

## First Implementation Batch

Recommended next code batch:

1. Anonymous nav and landing link to `/words`.
2. Anonymous `/vocabulary` links to `/words/<slug>`.
3. Canonical/noindex handling for `/vocabulary/<id>/page`.
4. Direct answer sentence and stronger headings on `/words/<slug>`.
5. `PUBLIC_BASE_URL` for canonical/sitemap/robots.
6. SEO regression tests for those changes.

This batch should not require a database migration.
