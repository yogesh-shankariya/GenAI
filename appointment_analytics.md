# Skill: `appointment_analytics`

## Short Description

Use this skill for read-only SQL questions about appointments, booked calls, scheduled calls, appointment outcomes, appointment no-shows, event types, hosts, setters, call categories, and appointment-linked Fathom call records.

This skill must generate SQL only. The application will execute the SQL through a safe read-only database helper.

## When To Use This Skill

Use `appointment_analytics` for read-only SQL analytics questions related to appointments, booked calls, scheduled calls, appointment outcomes, no-shows, event types, hosts, setters, call categories, and appointment-linked Fathom records.

Use this skill for:

- Appointment counts and call counts.
- Scheduled appointment or call counts by today, week, month, or custom date range.
- Upcoming appointment lists or counts.
- Past appointment lists or counts.
- Completed or attended call counts.
- Appointment no-show counts and no-show rates.
- No-show analysis by event type, host, setter, call category, or appointment source.
- Appointment outcome breakdowns using appointment outcome status.
- Appointment breakdowns by call category.
- Appointment breakdowns by source, such as Calendly or manual.
- Appointment event type performance and event type distribution.
- Host performance based on appointment volume or no-show rate.
- Setter performance based on booked appointment volume or no-show rate.
- Lists of no-show appointments.
- Fathom coverage analysis for past appointments.
- Appointments missing linked Fathom call records.
- Appointments or calls with Fathom summaries.
- Appointment-linked Fathom objections, key points, action items, and AI rationale.
- Average call duration and call duration analysis from Fathom records.
- AI-suggested Fathom outcome counts and applied outcome analysis.
- Appointment recording links, Fathom recording links, or transcript links only when explicitly requested.

## When Not To Use This Skill

Do not use this skill for:

- Lead-only counts, lead source breakdowns, stale leads, missing owners, missing setters, or lead creation trends. Use `lead_analytics`.
- Lead no-show status questions such as "how many leads are marked no-show". Use `lead_analytics`.
- Revenue, contracts, payments, invoices, refunds, subscriptions, or payment links. Use `revenue_analytics`.
- Form-answer, UTM, landing-page, traffic attribution, or opt-in question analysis. Use `acquisition_analytics`.
- Full single-lead summaries with notes, calls, contracts, payments, and complete timeline. Use `lead_360`.
- Provider integration health, webhook troubleshooting, credential validation, API keys, webhook payloads, or connection status. Use an integration/admin skill.
- Deep semantic search over long call text, notes, summaries, objections, or action items. Use `semantic_context` or a future pgvector/hybrid retrieval skill when the user asks for qualitative theme discovery across many records.

If the user question requires tables outside `appointments`, `appointment_event_types`, `sales_statuses`, `leads`, or `fathom_call_records`, do not use this skill unless the required logic is explicitly listed in this file.

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
fathom_call_records.raw_payload
```

Every business query must include an organization filter.

For appointment-first queries, use:

```sql
WHERE a.clerk_org_id = :org_id
```

For Fathom-first queries, use:

```sql
WHERE f.clerk_org_id = :org_id
```

For `appointments`, always exclude soft-deleted rows unless the user explicitly asks about deleted appointments:

```sql
AND a.is_deleted = false
```

For `leads`, exclude soft-deleted rows by default when joining to lead identity:

```sql
AND l.is_deleted = false
```

For historical appointment reporting, prefer appointment snapshot fields and do not remove appointment rows only because the current event type row is deleted.

When `appointment_event_types` is used as fallback display context, put the soft-delete filter inside the `LEFT JOIN`, not in the `WHERE` clause:

```sql
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
```

Use `aet.is_deleted = false` more strictly when the user asks about the current event type catalog.

Always use parameterized SQL for organization scope and dynamic values.

Use named parameters such as:

- `:org_id`
- `:start_date`
- `:end_date`
- `:host_id`
- `:setter_id`
- `:event_type_id`
- `:call_category`
- `:appointment_source`
- `:limit`

Do not hardcode the organization ID in generated agent SQL except in local manual debugging.

For aggregate analytics questions, return aggregate columns only.

For list-style questions such as "which appointments", select only the fields needed to answer the question, add a deterministic `ORDER BY`, and cap the result with a reasonable `LIMIT` unless the user asks for a specific limit.

Default list limit: `20`.

Do not include lead email, lead phone, meeting URL, recording URL, transcript URL, or provider references unless the user explicitly asks for contact details, meeting links, recording links, transcript links, or provider/debug identifiers.

`host_id` and `setter_id` are user IDs. Do not invent host or setter names unless a future user/profile table is available in another skill.

When joining `fathom_call_records`, use `COUNT(DISTINCT a.id)` for appointment counts to avoid double-counting appointments that have multiple call records.

## Count vs List Intent Rule

If the user asks "how many", "count", "total", or "number of", generate an aggregate query.

If the user asks "which", "show me", "list", "who had", "give me the appointments", or "give me the calls", generate a list query.

Do not answer list-style appointment questions using only `COUNT(*)`.

## Primary Tables

## `appointments`

One row is one booked appointment/call connected to a lead.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Appointment primary key. | Join key and appointment identity. |
| `lead_id` | Lead ID connected to the appointment. | Join to `leads.id`. |
| `clerk_org_id` | Tenant/organization ID. | Required filter. |
| `schedule_time` | Scheduled appointment datetime. | Date filtering, upcoming calls, past calls, no-show rate period, trends. |
| `host_id` | Host/closer user ID. | Host performance and missing host checks. |
| `setter_id` | Setter user ID. | Setter appointment booking analysis. |
| `meeting_url` | Meeting link. | Display only when explicitly asked. |
| `snapshot_event_name` | Event name saved on appointment. | Historical event type display. |
| `snapshot_call_category` | Call category saved on appointment. | Historical call category reporting. |
| `appointment_event_type_id` | Event type ID. | Join to `appointment_event_types.id`. |
| `outcome_id` | Appointment outcome status ID. | Join to `sales_statuses.id`. |
| `notes` | Appointment notes. | Light appointment context only when explicitly useful. |
| `recording_url` | Appointment recording URL. | Display only when explicitly asked. |
| `no_show` | Whether the appointment was a no-show. | Appointment no-show counts and rates. |
| `source` | Appointment source enum. | Calendly/manual breakdown. |
| `external_reference` | External provider reference. | Provider/debug context only when explicitly requested. |
| `created_by` | User/system that created appointment. | Admin context only when needed. |
| `created_at` | Appointment record creation datetime. | Booking-created trend only when user asks when appointments were created in the system. |
| `updated_at` | Last appointment record update datetime. | Recency/debug context only. |
| `is_deleted` | Soft-delete flag. | Usually filter false. |
| `deleted_at` | Deletion datetime. | Deleted-appointment analysis only. |

Required default filter:

```sql
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
```

## `appointment_event_types`

One row is a Calendly/manual event type catalog entry.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Event type primary key. | Join from `appointments.appointment_event_type_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `external_event_type_id` | Provider event type ID. | Provider/debug context only when explicitly requested. |
| `event_type_name` | Current event type name. | Event type fallback label or current event type catalog. |
| `call_category` | Current call category. | Current event catalog category analysis. |
| `provider` | Provider enum. | Calendly/manual/provider breakdown when needed. |
| `is_favourite` | Favorite flag. | Setup/admin context only. |
| `is_ignored` | Ignored event type flag. | Setup/admin context or excluding ignored event types when requested. |
| `owner_name` | Provider owner display name. | Event owner context when available. |
| `owner_ref` | Provider owner reference. | Provider/debug context only. |
| `kind` | Provider kind/type. | Provider context only. |
| `source` | Event type source enum. | Provider/manual event type source. |
| `metadata` | Provider metadata. | Avoid unless explicitly asked; do not expose raw provider internals. |
| `created_by` | User/system that created event type. | Admin context only. |
| `created_at` | Event type creation datetime. | Setup/admin context. |
| `updated_at` | Last update datetime. | Setup/admin context. |
| `is_deleted` | Soft-delete flag. | Usually filter false for current catalog questions. |

