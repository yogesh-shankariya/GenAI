# Skill: `lead_analytics`

## Short Description

Use this skill for read-only SQL questions about leads, including lead counts, lead status, pipeline status roles, lead assignment, setter assignment, lead source fields, next follow-up, overdue follow-up, and stale lead analysis.

This skill must generate SQL only. The application will execute the SQL through a safe read-only database helper.

## When To Use This Skill

Use `lead_analytics` for read-only SQL analytics questions related to leads, lead counts, lead statuses, pipeline roles, lead assignment, setter assignment, lead source fields, next touch points, overdue follow-ups, and stale lead analysis.

Use this skill for:

- Total lead counts and active lead counts.
- New lead counts based on normalized lead status role.
- Lead counts by pipeline role, such as won, lost, follow-up, no-show, appointment booked, unqualified, partial payment, cancelled, or rescheduled.
- Lead breakdowns by exact status name.
- Lead breakdowns by normalized pipeline role.
- Leads with no status.
- Leads with no owner or assignee.
- Leads with no setter.
- Leads with no next touch point.
- Leads that need operational follow-up.
- Leads with overdue follow-ups.
- Stale or stuck lead analysis.
- Lead source distribution using normalized first-touch source by default.
- Last-touch source distribution when the user explicitly asks for latest source or last source.
- High-level lead source enum analysis, such as Calendly, Typeform, landing page, manual, webinar, newsletter, or other.
- Lead assignment breakdown by owner or assignee.
- Lead setter breakdown by setter.
- Lead creation counts and trends by today, week, month, or custom date range.

## When Not To Use This Skill

Do not use this skill for:

- Payment, invoice, refund, contract, subscription, or revenue questions. Use `revenue_analytics`.
- Appointment/call/no-show details beyond current lead status. Use `appointment_analytics`.
- Appointment no-show rate, no-shows by appointment type, no-shows by call date, no-shows by host, or no-shows by Calendly event. Use `appointment_analytics`.
- Form-answer, UTM, landing-page, traffic attribution, or opt-in question analysis. Use `acquisition_analytics`.
- Full single-lead summaries with notes, calls, contracts, payments, Fathom records, or full timeline. Use `lead_360`.
- Provider integration health, webhook troubleshooting, credential validation, API keys, webhook payloads, or connection status. Use an integration/admin skill.

If the user question requires tables outside `leads`, `sales_statuses`, or `marketing_sources`, do not use this skill unless the required logic is explicitly listed in this file.

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

Every business query must include an organization filter:

```sql
WHERE l.clerk_org_id = :org_id
```

For `leads`, always exclude soft-deleted rows unless the user explicitly asks about deleted leads:

```sql
AND l.is_deleted = false
```

Always use parameterized SQL for organization scope and dynamic values.

Use named parameters such as:

- `:org_id`
- `:start_date`
- `:end_date`
- `:status_role`
- `:status_name`
- `:lead_source`
- `:limit`

Do not hardcode the organization ID in generated agent SQL except in local manual debugging.

For aggregate analytics questions, return aggregate columns only.

For list-style questions such as "which leads", select only the fields needed to answer the question, add a deterministic `ORDER BY`, and cap the result with a reasonable `LIMIT` unless the user asks for a specific limit.

Default list limit: `20`.

Do not include lead email or phone fields in list outputs unless the user explicitly asks for contact details.

`assigned_to` and `setter_id` are user IDs. Do not invent rep or setter names unless a future user/profile table is available in another skill.

## Primary Tables

## `leads`

