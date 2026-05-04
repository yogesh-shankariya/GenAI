# Skill: `acquisition_analytics`

## Short Description

Use this skill for read-only SQL questions about opt-ins, form submissions, form questions and answers, traffic attribution, UTM data, referrers, landing pages, provider forms, and acquisition-source performance.

This skill must generate SQL only. The application will execute the SQL through a safe read-only database helper.

## When To Use This Skill

Use `acquisition_analytics` for read-only SQL analytics questions related to acquisition, opt-ins, form submissions, campaign attribution, traffic attribution, and form-answer analysis.

Use this skill for:

- Opt-in counts and form submission counts.
- Unique lead counts from opt-ins or form submissions.
- Opt-in or form submission trends by day, week, month, or custom date range.
- Opt-in source breakdowns, such as Calendly, Typeform, landing page, webinar, newsletter, manual, or other.
- Provider form performance, including forms with the most submissions or unique leads.
- Setter attribution on opt-ins, including which setter is attached to the most opt-ins.
- UTM analysis, including UTM source, medium, campaign, content, and term breakdowns.
- Landing page and referrer performance.
- Traffic attribution coverage, including opt-ins with or without attribution records.
- Missing attribution checks, such as missing UTM source, UTM campaign, UTM medium, landing page, or referrer.
- Form question inventory, including which questions are being asked across forms.
- Form answer distribution for a specific question.
- Lists of opt-ins or leads tied to a specific UTM campaign, landing page, referrer, provider form, or opt-in source.
- Current lead-status conversion analysis by acquisition attributes, such as won leads by UTM campaign, landing page, provider form, or opt-in source.

## When Not To Use This Skill

Do not use this skill for:

- Lead-only counts, lead status, normalized marketing source breakdowns from `leads.first_source_id` or `leads.last_source_id`, stale leads, missing owners, missing setters, or lead creation trends. Use `lead_analytics`.
- Appointment counts, booked calls, appointment outcomes, appointment no-show rates, Fathom call summaries, objections, action items, Fathom coverage, or call duration. Use `appointment_analytics`.
- Revenue, contracts, payments, invoices, refunds, subscriptions, payment links, or payment proofs. Use `revenue_analytics`.
- Full single-lead summaries with notes, calls, contracts, payments, Fathom records, and full timeline. Use `lead_360`.
- Provider integration health, webhook troubleshooting, credential validation, API keys, raw webhook payloads, raw provider payloads, or connection status. Use an integration/admin skill.
- Broad semantic theme discovery over long form answers such as "what are people struggling with", "summarize the common pain points", or "what objections appear in form answers". Use `semantic_context` or a future pgvector/hybrid retrieval skill when the user asks for qualitative theme discovery across many text answers.

If the user question requires tables outside `opt_ins`, `opt_in_question_answers`, `traffic_attributions`, `leads`, or `sales_statuses`, do not use this skill unless the required logic is explicitly listed in this file.

## SQL Generation Rules

Generate exactly one read-only PostgreSQL SQL statement.

Allowed statements:

- `SELECT`
- `WITH ... SELECT`

Never generate:

- `INSERT`
- `UPDATE`
- `DELETE`
- `UPSERT`
- `MERGE`
- `DROP`
- `ALTER`
- `CREATE`
- `TRUNCATE`
- `GRANT`
- `REVOKE`
- `COPY`
- `CALL`
- `DO`
- `VACUUM`
- `ANALYZE`
- `EXPLAIN ANALYZE`

Do not generate multiple SQL statements.

Do not use `SELECT *`.

Do not expose secrets, webhook payloads, API keys, encrypted credentials, raw payloads, provider credentials, or private integration data.

Never select:

```text
opt_ins.raw_payload
```

Do not select these fields unless the user explicitly asks for technical/debug identifiers or technical request metadata:

```text
opt_ins.external_reference
opt_ins.provider_form_id
opt_ins.ip_address
opt_ins.user_agent
```

Even when explicitly requested, return only the minimum required fields.

Every business query must include an organization filter.

For opt-in-first queries, use:

```sql
WHERE o.clerk_org_id = :org_id
```

For question-answer queries, join through `opt_ins` and filter on the parent opt-in:

```sql
JOIN opt_ins o
  ON o.id = q.opt_in_id
WHERE o.clerk_org_id = :org_id
```

For traffic-attribution queries, join through `opt_ins` and filter on the parent opt-in:

```sql
JOIN opt_ins o
  ON o.id = ta.opt_in_id
WHERE o.clerk_org_id = :org_id
```

`opt_ins`, `opt_in_question_answers`, and `traffic_attributions` do not have `is_deleted` in the current schema, so do not add a soft-delete filter to those tables.

For `leads`, exclude soft-deleted rows by default when joining to lead identity or current lead status:

```sql
AND l.is_deleted = false
```

Always use parameterized SQL for organization scope and dynamic values.

Use named parameters such as:

- `:org_id`
- `:start_date`
- `:end_date`
- `:lead_source`
- `:setter_id`
- `:provider_form_name`
- `:utm_source`
- `:utm_medium`
- `:utm_campaign`
- `:landing_page`
- `:referrer`
- `:question_text`
- `:answer_text`
- `:limit`

Do not hardcode the organization ID in generated agent SQL except in local manual debugging.

For aggregate analytics questions, return aggregate columns only.

For list-style questions such as "which opt-ins", "show me submissions", "list leads from this campaign", or "which answers", select only the fields needed to answer the question, add a deterministic `ORDER BY`, and cap the result with a reasonable `LIMIT` unless the user asks for a specific limit.

Default list limit: `50`.

Do not include lead email, lead phone, IP address, user agent, raw payload, provider reference, or external reference unless the user explicitly asks for those fields.

`setter_id` is a user ID. Do not invent setter names unless a future user/profile table is available in another skill.

## Count vs List Intent Rule

If the user asks "how many", "count", "total", or "number of", generate an aggregate query.

If the user asks "which", "show me", "list", "who", "give me the opt-ins", "give me the submissions", or "give me the answers", generate a list query.

Do not answer list-style acquisition questions using only `COUNT(*)`.