Join from appointments:

```sql
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
```

Use `a.snapshot_event_name` for historical appointment reporting because it reflects the event name at appointment time.

Use `aet.event_type_name` when the user asks about the current event type catalog.

Do not join `appointment_event_types` without matching `clerk_org_id`.

## `sales_statuses`

One row is a readable pipeline status or appointment outcome for an organization.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Status primary key. | Join from `appointments.outcome_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `name` | Human-readable outcome/status name. | Display exact appointment outcome. |
| `description` | Status description. | Explain outcome if available. |
| `role` | Normalized status role enum. | Group appointment outcomes into business categories. |
| `is_default` | Whether default status. | Setup/admin context. |
| `is_system` | Whether system-created status. | Setup/admin context. |

Join from appointments:

```sql
LEFT JOIN sales_statuses outcome
  ON outcome.id = a.outcome_id
 AND outcome.clerk_org_id = a.clerk_org_id
```

Use `a.no_show` for true appointment no-show rate.

Use `outcome.role` or `outcome.name` when the user asks for appointment outcome breakdowns.

Do not join `sales_statuses` without matching `clerk_org_id`.

## `leads`

Use this table only when appointment answers need lead display context.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Lead primary key. | Join from `appointments.lead_id`. |
| `clerk_org_id` | Tenant/organization ID. | Required join safety. |
| `first_name` | First name. | Display and search. |
| `last_name` | Last name. | Display and search. |
| `full_name` | Generated/display full name. | Display and search. |
| `email` | Lead email. | Search and identity only when explicitly requested. |
| `phone_e164` | Phone number in E.164 format. | Contact detail only when explicitly requested. |
| `source` | Lead source enum. | Lead-source context only. |
| `assigned_to` | Lead owner/assignee user ID. | Lead owner context only. |
| `setter_id` | Lead setter user ID. | Lead setter context only. |
| `status_id` | Current lead status ID. | Lead status context only. |
| `created_at` | Lead creation datetime. | Lead-age context only. |
| `is_deleted` | Soft-delete flag. | Usually filter false. |

Join from appointments:

```sql
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = a.clerk_org_id
 AND l.is_deleted = false
```

Do not use this skill for lead-only analytics. Use `lead_analytics` for lead-only questions.

## `fathom_call_records`

One row is a Fathom AI call record, usually connected to an appointment.

Important columns:

| Column | Meaning | Use |
|---|---|---|
| `id` | Fathom record primary key. | Fathom record identity. |
| `appointment_id` | Appointment ID connected to the Fathom record. | Join to `appointments.id`. |
| `clerk_org_id` | Tenant/organization ID. | Required filter and join safety. |
| `fathom_call_id` | Fathom call ID. | Provider/debug context only. |
| `fathom_meeting_id` | Fathom meeting ID. | Provider/debug context only. |
| `summary` | Fathom call summary. | Call summary and light context. |
| `key_points` | Fathom key points JSON. | Call details and important points. |
| `action_items` | Fathom action items JSON. | Follow-up/action item analysis. |
| `objections` | Fathom objections JSON. | Objection row retrieval/counts only. |
| `transcript_url` | Transcript URL. | Display only when explicitly asked. |
| `recording_url` | Fathom recording URL. | Display only when explicitly asked. |
| `ai_suggested_outcome` | AI-suggested outcome status ID. | Join to `sales_statuses.id` if needed. |
| `ai_confidence_score` | AI confidence score. | AI outcome confidence analysis. |
| `ai_rationale` | AI rationale text. | AI outcome explanation. |
| `outcome_applied` | Whether AI outcome was applied. | Automation/application analysis. |
| `call_duration_seconds` | Call duration in seconds. | Average duration and duration distribution. |
| `call_started_at` | Actual call start datetime. | Actual call timing when available. |
| `call_ended_at` | Actual call end datetime. | Actual call timing when available. |
| `created_at` | Fathom record creation datetime. | Fathom ingestion timing. |
| `updated_at` | Last update datetime. | Debug context only. |
| `match_strategy` | How Fathom matched to appointment. | Matching quality/debug context. |
| `outcome_applied_by` | User/system applying outcome. | Admin context only. |
| `ai_generated_title` | AI-generated call title. | Display/context. |

Never select:

```text
raw_payload
```

For appointment-level Fathom analytics, join Fathom records to valid, non-deleted appointments unless the user explicitly asks for unmatched Fathom records.

Join from appointments:

```sql
LEFT JOIN fathom_call_records f
  ON f.appointment_id = a.id
 AND f.clerk_org_id = a.clerk_org_id
