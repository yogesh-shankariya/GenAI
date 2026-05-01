# Skill: `lead_analytics`

## Short Description

Use this skill for read-only SQL questions about leads, including lead counts, lead status, pipeline status roles, lead assignment, setter assignment, lead source fields, next follow-up, overdue follow-up, and stale lead analysis.

This skill must generate SQL only. The application will execute the SQL through a safe read-only database helper.

## When To Use This Skill

Use `lead_analytics` when the user asks questions like:

- How many leads do we have?
- How many active leads do we have?
- How many new leads are there?
- How many leads are won, lost, follow-up, no-show, appointment booked, or unqualified?
- What is the lead breakdown by status?
- What is the lead breakdown by pipeline role?
- Which leads have no status?
- Which leads have no owner?
- Which leads have no setter?
- Which leads have no next touch point?
- Which leads need follow-up?
- Which leads are overdue for follow-up?
- Which leads are stale or stuck?
- Which source has the most leads?
- How many leads came from Calendly, Typeform, landing page, manual, webinar, newsletter, or other?
- How many leads are assigned to each rep?
- How many leads are assigned to each setter?
- How many leads were created today, this week, this month, or during a specific date range?

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

Default list limit: `50`.

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

Use `leads.first_source_name` and `leads.last_source_name` when a simple source report is enough.

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
| `FOLLOW_UP` | Needs follow-up. |
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
LIMIT 50
```

Always use deterministic ordering, such as:

```sql
ORDER BY l.created_at DESC, l.id ASC
```

or, for follow-up/stale lists:

```sql
ORDER BY l.next_touch_point_at NULLS FIRST, l.updated_at ASC, l.created_at ASC, l.id ASC
```

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
  COUNT(*) AS lead_count
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
  COUNT(*) AS lead_count
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
  l.source,
  COUNT(*) AS lead_count
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY l.source
ORDER BY lead_count DESC, l.source ASC;
```

## Leads by First Source Name

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown') AS first_source_name,
  COUNT(*) AS lead_count
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, first_source_name ASC;
```

## Leads by Last Source Name

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown') AS last_source_name,
  COUNT(*) AS lead_count
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, last_source_name ASC;
```

## Leads by First and Last Source Names

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown') AS first_source_name,
  COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown') AS last_source_name,
  COUNT(*) AS lead_count
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY
  COALESCE(NULLIF(TRIM(l.first_source_name), ''), 'Unknown'),
  COALESCE(NULLIF(TRIM(l.last_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, first_source_name ASC, last_source_name ASC;
```

## Leads by Normalized Marketing Source

Use this when the user asks for normalized source names, source aliases, archived sources, or marketing source metadata.

```sql
SELECT
  COALESCE(first_ms.name, NULLIF(TRIM(l.first_source_name), ''), 'Unknown') AS normalized_first_source,
  COUNT(*) AS lead_count
FROM leads l
LEFT JOIN marketing_sources first_ms
  ON first_ms.id = l.first_source_id
 AND first_ms.clerk_org_id = l.clerk_org_id
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(first_ms.name, NULLIF(TRIM(l.first_source_name), ''), 'Unknown')
ORDER BY lead_count DESC, normalized_first_source ASC;
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
  COUNT(*) AS lead_count
FROM leads l
WHERE l.clerk_org_id = :org_id
  AND l.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(l.assigned_to), ''), 'Unassigned')
ORDER BY lead_count DESC, assigned_to ASC;
```

## Leads by Setter

```sql
SELECT
  COALESCE(NULLIF(TRIM(l.setter_id), ''), 'No Setter') AS setter_id,
  COUNT(*) AS lead_count
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
  COUNT(*) AS lead_count
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
  COUNT(*) AS lead_count
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
  COUNT(*) AS stale_lead_count
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
  COUNT(*) AS not_updated_lead_count
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
LIMIT 50;
```

## List Leads with No Owner

```sql
SELECT
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
LIMIT 50;
```

## List Leads with No Setter

```sql
SELECT
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
LIMIT 50;
```

## List Leads with Contact Details

Use this only when the user explicitly asks for contact details, emails, or phone numbers.

```sql
SELECT
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
LIMIT 50;
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
