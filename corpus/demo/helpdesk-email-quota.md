---
title: "Helpdesk: Institutional Email Quota and Delivery Problems"
doc_id: "DEMO/HELP/MAIL/2026/05"
is_demo: true
demo_reason: "Internal helpdesk articles covering mailbox limits and delivery
  troubleshooting are held in a ticketing system. Quota figures here are
  illustrative placeholders, not the institute's real limits."
category: "helpdesk"
department: "IT Services"
created: "2026-02-14"
---

> Quota figures are **illustrative** and not the real limits.

## Quota

Each account has a mailbox quota and a per-message attachment limit. Both are
visible in the account settings on the mail interface. The figures used as
examples here are a mailbox limit in the low gigabytes and an attachment limit
in the tens of megabytes.

When the mailbox is full, **incoming mail is rejected**, not queued. The sender
receives a bounce and you receive nothing. This is why a full mailbox looks
identical to "nobody is emailing me".

## Symptom: not receiving mail

1. **Check the quota first.** A full mailbox is the most common cause and the
   easiest to miss, because there is no error on your side.
2. Check the spam or junk folder.
3. Check whether a filter or rule is moving or deleting the message. Rules
   created for one purpose often outlive it.
4. Ask the sender whether they received a bounce, and what it said. The bounce
   text usually contains the entire answer.

## Symptom: cannot send

- **Attachment too large.** Compress, or share a link instead of the file.
  Splitting a large file across several messages is worse, not better.
- **Recipient rejected.** Check the address. An address that worked last year
  for a student who has since graduated may no longer exist.
- **Sending limit.** Accounts have a per-hour send limit to contain compromised
  accounts. Bulk mail to a class list should go through the department rather
  than from an individual account.

## Freeing space

Sort by size rather than by date. A handful of messages with large attachments
usually account for most of a full mailbox, and deleting hundreds of small old
messages achieves very little.

Remember to empty the deleted-items folder afterwards; on most systems deleted
mail still counts against the quota until it is purged.

## Institutional mail is externally hosted

Institutional email does not run on the campus network. It stays available
during campus network maintenance — see DEMO/IT/2026/02 — and a campus network
fault is not a mail fault. Diagnosing them together wastes time.

## After graduation

Student accounts are disabled thirty days after the programme end date, per
DEMO/WIKI/IT/012. Mail is not forwarded afterwards. Students should move
anything they want to keep, and update the address on any external service, well
before that date.

## Raising a ticket

Include: your address, the sender or recipient address, the approximate time,
the exact bounce or error text, and your current quota usage. The bounce text is
the single most useful item and the one most often left out.