One row is one lead/prospect/customer.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Lead primary key. | Join key and lead identity. |
| `clerk_org_id` | Tenant/organization ID. | Required filter. |
| `first_name` | First name. | Display and search. |
| `last_name` | Last name. | Display and search. |
| `full_name` | Generated/display full name. | Display and search. |
| `email` | Lead email. | Search and identity only when explicitly requested. |
| `phone_e164` | Phone number in E.164 format. | Contact detail only when explicitly requested. |
| `phone_country` | Phone country. | Geographic/contact context only when needed. |
| `source` | Lead source enum. | High-level source reporting. |
| `assigned_to` | Owner/assignee user ID. | Owner performance and missing owner checks. |
| `setter_id` | Setter user ID. | Setter performance and missing setter checks. |
| `external_reference` | External provider reference. | Provider/debug context only when explicitly requested. |
| `status_id` | Current sales status ID. | Join to `sales_statuses.id`. |
| `next_touch_point_at` | Next planned follow-up datetime. | Follow-up, overdue, stale lead analysis. |
| `next_touch_point_type` | Type of next touch point. | Follow-up channel analysis. |
| `mollie_customer_id` | Mollie customer reference. | Payment provider context only; normally do not use in this skill. |
| `first_source_id` | First normalized marketing source ID. | Join to `marketing_sources.id`. |
| `first_source_name` | First source snapshot/name. | Source analysis without join. |
| `last_source_id` | Last normalized marketing source ID. | Join to `marketing_sources.id`. |
| `last_source_name` | Last source snapshot/name. | Source analysis without join. |
| `ai_source_summary` | AI-generated source summary. | Optional source explanation. |
| `created_by` | User/system that created lead. | Admin context only when needed. |
| `created_at` | Lead creation datetime. | Date filtering and trend analysis. |
| `updated_at` | Last record update datetime. | Recency approximation only. Do not treat as sales activity unless the user asks for updated records. |
| `is_deleted` | Soft-delete flag. | Usually filter false. |
| `deleted_at` | Deletion datetime. | Deleted-lead analysis only. |

Required default filter:

```sql
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
```

## `sales_statuses`

One row is a readable pipeline status or appointment outcome for an organization.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Status primary key. | Join from `leads.status_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `name` | Human-readable status name. | Display exact status. |
| `description` | Status description. | Explain status if available. |
| `role` | Normalized status role enum. | Group statuses into business categories. |
| `is_default` | Whether default status. | Setup/admin context. |
| `is_system` | Whether system-created status. | Setup/admin context. |

Join from leads:

```sql
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
```

Use `role` when the user asks for general business categories like won, lost, follow-up, no-show, new lead, appointment booked, or unqualified.

Use `name` when the user asks for exact pipeline status labels.

Do not join `sales_statuses` without matching `clerk_org_id`.

## `marketing_sources`

One row is a normalized marketing source for an organization.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Marketing source primary key. | Join from `leads.first_source_id` or `leads.last_source_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `name` | Normalized source name. | Source reporting. |
| `aliases` | Alternate UTM/source aliases. | Source normalization context. |
| `description` | Source description. | Optional explanation. |
| `is_archived` | Archived source flag. | Usually keep for historical reporting. |

First source join:

```sql
LEFT JOIN marketing_sources first_ms
  ON first_ms.id = l.first_source_id
 AND first_ms.clerk_org_id = l.clerk_org_id
```

Last source join:

```sql
LEFT JOIN marketing_sources last_ms
  ON last_ms.id = l.last_source_id
 AND last_ms.clerk_org_id = l.clerk_org_id
```

For source reports, prefer normalized marketing source joins by ID. Use `first_source_name` and `last_source_name` only as fallback display values when the corresponding source ID is missing or unmatched.

Use `marketing_sources` when the user asks for normalized source names, aliases, archived sources, or source descriptions.

Do not join `marketing_sources` without matching `clerk_org_id`.

## Enums

## `LeadSource`

Business-defined values:

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
| `CALENDLY` | Lead came from Calendly booking flow. |
| `MANUAL` | Lead was manually created. |
| `TYPEFORM` | Lead came from Typeform. |
| `WEBINAR` | Lead came from webinar flow. |
| `NEWSLETTER` | Lead came from newsletter flow. |
| `LANDING_PAGE` | Lead came from landing page. |
| `OTHER` | Source did not fit a more specific enum. |

Use `l.source` for high-level source enum reporting.

## `SalesStatusRole`

Business-defined values:

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

Use `ss.role` for normalized funnel analysis.

Meaning:

| Value | Meaning |
|---|---|
| `NEW_LEAD` | Fresh lead. |
| `APPOINTMENT_BOOKED` | Lead has a booked appointment. |
| `NO_SHOW` | Lead missed a call or is marked no-show in pipeline status. |
| `RESCHEDULED` | Appointment or next step was rescheduled. |
| `CANCELED` | Appointment/deal was canceled. |
| `PARTIAL_PAYMENT` | Lead partially paid. |
| `WON` | Converted/won. |
| `UNQUALIFIED` | Not qualified. |
| `FOLLOW_UP` | Lead is in the Follow Up status role. This is not the same as operationally needing follow-up action. |
| `LOST` | Lost lead/deal. |

## `NextTouchPointType`

Business-defined values:

```text
PHONE_CALL
WHATSAPP
EMAIL
FOLLOW_UP_CALL
PROPOSAL_REVIEW
OTHER
```

