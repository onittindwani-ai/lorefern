# Recipes for tools without a built in adapter

## A knowledge source or recorder that is not on the Integrations page

Read apps/api/src/lorefern/adapters/base.py and one existing adapter in sources.py or meetings.py. Write a new adapter for <tool> that follows the same shape, reads the vendor's current API docs and links the page you used, is read only, and adds tests against a local mock of the vendor in mock/. Register it in apps/api/src/lorefern/registry.py as tier B. Do not call the real service. Tell me which facts you could not verify.

## Set up the company folder for a client

Read docs/10-USING-IT-FOR-A-CLIENT.md and templates/company-folder/README.md. Create a folder for <company> with `python3 tools/new_company_folder.py`. Interview me one folder at a time. For every document you write, ask me for the owner, the review date and the visibility tag, and never invent them. Mark anything I have not answered as [NEEDS FOUNDER FACT]. When we are done run `python3 tools/check_company_folder.py` and fix every error.

## Write a procedure for a red tile on the SOP map

Read the evidence of the process <name> on the SOP map. Draft a procedure using templates/company-folder/11 Templates/SOP template. Use only steps that appear in the evidence, and ask me about every step you cannot find. Do not set an owner or a review date for me.

## Measure Lorefern on my own documents

Read docs/ANSWER-EVAL.md. Help me write 50 or more real questions with the right document for each, in a file shaped like data/eval/heldout_questions.json. Run tools/eval_questions.py on it, keep the first run file untouched, and show me every miss.