## Primary Tables

## `opt_ins`

One row is one opt-in or form submission captured for a lead.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Opt-in primary key. | Join key and opt-in identity. |
| `lead_id` | Lead connected to the opt-in. | Join to `leads.id`. |
| `clerk_org_id` | Tenant/organization ID. | Required filter. |
| `source` | Acquisition source enum. | Source reporting for opt-ins/forms. |
| `setter_id` | Setter user ID attached to the opt-in. | Setter acquisition analysis. |
| `provider_form_id` | External provider form ID. | Provider/debug context only when explicitly requested. |
| `provider_form_name` | Provider form display name. | Form-level reporting. |
| `external_reference` | External provider submission/reference ID. | Provider/debug context only when explicitly requested. |
| `raw_payload` | Raw provider payload. | Never select. |
| `ip_address` | Submission IP address. | Technical/debug context only when explicitly requested. |
| `user_agent` | Submitter browser/device user agent. | Technical/debug context only when explicitly requested. |
| `created_at` | Opt-in capture/submission datetime. | Date filtering and trend analysis. |

Required default filter:

```sql
WHERE o.clerk_org_id = :org_id
```

Use `o.created_at` for acquisition timing questions.

Use `o.source` for acquisition source reporting.

Use `o.provider_form_name` for form-level reporting.

Do not use `leads.created_at` for opt-in submission timing unless the user explicitly asks when the lead record was created.

## `opt_in_question_answers`

One row is one question-answer pair submitted inside an opt-in form.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Question-answer primary key. | Row identity. |
| `opt_in_id` | Parent opt-in ID. | Join to `opt_ins.id`. |
| `question` | Form question text. | Question inventory and filtering. |
| `answer` | Submitted answer text. | Answer counts and answer listing. |
| `position` | Question order in the form. | Form display/order context. |
| `created_at` | Question-answer row creation datetime. | Usually secondary; use parent `opt_ins.created_at` for acquisition timing. |

Join through `opt_ins`:

```sql
JOIN opt_ins o
  ON o.id = q.opt_in_id
```

Because this table does not have `clerk_org_id`, never query it without joining to `opt_ins` and filtering `o.clerk_org_id = :org_id`.

For broad qualitative analysis across long answer text, do not rely on SQL-only counts. Use `semantic_context` or a future pgvector/hybrid retrieval skill.

## `traffic_attributions`

One row is traffic attribution metadata for one opt-in.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Traffic attribution primary key. | Row identity. |
| `opt_in_id` | Parent opt-in ID. | Join to `opt_ins.id`. |
| `utm_source` | UTM source. | Campaign/source reporting. |
| `utm_medium` | UTM medium. | Channel/medium reporting. |
| `utm_campaign` | UTM campaign. | Campaign reporting. |
| `utm_content` | UTM content. | Ad/content variant reporting. |
| `utm_term` | UTM term. | Keyword/term reporting. |
| `referrer` | Referring page/domain or URL. | Referrer reporting. |
| `landing_page` | Landing page captured for the opt-in. | Landing page reporting. |
| `created_at` | Attribution row creation datetime. | Technical attribution timing; use parent `opt_ins.created_at` for acquisition timing. |

Join through `opt_ins`:

```sql
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
```

Because this table does not have `clerk_org_id`, never query it without joining to `opt_ins` and filtering `o.clerk_org_id = :org_id`.

## `leads`

Use this table only when acquisition answers need lead display context, unique lead counts, or current lead status conversion context.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Lead primary key. | Join from `opt_ins.lead_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `first_name` | First name. | Display and search. |
| `last_name` | Last name. | Display and search. |
| `full_name` | Generated/display full name. | Display and search. |
| `email` | Lead email. | Search and identity only when explicitly requested. |
| `phone_e164` | Phone number in E.164 format. | Contact detail only when explicitly requested. |
| `source` | Current lead source enum. | Lead-source context only. Prefer `o.source` for acquisition source. |
| `status_id` | Current sales status ID. | Join to `sales_statuses.id` for current lead-status conversion context. |
| `assigned_to` | Lead owner/assignee user ID. | Context only. Do not use for owner analytics in this skill. |
| `setter_id` | Lead setter user ID. | Lead context only. Prefer `o.setter_id` for opt-in setter analysis. |
| `created_at` | Lead creation datetime. | Lead-created timing only when explicitly requested. |
| `is_deleted` | Soft-delete flag. | Usually filter false when displaying lead identity or current lead status. |

Join from opt-ins:

```sql
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
```

Do not use this skill for lead-only analytics. Use `lead_analytics` for lead-only questions.

## `sales_statuses`

Use this table only when the user asks for acquisition performance by current lead status or current won/lost/unqualified/follow-up status.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Status primary key. | Join from `leads.status_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `name` | Human-readable status name. | Display exact status. |
| `role` | Normalized status role enum. | Current funnel/conversion context for acquisition attributes. |

Join from leads:

```sql
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
```

Use `ss.role = 'WON'` only as current lead-status conversion context. Do not use this skill for revenue conversion.

## Enums

## `LeadSource`

Business-defined values used by `opt_ins.source` and `leads.source`:

```text
CALENDLY
MANUAL
TYPEFORM
WEBINAR
NEWSLETTER
LANDING_PAGE
OTHER
```

Meaning:

| Value | Meaning |
|---|---|
| `CALENDLY` | Lead or opt-in came from Calendly booking flow. |
| `MANUAL` | Lead or opt-in was manually created. |
| `TYPEFORM` | Lead or opt-in came from Typeform. |
| `WEBINAR` | Lead or opt-in came from webinar flow. |
| `NEWSLETTER` | Lead or opt-in came from newsletter flow. |
| `LANDING_PAGE` | Lead or opt-in came from landing page. |
| `OTHER` | Source did not fit a more specific enum. |

Use `o.source` for acquisition source reporting.

Use `l.source` only when the user explicitly asks for the current lead source field.

## `SalesStatusRole`

Relevant values for acquisition status conversion context:

