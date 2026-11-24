"""Fictional company documents, part B (folders 05 to 11)."""

from tools.seedgen.company_docs_a import add, D  # noqa: F401

add("05 Operations/expense-policy.md", """
# Expense policy

Any expense above $500 needs written approval from Aisha Khan before you buy. Expenses of $500 or less can be bought on the company card and filed in the expenses sheet by Friday.
Receipts are kept for 7 years.
""", owner="Aisha Khan", updated="2026-03-10", typ="policy")
add("05 Operations/weekly-client-report-sop.md", """
# SOP: send the weekly client report

Owner: Marcus Bell. Last reviewed 2026-02-10.

## Steps
1. Export the booking and visit numbers from the analytics tool every Monday morning.
2. Fill the report template for each client.
3. Marcus checks the numbers against the previous week.
4. Send the report from the shared inbox before 15:00.
""", owner="Marcus Bell", updated="2026-02-10", review_by="2026-08-10", typ="sop")
add("05 Operations/invoice-follow-up-sop.md", """
# SOP: invoice follow up

Owner: Aisha Khan. Last reviewed 2026-09-05.

## Steps
1. On the day after the due date, send the friendly reminder from the invoicing tool.
2. At 7 days overdue, call the client contact.
3. At 14 days overdue, tell Priya Nair and pause new work for that client.
""", owner="Aisha Khan", updated="2026-09-05", review_by="2027-03-05", typ="sop")
add("05 Operations/incident-response-sop.md", """
# SOP: respond to a client site incident

Owner: Tom Reyes. Last reviewed 2026-08-30.

## Steps
1. Whoever sees the problem posts in the incidents channel with the client name.
2. Tom takes the incident and posts an update every 30 minutes.
3. After the fix, Tom writes a short note with the cause and what changes.
""", owner="Tom Reyes", updated="2026-08-30", review_by="2027-02-28", typ="sop")
add("05 Operations/weekly-operating-review-sop.md", """
# SOP: run the weekly operating review

Owner: Priya Nair. Last reviewed 2026-10-12.

## Steps
1. Lorefern prepares the review document on Monday morning.
2. Priya reads the stuck work and the new decisions with the team at 09:30.
3. Each stuck task gets a next step and an owner, and Priya records anything decided as a decision record.
""", owner="Priya Nair", updated="2026-10-12", review_by="2027-04-12", typ="sop")
add("05 Operations/office-and-equipment.md", """
# Office and equipment

Laptops are replaced every 3 years. Ask Grace Lin for a new laptop or a monitor. Grace keeps the equipment list.
Visitors sign in at the front desk. Fire drills happen twice a year.
""", owner="Grace Lin", updated="2026-04-18", typ="policy")
add("06 Product and Engineering/support-runbook.md", """
# Support runbook

Sam Oduya answers support questions from the shared inbox. We reply to every question by the next business day.
Questions about billing go to Aisha Khan. Anything that looks like an outage goes to Tom Reyes at once.
""", owner="Sam Oduya", updated="2026-01-15", typ="policy")
add("06 Product and Engineering/release-process-sop.md", """
# SOP: release a client site

Owner: Ravi Menon. Last reviewed 2026-01-20.

## Steps
1. Merge to the main branch only after another developer has reviewed it.
2. Deploy to the staging site and check the booking form.
3. Deploy to production on a weekday before 15:00. Never release on a Friday.
""", owner="Ravi Menon", updated="2026-01-20", review_by="2026-07-20", typ="sop")
add("06 Product and Engineering/tech-stack.md", """
# Tech stack

Client sites use Next.js and a Postgres database. They are hosted on Railway. Tom Reyes owns hosting and backups.
Analytics come from a privacy friendly tool that Marcus Bell configures for each client.
""", owner="Tom Reyes", updated="2026-08-15", typ="other")
add("06 Product and Engineering/backup-and-restore.md", """
# Backup and restore

Databases are backed up every night. Tom Reyes tests a restore once a quarter and writes down the result.
""", owner="Tom Reyes", updated="2025-02-02", typ="policy")
add("07 Finance and Legal/spending-rules.md", """
# Spending rules

Any purchase above $250 needs approval from Aisha Khan before it is made. This applies to every person, including leadership.
""", vis="finance", owner="Aisha Khan", updated="2026-09-20", typ="policy")
add("07 Finance and Legal/budget-2027.md", """
# Budget 2027

The marketing budget is $48,000. The tools budget is $21,000. The training budget is $9,000.
Revenue target for 2027 is $1.1 million.
""", vis="finance", owner="Aisha Khan", updated="2026-11-10", typ="other")
add("07 Finance and Legal/payroll-summary.md", """
# Payroll summary

Fictional figures. Priya Nair earns $98,000. Marcus Bell earns $82,000. Tom Reyes earns $86,000. Dana Ortiz earns $64,000. Total yearly payroll is $641,000.
""", vis="finance", owner="Aisha Khan", updated="2026-10-31", typ="other")
add("07 Finance and Legal/standard-contract-notes.md", """
# Standard contract notes

Our standard services agreement says payment is due within 30 days of the invoice date. It limits our liability to the fees paid in the previous 12 months.
""", vis="clients", owner="Aisha Khan", updated="2026-02-14", typ="policy")
add("08 People/leave-policy.md", """
# Leave policy

Each person has 25 days of paid annual leave plus public holidays. Sick leave is paid for up to 10 days a year without a doctor's note. Ask Grace Lin to record leave.
""", owner="Grace Lin", updated="2026-06-01", typ="policy")
add("08 People/performance-review-process.md", """
# Performance review process

Reviews happen twice a year, in May and in November. Each person writes a short self review. Their lead writes a review and they meet for 45 minutes.
""", owner="Grace Lin", updated="2026-04-20", typ="policy")
add("08 People/salary-bands.md", """
# Salary bands

Fictional bands. Developer band: $70,000 to $95,000. Designer band: $55,000 to $75,000. Support band: $42,000 to $58,000.
""", vis="people", owner="Grace Lin", updated="2026-07-01", typ="policy")
add("08 People/performance-notes-2026.md", """
# Performance notes, 2026

Private notes. Ravi Menon is on a performance plan until January and will be reviewed again then. Dana Ortiz is due for a raise in the November review.
""", vis="people", owner="Grace Lin", updated="2026-11-05", typ="other")
add("08 People/onboarding-a-new-hire-sop.md", """
# SOP: onboard a new hire

Owner: Grace Lin. Last reviewed 2025-12-01.

## Steps
1. Order the laptop two weeks before the start date.
2. Create accounts and add the person to the shared inbox and the team channels.
3. Pair the person with a buddy for the first month.
""", owner="Grace Lin", updated="2025-12-01", review_by="2026-06-01", typ="sop")
add("09 Marketing/content-plan.md", """
# Content plan

We publish two blog posts a month. The newsletter goes out on the first Thursday of each month. Nora Quinn owns both.
""", owner="Nora Quinn", updated="2026-10-05", typ="other")
add("09 Marketing/brand-voice.md", """
# Brand voice

Plain words, short sentences, no jargon. We say "booking" and not "conversion". We never promise rankings.
""", owner="Nora Quinn", updated="2026-03-03", typ="policy")
add("10 Tools and Systems/tools-register.md", """
# Tools register

- Slack: team chat. Owner Priya Nair.
- Google Workspace: email and documents. Owner Grace Lin.
- Railway: hosting. Owner Tom Reyes.
- Invoicing tool: invoices and reminders. Owner Aisha Khan.
- Analytics tool: client site numbers. Owner Marcus Bell.
""", owner="Priya Nair", updated="2026-09-01", typ="other")
add("10 Tools and Systems/access-and-passwords.md", """
# Access and passwords

Everyone uses the company password manager. Two step sign in is required for email, Slack and hosting. Never paste a password into chat. Grace Lin removes access on the last day of a leaver.
""", owner="Tom Reyes", updated="2026-05-11", typ="policy")
