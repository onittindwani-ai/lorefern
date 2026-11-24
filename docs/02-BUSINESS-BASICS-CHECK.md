# Business basics check

Lorefern reads company documents and meeting transcripts and turns them into answers and proposed tasks. These checks come before a real company folder or a real recorder is connected. The shared guide for the company, domain, website and mailbox setup is `00-BUSINESS-BASICS.md` in the hub repo. This is general information, not legal advice.

1. **Permission to record and transcribe meetings.** Many places require everyone on a call to agree to recording. Tell people before a recorder joins. Lorefern only reads transcripts you give it and cannot decide whether you may record.
2. **Decide who may see what.** Lorefern uses tags as its only visibility rule and does not copy per person permissions from Drive or Notion (see `13-SECURITY-AND-DATA.md`). Keep people files, pay and legal papers out of a folder everyone can ask, or tag them for leadership only.
3. **Keep secrets out.** Do not put passwords, keys or card numbers into the company folder. Lorefern shows quotes from documents in answers.
4. **One owner per area.** Tasks need an owner who can accept or reject them. Name the people for each area of the company before you turn the weekly review on.
5. **A company folder that is true today.** Answers quote your documents. Give each folder an owner and a review date, as the folder template does.
6. **A second person approves.** Lorefern never lets the person who proposed a task approve it. Agree who the second person is.
7. **Know your rules.** Employee data, recordings and cross border storage are regulated in some places. Check where you operate.

Run `make check-env` and `python3 tools/doctor.py` for the technical side. They never print a secret.