```text
NEW_LEAD
APPOINTMENT_BOOKED
NO_SHOW
RESCHEDULED
CANCELED
PARTIAL_PAYMENT
WON
UNQUALIFIED
FOLLOW_UP
LOST
```

Use `ss.role` only when the user asks for current lead-status conversion by acquisition attributes, such as won leads by UTM campaign.

## Business Interpretation Rules

## Opt-In Count vs Unique Lead Count

When the user asks for "opt-ins", "submissions", "form submissions", or "registrations", count opt-in records:

```sql
COUNT(*) AS opt_in_count
```

When the user asks for "unique leads from opt-ins", "leads acquired", or "how many leads came from forms", count distinct lead IDs:

```sql
COUNT(DISTINCT o.lead_id) AS unique_lead_count
```

Do not treat opt-in count and unique lead count as the same metric. One lead can have more than one opt-in.

## Acquisition Timing

For opt-in or form submission timing, use:

```sql
o.created_at
```

For traffic-attribution reporting, still use `o.created_at` by default because the opt-in is the business event.

Use `ta.created_at` only when the user explicitly asks when attribution rows were created.

Use `l.created_at` only when the user explicitly asks when lead records were created.

## Source Selection Rules

There are multiple source concepts in the schema:

- `o.source` = source attached to the opt-in/submission. This is the default for acquisition source reporting.
- `ta.utm_source`, `ta.utm_medium`, `ta.utm_campaign`, `ta.utm_content`, `ta.utm_term` = traffic/campaign attribution fields.
- `ta.landing_page` and `ta.referrer` = page/referrer attribution.
- `l.source` = current lead source enum. Use only when the user explicitly asks for current lead source.
- `leads.first_source_id`, `leads.last_source_id`, and `marketing_sources` are handled by `lead_analytics`, not this skill.

Default behavior:

- For "acquisition source", "opt-in source", or "form source", use `o.source`.
- For "UTM source", use `ta.utm_source`.
- For "campaign", use `ta.utm_campaign` unless the user clearly means provider form campaign.
- For "landing page", use `ta.landing_page`.
- For "referrer", use `ta.referrer`.
- For "form", use `o.provider_form_name`.

Do not mix `o.source` and `ta.utm_source` unless the user asks to compare them.

## Missing Attribution Rules

For missing text attribution fields, treat both `NULL` and blank strings as missing.

Use expressions like:

```sql
NULLIF(TRIM(ta.utm_source), '') IS NULL
```

For grouped reporting, use:

```sql
COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown') AS utm_source
```

If the user asks for opt-ins with no traffic attribution record, use:

```sql
ta.id IS NULL
```

If the user asks for opt-ins missing a specific UTM field, use a `LEFT JOIN` to `traffic_attributions` and check that field with `NULLIF(TRIM(...), '') IS NULL`.

## Provider Form Rules

Use `o.provider_form_name` for form-level reporting.

If the provider form name is missing, use a safe fallback:

```sql
COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name
```

Do not display `provider_form_id` unless the user explicitly asks for provider form IDs or technical provider identifiers.

## Setter Rules

Use `o.setter_id` for acquisition setter analysis because it is attached to the opt-in event.

Treat both `NULL` and blank strings as missing:

```sql
NULLIF(TRIM(o.setter_id), '') IS NULL
```

For grouping, use:

```sql
COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter') AS setter_id
```

Do not invent setter names. These fields are user IDs.

## Question and Answer Analysis Rules

Use `opt_in_question_answers` for form question and answer analytics.

For question inventory, group by normalized `q.question` text.

For answer distribution to a specific question, filter by `q.question` and group by normalized `q.answer` text.

Use exact question text when the user provides the exact question.

Use `ILIKE :question_pattern` only when the user provides partial question text or asks for questions containing certain words.

For broad qualitative themes across many long answers, route to `semantic_context` instead of trying to summarize using SQL only.

## Current Lead Status Conversion Context

When the user asks acquisition-performance questions based on current lead status, such as:

- Which UTM campaign produced the most won leads?
- Which landing page has the most won leads?
- Which form source has the most appointment-booked leads?
- What is the won-lead rate by campaign?

Use `opt_ins -> leads -> sales_statuses`.

Default conversion grain:

- Group by the requested acquisition attribute, such as `ta.utm_campaign`, `ta.landing_page`, or `o.provider_form_name`.
- Count unique leads per group using `COUNT(DISTINCT o.lead_id)`.
- Count won/current-status leads using `COUNT(DISTINCT o.lead_id) FILTER (WHERE ss.role = 'WON')`.

Important limitation:

A single lead can have multiple opt-ins. If the same lead submitted multiple forms or campaigns, that lead can be attributed to multiple acquisition groups. Use a first-opt-in or last-opt-in attribution query only when the user explicitly asks for first-touch or last-touch opt-in attribution.

Do not use this skill to calculate revenue by acquisition campaign. Use `revenue_analytics` or a future cross-domain attribution skill if revenue joins are required.

## Timeframe Rules

For opt-ins captured during a date range, use:

```sql
o.created_at >= :start_date
AND o.created_at < :end_date
```

For question-answer activity during a date range, prefer parent opt-in timing:

```sql
o.created_at >= :start_date
AND o.created_at < :end_date
```

For daily opt-in trend questions, return counts only by default.

For weekly or monthly opt-in trend questions, include percentage change from the previous period when the user asks for growth, change, or trend percentage.

For trend-by-category questions, such as weekly trend by UTM campaign or landing page, keep SQL output row-based with period, category, count, previous-period count, and percentage-change columns.

Do not generate SQL pivot columns with hardcoded dates unless the user explicitly asks for pivot SQL.

If the user asks a generic weekly trend question without a date range, still generate SQL using `:start_date` and `:end_date`. The application should provide a default 12-week window.

If the user asks a generic monthly trend question without a date range, still generate SQL using `:start_date` and `:end_date`. The application should provide a default 12-month window.

## Percentage Rules

Use percentages only when they add business value.

For breakdown, distribution, grouped, ranking, source-wise, campaign-wise, landing-page-wise, form-wise, or setter-wise questions, include:

