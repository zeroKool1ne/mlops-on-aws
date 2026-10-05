# Design script — hand this to Claude Design

> Build a **9-slide deck**, 16:9, for a 5–10 minute talk to fellow bootcamp
> students. Technical audience, same course, same tools. Clean and pointed —
> code snippets must be legible from the back of the room. All text in English.
> Suggested look: dark slides, monospace for code, one accent colour.

---

## Slide 1 — Title

**Building AWS by hand, with an agent looking over my shoulder**
*What my workflow with Claude Code actually looked like*

Small, bottom: `Gold/USD forecasting · MLOps on AWS · 2 weeks solo`

---

## Slide 2 — The system, in one minute

Headline: **What I built**

A left-to-right row of five labelled steps:

`EventBridge` → `Lambda (ingest)` → `S3 data lake` → `Lambda (API)` → `API Gateway`

Below, three short lines:
- Scheduled ingestion, weekdays 23:30 UTC — 5 instruments, 10 years of data
- A model that predicts **how much** gold moves tomorrow, not which way
- A REST API and a demo page, answering in 0.5 seconds

Bottom strip: `$0.47 / month measured · 60 tests · 15 architecture decisions`

> Note for the designer: this slide is context only. Keep it plain, it gets 60 seconds.

---

## Slide 3 — Step 1 & 2: I think first, then I share

Headline: **It starts with me, not with a prompt**

Two numbered blocks:

**1. I design the architecture myself**
Which services, which path, what runs when. On paper, before any tool is open.

**2. I show Claude the diagram**
Not a prompt — an architecture diagram and my reasoning. It reacts to a *design*,
not to a wish.

Pull quote, large:
> **"If I describe what I want in one sentence, I get one sentence back worth of thinking."**

---

## Slide 4 — Step 3: The persona review

Headline: **Four roles, one architecture**

Centre: four labelled boxes around the word `ARCHITECTURE`:
`ML Engineer` · `Data Scientist` · `Data Engineer` · `The Customer`

Below:
- Claude takes each role in turn and attacks the design from that angle
- First run: **27 open questions, 3 of them real blockers**
- I decide what gets changed — not everything is worth fixing

Highlight box:
**This is now a saved skill: `/persona-review`**
One command, same four roles, on any architecture. Reusable across projects.

---

## Slide 5 — Step 4: The infrastructure is mine, and it goes through the CLI

Headline: **Why I build AWS in the terminal**

Two columns.

**Console**
- Click, click, next
- Nothing to show afterwards
- "What did I set last Tuesday?"
- Interfaces hang, change, move things

**CLI**
- Every setting is a word I typed
- Permissions are **files I wrote**: trust policies, IAM policies, lifecycle rules
- I can read back exactly what exists
- The CLI is always there

Pull quote:
> **"Writing a policy by hand taught me more about IAM than any tutorial."**

Bottom strip: `trust-lambda.json · policy-ingest.json · lifecycle.json · ecr-lifecycle.json`

---

## Slide 6 — The milestone (this is the main slide)

Headline: **The single thing that changed everything**

Large, centred, as the key statement:
> **Write bash scripts in the editor. Run them in the terminal.**
> *Not the other way round.*

Three short reasons, as three columns:

| **Reproducible** | **Documented** | **Understandable** |
|---|---|---|
| Run it again, get the same infrastructure | The script *is* the record of what was built | A typo doesn't mean retyping four lines |

Small line at the bottom: *In the terminal, a long multi-line command with a typo
means starting over. In the editor it's a file — fix one character, run it again.*

---

## Slide 7 — What that looks like

Headline: **`infra/manual/create-lambda.sh`**

A single, legible code block:

```bash
#!/usr/bin/env bash
source "$(dirname "$0")/_env.sh"

aws lambda create-function \
    --function-name "$PROJECT-ingest" \
    --package-type Image \
    --code ImageUri="$IMAGE" \
    --role "arn:aws:iam::$ACCOUNT:role/$PROJECT-lambda-ingest" \
    --architectures arm64 \
    --timeout 300 \
    --memory-size 2048 \
    --environment "Variables={DATA_BUCKET=$BUCKET,LOG_LEVEL=INFO}" \
    --image-config '{"Command":["src.data.ingest.handler"]}'

# OUTPUT:
# goldmlops-ingest   Pending   The function is being created.
# ARCHITECTURES      arm64
# VARIABLES          goldmlops-data-***   INFO
# COMMAND            src.data.ingest.handler
```

Callout beside or under the `# OUTPUT` block:
**I paste the result back in as a comment.** Weeks later I can see not just what
I ran, but what AWS answered.

---

## Slide 8 — Where I leaned on Claude, honestly

Headline: **The application was not mine**

Two blocks.

**What I did**
Said what the API should do. Decided the contract: send a date, get a forecast.

**What Claude did**
Wrote the FastAPI application, the Lambda adapter, the demo page, the tests.

Honest line, set apart:
> **"I didn't really understand what FastAPI was for when we started.
> It explained it to me afterwards — type hints become validation, documentation
> and the contract, all three from one definition. Now I get it. I still didn't
> write it."**

---

## Slide 9 — Lessons learned & Flaws discovered

Split slide, two halves, visually distinct.

### LESSONS LEARNED
- **A reusable review beats a one-off opinion** — `/persona-review` is now a skill, not a conversation
- **CLI + JSON policies = real understanding** of IAM, S3, ECR, Lambda
- **Bash scripts in the editor** made the whole build reproducible and documented
- **I stayed the person who can explain the infrastructure** — that was the point

### FLAWS DISCOVERED
- **ML notebooks are still hard for me.** Building and training models, evaluation, the maths underneath — I am not there yet
- I can read the results and defend the decisions. **I could not have derived them alone.**
- That gap is the next thing to close, and naming it is more useful than hiding it

Closing line across the bottom, large:
> **"I know exactly which half of this I could rebuild from scratch. That's the honest version — and it's more than I could say two weeks ago."**