```

Join AI-suggested outcome:

```sql
LEFT JOIN sales_statuses ai_outcome
  ON ai_outcome.id = f.ai_suggested_outcome
 AND ai_outcome.clerk_org_id = f.clerk_org_id
```

Fathom records can be missing for appointments.

Fathom records can have `appointment_id` as `NULL`; for appointment analytics, only count appointment-linked records unless the user explicitly asks for unmatched Fathom records.

## Enums

## `AppointmentSource`

Business-defined values:

```text
CALENDLY
MANUAL
```

Meaning:

| Value | Meaning |
|---|---|
| `CALENDLY` | Appointment came from Calendly/provider booking flow. |
| `MANUAL` | Appointment was manually created. |

Use `a.source` for appointment source reporting.

## `CallCategory`

Business-defined values:

```text
SALES_CALL
COACHING_CALL
TRIAGE_CALL
```

Meaning:

| Value | Meaning |
|---|---|
| `SALES_CALL` | Sales/discovery/closing call. |
| `COACHING_CALL` | Coaching/client call. |
| `TRIAGE_CALL` | Qualification or triage call. |

Use `a.snapshot_call_category` for historical appointment reporting.

Use `aet.call_category` for current event type catalog reporting.

## `AppointmentEventTypeSource`

Business-defined values:

```text
PROVIDER
MANUAL
```

Use `aet.source` when the user asks whether event types came from provider sync or manual setup.

## `ProviderType`

Relevant values for appointment analytics:

```text
CALENDLY
FATHOM
```

Other provider enum values may exist, but appointment event type reporting usually uses `CALENDLY`.

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

Use `outcome.role` for normalized appointment outcome analysis.

## Business Interpretation Rules

## Appointment Counts

When the user asks how many appointments, count rows in `appointments`:

```sql
COUNT(*) AS appointment_count
```

Use `a.schedule_time` for appointment timing questions.

Use `a.created_at` only when the user asks when appointments were created, added, or booked into the system.

## Scheduled vs Created / Booked Wording

If the user says "appointments scheduled for this month" or "calls scheduled this month", use `a.schedule_time`.

If the user says "appointments created this month", "appointments added this month", or "calls booked into the system this month", use `a.created_at`.

If the user simply says "calls booked this month" or "appointments booked this month", default to `a.schedule_time` and treat it as calls scheduled for that month.

## Upcoming Appointments

When the user asks for upcoming appointments, use:

```sql
a.schedule_time >= NOW()
```

Do not require a Fathom call record for upcoming appointments.

## Past and Completed Appointments

When the user asks for past appointments, previous appointments, call history, or previous calls, use:

```sql
a.schedule_time < NOW()
```

If the user specifically asks for attended, completed, or completed non-no-show calls, use:

```sql
a.schedule_time < NOW()
AND a.no_show = false
```

## No-Show Rate

For appointment no-show rate, prefer the explicit appointment field:

```sql
a.no_show = true
```

For no-show rate, use past appointments by default because future appointments cannot be no-shows yet.

Default no-show denominator:

- non-deleted appointments
- scoped by `a.clerk_org_id = :org_id`
- `a.schedule_time < NOW()`
- filtered by `a.schedule_time` if the user provides a date range

Only include future appointments in the denominator if the user explicitly asks for all scheduled appointments including upcoming appointments.

Use this rate formula:

```sql
ROUND(
  100.0 * COUNT(*) FILTER (WHERE a.no_show = true) / NULLIF(COUNT(*), 0),
  2
) AS no_show_rate_percent
```

If the user asks for no-show lead status, use `lead_analytics`.

If the user asks for appointment no-show rate, use this skill.

## Appointment Outcomes

Use `appointments.outcome_id` joined to `sales_statuses.id`.

Use `outcome.name` for exact outcome labels.

Use `outcome.role` for normalized outcome categories.

For no-show reporting, `a.no_show` is more direct than `outcome.role = 'NO_SHOW'`.

## Event Type Names

Use `a.snapshot_event_name` for historical appointment reports.

Use `aet.event_type_name` for current event type catalog reports.

If a query is grouped by event type for historical performance, prefer:

```sql
COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type')
```

## Host and Setter

`a.host_id` is the appointment host user ID.

`a.setter_id` is the appointment setter user ID.

Treat both `NULL` and blank strings as missing:

```sql
NULLIF(TRIM(a.host_id), '') IS NULL
```

and:

```sql
NULLIF(TRIM(a.setter_id), '') IS NULL
```

For grouping, use:

```sql
COALESCE(NULLIF(TRIM(a.host_id), ''), 'No Host') AS host_id
```

and:

```sql
COALESCE(NULLIF(TRIM(a.setter_id), ''), 'No Setter') AS setter_id
```

Do not invent host or setter names from IDs.

## Fathom Coverage

When the user asks whether appointments/calls have Fathom records, join `fathom_call_records`.

For Fathom coverage, use past appointments by default because upcoming appointments are not expected to have Fathom records yet.

Default Fathom coverage denominator:

- non-deleted appointments
- scoped by `a.clerk_org_id = :org_id`
- `a.schedule_time < NOW()`

Only include upcoming appointments if the user explicitly asks for all scheduled appointments.

Use `COUNT(DISTINCT a.id)` for appointment totals.

Use `COUNT(DISTINCT a.id) FILTER (WHERE f.id IS NOT NULL)` for appointments with Fathom records.

Use `COUNT(DISTINCT a.id) FILTER (WHERE f.id IS NULL)` for appointments missing Fathom records.

## Fathom Text Fields

Use Fathom text fields for direct SQL retrieval and light summaries:

- `f.summary`
- `f.key_points`
- `f.action_items`
- `f.objections`
- `f.ai_rationale`
- `f.ai_generated_title`

Do not use `f.raw_payload`.

For broad qualitative questions such as "what objections are common", "why are calls not converting", "what themes appear in calls", or "summarize themes across calls", do not use this SQL skill unless the user only wants rows/counts from Fathom fields. Route deeper theme discovery to `semantic_context`.

## Call Duration

For appointment-level call duration analytics, join `fathom_call_records` to `appointments` and require:

```sql
a.is_deleted = false
```

Do not calculate appointment call duration from Fathom records alone, because a Fathom record may be linked to a deleted or invalid appointment.

Use only records where:

```sql
f.call_duration_seconds IS NOT NULL
```

## Timeframe Rules

For appointments scheduled during a date range, use:

```sql
a.schedule_time >= :start_date
AND a.schedule_time < :end_date
```

For appointment records created during a date range, use:

```sql
a.created_at >= :start_date
AND a.created_at < :end_date
```

For Fathom calls that actually started during a date range, use:

```sql
f.call_started_at >= :start_date
AND f.call_started_at < :end_date
```

If the user says "calls booked this month", prefer `a.schedule_time` unless they clearly mean records created in the system.

If the user says "appointments created this month" or "calls booked into the system this month", use `a.created_at`.

## Percentage and Trend Rules

Use percentages only when they add business value.

For breakdown, distribution, grouped, ranking, source-wise, host-wise, setter-wise, event-wise, outcome-wise, or category-wise questions, include:

- the grouped count
- a helper total column such as `total_matching_appointments`, `total_matching_records`, or `total_calls_with_duration`
- `percentage_of_total` when useful

The helper total column is used by the main agent to write the opening summary sentence. It should not be shown to the user as a normal table column unless the user explicitly asks for it.

For no-show analysis, always include no-show rate percentage.

For Fathom coverage analysis, always include Fathom coverage percentage.

For weekly or monthly trend questions, include percentage change from the previous period when the user asks for growth, change, or trend percentage.

For daily trend questions, show counts only by default. Do not include daily percentage change unless the user explicitly asks for daily percentage, daily growth, or daily change.

Do not add percentages for list-style questions such as "which appointments", "show calls", or "list appointments".

## Default List Output Rules

For list-style appointment queries, default output fields are:

- `total_matching_rows`
- `a.id`
- `a.schedule_time`
- `display_name`
- `event_name`
- `call_category`
- `outcome_name`
- `outcome_role`
- `a.no_show`
- `appointment_source`
- `host_id`
- `setter_id`
- `has_fathom_record`

Use this display name expression:

```sql
COALESCE(
  NULLIF(TRIM(l.full_name), ''),
  NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
  l.first_name,
  'Unknown Lead'
) AS display_name
```

Use this event name expression:

```sql
COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name
```

Use this Fathom existence expression when a list query needs to show whether the appointment has a linked Fathom record:

```sql
EXISTS (
  SELECT 1
  FROM fathom_call_records f_check
  WHERE f_check.appointment_id = a.id
    AND f_check.clerk_org_id = a.clerk_org_id
) AS has_fathom_record
```

Do not include `l.email`, `l.phone_e164`, `a.meeting_url`, `a.recording_url`, `f.transcript_url`, or `f.recording_url` unless the user explicitly asks for contact details, meeting links, transcript links, or recording links.

Use `COUNT(*) OVER() AS total_matching_rows` for list-style queries with a `LIMIT`, so the final answer can show the exact total before the limited rows.

Use `LIMIT :limit` when the application passes a limit.

If the application does not pass a limit and the user does not request one, use:

```sql
LIMIT 20
```

Always use deterministic ordering, such as:

```sql
ORDER BY a.schedule_time DESC, a.id ASC
```

or, for upcoming appointments:

```sql
ORDER BY a.schedule_time ASC, a.id ASC
```

## Common Query Patterns

## Count Appointments

```sql
SELECT COUNT(*) AS appointment_count
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false;
```

## Count Appointments Scheduled in a Date Range

```sql
SELECT COUNT(*) AS appointments_scheduled_in_period
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time >= :start_date
  AND a.schedule_time < :end_date;