- grouped count
- a helper total column such as `total_matching_opt_ins`, `total_unique_leads`, or `total_records`
- `percentage_of_total` when useful

The helper total column is used by the main agent to write the opening summary sentence. It should not be shown to the user as a normal table column unless the user explicitly asks for it.

For attribution coverage questions, always include coverage percentage.

For list-style questions, do not add percentages.

## Default List Output Rules

For list-style opt-in queries, default output fields are:

- `total_matching_rows`
- `o.id`
- `o.created_at`
- `display_name`
- `opt_in_source`
- `provider_form_name`
- `setter_id`
- `utm_source`
- `utm_medium`
- `utm_campaign`
- `landing_page`
- `referrer`

Use this display name expression:

```sql
COALESCE(
  NULLIF(TRIM(l.full_name), ''),
  NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
  l.first_name,
  'Unknown Lead'
) AS display_name
```

Do not include `l.email`, `l.phone_e164`, `o.ip_address`, `o.user_agent`, `o.external_reference`, `o.provider_form_id`, or `o.raw_payload` unless explicitly requested.

Use `COUNT(*) OVER() AS total_matching_rows` for list-style queries with a `LIMIT`, so the final answer can show the exact total before the limited rows.

Use `LIMIT :limit` when the application passes a limit.

If the application does not pass a limit and the user does not request one, use:

```sql
LIMIT 50
```

Always use deterministic ordering, such as:

```sql
ORDER BY o.created_at DESC, o.id ASC
```

For question-answer list queries, order by:

```sql
ORDER BY o.created_at DESC, q.position ASC, q.id ASC
```

## Common Query Patterns

## Count Opt-Ins

```sql
SELECT COUNT(*) AS opt_in_count
FROM opt_ins o
WHERE o.clerk_org_id = :org_id;
```

## Count Unique Leads from Opt-Ins

```sql
SELECT COUNT(DISTINCT o.lead_id) AS unique_leads_from_opt_ins
FROM opt_ins o
WHERE o.clerk_org_id = :org_id;
```

## Count Opt-Ins in a Date Range

```sql
SELECT COUNT(*) AS opt_ins_in_period
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
  AND o.created_at >= :start_date
  AND o.created_at < :end_date;
```

## Count Unique Leads from Opt-Ins in a Date Range

```sql
SELECT COUNT(DISTINCT o.lead_id) AS unique_leads_from_opt_ins_in_period
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
  AND o.created_at >= :start_date
  AND o.created_at < :end_date;
```

## Opt-Ins by Acquisition Source

```sql
SELECT
  COALESCE(CAST(o.source AS text), 'Unknown') AS opt_in_source,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(CAST(o.source AS text), 'Unknown')
ORDER BY opt_in_count DESC, opt_in_source ASC;
```

## Opt-Ins by Provider Form

```sql
SELECT
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form')
ORDER BY opt_in_count DESC, provider_form_name ASC;
```

## Opt-Ins by Setter

```sql
SELECT
  COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter') AS setter_id,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter')
ORDER BY opt_in_count DESC, setter_id ASC;
```

## Top Actual Setter by Opt-In Count

Use this when the user asks:

- which setter generated the most opt-ins
- top setter by form submissions
- best setter by number of opt-ins

Exclude missing setter values. Do not return `No Setter` as the top setter unless the user explicitly asks to include opt-ins without a setter.

This query returns all setters tied for the highest opt-in count.

```sql
WITH setter_counts AS (
  SELECT
    NULLIF(TRIM(o.setter_id), '') AS setter_id,
    COUNT(*) AS opt_in_count
  FROM opt_ins o
  WHERE o.clerk_org_id = :org_id
    AND NULLIF(TRIM(o.setter_id), '') IS NOT NULL
  GROUP BY NULLIF(TRIM(o.setter_id), '')
),
max_count AS (
  SELECT MAX(opt_in_count) AS max_opt_in_count
  FROM setter_counts
)
SELECT
  sc.setter_id,
  sc.opt_in_count
FROM setter_counts sc
JOIN max_count mc
  ON sc.opt_in_count = mc.max_opt_in_count
ORDER BY sc.setter_id ASC;
```

## UTM Source Breakdown

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown') AS utm_source,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown')
ORDER BY opt_in_count DESC, utm_source ASC;
```

## UTM Medium Breakdown

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.utm_medium), ''), 'Unknown') AS utm_medium,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(ta.utm_medium), ''), 'Unknown')
ORDER BY opt_in_count DESC, utm_medium ASC;
```

## UTM Campaign Breakdown

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown')
ORDER BY opt_in_count DESC, utm_campaign ASC;
```

## UTM Source and Campaign Breakdown

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown') AS utm_source,
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
GROUP BY
  COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown'),
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown')
ORDER BY opt_in_count DESC, utm_source ASC, utm_campaign ASC;
```

## Landing Page Breakdown

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown') AS landing_page,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown')
ORDER BY opt_in_count DESC, landing_page ASC;
```

## Referrer Breakdown

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.referrer), ''), 'Unknown') AS referrer,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(ta.referrer), ''), 'Unknown')
ORDER BY opt_in_count DESC, referrer ASC;
```

## Traffic Attribution Coverage

```sql
SELECT
  COUNT(*) AS total_opt_ins,
  COUNT(*) FILTER (WHERE ta.id IS NOT NULL) AS opt_ins_with_traffic_attribution,
  COUNT(*) FILTER (WHERE ta.id IS NULL) AS opt_ins_without_traffic_attribution,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE ta.id IS NOT NULL) / NULLIF(COUNT(*), 0),
    2
  ) AS traffic_attribution_coverage_percent
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id;
```

## Missing UTM Field Coverage

Use this when the user asks which UTM fields are missing or how complete UTM tracking is.

