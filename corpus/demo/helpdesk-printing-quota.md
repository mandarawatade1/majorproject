---
title: "Helpdesk: Printing, Print Quota and Common Print Failures"
doc_id: "DEMO/HELP/PRINT/2026/03"
is_demo: true
demo_reason: "Internal helpdesk article on the print service, its quota model
  and failure modes. Not public information. Synthesised with deliberately
  illustrative quota figures that are not real institutional charges."
category: "helpdesk"
department: "IT Services"
created: "2026-02-06"
---

## The quota model

Each student account carries a per-semester print allowance, expressed in pages.
The figures used in this article are illustrative examples only and are not the
institute's actual allowance or charges.

- Single-sided black and white: 1 page counts as 1
- Double-sided black and white: 1 sheet counts as 2
- Colour: 1 page counts as 5

The balance is visible on the portal under Services → Printing. It updates when
the job completes, not when it is submitted, so a job stuck in the queue has not
yet been counted.

## Job submitted but nothing printed

### Check the queue first

A job sitting in the queue has not failed; it is waiting. Queues are per-device.
Submitting the same job again because nothing appeared is the most common cause
of duplicate charges.

### Then check the balance

A job exceeding the remaining balance is rejected silently by some clients. If
the balance is lower than the job size, that is the answer.

### Then check the device

Out of paper, out of toner, or a paper jam will hold the whole queue. The device
panel states which. A jam cleared by a user who then walks away often leaves the
job cancelled rather than resumed; re-submit after confirming the panel is clear.

## Printed but wrong

**Wrong size or scaling.** Set the paper size in the application before printing
rather than relying on the driver default. A document formatted for one size and
printed at another is charged for the pages produced, correctly or not.

**Printed in colour unintentionally.** A document containing a single coloured
element may be sent as a colour job, at five times the count. Set greyscale in
the print dialog when colour is not needed.

**Blank pages at the end.** Usually a trailing empty page in the source
document. These count against the quota. Check the page count in the print
preview, which is the number that will be charged.

## Quota exhausted

A quota top-up is requested through the portal. Top-ups are processed on working
days and are not instant; plan submissions accordingly rather than discovering
an exhausted quota the evening before a deadline.

## Raising a ticket

Include: identity number, the device name from its label, the time of
submission, the document page count, and whether the balance changed. A ticket
saying only "printing not working" cannot be diagnosed and will be returned for
these details.
