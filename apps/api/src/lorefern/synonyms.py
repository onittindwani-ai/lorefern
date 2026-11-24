"""Words people use for the same thing as the company documents. Built by hand, then extended only from failures on the DEVELOPMENT question set (never from the held out set,
which is run once before any change to this file and saved untouched). It is an offline stand in for what a language model embedding would do."""

from lorefern.textproc import stem

RAW: dict[str, list[str]] = {
    "refund": ["credit", "reimburse"], "boss": ["owner", "lead"], "salary": ["pay", "compensation", "payroll", "earn", "wage"],  "holiday": ["leave", "vacation"], "vacation": ["leave", "holiday"],
    "sick": ["leave", "illness"], "laptop": ["equipment", "device"], "buy": ["purchase", "spend"], "spend": ["purchase", "expense"], "expense": ["spend", "reimbursement"], "bill": ["invoice"],
    "customer": ["client"], "client": ["customer"], "fire": ["terminate", "offboarding"], "hire": ["onboarding", "recruit"], "start": ["onboarding", "begin"], "newcomer": ["onboarding", "hire"],
    "quit": ["offboarding", "resign"], "password": ["credential", "login"], "login": ["password", "account"], "meeting": ["call", "sync"], "weekly": ["week"], "chase": ["follow", "overdue"], "late": ["overdue"],
    "choose": ["decide", "decided"], "chose": ["decide", "decided"], "price": ["rate", "fee", "cost"], "pay": ["due", "payment", "salary", "payroll"], "due": ["pay", "payment"], "payment": ["pay", "due"], "purchase": ["expense", "spend", "buy", "approval"], "big": ["above", "limit"], "asking": ["approval"], "framework": ["next", "stack", "tech"], "tone": ["voice", "plain"], "earn": ["salary", "pay", "payroll"], "buying": ["purchase", "expense"], "propose": ["offer"], "acquire": ["buy", "offer"], "offer": ["acquire"],
     "approve": ["sign", "authorize", "approval"], "approval": ["approve", "sign"], "limit": ["cap", "maximum"], "cap": ["limit", "maximum"], "deadline": ["due"], "vehicle": ["truck", "van"], "car": ["vehicle", "truck"], "truck": ["vehicle", "van"], "van": ["vehicle", "truck"],
     "worker": ["employee", "staff"], "employee": ["staff", "worker"], "technician": ["employee", "staff"], "complaint": ["issue", "problem"], "warranty": ["guarantee"], "guarantee": ["warranty"], "discount": ["rebate", "deal"], 
     "insurance": ["coverage"], "manager": ["supervisor"], "supervisor": ["manager"], "phone": ["mobile", "cell"], "mobile": ["phone", "cell"], "location": ["address"], "address": ["location"], "bonus": ["commission", "incentive"], "vendor": ["supplier", "provider"],
     "supplier": ["vendor"], "contract": ["agreement"], "agreement": ["contract"], "appointment": ["booking", "schedule"], "booking": ["appointment"], "license": ["permit", "certification"], "permit": ["license"],
     "stock": ["inventory"], "inventory": ["stock"], "equipment": ["tool", "device"], 
     "cost": ["price", "fee"], "fee": ["price", "rate"], "backup": ["restore", "copy"], "outage": ["incident", "down"], "incident": ["outage"], "release": ["deploy", "ship"],
}
EXPAND: dict[str, list[str]] = {stem(k): [stem(v) for v in vs] for k, vs in RAW.items()}


def expand(stems_: list[str]) -> list[str]:
    out = list(stems_)
    for w in stems_:
        for x in EXPAND.get(w, []):
            if x not in out:
                out.append(x)
    return out
