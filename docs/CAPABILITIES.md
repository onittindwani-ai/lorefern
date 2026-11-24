# Capabilities

What Lorefern does, with a picture of each page. Pictures are of the demo with made up data. Counts are from `data/counts.json`: <!--n:pages-->11<!--/n--> pages, <!--n:api_operations-->58<!--/n--> API operations, <!--n:tables-->14<!--/n--> tables.

## Ask, with sources

![Ask page with an answer and its source](screenshots/state-1-default-answer-desktop.png)

The answer, the passage it used, how well the search matched and how well each sentence is backed. Open in source shows the document with the passage marked.

![Source viewer](screenshots/state-2-detail-source-viewer-desktop.png)

When two documents disagree, both are shown:

![Documents disagree](screenshots/state-3-warning-documents-disagree-desktop.png)

## Tasks from meetings, approved by a person

![Task board](screenshots/page-tasks-desktop.png)

![Approving a task, with undo](screenshots/state-5-toast-with-undo-desktop.png)

## Meetings, with the exact words marked

![Meeting detail](screenshots/state-8-dark-desktop.png)

## SOP map

![SOP map](screenshots/page-sops-desktop.png)

## Weekly review

![Weekly review](screenshots/page-review-desktop.png)

## Decisions, sources, company folder

![Decisions](screenshots/page-decisions-desktop.png)

![Sources](screenshots/page-sources-desktop.png)

![Company folder](screenshots/page-folder-desktop.png)

## On a phone

![Ask on a phone](screenshots/page-ask-phone.png)

![Tasks on a phone](screenshots/page-tasks-phone.png)

## States

Every page has a loading, empty and error state. The set below is the same at both sizes: default, detail, warning, a button while it works, a message with undo, empty, error and dark. See `screenshots/` (<!--n:screenshots-->39<!--/n--> images).

![Empty](screenshots/state-6-empty-state-desktop.png)

![Error](screenshots/state-7-error-state-phone.png)

## What it does not do

See `14-LIMITS-AND-HONEST-NOTES.md`: rules instead of a language model, no per user source permissions, single tenant.
