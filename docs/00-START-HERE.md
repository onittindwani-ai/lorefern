# Start here

Lorefern is a company brain and operations helper for a small company, set up by an implementer. You point it at the company's written knowledge (a folder of documents, a wiki, a drive, a Slack export, meeting transcripts). It then does six jobs:

1. **Answers questions** with the exact passage it used, and says "not found" when nothing supports an answer.
2. **Turns meetings into tasks.** It reads transcripts, proposes the action items and decisions with the exact words, and a person approves each one. Nothing becomes a task by itself.
3. **Keeps work moving.** It drafts reminders, and flags overdue, blocked, silent and overloaded work.
4. **Maps procedures.** It finds work the company repeats and shows which of it has a written procedure, which is out of date, and which has none.
5. **Writes a weekly review** where every line links to the record it came from.
6. **Keeps a decision log** with the meeting and the words behind each decision.

It also ships a **company folder template**: a numbered skeleton an implementer fills in with a client, so the company's knowledge is organised the way Lorefern reads best. See `10-USING-IT-FOR-A-CLIENT.md` for the implementer's routine.

You can try everything with sample data in about five minutes, with no accounts and no keys.

## Pick your path

| You want to | Read |
| --- | --- |
| See it work now | `01-QUICK-DEMO.md` |
| Check your business basics first | `02-BUSINESS-BASICS-CHECK.md` |
| Understand each page | `WHAT-IT-DOES.md` |
| Connect a drive, wiki, recorder or Slack export | `03-CONNECT-YOUR-TOOLS.md` and `04-ENVIRONMENT-VARIABLES.md` |
| Run it on your computer | `05-RUN-LOCALLY.md` |
| Put it online | `06-DEPLOY-VERCEL.md`, `07-DEPLOY-RAILWAY.md` or `08-DEPLOY-HETZNER.md` |
| Go live safely | `09-GO-LIVE-CHECKLIST.md` |
| Use it for a client: charging, onboarding, handover, the company folder | `10-USING-IT-FOR-A-CLIENT.md` |
| Back up, update, keep it healthy | `11-OPERATING-AND-BACKUPS.md` and `12-UPDATING.md` |
| Understand who can see what | `13-SECURITY-AND-DATA.md` |
| Know the limits | `14-LIMITS-AND-HONEST-NOTES.md` |
| Fix a problem | `15-TROUBLESHOOTING.md` |

## What is real and what is not

- Everything in the demo is sample data and nothing leaves your computer.
- The answer writer in the demo is a set of rules that picks sentences from your documents. It is **not a language model**. Real model wording was not tested here. See `ANSWER-EVAL.md` and `EXTRACTION-EVAL.md` for the measured results, including the poor ones.
- No real vendor was contacted while building this. Every connection was tested only against a local copy that imitates the vendor. `FACTS-AND-SOURCES.md` lists what was read from vendor pages and what was not.
- Lorefern is **single tenant**: one company per install. And it **does not copy the permissions** of Drive, Notion or Slack. Who may see what is set by tags in Lorefern. Read `13-SECURITY-AND-DATA.md` before you connect anything that holds private material.