```

## Count Appointments Created in a Date Range

Use this only when the user asks when appointments were created, added, or booked into the system.

```sql
SELECT COUNT(*) AS appointments_created_in_period
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.created_at >= :start_date
  AND a.created_at < :end_date;
```

## Count Upcoming Appointments

```sql
SELECT COUNT(*) AS upcoming_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time >= NOW();
```

## Count Past Appointments

```sql
SELECT COUNT(*) AS past_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW();
```

## Count Completed Attended Calls

```sql
SELECT COUNT(*) AS completed_attended_calls
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW()
  AND a.no_show = false;
```

## Appointment No-Show Rate

```sql
SELECT
  COUNT(*) AS total_past_appointments,
  COUNT(*) FILTER (WHERE a.no_show = true) AS no_show_appointments,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE a.no_show = true) / NULLIF(COUNT(*), 0),
    2
  ) AS no_show_rate_percent
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW();
```

## Appointment No-Show Rate in a Date Range

```sql
SELECT
  COUNT(*) AS total_past_appointments,
  COUNT(*) FILTER (WHERE a.no_show = true) AS no_show_appointments,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE a.no_show = true) / NULLIF(COUNT(*), 0),
    2
  ) AS no_show_rate_percent
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time >= :start_date
  AND a.schedule_time < :end_date
  AND a.schedule_time < NOW();
