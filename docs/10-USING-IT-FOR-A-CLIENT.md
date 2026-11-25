# Using it for a client

One copy of Lorefern serves one client. Do not mix two clients in one database, one company folder, one set of sources or one set of logins. The visibility tags separate people inside one company, not companies from each other.

## What you are selling

Setup, a trial period in draft mode, and a monthly review of the company folder, the tasks and the weekly review. You are selling a company brain that answers with a source and shows when it does not know, and a way for meetings to become tasks that a person approves. You are not selling a promise that every answer is right, a promise that nothing is missed in a meeting, or a promise of fewer meetings. Say that plainly. Lorefern never makes a task, sends a reminder or changes a document by itself.

## What to charge for

This guide gives no price figures. It gives the shape of the offer, so you can price it yourself after looking at your market and your costs.

- **Setup, once.** Business basics check (`02`), a fresh copy for the client, building the company folder with the client (the routine below), tagging every source, connecting the meeting recorder and the document tool, agreeing the working week and the task rules, setting the logins for each audience, and a trial period in draft mode. Charge for the hours and the care, not for the software, which is free.
- **Writing the missing documents, separately.** The SOP map shows which processes have no written procedure, and questions that get "not found" show where a document is missing. Writing those documents is real work for the client's team or for you, priced on its own.
- **Running it, monthly.** A short review of the proposed tasks that waited too long, the stuck list, the documents that disagree, the sources that were not read again, and a check of who can see what after any change of staff. State plainly how many hours a month that includes.
- **Costs that pass through, at cost.** Hosting, the meeting recorder's own fees, the document tool's fees and any model usage. Show these as the client's own accounts, not as your markup.
- **Never charge for** a promised number of tasks found, a promised score, or promised time saved. Never present the demo numbers as a result: the demo company is fictional.

## Onboarding checklist

1. Run `02-BUSINESS-BASICS-CHECK.md` with the client: who agrees to meetings being recorded and read, what is private, how long transcripts are kept.
2. Make a fresh copy for this client with `DEMO_MODE=false`, their company name, their own owner login and their own `SESSION_SECRET`.
3. Decide with the client who is in which audience. The defaults are owner (everything), leadership (company, clients, finance and leadership material), finance (company and finance) and staff (company and client material). The people tag is for the owner only. These are a starting point: the client can move a person, and you can change the tag map in `visibility.py`. Write down who is where, and who can approve tasks (owner and leadership).
4. Build the company folder with the client (the routine below). Tag every source before the first read (`13`). When unsure choose the stricter tag.
5. Connect the meeting recorder first (`03`), then the document tool. For Google Drive use a service account or a consent given once (`03`), and share only the folders that should be read with it.
6. Agree the task rules in plain words: working days, how many days of silence make a task stuck, how many open tasks make a person overloaded. The defaults are Monday to Friday, 10 days, 5 days blocked, 8 open tasks and 5 due within a week. A due date such as "Friday" means the next Friday after the meeting, and "next Friday" means that weekday in the week after.
7. Add the people who may own tasks on the Sources page. A name spoken in a meeting is matched to this list, and without it tasks have no owner.
8. Agree the weekly review: it is built on Monday by default, and every line links to a record. Decide who reads it and who acts on it.
9. Run in draft mode for at least two weeks. Compare the tasks proposed with what people really agreed, and count the misses and the false items.
10. Write 50 or more real questions with the right document for each, run `tools/eval_questions.py` on them, and show the client the measured result, including the misses.
11. Follow `09-GO-LIVE-CHECKLIST.md`.

## Handover

- Give the client their own owner login and one for leadership, set a login for each person who needs one, and remove yours.
- Hand over the backup steps in `11` and the name of the person who updates the app (`12`).
- Hand over the secrets inside the client's own hosting account, never by chat or email. A Drive service account key belongs to the client's own Google account.
- Hand over the company folder, the owners and review dates in it, and the visibility plan you wrote with them.
- Show them the kill switch (Pause all), the audit log check and how the owner previews a narrower audience (View as).
- Agree who answers when Lorefern gets something wrong. It will.

## What to put in the client contract

Plain wording, checked by your own lawyer: what is included in setup and in the monthly work; that third party accounts and their costs belong to the client; that the client owns the data, the documents and the accounts; that the client sets who sees what and approves every task; that Lorefern proposes and a person decides, with no promised results; that the people in recorded meetings have agreed to being recorded and read by software; that the visibility tags are a company set rule and not a copy of the permissions in Drive, Notion or Slack; how long transcripts are kept and who can read them; who answers if something is shown to the wrong person, and how fast; how either side ends the work and what happens to the data afterwards. This is not legal advice.

## Keep it honest

The answer writer in the demo is a rule based stand in, not a language model, and its measured scores are in `ANSWER-EVAL.md` and `EXTRACTION-EVAL.md`. An answer is supported by the document it quotes, which is only as true as the document. The task finder reads made up meetings in the demo: measure it on the client's real ones before you trust it.

## The company folder routine, step by step

1. **Create the folder.** `python3 tools/new_company_folder.py ./client-brain --name "Client name"`. It makes the numbered skeleton (00 Governance to 11 Templates), a README in every folder, `INDEX.md`, `SOURCE-REGISTER.md` and `OWNERS-AND-REVIEW-CADENCE.md`.
2. **Interview, then fill in.** Walk the folders with the client. For each document write: an owner (a named person), a review date, a visibility tag, and a source line (where the fact came from). The templates in `11 Templates` show the shape for a procedure (SOP), a decision record, a meeting note and a client brief.
3. **Tag every document.** The front matter has `visibility:` with company, clients, finance, people or leadership. A document can only narrow the tag of its folder (a `.visibility` file or the `visibility:` line of the folder README), never widen it, so put a document in the folder that matches who may read it, and write `visibility: inherit` to take the folder's tag. A file marked `company` in a `people` folder is `people`. When unsure choose the stricter tag.
4. **Check it.** `python3 tools/check_company_folder.py ./client-brain`. Fix every error (missing README, owner, index entry, review date, bad tag, broken link). `--reindex` rewrites `INDEX.md`. The same check runs on the Company folder page.
5. **Read it in.** Set `KNOWLEDGE_DIR`. Open Sources, press **Add a source**, choose kind `folder`, leave the path empty, pick the tag `company` (each document takes the narrowest of its own `visibility:` line and its folder's tag), then press **Read again**. Put transcripts in a `meetings` folder inside it (set `MEETINGS_ADAPTER=file`), and a Slack export in a sub folder, added the same way with kind `slack`.
5b. **Add the people.** On the Sources page, under People who can own work, add everyone who may own a task. A name spoken in a meeting is matched to this list. Without it tasks have no owner.
6. **Ask ten questions the client's staff really ask.** Anything wrong is a document problem more often than a Lorefern problem: add the missing page or fix the owner.
7. **Hand over the routine below.** The client owns the folder after the first month.

`INDEX.md` is never read into the search, because it lists titles of restricted documents.

## What the owner does each week

- Open **Tasks**, approve or reject the proposed ones, and look at the stuck list.
- Open **Weekly review**, press Generate now if it was not built, read it, and follow the links.
- Open **SOP map** and write a procedure for the red tiles, one a month.
- Open **Decisions** and confirm the proposed ones.
- Open **Approvals** if a second person asked for a send.

## What everyone does

Press Cmd K, ask, check the passage, and open the source when it matters. If the answer is wrong or missing, tell the document's owner.
