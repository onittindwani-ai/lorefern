"""The planted tasks. Each row is (key, title, owner, due, status, days since last update, meeting file stem, quote, tag, extra).
`expected_stuck` is written by hand here and is the answer key for stuck work detection. Today in the demo is 2026-12-01."""

from __future__ import annotations

M = lambda n: n  # noqa: E731

# key, title, owner, due, status, idle_days, meeting, quote, tag, extra
ROWS = [
    ("t01", "Send the weekly client report to all five clients", "Marcus Bell", "2026-10-13", "done", 48, "m01-ops-review-2026-10-12", "I'll send the weekly client report to all five clients by Tuesday.", "company", {"process": "weekly client report"}),
    ("t02", "Send the welcome email and kickoff form to Brightside Physio", "Leo Fischer", "2026-10-14", "done", 46, "m01-ops-review-2026-10-12", "I'll send the welcome email and the kickoff form to Brightside Physio by Wednesday.", "company", {"process": "onboarding a new client"}),
    ("t03", "Design the new location page for Brightside Physio", "Dana Ortiz", "2026-10-16", "done", 44, "m01-ops-review-2026-10-12", "I can have a first design by Friday.", "company", {}),
    ("t04", "Chase the overdue invoices", "Aisha Khan", "2026-10-15", "done", 45, "m01-ops-review-2026-10-12", "I'll chase the overdue invoices on Thursday.", "company", {"process": "invoice follow up"}),
    ("t05", "Renew the domain for Corner Cycle Co", "Ravi Menon", "2026-10-15", "open", 45, "m01-ops-review-2026-10-12", "I'll renew the domain for Corner Cycle Co by Thursday.", "company", {"process": "renew domains"}),
    ("t06", "Send the overdue invoice follow up list every Monday", "Aisha Khan", None, "in_progress", 3, "m02-finance-sync-2026-10-14", "I'll send the overdue invoice follow up list every Monday starting next week.", "finance", {"process": "invoice follow up"}),
    ("t07", "Improve the weekly client report template", "Marcus Bell", "2026-10-30", "open", 30, "m03-ops-review-2026-10-19", "I'll improve the weekly client report template and share it by next Friday.", "company", {"process": "weekly client report"}),
    ("t08", "Run the backup restore test", "Tom Reyes", "2026-11-20", "blocked", 15, "m08-ops-review-2026-11-09", "I'll run the backup restore test on the 20th.", "company", {"process": "backup restore test", "blocked_reason": "The staging database is full."}),
    ("t09", "Review the leave policy and bring a proposal", "Grace Lin", "2026-10-26", "done", 40, "m03-ops-review-2026-10-19", "Grace, can you review the leave policy and bring a proposal to the next review?", "company", {}),
    ("t10", "Publish the monthly newsletter", "Nora Quinn", "2026-10-22", "done", 40, "m03-ops-review-2026-10-19", "I'll publish the monthly newsletter on Thursday.", "company", {"process": "publish the monthly newsletter"}),
    ("t11", "Send Harbor Dental a confirmation email", "Leo Fischer", "2026-10-22", "done", 39, "m04-harbor-dental-debrief-2026-10-21", "I'll send the client a confirmation email by tomorrow.", "clients", {}),
    ("t12", "Set up the second booking calendar for Harbor Dental", "Tom Reyes", "2026-10-23", "done", 6, "m04-harbor-dental-debrief-2026-10-21", "I'll set up the second booking calendar this week.", "clients", {}),
    ("t13", "Renew the domain for Harbor Dental", "Leo Fischer", "2026-10-30", "open", 38, "m04-harbor-dental-debrief-2026-10-21", "Let me check the registrar and renew the domain next week.", "clients", {"process": "renew domains"}),
    ("t14", "Update the weekly client report SOP", "Marcus Bell", "2026-10-31", "in_progress", 25, "m05-ops-review-2026-10-26", "I'll update the weekly client report SOP by the end of the month.", "company", {"process": "weekly client report"}),
    ("t15", "Fix the release checklist and send it to Marcus", "Ravi Menon", "2026-10-28", "done", 33, "m05-ops-review-2026-10-26", "I'll fix the release checklist and send it to Marcus by Wednesday.", "company", {"process": "release a client site"}),
    ("t16", "Collect two client testimonials", "Leo Fischer", "2026-11-06", "open", 22, "m05-ops-review-2026-10-26", "I'll ask Harbor Dental and Elm Street Bakery.", "company", {"process": "collect client testimonials"}),
    ("t17", "Start the onboarding of Elm Street Bakery", "Leo Fischer", "2026-11-03", "done", 28, "m06-ops-review-2026-11-02", "I'll start the onboarding of the new client tomorrow.", "company", {"process": "onboarding a new client"}),
    ("t18", "Renew the domains for every client", "Ravi Menon", "2026-11-10", "open", 21, "m06-ops-review-2026-11-02", "I'll renew the domains for every client by the 10th.", "company", {"process": "renew domains"}),
    ("t19", "Write the 14 day pause rule into the invoice follow up SOP", "Aisha Khan", "2026-11-18", "open", 12, "m07-finance-sync-2026-11-04", "I'll write that into the invoice follow up SOP by the 18th.", "finance", {"process": "invoice follow up"}),
    ("t20", "Move the weekly client report to the new template", "Marcus Bell", "2026-11-13", "in_progress", 11, "m08-ops-review-2026-11-09", "I'll move the weekly client report to the new template by Friday.", "company", {"process": "weekly client report"}),
    ("t21", "Collect client testimonials from Brightside Physio and Lantern Books", "Sam Oduya", "2026-11-20", "open", 12, "m08-ops-review-2026-11-09", "I'll collect client testimonials from Brightside Physio and Lantern Books by the 20th.", "company", {"process": "collect client testimonials"}),
    ("t22", "Renew the Lantern Books domain", "Ravi Menon", "2026-11-18", "done", 7, "m10-ops-review-2026-11-16", "I'll renew the Lantern Books domain on Wednesday.", "company", {"process": "renew domains"}),
    ("t23", "Rewrite the Care Plan description", "Marcus Bell", "2026-11-30", "open", 12, "m11-leadership-2026-11-18", "I'll rewrite the Care Plan description by the 30th.", "leadership", {}),
    ("t24", "Update the budget model with the Care Plan price", "Aisha Khan", "2026-11-27", "done", 4, "m11-leadership-2026-11-18", "I'll update the budget model with that by next Friday.", "leadership", {}),
    ("t25", "Update the pricing page for the new Care Plan wording", None, None, "open", 8, "m09-marketing-release-2026-11-11", "Someone needs to update the pricing page for the new Care Plan wording.", "company", {}),
    # manual tasks, not from a meeting
    ("m01", "Prepare the Q4 client review deck", "Marcus Bell", "2026-12-08", "open", 3, None, "", "company", {}),
    ("m02", "Draft the March Care Plan renewal offers", "Marcus Bell", "2026-12-12", "in_progress", 2, None, "", "company", {}),
    ("m03", "Review the staging cleanup plan", "Marcus Bell", "2026-12-04", "open", 5, None, "", "company", {}),
    ("m04", "Update the project template", "Marcus Bell", "2026-12-15", "open", 6, None, "", "company", {}),
    ("m05", "Plan January delivery capacity", "Marcus Bell", "2026-12-18", "open", 4, None, "", "company", {}),
    ("n01", "Move the client folder to the new structure", "Ravi Menon", None, "in_progress", 18, None, "", "company", {}),
    ("n02", "Review the contract template for the 2027 renewals", "Aisha Khan", "2026-12-20", "in_progress", 16, None, "", "clients", {}),
    ("n03", "Prepare the onboarding checklist for the March hire", "Grace Lin", None, "open", 24, None, "", "company", {}),
    ("n04", "Write the Elm Street Bakery case study", "Nora Quinn", "2026-12-18", "open", 12, None, "", "company", {}),
    ("b01", "Switch Harbor Dental to the new analytics tool", "Tom Reyes", "2026-12-15", "blocked", 9, None, "", "clients", {"blocked_reason": "Waiting for the client to grant access."}),
]

# Hand written answer key for stuck work as of 2026-12-01 (not computed by the detector).
EXPECTED_STUCK = [
    ("t05", "overdue"), ("t07", "overdue"), ("t08", "overdue"), ("t08", "blocked"), ("t13", "overdue"), ("t14", "overdue"), ("t16", "overdue"),
    ("t18", "overdue"), ("t19", "overdue"), ("t20", "overdue"), ("t21", "overdue"), ("t23", "overdue"),
    ("n01", "no_update"), ("n02", "no_update"), ("n03", "no_update"), ("n04", "no_update"), ("b01", "blocked"),
    ("t25", "unassigned"),
]
EXPECTED_OVERLOADED = ["Marcus Bell"]
