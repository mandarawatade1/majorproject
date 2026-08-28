---
title: "Internal Wiki: Laboratory and Server Account Provisioning"
doc_id: "DEMO/WIKI/IT/012"
is_demo: true
demo_reason: "Internal wiki pages documenting account provisioning, naming
  conventions and access tiers are held on an internal system and are never
  public. Synthesised to provide reference-style content with conventions and
  tables for retrieval testing."
category: "internal_wiki"
department: "IT Services"
created: "2026-01-27"
---

## Overview

This page documents how laboratory and server accounts are created, named and
retired. It is the reference for lab assistants and department IT coordinators.

## Account naming

| Account type | Pattern | Example |
|---|---|---|
| Student lab account | `<roll-number-lowercase>` | `b542` |
| Faculty account | `<initial><surname>` | `rfulzele` |
| Departmental service account | `svc-<dept>-<purpose>` | `svc-ce-jenkins` |
| Shared teaching account | `lab<n>-teach` | `lab3-teach` |

Service accounts are never used interactively. If a service account appears in
an interactive login audit, it is treated as a credential compromise and the
account is disabled pending review.

## Access tiers

**Tier 0 — Lab workstation.** Local login on lab machines. Home directory is
local to the machine and is wiped by the reimaging process; nothing of value
should be kept there.

**Tier 1 — Departmental share.** Network home directory with a per-user quota.
Retained for the duration of the programme.

**Tier 2 — Compute server.** Shell access to departmental compute hardware.
Granted on a supervisor's request for a named project, with an expiry date. Not
granted open-ended.

**Tier 3 — Administrative.** Held only by IT Services staff. Never granted to
students, including student assistants.

## Provisioning

Student Tier 0 and Tier 1 accounts are created in bulk at the start of the first
semester from the admitted-students list. Individual creation outside the bulk
run requires the department IT coordinator to raise a request naming the student
and the reason.

Tier 2 accounts require: the supervisor's request, the project name, the
expected end date, and the student's acknowledgement of the acceptable use note.
Requests without an end date are returned rather than granted indefinitely.

## Password policy

Initial passwords are issued once and must be changed at first login. Accounts
that have not had a first login within thirty days of creation are disabled and
must be re-requested; this closes the standing pool of never-used accounts with
known initial passwords.

Passwords are not communicated over email or chat. They are collected in person
against identity verification.

## Retirement

Student accounts are disabled thirty days after the programme end date, and
their Tier 1 data is retained for a further ninety days before deletion.
Students are notified before the deletion date so that work can be copied out.

Faculty accounts are disabled on the last working day and data is retained for
one year, since teaching material is frequently needed by whoever takes over
the course.

Tier 2 accounts expire automatically on the stated end date. Extension requires
a fresh request; extension is not automatic on the basis that the project is
still running.

## Common problems

An account that authenticates on a lab workstation but not on the share is
usually a quota problem rather than a credential problem — check the quota
before resetting anything.