```

## Appointments by Outcome Name

```sql
SELECT
  COALESCE(outcome.name, 'No Outcome') AS outcome_name,
  COALESCE(CAST(outcome.role AS text), 'NO_OUTCOME') AS outcome_role,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM appointments a
LEFT JOIN sales_statuses outcome
  ON outcome.id = a.outcome_id
 AND outcome.clerk_org_id = a.clerk_org_id
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY
  COALESCE(outcome.name, 'No Outcome'),
  COALESCE(CAST(outcome.role AS text), 'NO_OUTCOME')
ORDER BY appointment_count DESC, outcome_name ASC;
```

## Appointments by Call Category

```sql
SELECT
  CAST(a.snapshot_call_category AS text) AS call_category,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY CAST(a.snapshot_call_category AS text)
ORDER BY appointment_count DESC, call_category ASC;
```

## Appointments by Source

```sql
SELECT
  CAST(a.source AS text) AS appointment_source,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY CAST(a.source AS text)
ORDER BY appointment_count DESC, appointment_source ASC;
```

## Appointments by Event Type

```sql
SELECT
  COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM appointments a
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type')
ORDER BY appointment_count DESC, event_name ASC;
```

## No-Show Rate by Event Type

```sql
SELECT
  COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name,
  COUNT(*) AS total_past_appointments,
  COUNT(*) FILTER (WHERE a.no_show = true) AS no_show_appointments,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE a.no_show = true) / NULLIF(COUNT(*), 0),
    2
  ) AS no_show_rate_percent,
  SUM(COUNT(*)) OVER() AS total_matching_past_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total_past_appointments
FROM appointments a
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW()
GROUP BY COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type')
ORDER BY no_show_rate_percent DESC NULLS LAST, total_past_appointments DESC, event_name ASC;
```

## Appointments by Host

```sql
SELECT
  COALESCE(NULLIF(TRIM(a.host_id), ''), 'No Host') AS host_id,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(a.host_id), ''), 'No Host')
ORDER BY appointment_count DESC, host_id ASC;
```

## Top Actual Host by Appointment Count

Use this when the user asks:

- which host has the most appointments
- top host by appointment count
- best host by number of appointments

Exclude missing host values. Do not return `No Host` as the top host unless the user explicitly asks to include appointments without a host.

This query returns all hosts tied for the highest appointment count.

```sql
WITH host_counts AS (
  SELECT
    NULLIF(TRIM(a.host_id), '') AS host_id,
    COUNT(*) AS appointment_count
  FROM appointments a
  WHERE a.clerk_org_id = :org_id
    AND a.is_deleted = false
    AND NULLIF(TRIM(a.host_id), '') IS NOT NULL
  GROUP BY NULLIF(TRIM(a.host_id), '')
),
max_count AS (
  SELECT MAX(appointment_count) AS max_appointment_count
  FROM host_counts
)
SELECT
  hc.host_id,
  hc.appointment_count
FROM host_counts hc
JOIN max_count mc
  ON hc.appointment_count = mc.max_appointment_count
ORDER BY hc.host_id ASC;
```

## Appointments by Setter

```sql
SELECT
  COALESCE(NULLIF(TRIM(a.setter_id), ''), 'No Setter') AS setter_id,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY COALESCE(NULLIF(TRIM(a.setter_id), ''), 'No Setter')
ORDER BY appointment_count DESC, setter_id ASC;
```

## Top Actual Setter by Appointment Count

Use this when the user asks:

- which setter booked the most appointments
- top setter by appointment count
- best setter by number of booked appointments

Exclude missing setter values. Do not return `No Setter` as the top setter unless the user explicitly asks to include appointments without a setter.

This query returns all setters tied for the highest appointment count.

```sql
WITH setter_counts AS (
  SELECT
    NULLIF(TRIM(a.setter_id), '') AS setter_id,
    COUNT(*) AS appointment_count
  FROM appointments a
  WHERE a.clerk_org_id = :org_id
    AND a.is_deleted = false
    AND NULLIF(TRIM(a.setter_id), '') IS NOT NULL
  GROUP BY NULLIF(TRIM(a.setter_id), '')
),
max_count AS (
  SELECT MAX(appointment_count) AS max_appointment_count
  FROM setter_counts
)
SELECT
  sc.setter_id,
  sc.appointment_count
FROM setter_counts sc
JOIN max_count mc
  ON sc.appointment_count = mc.max_appointment_count
ORDER BY sc.setter_id ASC;
```

## List Upcoming Appointments

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  a.id,
  a.schedule_time,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name,
  CAST(a.snapshot_call_category AS text) AS call_category,
  COALESCE(outcome.name, 'No Outcome') AS outcome_name,
  COALESCE(CAST(outcome.role AS text), 'NO_OUTCOME') AS outcome_role,
  a.no_show,
  CAST(a.source AS text) AS appointment_source,
  COALESCE(NULLIF(TRIM(a.host_id), ''), 'No Host') AS host_id,
  COALESCE(NULLIF(TRIM(a.setter_id), ''), 'No Setter') AS setter_id,
  EXISTS (
    SELECT 1
    FROM fathom_call_records f_check
    WHERE f_check.appointment_id = a.id
      AND f_check.clerk_org_id = a.clerk_org_id
  ) AS has_fathom_record
FROM appointments a
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = a.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN sales_statuses outcome
  ON outcome.id = a.outcome_id
 AND outcome.clerk_org_id = a.clerk_org_id
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time >= NOW()
ORDER BY a.schedule_time ASC, a.id ASC
LIMIT 20;
```

## List No-Show Appointments

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  a.id,
  a.schedule_time,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name,
  CAST(a.snapshot_call_category AS text) AS call_category,
  COALESCE(outcome.name, 'No Outcome') AS outcome_name,
  COALESCE(CAST(outcome.role AS text), 'NO_OUTCOME') AS outcome_role,
  a.no_show,
  CAST(a.source AS text) AS appointment_source,
  COALESCE(NULLIF(TRIM(a.host_id), ''), 'No Host') AS host_id,
  COALESCE(NULLIF(TRIM(a.setter_id), ''), 'No Setter') AS setter_id,
  EXISTS (
    SELECT 1
    FROM fathom_call_records f_check
    WHERE f_check.appointment_id = a.id
      AND f_check.clerk_org_id = a.clerk_org_id
  ) AS has_fathom_record
