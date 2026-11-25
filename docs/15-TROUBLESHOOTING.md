# Troubleshooting

| What you see | Why | Fix |
| --- | --- | --- |
| Sign in says "Email or password is wrong" | Demo password used outside demo mode, or no hash set | Set `OWNER_PASSWORD_HASH` (`tools/hash_password.py`) and `DEMO_MODE=false` |
| A team member cannot sign in | No password hash in `MEMBERS_JSON` | Add `password_hash` for that person (doc 04) |
| Web app says it could not reach the server | API not running, or `API_BASE_URL` wrong | Start the API, check the address has no trailing slash |
| Every change returns 400 in your own script | The required header is missing | Send `x-lorefern: 1` (the web app does this for you) |
| Ask says "not found" for something that is written down | Wording differs a lot from the document, or the document has a stricter tag than your audience | Ask with the document's own words, check the document's tag on the Sources page, add a synonym line to the document |
| A document is not found at all | The folder was not read, or the file is INDEX.md (never read) | Press Read again on the Sources page, check `KNOWLEDGE_DIR` |
| Tasks show no owner | The name in the transcript is not on the owners list | Add the person on the Sources page (People who can own work), then change the owner on the task |
| Proposed tasks never appear | No transcript was read yet | Press Run now (demo) or check the worker is running and `MEETINGS_ADAPTER` |
| "Send reminders" waits forever | A second person must approve | Sign in as the approver and open Approvals |
| You cannot approve your own request | By design | Ask another person |
| Company folder page says the folder is not on this machine | `KNOWLEDGE_DIR` points nowhere | Fix the path |
| `make check-env` lists unknown names | Typo in `.env` | Compare with `.env.example` |
| Vercel build cannot find `packages/ui-kit` | Files outside the Root Directory were not included | See doc 06 step 4 |
| Everything is read only | Kill switch is on, and changes answer "The kill switch is on" | Turn it off from the banner, the top bar or Cmd K (owner) |
| Postgres: "relation does not exist" | Migrations not run | `cd apps/api && alembic upgrade head` |

If nothing here helps: run `.venv/bin/python tools/doctor.py` and read every FAIL line.
