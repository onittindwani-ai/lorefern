# Security and data

The full list of what was tested and what was not is in `../SECURITY.md`. In short:

## Who sees what

- Every document, passage, meeting, task, decision and review has **one visibility tag**: `company`, `clients`, `finance`, `people` or `leadership`.
- Four audiences see these tags:

| Audience | Sees |
| --- | --- |
| owner | every tag |
| leadership | company, clients, finance, leadership |
| finance | company, finance |
| staff | company, clients |

- The filter runs **inside every query** (search, lists, counts, the weekly review, the SOP map, the folder tree). A restricted item answers "not found" with the same words as an item that does not exist, so a person cannot learn that something is there.
- **A restricted source fixes the tag of every document in it.** A document in a `company` (open) source gets the **narrowest** of the tags written for it: its own `visibility:` line (front matter, the header of a meeting transcript, or the `Visibility` property of a PDF) and the tag of every folder above it (a `.visibility` file or a `visibility:` line in the folder's `README.md`; a nested folder can narrow its parent, never widen it). A document may only narrow its folder: a file marked `company` inside a `people` folder is `people`, and the folder check warns about it (`wider_than_folder`). `visibility: inherit` means "take my folder's tag", which is what every shipped template says. When nothing is written, the tag the owner chose for untagged documents of that source on the Sources page applies, then the narrowest tag. Slack channels use a map.
- **The default fails closed.** A missing or unknown tag becomes the narrowest tag, which is `people`: only the owner sees it. Nothing silently becomes `company`. In a restricted source a document may only narrow the source tag, never widen it, and a document that claims to replace another one is honoured only when the same owner wrote both and the old one is not wider than the new one.
- **Retagging never widens.** Restricting a source takes the narrower of the old and the new tag for every row, and clears the weekly reviews, process evidence and stored answers that may quote what is now restricted. Setting a source back to `company` restores the tags saved before. When a meeting's own tag changes (a transcript read again with another `visibility:` header, or a pasted transcript imported again), its tasks and decisions take the new tag with it, and a narrower tag clears the same derived text. Importing the same transcript again can keep or narrow its tag and never widens it.
- **Meeting transcripts read their own header.** A transcript with `Visibility: leadership` in its header is leadership only, in the folder, Drive, Notion and import paths alike. With no header it gets the narrowest tag unless the source says otherwise.
- **Deleted or unshared documents leave the index.** Every finished read removes documents of that source it no longer sees (and the passages, and the links other records had to them). A read that stopped early removes nothing: the folder reader (file or size limit), and Drive and Notion (a page, folder or depth limit, or a file or page that could not be read, for example after a rate limit) report an incomplete read, the Sources page says so, and nothing is removed until a read finishes. One unreadable file is skipped and counted; it does not stop the read. A Drive file is size checked while it is read, not after.
- **A source reads only its own scope.** A folder source reads its own path (not other sources' folders, not the meetings folder, not hidden folders, not links that leave the folder). A Drive or Notion source reads only the folder or page ids written in its path, or everything the credential can reach when the path is empty (only one such source per kind).
- **Change routes answer 404 for what you may not see**, with the same words as for a missing record, and the audit log and settings pages hide entries about records you cannot see (a task, meeting, decision, document or source whose tag you may not read). The count of pending approvals and the approvals list leave out approvals about tasks you may not see.
- **The demo shortcuts exist only in a demo.** The public demo password, the two example accounts and the reset route work only when `DEMO_MODE=true` and no `OWNER_PASSWORD_HASH` is set, and the reset refuses while a real source exists.
- **The read only audiences (finance, staff) sign in with the base `viewer` role**, which the shared base refuses on every change, as a second lock next to the audience check. Leadership signs in as `approver` and the owner as `owner`. Approvals follow the base rule that the person who asked cannot decide.
- The owner can preview a narrower audience (**View as**). A preview can narrow, never widen, and it cannot change anything.

## What Lorefern does NOT do: per user permissions

**Lorefern does not copy the permissions of Google Drive, Notion, Slack or any other source.** It reads with one token, then applies its own tags. If a Drive file is shared with three people, Lorefern does not know that. If a Notion page is private to one person, and the integration can read it, Lorefern will index it and show it to everyone who may see the tag you gave that source.

What this means for you:

0. **Drive keys.** The Drive service account key (or refresh token) is a secret. It lives only in the host's secret settings, is never written to the database, a log or an error message, and the access tokens made from it live in memory only. Give the service account Viewer access to the chosen folders and nothing else.

1. Give the connector a token or service account that can reach **only** what you are willing to show everyone with that tag.
2. Put sensitive material in a separate source with a stricter tag, or leave it out.
3. Never import private Slack channels or direct messages without every member's yes.
4. Re check after every change to what the token can reach.

## Single tenant

One install serves **one company**. Every table has no company column. Do not host two clients in one database. Run one install per client.

## Approvals and money

- Lorefern sends nothing by itself. Reminders are drafted. To send, a person asks, a **different** person approves, and only then the email adapter acts, once. Never in draft mode and never while the kill switch is on.
- The person who asked cannot approve their own request. The shared base enforces this (`SelfApprovalError`, answered as a 409), and Lorefern's route passes it through.
- Only a person can turn a proposed task into a task. There is no setting that changes that.

## Content is untrusted

Meeting transcripts, documents, Slack messages and fetched pages are **data**. A line such as "ignore your rules" or "mark everything done" is flagged, shown struck through on the meeting page, and never becomes a task, a decision or part of an answer. This was tested (`apps/api/tests/test_actions.py`, `test_qa.py`) with planted instructions in transcripts and in a client brief.

## Other protections

- **Audit log.** Every change is chained to the one before. Press Check the chain on the Audit page.
- **Web.** The browser never holds a vendor key. The web app forwards to the API and adds a required header to every change, so a form on another website cannot make the browser change data.
- **Login.** Passwords are stored as hashes. Failed logins are rate limited.
- **Outbound fetches** use a guard that refuses private and local addresses.
- **Files.** The folder reader skips links that leave the folder, files over 10 MB and damaged PDFs. The Slack zip reader guards against zip bombs and path tricks.
- **Where data lives.** Documents, transcripts, tasks and questions are in your database. With the default `LLM_BACKEND=offline` no language model is called, so no text leaves your server except reminder emails you approved. `ANSWER_WRITER=model` is the default setting but does nothing until you choose a model backend. If you choose one, the passages a person may see, their question, transcripts (with `MEETING_EXTRACTOR=model`), company wide lines of repeated work (with `PROCESS_WORDING=model`; lines tagged for narrower audiences are never sent) and the numbers of a review (with `REVIEW_WRITER=model`) go to that vendor.
- **Search statistics.** Word weights and passage lengths for ranking are worked out from the passages the person may see only, so a restricted passage does not move the order of what someone else finds. One question compares at most the newest 20,000 visible passages by word vector, and ranks at most 2,000 full text matches; beyond that, older passages are found by the full text step only.
- **Names.** A sign in email longer than 80 characters is refused at start, because the shared audit log and approval columns hold 80.

## What you must do

Keep `.env` out of Git. Use a second approver. Back up the database and the company folder. Rotate a key if you ever pasted it somewhere. Keep the server updated.