FROM appointments a
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = a.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN sales_statuses outcome
  ON outcome.id = a.outcome_id
 AND outcome.clerk_org_id = a.clerk_org_id
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW()
  AND a.no_show = true
ORDER BY a.schedule_time DESC, a.id ASC
LIMIT 20;
```

## Fathom Coverage for Past Appointments

```sql
SELECT
  COUNT(DISTINCT a.id) AS total_past_appointments,
  COUNT(DISTINCT a.id) FILTER (WHERE f.id IS NOT NULL) AS appointments_with_fathom,
  COUNT(DISTINCT a.id) FILTER (WHERE f.id IS NULL) AS appointments_without_fathom,
  ROUND(
    100.0 * COUNT(DISTINCT a.id) FILTER (WHERE f.id IS NOT NULL) / NULLIF(COUNT(DISTINCT a.id), 0),
    2
  ) AS fathom_coverage_percent
FROM appointments a
LEFT JOIN fathom_call_records f
  ON f.appointment_id = a.id
 AND f.clerk_org_id = a.clerk_org_id
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW();
```

## List Appointments Missing Fathom Records

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  a.id,
  a.schedule_time,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name,
  CAST(a.snapshot_call_category AS text) AS call_category,
  COALESCE(outcome.name, 'No Outcome') AS outcome_name,
  COALESCE(CAST(outcome.role AS text), 'NO_OUTCOME') AS outcome_role,
  a.no_show,
  CAST(a.source AS text) AS appointment_source,
  COALESCE(NULLIF(TRIM(a.host_id), ''), 'No Host') AS host_id,
  COALESCE(NULLIF(TRIM(a.setter_id), ''), 'No Setter') AS setter_id,
  false AS has_fathom_record
FROM appointments a
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = a.clerk_org_id
 AND l.is_deleted = false
LEFT JOIN sales_statuses outcome
  ON outcome.id = a.outcome_id
 AND outcome.clerk_org_id = a.clerk_org_id
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW()
  AND NOT EXISTS (
    SELECT 1
    FROM fathom_call_records f_check
    WHERE f_check.appointment_id = a.id
      AND f_check.clerk_org_id = a.clerk_org_id
  )
ORDER BY a.schedule_time DESC, a.id ASC
LIMIT 20;
```

## List Appointments with Fathom Summaries

Use this when the user asks which appointments have Fathom summaries.

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  f.id AS fathom_record_id,
  a.id AS appointment_id,
  a.schedule_time,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(f.ai_generated_title), ''), NULLIF(TRIM(a.snapshot_event_name), ''), 'Untitled Call') AS call_title,
  f.summary,
  f.call_duration_seconds,
  f.call_started_at,
  f.call_ended_at
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = f.clerk_org_id
 AND l.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND NULLIF(TRIM(f.summary), '') IS NOT NULL
ORDER BY COALESCE(f.call_started_at, a.schedule_time, f.created_at) DESC, f.id ASC
LIMIT 20;
```

## List Fathom Call Summaries

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  f.id AS fathom_record_id,
  a.id AS appointment_id,
  a.schedule_time,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(f.ai_generated_title), ''), NULLIF(TRIM(a.snapshot_event_name), ''), 'Untitled Call') AS call_title,
  f.summary,
  f.key_points,
  f.action_items,
  f.objections,
  f.call_duration_seconds,
  f.call_started_at,
  f.call_ended_at
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = f.clerk_org_id
 AND l.is_deleted = false
WHERE f.clerk_org_id = :org_id
ORDER BY COALESCE(f.call_started_at, a.schedule_time, f.created_at) DESC, f.id ASC
LIMIT 20;
```

## Count Fathom Calls with Action Items

```sql
SELECT
  COUNT(*) AS calls_with_action_items
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND f.action_items IS NOT NULL
  AND f.action_items::text NOT IN ('null', '[]', '{}');
```

## Count Fathom Calls with Objections

```sql
SELECT
  COUNT(*) AS calls_with_objections
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND f.objections IS NOT NULL
  AND f.objections::text NOT IN ('null', '[]', '{}');
```

## List Fathom Calls with Action Items or Objections

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  f.id AS fathom_record_id,
  a.id AS appointment_id,
  a.schedule_time,
  COALESCE(
    NULLIF(TRIM(l.full_name), ''),
    NULLIF(TRIM(CONCAT_WS(' ', l.first_name, l.last_name)), ''),
    l.first_name,
    'Unknown Lead'
  ) AS display_name,
  COALESCE(NULLIF(TRIM(f.ai_generated_title), ''), NULLIF(TRIM(a.snapshot_event_name), ''), 'Untitled Call') AS call_title,
  f.action_items,
  f.objections
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
LEFT JOIN leads l
  ON l.id = a.lead_id
 AND l.clerk_org_id = f.clerk_org_id
 AND l.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND (
    (f.action_items IS NOT NULL AND f.action_items::text NOT IN ('null', '[]', '{}'))
    OR
    (f.objections IS NOT NULL AND f.objections::text NOT IN ('null', '[]', '{}'))
  )
ORDER BY COALESCE(f.call_started_at, a.schedule_time, f.created_at) DESC, f.id ASC
LIMIT 20;
```

## Average Call Duration

```sql
SELECT
  COUNT(*) AS calls_with_duration,
  ROUND(AVG(f.call_duration_seconds) / 60.0, 2) AS avg_call_duration_minutes
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND f.call_duration_seconds IS NOT NULL;
```

## Average Call Duration by Event Type

```sql
SELECT
  COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type') AS event_name,
  COUNT(*) AS calls_with_duration,
  ROUND(AVG(f.call_duration_seconds) / 60.0, 2) AS avg_call_duration_minutes,
  SUM(COUNT(*)) OVER() AS total_calls_with_duration,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_duration_records
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
LEFT JOIN appointment_event_types aet
  ON aet.id = a.appointment_event_type_id
 AND aet.clerk_org_id = a.clerk_org_id
 AND aet.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND f.call_duration_seconds IS NOT NULL
