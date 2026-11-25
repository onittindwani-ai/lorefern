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
- **The default fails closed.** A missing or unknown tag becomes the narrowest tag, which is `people`: only the owner sees it. Nothing silently becomes `company`. In a restricted source a document may only narrow the source tag, never widen it, and a document that claims to replace another one (`supersedes:`) is honoured only when the same owner is named on both, the replacing document sits in the same folder as the old one or in a folder above it, and the old one is not wider than the new one. The folders are the boundary: anyone who may add files to a folder can still retire a document in it, as they could edit it, so limit who can write to the folders that hold policies. A document that says about itself that it was replaced (a status word, a banner, `superseded_by:`) is believed as written.
- **Retagging never widens.** Restricting a source takes the narrower of the old and the new tag for every row, and clears the weekly reviews, process evidence and stored answers that may quote what is now restricted. Setting a source back to `company` gives every row the tag it would have in an open source, and only to rows that still hold the tag the restriction gave them: a row that was narrowed meanwhile (a line written in its file, a transcript imported again as `people`) keeps the narrower tag, and a row made while the source was restricted gets the tag its file or header says. Every document is also marked as changed, so the next read works its tag out again from the file: a file edited while nobody read it is corrected then, not at the moment of the restore. Tasks and decisions of a meeting follow the meeting. When a meeting's own tag changes (a transcript read again with another `visibility:` header, or a pasted transcript imported again), its tasks and decisions take the new tag with it, and a narrower tag clears the same derived text. Importing the same transcript again keeps its tag unless the caller names another, and can narrow it and never widen it.
- **Meeting transcripts read their own header.** A transcript with `Visibility: leadership` in its header is leadership only, in the folder, Drive, Notion and import paths alike. With no header it gets the narrowest tag unless the source says otherwise.
- **Deleted or unshared documents leave the index.** Every finished read removes documents of that source it no longer sees (and the passages, and the links other records had to them). A meeting the recorder (or the transcript folder) no longer returns leaves the app the same way: its transcript, its indexed text, its decisions and its proposed or rejected tasks are removed, a task a person already approved stays but no longer quotes or points at the transcript, and the weekly reviews, process evidence and stored answers that may quote it are cleared. A transcript a person pasted in is never removed by a read of the recorder, and a transcript folder that could not be read in full (a link, a file that is too large, a file that cannot be opened, a folder that is not there) or a recorder that may have more meetings than it returned (Fireflies returns 50 at a time) removes nothing. A Slack day file that cannot be read keeps its old copy the same way. A read that stopped early removes nothing: the folder reader (file or size limit), and Drive and Notion (a page, folder or depth limit, or a file or page that could not be read, for example after a rate limit) report an incomplete read, the Sources page says so, and nothing is removed until a read finishes. One unreadable file is skipped and counted; it does not stop the read. A Drive file is size checked while it is read, not after.
- **A folder tag that cannot be read fails closed.** A `.visibility` file or folder `README.md` that is a link, larger than 64 KB or unreadable makes its folder owner only (the narrowest tag) until it is fixed, and the Sources page names the file. It never turns into "no tag", which would open the folder.
- **A source reads only its own scope.** A folder source reads its own path (not other sources' folders, not the meetings folder, not hidden folders, not links that leave the folder). A Drive or Notion source reads only the folder or page ids written in its path, or everything the credential can reach when the path is empty (only one such source per kind).
- **Change routes answer 404 for what you may not see**, with the same words as for a missing record, and the audit log and settings pages hide entries about records you cannot see (a task, meeting, decision, document or source whose tag you may not read). The count of pending approvals, the approvals list and the approval entries of the audit log leave out approvals about tasks you may not see, and deciding such an approval answers exactly like deciding one that does not exist. The SOP map works out "covered" and "stale" from the SOPs you may read only, so it never tells you that a restricted SOP exists.
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
- **What an approval says is what is sent.** A send approval lists every recipient with the exact subject and text, and flags an address outside the company's email domains. It keeps a fingerprint of those recipients and texts, and approving it is refused (rejecting is not) when a person, an address or a text is different by then.
- **Task owners keep to the company's domains.** An owner's email must be on `ALLOWED_EMAIL_DOMAINS` (empty: the domains people sign in with), and a reminder is never sent to an address outside them, whoever approved it.
- Only a person can turn a proposed task into a task. There is no setting that changes that.

## Content is untrusted

Meeting transcripts, documents, Slack messages and fetched pages are **data**. A line such as "ignore your rules" or "mark everything done" is flagged, shown struck through on the meeting page, and never becomes a task, a decision or part of an answer. This was tested (`apps/api/tests/test_actions.py`, `test_qa.py`) with planted instructions in transcripts and in a client brief.

## Other protections

- **Audit log.** Every change is chained to the one before. Press Check the chain on the Audit page.
- **Web.** The browser never holds a vendor key. The web app forwards to the API and adds a required header to every change, so a form on another website cannot make the browser change data.
- **Login.** Passwords are stored as hashes. Failed logins are rate limited. Signing out ends the token on this server at once (the list of signed out tokens is in memory, so it is lost when the API restarts, and it is per process), and a live stream closes within about a second of its session ending or being signed out. One person may hold 5 live streams at a time, so they cannot use up the process wide cap of 50.
- **Outbound fetches** use a guard that refuses private and local addresses.
- **Files.** The folder reader skips links that leave the folder, files over 10 MB and damaged PDFs. The Slack zip reader guards against zip bombs and path tricks.
- **Where data lives.** Documents, transcripts, tasks and questions are in your database. With the default `LLM_BACKEND=offline` no language model is called, so no text leaves your server except reminder emails you approved. `ANSWER_WRITER=model` is the default setting but does nothing until you choose a model backend. If you choose one, the passages a person may see, their question, transcripts (with `MEETING_EXTRACTOR=model`), company wide lines of repeated work (with `PROCESS_WORDING=model`; lines tagged for narrower audiences are never sent) and the numbers of a review (with `REVIEW_WRITER=model`) go to that vendor.
- **Search statistics.** Word weights and passage lengths for ranking are worked out from the passages the person may see only, so a restricted passage does not move the order of what someone else finds. One question compares at most the newest 20,000 visible passages by word vector, and ranks at most 2,000 full text matches; beyond that, older passages are found by the full text step only.
- **Names.** A sign in email longer than 80 characters is refused at start, because the shared audit log and approval columns hold 80.

## What you must do

Keep `.env` out of Git. Use a second approver. Back up the database and the company folder. Rotate a key if you ever pasted it somewhere. Keep the server updated.
