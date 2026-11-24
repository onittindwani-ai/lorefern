# Quick demo

About five minutes. You need Python 3.12 or newer (or uv), Node 22 or newer and pnpm (`corepack enable` or `npm i -g pnpm`). No accounts, no keys.

1. `python3.12 -m venv .venv`. No python3.12 on your Mac? Use uv instead: `uv venv --python 3.12 .venv`.
2. `.venv/bin/pip install -e packages/core-py -e "apps/api[dev]"`, or with uv: `uv pip install --python .venv/bin/python -e packages/core-py -e "apps/api[dev]"`. (Steps 1 and 2 together: `make install`.)
3. `pnpm install` then `pnpm build`
4. Start the API in demo mode, in one terminal:
   `DEMO_MODE=true .venv/bin/python -m uvicorn lorefern.api.app:app_from_env --factory --port 8000 --proxy-headers`
5. Start the web app in another: `API_BASE_URL=http://127.0.0.1:8000 INSECURE_COOKIES=1 NEXT_PUBLIC_DEMO_HINT=1 pnpm --filter web start`
6. Open http://localhost:3000 and sign in as `owner@example.test` with the password shown on the sign in page (demo only).

## A walk through

1. **Ask.** Press Cmd K (Ctrl K on Windows) on any page. Ask "How are databases backed up?". The answer shows the passage it came from. Press **Open in source** to see the document with that passage marked.
2. **Run now.** Press the **Run now** button in the banner (or Cmd K, then Run every job now). It reads any transcript it has not read yet, checks stuck work and drafts reminders, and the message tells you how many of each. On a fresh demo the newest meeting is already read, so Proposed is full before you press it. To see a transcript read, open Meetings, press **Import a transcript**, paste lines like `Priya Nair: I will send the board report on Friday.` and import: it is read at once.
3. **Tasks.** Open Tasks. The Proposed column holds what it found. Open a card, press **Approve**, then press **Undo** in the message that appears. Under the board, **Reminder drafts** lists what would be sent; **Ask to send** puts it on Approvals, where a different person has to approve it.
4. **Meetings.** Open a meeting. Action items are marked inside the transcript. A line that tried to give the system orders is struck through and was not acted on.
5. **SOP map.** Open SOP map. Click a red tile to see the repeated work that has no written procedure, with the records that prove it.
6. **Weekly review.** Press **Generate now**. Every line carries a link to its source.
7. **Who sees what.** As the owner, choose **View as** in the top bar and pick staff. Ask "What did the Larkspur Group propose?". You get the same "not found" you would get for something that does not exist. Press **Back to owner view** in the banner.
8. **Sign in as someone else.** The demo accounts are `owner@`, `approver@` (leadership), `finance@` and `staff@` at `example.test`.

The demo clock starts on a made up Tuesday. **+1 day** moves it forward so overdue and stuck work appear. To start again, press Cmd K and choose **Reset the demo data** (owner only).