Use this when the user asks about follow-up channel or next action type.

## Business Interpretation Rules

## New Leads

When the user says "new leads" without a date range, interpret it as the normalized status role:

```sql
ss.role = 'NEW_LEAD'
```

When the user asks for leads created today, this week, this month, or in another timeframe, use `l.created_at`.

When the user asks for "new leads today", "new leads this week", or "new leads this month", combine:

```sql
ss.role = 'NEW_LEAD'
```

with the `l.created_at` timeframe filter.

## No-Show Leads

If the user asks:

- How many no-show leads?
- Which leads are no-show?
- Leads marked as no-show

Use:

```sql
ss.role = 'NO_SHOW'
```

If the user asks about appointment no-show rate, no-shows by appointment type, no-shows by call date, no-shows by host, or no-shows by Calendly event, do not use this skill. Use `appointment_analytics`.

## Operational Follow-Up and Stale Lead Rules

## Follow-Up Meaning

When the user says "need follow-up", "needs follow-up", "needing follow-up", "follow-up needed", "waiting for follow-up", or "need action", use operational follow-up logic:

- exclude terminal statuses: `WON`, `LOST`, `UNQUALIFIED`, `CANCELED`
- include leads where `l.next_touch_point_at IS NULL OR l.next_touch_point_at < NOW()`

Do not use only `ss.role = 'FOLLOW_UP'` for "need follow-up" questions.

Use `ss.role = 'FOLLOW_UP'` only when the user explicitly asks for "Follow Up status", "Follow Up stage", or "marked as Follow Up".

Example:

- "How many Calendly leads need follow-up?" -> use `next_touch_point_at` logic.
- "How many Calendly leads are in Follow Up status?" -> use `ss.role = 'FOLLOW_UP'`.

For operational questions such as:

- Which leads are stale?
- Which leads need follow-up?
- Which leads are overdue?
- Which leads have no next touch point?
- Which leads are stuck?

Exclude terminal statuses by default:

- `WON`
- `LOST`
- `UNQUALIFIED`
- `CANCELED`

Only include terminal statuses if the user explicitly asks for them.

Default stale lead definition:

A lead is stale if:

1. The lead is not deleted.
2. The lead is not in a terminal status.
3. The lead either:
   - has no `next_touch_point_at`, or
   - has `next_touch_point_at` in the past.

Use `updated_at` only when the user specifically asks for records not updated in a timeframe.

Do not treat `updated_at` as sales activity unless the user accepts that approximation.

## Missing Owner and Setter Rules

For `assigned_to` and `setter_id`, treat both `NULL` and blank strings as missing.

Use:

```sql
NULLIF(TRIM(l.assigned_to), '') IS NULL
```

and:

```sql
NULLIF(TRIM(l.setter_id), '') IS NULL
```

For grouping, use:

```sql
COALESCE(NULLIF(TRIM(l.assigned_to), ''), 'Unassigned') AS assigned_to
```

and:

```sql
COALESCE(NULLIF(TRIM(l.setter_id), ''), 'No Setter') AS setter_id
```

Do not invent owner or setter names. These fields are user IDs.

## Timeframe Rules

When the user asks for leads created today, this week, this month, or within a custom date range, use `l.created_at`.

Prefer application-provided date parameters:

```sql
l.created_at >= :start_date
AND l.created_at < :end_date
```

Do not hardcode dates inside generated SQL.

Use `next_touch_point_at` for follow-up timing questions.

Prefer application-provided date parameters for follow-up windows:

```sql
l.next_touch_point_at >= :start_date
AND l.next_touch_point_at < :end_date
```

If the user asks for overdue follow-ups, use:

```sql
l.next_touch_point_at IS NOT NULL
AND l.next_touch_point_at < NOW()
```

If the user gives a specific stale timeframe, use their timeframe instead of the default stale rule.

## Previous Completed Month Lead Change

Use this when the user asks:

- did leads increase or decrease previous month
- previous month growth
- last month compared to the month before
- did leads go up or down last month

Compare the previous completed month against the month before the previous completed month.

Do not compare the current month against the previous month unless the user explicitly asks for current month or month-to-date.

Ensure both months are returned, even if one month has zero leads.