```sql
SELECT
  COUNT(*) AS total_opt_ins,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_source), '') IS NOT NULL) AS opt_ins_with_utm_source,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_medium), '') IS NOT NULL) AS opt_ins_with_utm_medium,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_campaign), '') IS NOT NULL) AS opt_ins_with_utm_campaign,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_content), '') IS NOT NULL) AS opt_ins_with_utm_content,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_term), '') IS NOT NULL) AS opt_ins_with_utm_term,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.landing_page), '') IS NOT NULL) AS opt_ins_with_landing_page,
  COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.referrer), '') IS NOT NULL) AS opt_ins_with_referrer,
  ROUND(100.0 * COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_source), '') IS NOT NULL) / NULLIF(COUNT(*), 0), 2) AS utm_source_coverage_percent,
  ROUND(100.0 * COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.utm_campaign), '') IS NOT NULL) / NULLIF(COUNT(*), 0), 2) AS utm_campaign_coverage_percent,
  ROUND(100.0 * COUNT(*) FILTER (WHERE NULLIF(TRIM(ta.landing_page), '') IS NOT NULL) / NULLIF(COUNT(*), 0), 2) AS landing_page_coverage_percent
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id;
```

## List Opt-Ins Missing Traffic Attribution

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  o.id,
  o.created_at,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  CAST(o.source AS text) AS opt_in_source,
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter') AS setter_id
FROM opt_ins o
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
  AND ta.id IS NULL
ORDER BY o.created_at DESC, o.id ASC
LIMIT 50;
```

## List Opt-Ins Missing UTM Campaign

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  o.id,
  o.created_at,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  CAST(o.source AS text) AS opt_in_source,
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter') AS setter_id,
  COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown') AS utm_source,
  COALESCE(NULLIF(TRIM(ta.utm_medium), ''), 'Unknown') AS utm_medium,
  COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown') AS landing_page,
  COALESCE(NULLIF(TRIM(ta.referrer), ''), 'Unknown') AS referrer
FROM opt_ins o
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
  AND NULLIF(TRIM(ta.utm_campaign), '') IS NULL
ORDER BY o.created_at DESC, o.id ASC
LIMIT 50;
```

## List Opt-Ins from a Specific UTM Campaign

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  o.id,
  o.created_at,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  CAST(o.source AS text) AS opt_in_source,
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter') AS setter_id,
  COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown') AS utm_source,
  COALESCE(NULLIF(TRIM(ta.utm_medium), ''), 'Unknown') AS utm_medium,
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
  COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown') AS landing_page,
  COALESCE(NULLIF(TRIM(ta.referrer), ''), 'Unknown') AS referrer
FROM opt_ins o
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
  AND ta.utm_campaign = :utm_campaign
ORDER BY o.created_at DESC, o.id ASC
LIMIT 50;
```

## List Opt-Ins from a Specific Landing Page

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  o.id,
  o.created_at,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  CAST(o.source AS text) AS opt_in_source,
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  COALESCE(NULLIF(TRIM(o.setter_id), ''), 'No Setter') AS setter_id,
  COALESCE(NULLIF(TRIM(ta.utm_source), ''), 'Unknown') AS utm_source,
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
  COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown') AS landing_page,
  COALESCE(NULLIF(TRIM(ta.referrer), ''), 'Unknown') AS referrer
FROM opt_ins o
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
WHERE o.clerk_org_id = :org_id
  AND ta.landing_page = :landing_page
ORDER BY o.created_at DESC, o.id ASC
LIMIT 50;
```

## Form Question Inventory

```sql
SELECT
  NULLIF(TRIM(q.question), '') AS question,
  COUNT(*) AS answer_count,
  COUNT(DISTINCT q.opt_in_id) AS opt_in_count,
  MIN(q.position) AS first_observed_position,
  SUM(COUNT(*)) OVER() AS total_answer_rows
FROM opt_in_question_answers q
JOIN opt_ins o
  ON o.id = q.opt_in_id
WHERE o.clerk_org_id = :org_id
  AND NULLIF(TRIM(q.question), '') IS NOT NULL
GROUP BY NULLIF(TRIM(q.question), '')
ORDER BY answer_count DESC, question ASC;
```

## Form Question Inventory by Provider Form

```sql
SELECT
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  NULLIF(TRIM(q.question), '') AS question,
  COUNT(*) AS answer_count,
  COUNT(DISTINCT q.opt_in_id) AS opt_in_count,
  MIN(q.position) AS first_observed_position,
  SUM(COUNT(*)) OVER() AS total_answer_rows
FROM opt_in_question_answers q
JOIN opt_ins o
  ON o.id = q.opt_in_id
WHERE o.clerk_org_id = :org_id
  AND NULLIF(TRIM(q.question), '') IS NOT NULL
GROUP BY
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form'),
  NULLIF(TRIM(q.question), '')
ORDER BY provider_form_name ASC, first_observed_position ASC, answer_count DESC, question ASC;
```

## Answer Distribution for a Specific Question

Use this when the user gives the exact question text.

```sql
SELECT
  COALESCE(NULLIF(TRIM(q.answer), ''), 'No Answer') AS answer,
  COUNT(*) AS answer_count,
  COUNT(DISTINCT q.opt_in_id) AS opt_in_count,
  SUM(COUNT(*)) OVER() AS total_matching_answers,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_in_question_answers q
JOIN opt_ins o
  ON o.id = q.opt_in_id
WHERE o.clerk_org_id = :org_id
  AND q.question = :question_text
GROUP BY COALESCE(NULLIF(TRIM(q.answer), ''), 'No Answer')
ORDER BY answer_count DESC, answer ASC;
```

## Answer Distribution for a Partial Question Match

Use this only when the user provides partial question text or asks for questions containing certain words.

```sql
SELECT
  q.question,
  COALESCE(NULLIF(TRIM(q.answer), ''), 'No Answer') AS answer,
  COUNT(*) AS answer_count,
  COUNT(DISTINCT q.opt_in_id) AS opt_in_count,
  SUM(COUNT(*)) OVER() AS total_matching_answers,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM opt_in_question_answers q
JOIN opt_ins o
  ON o.id = q.opt_in_id
WHERE o.clerk_org_id = :org_id
  AND q.question ILIKE :question_pattern
GROUP BY
  q.question,
  COALESCE(NULLIF(TRIM(q.answer), ''), 'No Answer')
ORDER BY answer_count DESC, q.question ASC, answer ASC;
```

