# Glossary

| Word | Meaning here |
| --- | --- |
| Audience | Who is looking: owner, leadership, finance or staff. It decides which tags are visible. |
| Tag (visibility tag) | One of company, clients, finance, people, leadership on every document, meeting, task, decision and review. |
| Source | A place Lorefern reads from: a folder, a Slack export, a recorder, Drive or Notion. |
| Document | One readable file or page after it was read into the index. |
| Chunk (passage) | A short piece of a document, with its section heading. Search and citations work on passages. |
| Citation | The passage an answer relies on, with title, section, owner and date, and a link to the document at that spot. |
| Groundedness check | A check, in code, that every sentence of an answer is backed by its source passage. A sentence that fails is dropped. |
| Not found | The answer when nothing visible supports an answer. It is the same for missing and for restricted material. |
| Conflict | Two visible documents say different things. Lorefern shows both and picks neither. |
| Proposal | A task or decision found in a transcript. It waits for a person. |
| Approval | A person accepting a proposal, or a second person accepting a request such as sending reminders. |
| Stuck work | A task that is overdue, silent, blocked too long, unassigned, or belongs to an overloaded person. |
| SOP | Standard operating procedure: a written way of doing a repeated job. |
| SOP map | Repeated work matched against written procedures: covered, needs review or no procedure. |
| Company folder | The numbered folder of documents Lorefern learns from. The template is in `templates/company-folder/`. |
| Draft mode | Nothing is sent. Reminders are drafted only. |
| Kill switch | A setting that stops every send and every change at once, including the background jobs. Questions can still be asked. |
| Adapter | A small piece of code that reads one tool, with the same shape for every tool in its group. |
| Held out set | Test questions or transcripts written before the rules ran on them, never tuned on. |
| Single tenant | One company per install. |
| Implementer | The person who sets Lorefern up for a company. |