```sql
WITH month_range AS (
  SELECT generate_series(
    DATE_TRUNC('month', CURRENT_DATE)::date - INTERVAL '2 months',
    DATE_TRUNC('month', CURRENT_DATE)::date - INTERVAL '1 month',
    INTERVAL '1 month'
  )::date AS month_start
),
monthly_counts AS (
  SELECT
    mr.month_start,
    COUNT(l.id) AS lead_count
  FROM month_range mr
  LEFT JOIN leads l
    ON DATE_TRUNC('month', l.created_at)::date = mr.month_start
   AND l.clerk_org_id = :org_id
   AND l.is_deleted = false
   AND l.created_at >= DATE_TRUNC('month', CURRENT_DATE)::date - INTERVAL '2 months'
   AND l.created_at < DATE_TRUNC('month', CURRENT_DATE)::date
  GROUP BY mr.month_start
),
monthly_with_change AS (
  SELECT
    month_start,
    lead_count,
    LAG(lead_count) OVER (ORDER BY month_start) AS previous_month_count
  FROM monthly_counts
)
SELECT
  TO_CHAR(month_start, 'Mon YYYY') AS month,
  lead_count,
  previous_month_count,
  CASE
    WHEN previous_month_count IS NULL OR previous_month_count = 0 THEN NULL
    ELSE ROUND((lead_count - previous_month_count) * 100.0 / previous_month_count, 2)
  END AS pct_change,
  CASE
    WHEN previous_month_count IS NULL THEN 'N/A'
    WHEN lead_count > previous_month_count THEN 'Increased'
    WHEN lead_count < previous_month_count THEN 'Decreased'
    ELSE 'No Change'
  END AS trend
FROM monthly_with_change
ORDER BY month_start ASC;
```

## Default List Output Rules

For list-style lead queries, default output fields are:

- `l.id`
- `display_name`
- `status_name`
- `status_role`
- `assigned_to`
- `setter_id`
- `source`
- `next_touch_point_at`
- `created_at`
- `updated_at`

Use this display name expression:

```sql
COALESCE(
  NULLIF(TRIM(l.full_name), ''),
  NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
  l.first_name,
  'Unknown Lead'
) AS display_name
```

Do not include `email`, `phone_e164`, or `phone_country` unless the user explicitly asks for contact details.

Use `LIMIT :limit` when the application passes a limit.

If the application does not pass a limit and the user does not request one, use:

```sql
LIMIT 20
```

Always use deterministic ordering, such as:

```sql
ORDER BY l.created_at DESC, l.id ASC
```

or, for follow-up/stale lists:

```sql
ORDER BY l.next_touch_point_at NULLS FIRST, l.updated_at ASC, l.created_at ASC, l.id ASC
```

For list-style queries with `LIMIT`, include the exact total matching row count whenever possible.

Use:

```sql
COUNT(*) OVER() AS total_matching_rows
```

## Source Selection and Marketing Source Join Rules

The `leads` table has three different source concepts:

- `l.source` = high-level lead source enum, such as CALENDLY, MANUAL, TYPEFORM, WEBINAR, NEWSLETTER, LANDING_PAGE, OTHER.
- `l.first_source_id` / `l.first_source_name` = original or first-touch marketing source.
- `l.last_source_id` / `l.last_source_name` = latest or last-touch marketing source.

Always join marketing sources by ID, not by name.

Correct first source join:

    LEFT JOIN marketing_sources first_ms
      ON first_ms.id = l.first_source_id
     AND first_ms.clerk_org_id = l.clerk_org_id

Correct last source join:

    LEFT JOIN marketing_sources last_ms
      ON last_ms.id = l.last_source_id
     AND last_ms.clerk_org_id = l.clerk_org_id

Do not join using:

    first_ms.name = l.first_source_name
    last_ms.name = l.last_source_name

Default source behavior:

- For generic questions like "source distribution", "lead source breakdown", "which source generated the most leads", "top source", or "where are leads coming from", use first-touch source by default:
  `l.first_source_id -> marketing_sources.id`, display `first_ms.name`.

- For latest source questions like "latest source distribution", "last source breakdown", "last-touch source", "recent source", or "what was the latest source before conversion", use last-touch source:
  `l.last_source_id -> marketing_sources.id`, display `last_ms.name`.

- Use `l.first_source_name` only as fallback when `l.first_source_id` is NULL or has no matching marketing source row.

- Use `l.last_source_name` only as fallback when `l.last_source_id` is NULL or has no matching marketing source row.

- Use `l.source` only when the user asks for high-level source category or enum source such as Calendly, Manual, Typeform, Webinar, Newsletter, Landing Page, or Other.

