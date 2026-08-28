---
title: "Helpdesk: Campus Wi-Fi Will Not Authenticate"
doc_id: "DEMO/HELP/WIFI/2026/01"
is_demo: true
demo_reason: "Helpdesk knowledge base articles live in an internal ticketing
  system and are not published. Synthesised to provide short troubleshooting
  content in a question-and-answer shape, which stresses retrieval differently
  from long procedural documents."
category: "helpdesk"
department: "IT Services"
created: "2026-01-30"
---

## Symptom

The device sees the campus network but authentication fails, or the device
connects and then immediately disconnects.

## Work through these in order

### 1. Confirm the account is active

An account disabled for non-payment of dues, or a student account past its
programme end date, will fail authentication while still showing the network.
Check the portal: if the portal also refuses the credentials, the problem is the
account, not the Wi-Fi, and no amount of reconnecting will help.

### 2. Check you are on the right network

The campus publishes a staff network, a student network and a guest network.
Student credentials do not authenticate against the staff network. A device that
previously connected to guest access may keep trying it.

### 3. Forget the network and reconnect

A device that has cached an old password or an old certificate will fail
silently. Forget the network entirely, then reconnect and enter credentials
fresh. This resolves the majority of tickets in this category.

### 4. Check the certificate prompt

On first connection the device should present a certificate for the
authentication server. Accept it only if it matches the one published on the
portal. If a certificate appears that does not match, stop, do not accept it,
and report it — that is a security matter, not a connectivity one.

### 5. Check the device clock

A device whose date is significantly wrong will reject a valid certificate as
not yet valid or expired. Set the clock to network time and retry.

### 6. Try a second device

If a second device authenticates on the same credentials, the problem is the
first device. If neither does, the problem is the account.

## When to raise a ticket

Raise a ticket if all six steps have been completed and authentication still
fails. Include: your identity number, the device type and operating system
version, which network you attempted, the exact error shown, and which of the
steps above you have already done.

Tickets that do not state which steps were attempted are returned with a request
for that information, which delays resolution by a day.

## What will not be done

Passwords are not reset over the phone or by email, and never on the basis of a
message alone. Reset is in person against identity verification, per
DEMO/WIKI/IT/012.