## List Answers for a Specific Question

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  o.id AS opt_in_id,
  o.created_at AS opt_in_created_at,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  q.question,
  q.answer,
  q.position
FROM opt_in_question_answers q
JOIN opt_ins o
  ON o.id = q.opt_in_id
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
WHERE o.clerk_org_id = :org_id
  AND q.question = :question_text
ORDER BY o.created_at DESC, q.position ASC, q.id ASC
LIMIT 50;
```

## List Opt-Ins with Form Answers

Use this when the user asks to show form submissions with their answers.

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  o.id AS opt_in_id,
  o.created_at AS opt_in_created_at,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  CAST(o.source AS text) AS opt_in_source,
  COALESCE(NULLIF(TRIM(o.provider_form_name), ''), 'Unknown Form') AS provider_form_name,
  q.question,
  q.answer,
  q.position
FROM opt_ins o
JOIN opt_in_question_answers q
  ON q.opt_in_id = o.id
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
WHERE o.clerk_org_id = :org_id
ORDER BY o.created_at DESC, q.position ASC, q.id ASC
LIMIT 50;
```

## Opt-In Trend by Day

```sql
SELECT
  DATE_TRUNC('day', o.created_at)::date AS opt_in_date,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
GROUP BY DATE_TRUNC('day', o.created_at)::date
ORDER BY opt_in_date ASC;
```

## Opt-In Trend by Day in a Date Range

```sql
SELECT
  DATE_TRUNC('day', o.created_at)::date AS opt_in_date,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins
FROM opt_ins o
WHERE o.clerk_org_id = :org_id
  AND o.created_at >= :start_date
  AND o.created_at < :end_date
GROUP BY DATE_TRUNC('day', o.created_at)::date
ORDER BY opt_in_date ASC;
```

## Opt-In Weekly Trend with Percentage Change

Use this when the user asks for weekly opt-in growth, weekly opt-in change, or week-over-week opt-in trend.

```sql
WITH weeks AS (
  SELECT generate_series(
    DATE_TRUNC('week', :start_date::timestamp)::date,
    DATE_TRUNC('week', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 week'
  )::date AS opt_in_week
),
weekly_counts AS (
  SELECT
    w.opt_in_week,
    COUNT(o.id) AS opt_in_count,
    COUNT(DISTINCT o.lead_id) AS unique_lead_count
  FROM weeks w
  LEFT JOIN opt_ins o
    ON DATE_TRUNC('week', o.created_at)::date = w.opt_in_week
   AND o.clerk_org_id = :org_id
   AND o.created_at >= :start_date
   AND o.created_at < :end_date
  GROUP BY w.opt_in_week
),
weekly_with_previous AS (
  SELECT
    opt_in_week,
    opt_in_count,
    unique_lead_count,
    LAG(opt_in_count) OVER (ORDER BY opt_in_week ASC) AS previous_period_opt_in_count
  FROM weekly_counts
)
SELECT
  opt_in_week,
  opt_in_count,
  unique_lead_count,
  previous_period_opt_in_count,
  CASE
    WHEN previous_period_opt_in_count IS NULL OR previous_period_opt_in_count = 0 THEN NULL
    ELSE ROUND(
      ((opt_in_count - previous_period_opt_in_count)::numeric / previous_period_opt_in_count) * 100,
      2
    )
  END AS percentage_change_from_previous_period,
  SUM(opt_in_count) OVER() AS total_matching_opt_ins
FROM weekly_with_previous
ORDER BY opt_in_week ASC;
```

## Opt-In Monthly Trend with Percentage Change

Use this when the user asks for monthly opt-in growth, monthly opt-in change, or month-over-month opt-in trend.

```sql
WITH months AS (
  SELECT generate_series(
    DATE_TRUNC('month', :start_date::timestamp)::date,
    DATE_TRUNC('month', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 month'
  )::date AS opt_in_month
),
monthly_counts AS (
  SELECT
    m.opt_in_month,
    COUNT(o.id) AS opt_in_count,
    COUNT(DISTINCT o.lead_id) AS unique_lead_count
  FROM months m
  LEFT JOIN opt_ins o
    ON DATE_TRUNC('month', o.created_at)::date = m.opt_in_month
   AND o.clerk_org_id = :org_id
   AND o.created_at >= :start_date
   AND o.created_at < :end_date
  GROUP BY m.opt_in_month
),
monthly_with_previous AS (
  SELECT
    opt_in_month,
    opt_in_count,
    unique_lead_count,
    LAG(opt_in_count) OVER (ORDER BY opt_in_month ASC) AS previous_period_opt_in_count
  FROM monthly_counts
)
SELECT
  opt_in_month,
  opt_in_count,
  unique_lead_count,
  previous_period_opt_in_count,
  CASE
    WHEN previous_period_opt_in_count IS NULL OR previous_period_opt_in_count = 0 THEN NULL
    ELSE ROUND(
      ((opt_in_count - previous_period_opt_in_count)::numeric / previous_period_opt_in_count) * 100,
      2
    )
  END AS percentage_change_from_previous_period,
  SUM(opt_in_count) OVER() AS total_matching_opt_ins
FROM monthly_with_previous
ORDER BY opt_in_month ASC;
```

## Weekly Opt-In Trend by UTM Campaign

Use this when the user asks:

- weekly trend by campaign
- week-wise opt-in trend by UTM campaign
- weekly campaign trend
- campaign-wise weekly opt-in trend

For campaign value, use `ta.utm_campaign` by default.

Use `:start_date` and `:end_date` for weekly trend queries.

Do not ask the user for a date range when they ask a generic weekly trend question. The application must provide a default 12-week window.

Return `previous_week_count` and `pct_change` so the final answer can show week-over-week movement by campaign.