GROUP BY COALESCE(NULLIF(TRIM(a.snapshot_event_name), ''), aet.event_type_name, 'Unknown Event Type')
ORDER BY avg_call_duration_minutes DESC NULLS LAST, calls_with_duration DESC, event_name ASC;
```

## AI-Suggested Outcomes from Fathom

```sql
SELECT
  COALESCE(ai_outcome.name, 'No AI Suggested Outcome') AS ai_suggested_outcome_name,
  COALESCE(CAST(ai_outcome.role AS text), 'NO_AI_OUTCOME') AS ai_suggested_outcome_role,
  COUNT(*) AS fathom_record_count,
  SUM(COUNT(*)) OVER() AS total_matching_fathom_records,
  ROUND(COUNT(*) * 100.0 / NULLIF(SUM(COUNT(*)) OVER(), 0), 2) AS percentage_of_total,
  ROUND(AVG(f.ai_confidence_score), 2) AS avg_ai_confidence_score,
  COUNT(*) FILTER (WHERE f.outcome_applied = true) AS applied_count,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE f.outcome_applied = true) / NULLIF(COUNT(*), 0),
    2
  ) AS applied_rate_percent
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
LEFT JOIN sales_statuses ai_outcome
  ON ai_outcome.id = f.ai_suggested_outcome
 AND ai_outcome.clerk_org_id = f.clerk_org_id
WHERE f.clerk_org_id = :org_id
GROUP BY
  COALESCE(ai_outcome.name, 'No AI Suggested Outcome'),
  COALESCE(CAST(ai_outcome.role AS text), 'NO_AI_OUTCOME')
ORDER BY fathom_record_count DESC, ai_suggested_outcome_name ASC;
```

## Count Fathom Calls with AI-Suggested Outcomes

```sql
SELECT
  COUNT(*) AS calls_with_ai_suggested_outcome
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND f.ai_suggested_outcome IS NOT NULL;
```

## Count Applied Fathom Outcomes

```sql
SELECT
  COUNT(*) AS applied_fathom_outcomes
FROM fathom_call_records f
JOIN appointments a
  ON a.id = f.appointment_id
 AND a.clerk_org_id = f.clerk_org_id
 AND a.is_deleted = false
WHERE f.clerk_org_id = :org_id
  AND f.outcome_applied = true;
```

## Appointment Trend by Day

```sql
SELECT
  DATE_TRUNC('day', a.schedule_time)::date AS appointment_date,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY DATE_TRUNC('day', a.schedule_time)::date
ORDER BY appointment_date ASC;
```

## Appointment Trend by Day in a Date Range

```sql
SELECT
  DATE_TRUNC('day', a.schedule_time)::date AS appointment_date,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time >= :start_date
  AND a.schedule_time < :end_date
GROUP BY DATE_TRUNC('day', a.schedule_time)::date
ORDER BY appointment_date ASC;
```

## Appointment Trend by Week

```sql
SELECT
  DATE_TRUNC('week', a.schedule_time)::date AS appointment_week,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY DATE_TRUNC('week', a.schedule_time)::date
ORDER BY appointment_week ASC;
```

## Appointment Trend by Month

```sql
SELECT
  DATE_TRUNC('month', a.schedule_time)::date AS appointment_month,
  COUNT(*) AS appointment_count,
  SUM(COUNT(*)) OVER() AS total_matching_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
GROUP BY DATE_TRUNC('month', a.schedule_time)::date
ORDER BY appointment_month ASC;
```

## Appointment Weekly Trend with Percentage Change

Use this when the user asks for weekly appointment growth, weekly appointment change, or week-over-week appointment trend.

```sql
WITH weeks AS (
  SELECT generate_series(
    DATE_TRUNC('week', :start_date::timestamp)::date,
    DATE_TRUNC('week', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 week'
  )::date AS appointment_week
),
weekly_counts AS (
  SELECT
    w.appointment_week,
    COUNT(a.id) AS appointment_count
  FROM weeks w
  LEFT JOIN appointments a
    ON DATE_TRUNC('week', a.schedule_time)::date = w.appointment_week
   AND a.clerk_org_id = :org_id
   AND a.is_deleted = false
   AND a.schedule_time >= :start_date
   AND a.schedule_time < :end_date
  GROUP BY w.appointment_week
),
weekly_with_previous AS (
  SELECT
    appointment_week,
    appointment_count,
    LAG(appointment_count) OVER (ORDER BY appointment_week ASC) AS previous_period_appointment_count
  FROM weekly_counts
)
SELECT
  appointment_week,
  appointment_count,
  previous_period_appointment_count,
  CASE
    WHEN previous_period_appointment_count IS NULL OR previous_period_appointment_count = 0 THEN NULL
    ELSE ROUND(
      ((appointment_count - previous_period_appointment_count)::numeric / previous_period_appointment_count) * 100,
      2
    )
  END AS percentage_change_from_previous_period,
  SUM(appointment_count) OVER() AS total_matching_appointments
FROM weekly_with_previous
ORDER BY appointment_week ASC;
```

## Appointment Monthly Trend with Percentage Change

Use this when the user asks for monthly appointment growth, monthly appointment change, or month-over-month appointment trend.

```sql
WITH months AS (
  SELECT generate_series(
    DATE_TRUNC('month', :start_date::timestamp)::date,
    DATE_TRUNC('month', (:end_date::timestamp - INTERVAL '1 day'))::date,
    INTERVAL '1 month'
  )::date AS appointment_month
),
monthly_counts AS (
  SELECT
    m.appointment_month,
    COUNT(a.id) AS appointment_count
  FROM months m
  LEFT JOIN appointments a
    ON DATE_TRUNC('month', a.schedule_time)::date = m.appointment_month
   AND a.clerk_org_id = :org_id
   AND a.is_deleted = false
   AND a.schedule_time >= :start_date
   AND a.schedule_time < :end_date
  GROUP BY m.appointment_month
),
monthly_with_previous AS (
  SELECT
    appointment_month,
    appointment_count,
    LAG(appointment_count) OVER (ORDER BY appointment_month ASC) AS previous_period_appointment_count
  FROM monthly_counts
)
SELECT
  appointment_month,
  appointment_count,
  previous_period_appointment_count,
  CASE
    WHEN previous_period_appointment_count IS NULL OR previous_period_appointment_count = 0 THEN NULL
    ELSE ROUND(
      ((appointment_count - previous_period_appointment_count)::numeric / previous_period_appointment_count) * 100,
      2
    )
  END AS percentage_change_from_previous_period,
  SUM(appointment_count) OVER() AS total_matching_appointments
FROM monthly_with_previous
ORDER BY appointment_month ASC;
```

## No-Show Trend by Day

```sql
SELECT
  DATE_TRUNC('day', a.schedule_time)::date AS appointment_date,
  COUNT(*) AS total_past_appointments,
  COUNT(*) FILTER (WHERE a.no_show = true) AS no_show_appointments,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE a.no_show = true) / NULLIF(COUNT(*), 0),
    2
  ) AS no_show_rate_percent,
  SUM(COUNT(*)) OVER() AS total_matching_past_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time < NOW()