- Do not use raw `first_source_name` or `last_source_name` directly for distribution reports unless the user explicitly asks for raw source names.

## Common Query Patterns

## Count Active Leads

```sql
SELECT COUNT(*) AS active_leads
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false;
```

## Count New Leads

```sql
SELECT COUNT(*) AS new_leads
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND ss.role = 'NEW_LEAD';
```

## Count Leads Created in a Date Range

```sql
SELECT COUNT(*) AS leads_created_in_period
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND l.created_at >= :start_date
  AND l.created_at < :end_date;
```

## Count New Leads Created in a Date Range

```sql
SELECT COUNT(*) AS new_leads_created_in_period
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND ss.role = 'NEW_LEAD'
  AND l.created_at >= :start_date
  AND l.created_at < :end_date;
```

## Leads by Exact Status Name

```sql
SELECT
  COALESCE(ss.name, 'No Status') AS status_name,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(ss.name, 'No Status')
ORDER BY lead_count DESC, status_name ASC;
```

## Leads by Normalized Status Role

```sql
SELECT
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(CAST(ss.role AS text), 'NO_STATUS')
ORDER BY lead_count DESC, status_role ASC;
```

## Count Leads by a Specific Normalized Status Role

```sql
SELECT COUNT(*) AS lead_count
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND ss.role = :status_role;
```

## Leads by Source Enum

```sql
SELECT
  COALESCE(CAST(l.source AS text), 'Unknown') AS source,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(CAST(l.source AS text), 'Unknown')
ORDER BY lead_count DESC, source ASC;
```

## Default Source Distribution

Use this for generic source questions such as:

- give me all distribution of source
- source distribution
- lead source breakdown
- which source generated the most leads
- top source
- where are most leads coming from
- normalized first source counts

Default interpretation: first-touch normalized marketing source.

This pattern also covers normalized first source count questions.  
Use `l.first_source_id -> marketing_sources.id` and display `first_ms.name`, with `l.first_source_name` only as fallback when the source ID is missing or unmatched.

```sql
WITH source_counts AS (
  SELECT
    COALESCE(
      NULLIF(TRIM(first_ms.name), ''),
      NULLIF(TRIM(l.first_source_name), ''),
      'Unknown'
    ) AS source,
    COUNT(*) AS lead_count
  FROM leads l
  LEFT JOIN marketing_sources first_ms
    ON first_ms.id = l.first_source_id
   AND first_ms.clerk_org_id = l.clerk_org_id
  WHERE l.clerk_org_id = :org_id
    AND l.is_deleted = false
  GROUP BY COALESCE(
    NULLIF(TRIM(first_ms.name), ''),
    NULLIF(TRIM(l.first_source_name), ''),
    'Unknown'
  )
),
total AS (
  SELECT SUM(lead_count) AS total_leads
  FROM source_counts
)
SELECT
  sc.source,
  sc.lead_count,
  t.total_leads AS total_matching_leads,
  ROUND(sc.lead_count * 100.0 / NULLIF(t.total_leads, 0), 2) AS percentage_of_total
FROM source_counts sc
CROSS JOIN total t
ORDER BY sc.lead_count DESC, sc.source ASC;
```

## Weekly Lead Trend by Source

Use this when the user asks:

- weekly trend by source
- week-wise lead trend by source
- weekly source trend
- source-wise weekly lead trend
- how leads changed week by week for each source

This is a trend query, not only a weekly distribution query.

For source value, use first-touch normalized marketing source by default:

- `l.first_source_id -> marketing_sources.id`
- display `first_ms.name`
- fallback to `l.first_source_name`
- fallback to `Unknown`

Do not fallback to `l.source` unless the user explicitly asks for high-level source enum reporting.

Use `:start_date` and `:end_date` for weekly trend queries.

Do not ask the user for a date range when they ask a generic weekly trend question.

If the user does not specify a date range, still generate the SQL using `:start_date` and `:end_date`. The application must provide a default 12-week window:

- `:start_date` = start of the week 12 weeks before the current week
- `:end_date` = start of the next week, or the application-defined reporting cutoff

Only ask the user for a date range if they explicitly request a custom period but the period is ambiguous.

Return `previous_week_count` and `pct_change` so the final answer can show week-over-week movement by source.

For SQL generation:

