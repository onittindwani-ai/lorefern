# Go live checklist

Do every line. Do not skip the first run in draft mode.

1. **Facts to confirm with the company** (Lorefern ships decided defaults, a starting point you change per client): working days, how many days of silence make a task stuck, how many open tasks make a person overloaded, who may approve tasks, who counts as leadership, who may see finance and people material.
2. `DEMO_MODE=false`, a real `OWNER_PASSWORD_HASH`, a long `SESSION_SECRET`, the second approver login set (`APPROVER_EMAIL`, `APPROVER_PASSWORD_HASH`), and a password hash for everyone in `MEMBERS_JSON`.
3. **Decide the visibility tag of every source** (doc 13) before the first read. Read the plain statement there: Lorefern does not copy Drive, Notion or Slack permissions.
4. Run the company folder check (`python3 tools/check_company_folder.py <folder>`) and fix every error. Read the warnings.
5. Load the real documents. Open the Sources page and read the counts. Sign in as each audience (or use View as) and ask a question you know only leadership should see. It must answer "not found" for staff.
6. Run in draft mode for at least two weeks. Compare the tasks Lorefern proposed with what people actually agreed. Count the misses and the false items, because the demo numbers in `EXTRACTION-EVAL.md` are for made up meetings only.
7. Write 50 or more real questions with the right document for each, and run `tools/eval_questions.py` on them. Do not rely on answers you did not measure.
8. Test the kill switch: press Pause all, confirm an approval or an import answers that the kill switch is on, then release it.
9. Test one reminder send end to end: request it, have a second person approve it, check the email arrived. The person who asked cannot approve it.
10. Set `MODE=live` on the server only.
11. Back up the database and the company folder (doc 11) and test the restore once.
12. Decide who reads the weekly review and who approves proposed tasks each week.

When anything looks wrong: Pause all first, ask questions after.
