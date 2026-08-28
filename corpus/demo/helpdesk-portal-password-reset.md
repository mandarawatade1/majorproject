---
title: "Helpdesk: Student Portal Password Reset"
doc_id: "DEMO/HELP/PORTAL/2026/02"
is_demo: true
demo_reason: "Internal helpdesk article describing an account recovery flow and
  its verification requirements. Not public. Synthesised to provide short
  question-and-answer content that overlaps in vocabulary with the Wi-Fi
  article, so that retrieval precision between similar documents can be
  measured."
category: "helpdesk"
department: "IT Services"
created: "2026-01-30"
---

## Before anything else

Portal credentials and Wi-Fi credentials are the same account. If Wi-Fi also
fails, read DEMO/HELP/WIFI/2026/01 first — resetting the password will not help
if the account itself is disabled.

## Self-service reset

Use Forgot Password on the portal login page. A reset link is sent to the
registered email address. The link is valid for **thirty minutes** and can be
used once.

If the link has expired, request a new one rather than re-clicking the old one.
A used or expired link produces a generic error that is easily mistaken for a
wrong password.

## If the registered email is not reachable

Self-service reset requires access to the registered address. Where that address
is no longer reachable — a personal address that has been lost, or an address
entered incorrectly at admission — self-service cannot work, and no amount of
retrying will change that.

In that case the reset is performed in person at the IT Services desk against
photo identity. Bring the identity card. The address on record is corrected at
the same time so the problem does not recur.

## Account lockout

The account locks after repeated failed attempts. Lockout clears automatically
after **thirty minutes**. It is not cleared faster by further attempts; each
attempt during lockout extends nothing but does confirm the account exists,
which is why the counter is deliberately generous rather than infinite.

## Password requirements

The new password must differ from the previous one, must be at least twelve
characters, and must not contain the identity number or the account name. The
portal states which rule was violated; read the message rather than guessing.

## What IT Services will not do

- Send a password by email or chat, ever
- Reset a password on a request from someone other than the account holder
- Reset on the basis of a phone call, however convincing

These are not obstacles for their own sake. An account with a resettable
password and a reachable requester is an account anyone can take over.

## Raising a ticket

If self-service fails and you can reach the registered email, raise a ticket
with: identity number, the exact error, the time of the attempt, and whether the
reset email arrived at all. Whether the email arrived is the single most useful
fact in this category, and is the one most often omitted.