- Keep the SQL row-based.
- Return `week_start`, `source`, `lead_count`, `previous_week_count`, `pct_change`, and helper total columns.
- Do not generate SQL pivot columns with hardcoded week dates.
- Do not create one SQL column per week.
- Do not create separate SQL columns like `2026-03-02_count` and `2026-03-02_pct_change` unless the user explicitly asks for pivot SQL.

For final answer formatting:

- Prefer source in rows and weeks in columns when there are 12 or fewer weeks and 20 or fewer sources.
- Each cell should show `lead_count` and `pct_change` together when `pct_change` is available.
- Use this cell format: `85 (+142.86%)`
- For negative change, use this format: `41 (-51.76%)`
- For zero change, use this format: `1 (0.00%)`
- For the first week or when `pct_change` is unavailable, show only the count.
- If there are more than 12 weeks, show only the latest 12 weeks unless the user explicitly asks for all weeks.

```sql
WITH weeks AS (
  SELECT generate_series(
    DATE_TRUNC('week', :start_date::timestamp)::date,
    DATE_TRUNC('week', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 week'
  )::date AS week_start
),
sources AS (
  SELECT DISTINCT
    COALESCE(
      NULLIF(TRIM(first_ms.name), ''),
      NULLIF(TRIM(l.first_source_name), ''),
      'Unknown'
    ) AS source
  FROM leads l
  LEFT JOIN marketing_sources first_ms
    ON first_ms.id = l.first_source_id
   AND first_ms.clerk_org_id = l.clerk_org_id
  WHERE l.clerk_org_id = :org_id
    AND l.is_deleted = false
    AND l.created_at >= :start_date
    AND l.created_at < :end_date
),
weekly_source_grid AS (
  SELECT
    w.week_start,
    s.source
  FROM weeks w
  CROSS JOIN sources s
),
weekly_source_counts AS (
  SELECT
    DATE_TRUNC('week', l.created_at)::date AS week_start,
    COALESCE(
      NULLIF(TRIM(first_ms.name), ''),
      NULLIF(TRIM(l.first_source_name), ''),
      'Unknown'
    ) AS source,
    COUNT(*) AS lead_count
  FROM leads l
  LEFT JOIN marketing_sources first_ms
    ON first_ms.id = l.first_source_id
   AND first_ms.clerk_org_id = l.clerk_org_id
  WHERE l.clerk_org_id = :org_id
    AND l.is_deleted = false
    AND l.created_at >= :start_date
    AND l.created_at < :end_date
  GROUP BY
    DATE_TRUNC('week', l.created_at)::date,
    COALESCE(
      NULLIF(TRIM(first_ms.name), ''),
      NULLIF(TRIM(l.first_source_name), ''),
      'Unknown'
    )
),
weekly_source_filled AS (
  SELECT
    wsg.week_start,
    wsg.source,
    COALESCE(wsc.lead_count, 0) AS lead_count
  FROM weekly_source_grid wsg
  LEFT JOIN weekly_source_counts wsc
    ON wsc.week_start = wsg.week_start
   AND wsc.source = wsg.source
),
weekly_source_trend AS (
  SELECT
    week_start,
    source,
    lead_count,
    LAG(lead_count) OVER (
      PARTITION BY source
      ORDER BY week_start
    ) AS previous_week_count
  FROM weekly_source_filled
),
total AS (
  SELECT SUM(lead_count) AS total_leads
  FROM weekly_source_filled
)
SELECT
  wst.week_start,
  wst.source,
  wst.lead_count,
  wst.previous_week_count,
  CASE
    WHEN wst.previous_week_count IS NULL OR wst.previous_week_count = 0 THEN NULL
    ELSE ROUND(
      (wst.lead_count - wst.previous_week_count) * 100.0 / wst.previous_week_count,
      2
    )
  END AS pct_change,
  t.total_leads AS total_matching_leads
FROM weekly_source_trend wst
CROSS JOIN total t
ORDER BY wst.week_start ASC, wst.source ASC;
```


## Raw Leads by First Source Name

Use this only when the user explicitly asks for raw first source names.
Do not use this for generic source distribution or top source questions.

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown') AS first_source_name,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, first_source_name ASC;
```

## Raw Leads by Last Source Name

Use this only when the user explicitly asks for raw last source names.
Do not use this for generic source distribution or top source questions.

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown') AS last_source_name,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, last_source_name ASC;
```

## Raw Leads by First and Last Source Names

Use this only when the user explicitly asks to compare raw first source name and raw last source name.
Do not use this for generic source distribution or normalized source reporting.

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown') AS first_source_name,
  COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown') AS last_source_name,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY
  COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown'),
  COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, first_source_name ASC, last_source_name ASC;
