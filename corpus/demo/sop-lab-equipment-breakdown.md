---
title: "SOP: Laboratory Equipment Breakdown and Repair Requisition"
doc_id: "DEMO/SOP/LAB/2026/04"
is_demo: true
demo_reason: "Laboratory maintenance procedures are internal operational
  documents held by department staff and are never published publicly.
  Synthesised to provide procedural content with equipment identifiers and
  escalation thresholds for retrieval testing."
category: "sop"
department: "Computer Engineering"
created: "2026-01-19"
---

## 1. Purpose

To define how laboratory equipment faults are reported, triaged, repaired and
recorded, so that teaching is disrupted as little as possible and the asset
register stays accurate.

## 2. Reporting a fault

Any user who observes a fault records it in the lab fault register kept at the
lab assistant's desk, and in the digital register under Lab → Faults. The entry
must state the asset tag, the observed symptom, and whether the machine is
usable in a degraded state. "Not working" is not an acceptable symptom
description; "does not POST, no display, fans spin" is.

Asset tags in this department follow the pattern `DEMO-CE-LAB<n>-<serial>`, for
example `DEMO-CE-LAB3-0142`.

## 3. Triage categories

| Category | Meaning | Response target |
|---|---|---|
| A | Lab cannot run a scheduled practical | Same working day |
| B | One or more workstations unusable, practical can proceed | 3 working days |
| C | Cosmetic or non-blocking | Next maintenance window |

Category A faults are communicated to the Head of Department the same day,
because they may require a session to be rescheduled.

## 4. In-house repair

The lab assistant attempts first-line repair for: peripheral replacement, cable
and connector faults, operating system reinstallation from the standard image,
and RAM or storage reseating. First-line repair is attempted only on equipment
outside its warranty period; opening a machine still under warranty voids it,
and the warranty status is recorded against every asset tag in the register.

## 5. External repair requisition

Where first-line repair fails or is not permitted, the lab assistant raises a
requisition on Form DEMO/LAB/F3 stating the asset tag, fault description, steps
already attempted, warranty status and vendor. The requisition is approved by
the Head of Department before it leaves the department.

Equipment sent off site is recorded as "out for repair" against its asset tag
with the date of despatch and the expected return date. An item overdue by more
than thirty days is escalated to the administrative office for follow-up with
the vendor.

## 6. Condemnation

Equipment beyond economic repair is proposed for condemnation with a written
justification comparing the repair estimate against replacement cost. The
proposal goes to the departmental committee, which meets at the end of each
semester. Condemned equipment is removed from the asset register only after the
committee records its decision; it is never removed on the basis of the
proposal alone.

## 7. Records

The fault register is reconciled against the asset register at the end of each
semester. Discrepancies — an asset marked working that is missing, or an item
out for repair for more than one semester — are listed in the reconciliation
note submitted to the Head of Department.
