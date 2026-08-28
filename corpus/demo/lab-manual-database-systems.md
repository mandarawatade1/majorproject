---
title: "Lab Manual: Database Management Systems Laboratory, Semester IV"
doc_id: "DEMO/LAB/CE/DBMS/2026"
is_demo: true
demo_reason: "Laboratory manuals are distributed to enrolled students and are
  not published on the public website. Synthesised to provide long, structured
  technical content with numbered experiments for testing structure-aware
  chunking across many sibling sections."
category: "lab_manual"
department: "Computer Engineering"
created: "2026-01-06"
---

## Laboratory environment

All experiments use PostgreSQL 16 on the lab workstations. The server runs
locally on each workstation on port 5432. Each student works in their own
database, named for their roll number in lowercase.

Work is not preserved between sessions on Tier 0 accounts. Export your schema
and data to your Tier 1 network home at the end of every session; a workstation
may be reimaged without notice.

## Assessment

Each experiment carries a write-up and a demonstration. The write-up is checked
at the start of the following session; the demonstration happens in the session
itself. An experiment demonstrated but not written up scores zero, and so does
the reverse.

## Experiment 1: Data definition and constraints

**Objective.** Create a normalised schema and enforce integrity through
constraints rather than application code.

Create a schema for a small library: members, titles, copies, loans. Declare
primary keys, foreign keys, a uniqueness constraint preventing the same copy
being on loan twice concurrently, and a check constraint ensuring a loan's due
date is after its issue date.

**Expected observation.** Attempting each violation must produce a database
error, not a silently accepted row. Record the exact error text for each.

## Experiment 2: Querying with joins

**Objective.** Retrieve across related tables and understand join semantics.

Write queries returning: all members with at least one overdue loan; titles
never borrowed; the member with the most loans in a given month; and, for each
title, the number of copies currently available.

**Expected observation.** The "never borrowed" query must return titles with no
matching loan rows. Compare an inner join, a left join with a null test, and a
`NOT EXISTS` formulation, and record which returns the correct result and why.

## Experiment 3: Aggregation and grouping

**Objective.** Summarise data and understand the difference between filtering
rows and filtering groups.

Produce loan counts by month, average loan duration by title category, and the
categories whose average loan duration exceeds fourteen days.

**Expected observation.** The last query requires `HAVING`, not `WHERE`.
Attempt it with `WHERE` first and record the error; understanding why it fails
is the point of the experiment.

## Experiment 4: Indexing and query plans

**Objective.** Read a query plan and measure the effect of an index.

Load at least fifty thousand loan rows. Run a selective query and record
`EXPLAIN ANALYZE` output. Create an appropriate index, re-run, and record the
plan and timing again.

**Expected observation.** The plan should change from a sequential scan to an
index scan and the execution time should fall. Where it does not, explain why —
a low-selectivity predicate will correctly continue to use a sequential scan,
and recognising that is a better outcome than forcing an index.

## Experiment 5: Transactions and isolation

**Objective.** Observe concurrent behaviour and isolation levels.

Using two sessions, demonstrate a lost update under read-committed isolation,
then prevent it using explicit row locking, then using serializable isolation.

**Expected observation.** Under serializable isolation one transaction must
fail with a serialization error. Record the error and describe how an
application should respond to it.

## Experiment 6: Views and access control

**Objective.** Expose a restricted projection of data.

Create a view exposing loan history without member contact details. Create a
role with select permission on the view but not the underlying tables, and
demonstrate that the role cannot reach the base tables.

**Expected observation.** Direct selection from a base table by the restricted
role must be refused.

## Experiment 7: Stored procedures and triggers

**Objective.** Move an invariant into the database.

Write a trigger preventing a loan from being issued for a copy already on loan,
and a procedure that issues a loan and updates availability atomically.

**Expected observation.** The trigger must fire on the violating insert. Test
that the procedure leaves no partial state when it fails midway.

## Submission

Write-ups follow the departmental format: objective, schema or code, output,
observation, conclusion. Screenshots must be legible; an unreadable screenshot
is treated as absent output.