```

## Leads with No Status

```sql
SELECT COUNT(*) AS leads_without_status
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND l.status_id IS NULL;
```

## Leads with No Owner

```sql
SELECT COUNT(*) AS unassigned_leads
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND NULLIF(TRIM(l.assigned_to), '') IS NULL;
```

## Leads with No Setter

```sql
SELECT COUNT(*) AS leads_without_setter
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND NULLIF(TRIM(l.setter_id), '') IS NULL;
```

## Leads Missing Next Touch Point

By default, exclude terminal statuses for operational follow-up questions.

```sql
SELECT COUNT(*) AS leads_missing_next_touch_point
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND COALESCE(CAST(ss.role AS text), 'NO_STATUS') NOT IN (
    'WON',
    'LOST',
    'UNQUALIFIED',
    'CANCELED'
  )
  AND l.next_touch_point_at IS NULL;
```

## Overdue Next Touch Points

By default, exclude terminal statuses for operational follow-up questions.

```sql
SELECT COUNT(*) AS overdue_next_touch_points
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND COALESCE(CAST(ss.role AS text), 'NO_STATUS') NOT IN (
    'WON',
    'LOST',
    'UNQUALIFIED',
    'CANCELED'
  )
  AND l.next_touch_point_at IS NOT NULL
  AND l.next_touch_point_at < NOW();
```

## Leads by Owner

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.assigned_to), ''), 'Unassigned') AS assigned_to,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.assigned_to), ''), 'Unassigned')
ORDER BY lead_count DESC, assigned_to ASC;
```

## Top Actual Setter by Lead Count

Use this when the user asks:

- which setter has the most leads
- top setter by lead count
- best setter by number of leads

Exclude missing setter values. Do not return `No Setter` as the top setter unless the user explicitly asks to include leads without a setter.

This query returns all setters tied for the highest lead count.

```sql
WITH setter_counts AS (
  SELECT
    NULLIF(TRIM(l.setter_id), '') AS setter_id,
    COUNT(*) AS lead_count
  FROM leads l
  WHERE l.clerk_org_id = :org_id
    AND l.is_deleted = false
    AND NULLIF(TRIM(l.setter_id), '') IS NOT NULL
  GROUP BY NULLIF(TRIM(l.setter_id), '')
),
max_count AS (
  SELECT MAX(lead_count) AS max_lead_count
  FROM setter_counts
)
SELECT
  sc.setter_id,
  sc.lead_count
FROM setter_counts sc
JOIN max_count mc
  ON sc.lead_count = mc.max_lead_count
ORDER BY sc.setter_id ASC;
```

## Leads by Setter

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.setter_id), ''), 'No Setter') AS setter_id,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.setter_id), ''), 'No Setter')
ORDER BY lead_count DESC, setter_id ASC;
```

## Lead Creation Trend by Day

```sql
SELECT
  DATE_TRUNC('day', l.created_at)::date AS lead_created_date,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY DATE_TRUNC('day', l.created_at)::date
ORDER BY lead_created_date ASC;
```

## Lead Creation Trend by Day in a Date Range

```sql
SELECT
  DATE_TRUNC('day', l.created_at)::date AS lead_created_date,
  COUNT(*) AS lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND l.created_at >= :start_date
  AND l.created_at < :end_date
GROUP BY DATE_TRUNC('day', l.created_at)::date
ORDER BY lead_created_date ASC;
```

## Stale Leads by Status

Use this when the user asks what leads are stuck, stale, overdue, or need action.

Default stale rule: lead is non-terminal and either has no `next_touch_point_at` or has `next_touch_point_at` in the past.

```sql
SELECT
  COALESCE(ss.name, 'No Status') AS status_name,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  COUNT(*) AS stale_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND COALESCE(CAST(ss.role AS text), 'NO_STATUS') NOT IN (
    'WON',
    'LOST',
    'UNQUALIFIED',
    'CANCELED'
  )
  AND (
    l.next_touch_point_at IS NULL
    OR l.next_touch_point_at < NOW()
  )
GROUP BY
  COALESCE(ss.name, 'No Status'),
  COALESCE(CAST(ss.role AS text), 'NO_STATUS')
