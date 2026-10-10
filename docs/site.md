# Public website and traffic reports

Cellwright is published at [cellwright.scottcampbell.io](https://cellwright.scottcampbell.io/). Cloudflare Pages builds the `site/` directory from this repository's `main` branch. Workbook scanning and conversion remain in the local application.

The public website remains in English. The current source checkout supports English, French and German in the local dashboard; see [language support](localization.md). Update download wording when archives containing that change are published, so the website does not advertise a capability absent from its linked release.

The site includes crawlable migration guides, descriptive titles, canonical URLs, structured SoftwareApplication/Article data, `robots.txt`, a four-page sitemap and a plain-text crawler overview. Search placement depends on indexing, relevance and outside links; these files do not guarantee a ranking. The site is verified in [Google Search Console](https://search.google.com/search-console?resource_id=https%3A%2F%2Fcellwright.scottcampbell.io%2F), which tracks indexing and search queries separately from website visits.

## Owner's reports

- [Cloudflare Web Analytics](https://dash.cloudflare.com/21e9dac78809be183e1c0376f3f756b3/web-analytics/overview?siteTag~in=8b210ba38461417eb4a2cfe2aaf3806d) shows visits, page views, referring sites, countries, devices and page performance.
- [Private engagement console](https://dash.cloudflare.com/21e9dac78809be183e1c0376f3f756b3/workers/d1/databases/0f974b9a-8f10-48c0-86b2-ea639828e4ac/console) shows aggregate active reading time, download clicks and scrolling. It requires the owner's Cloudflare login.

Run this read-only query in the engagement console:

```sql
SELECT day, path, views,
       ROUND(active_seconds * 1.0 / NULLIF(views, 0), 1) AS avg_active_seconds,
       downloads, scrolled_views
FROM daily_engagement
ORDER BY day DESC, path;
```

Active time includes only visible, focused pages and pauses after one minute without interaction. It is an estimate, not total session duration. Views do not identify unique people; blocked scripts, failed beacons and automated traffic affect counts. Initial totals include deployment checks.

A production browser check on 10 October 2026 confirmed that page views, foreground active seconds and scrolling reach the private database. Download clicks are covered by the client test; a recorded click does not prove that an archive finished downloading.

The first-party collector stores only UTC day, allowlisted public page path and numeric totals, with no cookies or visitor identifiers. Global Privacy Control and Do Not Track disable this collector. See the [public privacy explanation](https://cellwright.scottcampbell.io/privacy/) for the distinction between engagement storage and hosting request metadata.

## Deployment configuration

Pages production binds the dedicated D1 database `cellwright-traffic` as `TRAFFIC`. Initialize its table with `site/engagement.sql`. Only `/api/engagement` invokes the Pages Function; normal pages are static assets. The endpoint accepts bounded same-origin numeric counters and exposes no public reports. No credential belongs in these files.

Web Analytics is enabled in Pages Metrics and is injected on deployment. `site/_headers` allows the Cloudflare beacon and the local engagement script. The database and Functions use the existing free plan; daily quotas can stop collection. The website continues serving static pages independently.

Validation: `node --test tests/test_*.mjs` runs the website and dashboard language checks. Website checks cover the site/dashboard/report palette restriction, counter bounds, private-field rejection, cross-origin rejection, foreground time and opt-outs. CI runs them on Windows and Ubuntu alongside the existing application tests.