```sql
WITH weeks AS (
  SELECT generate_series(
    DATE_TRUNC('week', :start_date::timestamp)::date,
    DATE_TRUNC('week', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 week'
  )::date AS week_start
),
campaigns AS (
  SELECT DISTINCT
    COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign
  FROM opt_ins o
  LEFT JOIN traffic_attributions ta
    ON ta.opt_in_id = o.id
  WHERE o.clerk_org_id = :org_id
    AND o.created_at >= :start_date
    AND o.created_at < :end_date
),
weekly_campaign_grid AS (
  SELECT
    w.week_start,
    c.utm_campaign
  FROM weeks w
  CROSS JOIN campaigns c
),
weekly_campaign_counts AS (
  SELECT
    DATE_TRUNC('week', o.created_at)::date AS week_start,
    COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
    COUNT(*) AS opt_in_count
  FROM opt_ins o
  LEFT JOIN traffic_attributions ta
    ON ta.opt_in_id = o.id
  WHERE o.clerk_org_id = :org_id
    AND o.created_at >= :start_date
    AND o.created_at < :end_date
  GROUP BY
    DATE_TRUNC('week', o.created_at)::date,
    COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown')
),
weekly_campaign_filled AS (
  SELECT
    wcg.week_start,
    wcg.utm_campaign,
    COALESCE(wcc.opt_in_count, 0) AS opt_in_count
  FROM weekly_campaign_grid wcg
  LEFT JOIN weekly_campaign_counts wcc
    ON wcc.week_start = wcg.week_start
   AND wcc.utm_campaign = wcg.utm_campaign
),
weekly_campaign_trend AS (
  SELECT
    week_start,
    utm_campaign,
    opt_in_count,
    LAG(opt_in_count) OVER (
      PARTITION BY utm_campaign
      ORDER BY week_start
    ) AS previous_week_count
  FROM weekly_campaign_filled
),
total AS (
  SELECT SUM(opt_in_count) AS total_opt_ins
  FROM weekly_campaign_filled
)
SELECT
  wct.week_start,
  wct.utm_campaign,
  wct.opt_in_count,
  wct.previous_week_count,
  CASE
    WHEN wct.previous_week_count IS NULL OR wct.previous_week_count = 0 THEN NULL
    ELSE ROUND(
      (wct.opt_in_count - wct.previous_week_count) * 100.0 / wct.previous_week_count,
      2
    )
  END AS pct_change,
  t.total_opt_ins AS total_matching_opt_ins
FROM weekly_campaign_trend wct
CROSS JOIN total t
ORDER BY wct.week_start ASC, wct.utm_campaign ASC;
```

## Weekly Opt-In Trend by Landing Page

Use this when the user asks for weekly opt-in trend by landing page.

```sql
WITH weeks AS (
  SELECT generate_series(
    DATE_TRUNC('week', :start_date::timestamp)::date,
    DATE_TRUNC('week', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 week'
  )::date AS week_start
),
landing_pages AS (
  SELECT DISTINCT
    COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown') AS landing_page
  FROM opt_ins o
  LEFT JOIN traffic_attributions ta
    ON ta.opt_in_id = o.id
  WHERE o.clerk_org_id = :org_id
    AND o.created_at >= :start_date
    AND o.created_at < :end_date
),
weekly_landing_grid AS (
  SELECT
    w.week_start,
    lp.landing_page
  FROM weeks w
  CROSS JOIN landing_pages lp
),
weekly_landing_counts AS (
  SELECT
    DATE_TRUNC('week', o.created_at)::date AS week_start,
    COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown') AS landing_page,
    COUNT(*) AS opt_in_count
  FROM opt_ins o
  LEFT JOIN traffic_attributions ta
    ON ta.opt_in_id = o.id
  WHERE o.clerk_org_id = :org_id
    AND o.created_at >= :start_date
    AND o.created_at < :end_date
  GROUP BY
    DATE_TRUNC('week', o.created_at)::date,
    COALESCE(NULLIF(TRIM(ta.landing_page), ''), 'Unknown')
),
weekly_landing_filled AS (
  SELECT
    wlg.week_start,
    wlg.landing_page,
    COALESCE(wlc.opt_in_count, 0) AS opt_in_count
  FROM weekly_landing_grid wlg
  LEFT JOIN weekly_landing_counts wlc
    ON wlc.week_start = wlg.week_start
   AND wlc.landing_page = wlg.landing_page
),
weekly_landing_trend AS (
  SELECT
    week_start,
    landing_page,
    opt_in_count,
    LAG(opt_in_count) OVER (
      PARTITION BY landing_page
      ORDER BY week_start
    ) AS previous_week_count
  FROM weekly_landing_filled
),
total AS (
  SELECT SUM(opt_in_count) AS total_opt_ins
  FROM weekly_landing_filled
)
SELECT
  wlt.week_start,
  wlt.landing_page,
  wlt.opt_in_count,
  wlt.previous_week_count,
  CASE
    WHEN wlt.previous_week_count IS NULL OR wlt.previous_week_count = 0 THEN NULL
    ELSE ROUND(
      (wlt.opt_in_count - wlt.previous_week_count) * 100.0 / wlt.previous_week_count,
      2
    )
  END AS pct_change,
  t.total_opt_ins AS total_matching_opt_ins
FROM weekly_landing_trend wlt
CROSS JOIN total t
ORDER BY wlt.week_start ASC, wlt.landing_page ASC;
```

## Won Lead Rate by UTM Campaign

Use this when the user asks which UTM campaign produced the most won leads or asks for won-lead rate by campaign.

This uses current lead status. It does not calculate revenue.

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
  COUNT(*) AS opt_in_count,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  COUNT(DISTINCT o.lead_id) FILTER (WHERE ss.role = 'WON') AS won_lead_count,
  ROUND(
    100.0 * COUNT(DISTINCT o.lead_id) FILTER (WHERE ss.role = 'WON') / NULLIF(COUNT(DISTINCT o.lead_id), 0),
    2
  ) AS won_lead_rate_percent,
  SUM(COUNT(*)) OVER() AS total_matching_opt_ins
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE o.clerk_org_id = :org_id
GROUP BY COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown')
ORDER BY won_lead_count DESC, won_lead_rate_percent DESC NULLS LAST, unique_lead_count DESC, utm_campaign ASC;
```

## Current Lead Status by UTM Campaign

Use this when the user asks for acquisition campaign performance by current lead status.

```sql
SELECT
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown') AS utm_campaign,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  COUNT(DISTINCT o.lead_id) AS unique_lead_count,
  SUM(COUNT(DISTINCT o.lead_id)) OVER() AS total_grouped_unique_lead_count,
  ROUND(
    COUNT(DISTINCT o.lead_id) * 100.0 / NULLIF(SUM(COUNT(DISTINCT o.lead_id)) OVER(), 0),
    2
  ) AS percentage_of_grouped_total