ORDER BY stale_lead_count DESC, status_name ASC;
```

## Leads Not Updated in a Date Range or Timeframe

Use this only when the user specifically asks for leads not updated recently or not updated in a certain number of days.

Example for a parameterized cutoff:

```sql
SELECT
  COALESCE(ss.name, 'No Status') AS status_name,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  COUNT(*) AS not_updated_lead_count,
  SUM(COUNT(*)) OVER() AS total_matching_leads,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND l.updated_at < :cutoff_date
GROUP BY
  COALESCE(ss.name, 'No Status'),
  COALESCE(CAST(ss.role AS text), 'NO_STATUS')
ORDER BY not_updated_lead_count DESC, status_name ASC;
```

## List Stale Leads

Use this for "which leads are stale", "show stale leads", or "which leads need action".

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  l.id,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(ss.name, 'No Status') AS status_name,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  COALESCE(NULLIF(TRIM(l.assigned_to), ''), 'Unassigned') AS assigned_to,
  COALESCE(NULLIF(TRIM(l.setter_id), ''), 'No Setter') AS setter_id,
  l.source,
  l.next_touch_point_at,
  l.created_at,
  l.updated_at
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND COALESCE(CAST(ss.role AS text), 'NO_STATUS') NOT IN (
    'WON',
    'LOST',
    'UNQUALIFIED',
    'CANCELED'
  )
  AND (
    l.next_touch_point_at IS NULL
    OR l.next_touch_point_at < NOW()
  )
ORDER BY
  l.next_touch_point_at NULLS FIRST,
  l.updated_at ASC,
  l.created_at ASC,
  l.id ASC
LIMIT 20;
```

## List Leads with No Owner

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  l.id,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(ss.name, 'No Status') AS status_name,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  l.source,
  l.next_touch_point_at,
  l.created_at,
  l.updated_at
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND NULLIF(TRIM(l.assigned_to), '') IS NULL
ORDER BY l.created_at DESC, l.id ASC
LIMIT 20;
```

## List Leads with No Setter

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  l.id,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(ss.name, 'No Status') AS status_name,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  l.source,
  l.next_touch_point_at,
  l.created_at,
  l.updated_at
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
  AND NULLIF(TRIM(l.setter_id), '') IS NULL
ORDER BY l.created_at DESC, l.id ASC
LIMIT 20;
```

## List Leads with Contact Details

Use this only when the user explicitly asks for contact details, emails, or phone numbers.

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  l.id,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  l.email,
  l.phone_e164,
  COALESCE(ss.name, 'No Status') AS status_name,
  COALESCE(CAST(ss.role AS text), 'NO_STATUS') AS status_role,
  COALESCE(NULLIF(TRIM(l.assigned_to), ''), 'Unassigned') AS assigned_to,
  COALESCE(NULLIF(TRIM(l.setter_id), ''), 'No Setter') AS setter_id,
  l.source,
  l.created_at
FROM leads l
LEFT JOIN sales_statuses ss
  ON ss.id = l.status_id
 AND ss.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
ORDER BY l.created_at DESC, l.id ASC
LIMIT 20;
```

## Mistakes To Avoid

- Do not count deleted leads unless explicitly requested.
- Do not join `sales_statuses` without matching `clerk_org_id`.
- Do not join `marketing_sources` without matching `clerk_org_id`.
- Do not assume `source`, `first_source_name`, `last_source_name`, and normalized `marketing_sources.name` mean the same thing.
- Do not use raw payloads from opt-ins, webhooks, provider integrations, or any unrelated table in this skill.
- Do not treat `updated_at` as sales activity unless the user accepts that approximation or specifically asks for updated/not-updated records.
- Do not claim a lead is won based on revenue, payment, invoice, or contract logic. This skill can only use lead status role for lead-status reporting.
- Do not convert `assigned_to` or `setter_id` into names. They are user IDs in this skill.
- Do not include lead email or phone unless explicitly requested.
- Do not use `SELECT *`.
- Do not generate SQL without a tenant filter.
- Do not generate non-read SQL.
- Do not answer appointment, revenue, acquisition, integration, or full lead timeline questions from this skill.

## Related Skills

- `acquisition_analytics`: opt-ins, form answers, UTM, traffic attribution, landing pages.
- `appointment_analytics`: appointments, appointment outcomes, appointment no-show rate, Fathom call records.
- `revenue_analytics`: programs, contracts, payments, payment links, proofs, refunds, invoices, subscriptions.
- `lead_360`: single-lead complete view across notes, calls, contracts, payments, and timeline.
- `integration_health`: provider connections, webhook health, API validation, integration failures.