GROUP BY DATE_TRUNC('day', a.schedule_time)::date
ORDER BY appointment_date ASC;
```

## No-Show Trend by Day in a Date Range

```sql
SELECT
  DATE_TRUNC('day', a.schedule_time)::date AS appointment_date,
  COUNT(*) AS total_past_appointments,
  COUNT(*) FILTER (WHERE a.no_show = true) AS no_show_appointments,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE a.no_show = true) / NULLIF(COUNT(*), 0),
    2
  ) AS no_show_rate_percent,
  SUM(COUNT(*)) OVER() AS total_matching_past_appointments
FROM appointments a
WHERE a.clerk_org_id = :org_id
  AND a.is_deleted = false
  AND a.schedule_time >= :start_date
  AND a.schedule_time < :end_date
  AND a.schedule_time < NOW()
GROUP BY DATE_TRUNC('day', a.schedule_time)::date
ORDER BY appointment_date ASC;
```

## Count Unmatched Fathom Records

Use this only when the user explicitly asks for unmatched Fathom records.

```sql
SELECT
  COUNT(*) AS unmatched_fathom_records
FROM fathom_call_records f
WHERE f.clerk_org_id = :org_id
  AND f.appointment_id IS NULL;
```

## List Unmatched Fathom Records

Use this only when the user explicitly asks to list unmatched Fathom records.

Do not select `raw_payload`.

```sql
SELECT
  COUNT(*) OVER() AS total_matching_rows,
  f.id AS fathom_record_id,
  f.fathom_call_id,
  f.fathom_meeting_id,
  COALESCE(NULLIF(TRIM(f.ai_generated_title), ''), 'Untitled Call') AS call_title,
  f.summary,
  f.call_duration_seconds,
  f.call_started_at,
  f.call_ended_at,
  f.created_at
FROM fathom_call_records f
WHERE f.clerk_org_id = :org_id
  AND f.appointment_id IS NULL
ORDER BY COALESCE(f.call_started_at, f.created_at) DESC, f.id ASC
LIMIT 20;
```

## Mistakes To Avoid

- Do not count deleted appointments unless explicitly requested.
- Do not include future appointments in appointment no-show rate unless the user explicitly asks for all scheduled appointments including upcoming.
- Do not count upcoming appointments as missing Fathom records by default.
- Do not join `appointments` to `sales_statuses`, `appointment_event_types`, `leads`, or `fathom_call_records` without matching `clerk_org_id`.
- Do not put `aet.is_deleted = false` in the `WHERE` clause after a `LEFT JOIN` for historical appointment reporting, because it can accidentally remove valid appointment rows.
- Do not use `fathom_call_records.raw_payload`.
- Do not use webhook payloads, provider credentials, API keys, or unrelated integration tables in this skill.
- Do not use `a.created_at` when the user asks when calls happened. Use `a.schedule_time`.
- Do not use `f.call_started_at` for appointment schedule counts unless the user asks for actual Fathom call start time.
- Do not treat `outcome.role = 'NO_SHOW'` as the primary appointment no-show metric. Prefer `a.no_show`.
- Do not double-count appointments when joining to Fathom records. Use `COUNT(DISTINCT a.id)` for appointment counts after a Fathom join.
- Do not calculate appointment call duration from Fathom records alone. Join to valid non-deleted appointments.
- Do not invent host or setter names from `host_id` or `setter_id`.
- Do not include lead email, lead phone, meeting URL, recording URL, or transcript URL unless explicitly requested.
- Do not perform broad qualitative theme analysis from SQL alone. Route deep objection/theme discovery to `semantic_context`.
- Do not use `SELECT *`.
- Do not generate SQL without a tenant filter.
- Do not generate non-read SQL.
- Do not answer lead-only, revenue, acquisition, integration, or full lead timeline questions from this skill.

## Related Skills

- `lead_analytics`: lead counts, lead statuses, lead sources, owners, setters, stale leads, follow-up.
- `acquisition_analytics`: opt-ins, form answers, UTM, traffic attribution, landing pages.
- `revenue_analytics`: programs, contracts, payments, payment links, proofs, refunds, invoices, subscriptions.
- `lead_360`: single-lead complete view across notes, calls, contracts, payments, and timeline.
- `integration_health`: provider connections, webhook health, API validation, integration failures.
- `semantic_context`: pgvector or hybrid semantic search over notes, call summaries, objections, action items, and form answers.