FROM opt_ins o
LEFT JOIN traffic_attributions ta
  ON ta.opt_in_id = o.id
LEFT JOIN leads l
  ON l.id = o.lead_id
 AND l.clerk_org_id = o.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE o.clerk_org_id = :org_id
GROUP BY
  COALESCE(NULLIF(TRIM(ta.utm_campaign), ''), 'Unknown'),
  COALESCE(CAST(ss.role AS text), 'NO_STATUS')
ORDER BY unique_lead_count DESC, utm_campaign ASC, status_role ASC;
```

## First Opt-In Attribution by UTM Campaign

Use this only when the user explicitly asks for first-touch opt-in attribution.

```sql
WITH ranked_opt_ins AS (
  SELECT
    o.id,
    o.lead_id,
    o.clerk_org_id,
    o.created_at,
    ta.utm_campaign,
    ROW_NUMBER() OVER (
      PARTITION BY o.lead_id
      ORDER BY o.created_at ASC, o.id ASC
    ) AS rn
  FROM opt_ins o
  LEFT JOIN traffic_attributions ta
    ON ta.opt_in_id = o.id
  WHERE o.clerk_org_id = :org_id
)
SELECT
  COALESCE(NULLIF(TRIM(roi.utm_campaign), ''), 'Unknown') AS first_touch_utm_campaign,
  COUNT(DISTINCT roi.lead_id) AS unique_lead_count,
  SUM(COUNT(DISTINCT roi.lead_id)) OVER() AS total_unique_leads,
  ROUND(
    COUNT(DISTINCT roi.lead_id) * 100.0 / NULLIF(SUM(COUNT(DISTINCT roi.lead_id)) OVER(), 0),
    2
  ) AS percentage_of_total
FROM ranked_opt_ins roi
WHERE roi.rn = 1
GROUP BY COALESCE(NULLIF(TRIM(roi.utm_campaign), ''), 'Unknown')
ORDER BY unique_lead_count DESC, first_touch_utm_campaign ASC;
```

## Last Opt-In Attribution by UTM Campaign

Use this only when the user explicitly asks for last-touch opt-in attribution.

```sql
WITH ranked_opt_ins AS (
  SELECT
    o.id,
    o.lead_id,
    o.clerk_org_id,
    o.created_at,
    ta.utm_campaign,
    ROW_NUMBER() OVER (
      PARTITION BY o.lead_id
      ORDER BY o.created_at DESC, o.id DESC
    ) AS rn
  FROM opt_ins o
  LEFT JOIN traffic_attributions ta
    ON ta.opt_in_id = o.id
  WHERE o.clerk_org_id = :org_id
)
SELECT
  COALESCE(NULLIF(TRIM(roi.utm_campaign), ''), 'Unknown') AS last_touch_utm_campaign,
  COUNT(DISTINCT roi.lead_id) AS unique_lead_count,
  SUM(COUNT(DISTINCT roi.lead_id)) OVER() AS total_unique_leads,
  ROUND(
    COUNT(DISTINCT roi.lead_id) * 100.0 / NULLIF(SUM(COUNT(DISTINCT roi.lead_id)) OVER(), 0),
    2
  ) AS percentage_of_total
FROM ranked_opt_ins roi
WHERE roi.rn = 1
GROUP BY COALESCE(NULLIF(TRIM(roi.utm_campaign), ''), 'Unknown')
ORDER BY unique_lead_count DESC, last_touch_utm_campaign ASC;
```

## Mistakes To Avoid

- Do not count opt-ins and unique leads as the same metric.
- Do not use `leads.created_at` for opt-in submission timing. Use `opt_ins.created_at`.
- Do not use `traffic_attributions.created_at` for acquisition trend unless the user explicitly asks for attribution row creation timing.
- Do not query `opt_in_question_answers` without joining through `opt_ins` and filtering `o.clerk_org_id = :org_id`.
- Do not query `traffic_attributions` without joining through `opt_ins` and filtering `o.clerk_org_id = :org_id`.
- Do not select `opt_ins.raw_payload`.
- Do not expose IP address, user agent, provider form ID, or external reference by default.
- Do not include lead email or phone unless explicitly requested.
- Do not invent setter names from `setter_id`.
- Do not use `o.source` and `ta.utm_source` interchangeably. They are different fields.
- Do not use raw lead first/last source or normalized marketing source reporting in this skill. Use `lead_analytics` for that.
- Do not calculate appointment no-show rate, appointment booking performance, or Fathom analytics from this skill. Use `appointment_analytics`.
- Do not calculate revenue by campaign, payment status by campaign, or refund impact from this skill. Use `revenue_analytics` or a future cross-domain attribution skill if revenue joins are required.
- Do not perform broad qualitative theme analysis from form answer text using SQL alone. Route deep theme discovery to `semantic_context`.
- Do not use `SELECT *`.
- Do not generate SQL without a tenant filter.
- Do not generate non-read SQL.
- Do not answer lead-only, appointment, revenue, integration, or full lead timeline questions from this skill.

## Related Skills

- `lead_analytics`: lead counts, lead statuses, normalized marketing sources, owners, setters, stale leads, follow-up.
- `appointment_analytics`: appointments, appointment outcomes, appointment no-show rate, Fathom call records.
- `revenue_analytics`: programs, contracts, payments, payment links, proofs, refunds, invoices, subscriptions.
- `lead_360`: single-lead complete view across notes, calls, contracts, payments, opt-ins, and timeline.
- `integration_health`: provider connections, webhook health, API validation, integration failures.
- `semantic_context`: pgvector or hybrid semantic search over notes, call summaries, objections, action items, and form answers.
