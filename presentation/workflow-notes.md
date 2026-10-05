# Speaker notes — 9 slides, 5–10 minutes

> Written to be said out loud. Cut anything that doesn't sound like you.

---

### Slide 1 — Title · *15 seconds*

> "I'm going to talk about how I actually worked with Claude Code on this
> project. Not what I built — **how we split it, and what I got out of it.**"

---

### Slide 2 — The system · *60 seconds, no longer*

> "Thirty seconds of context so the rest makes sense.
>
> A scheduler fires every weekday at half eleven at night. A Lambda pulls ten
> years of market data for five instruments into S3. A model predicts how much
> gold moves the next day — not which direction, that turned out to be
> unpredictable, but the size of the move. A second Lambda serves that through an
> API and a small demo page, in about half a second.
>
> Costs forty-seven cents a month. That's the system. **Now the interesting
> part.**"

---

### Slide 3 — I think first · *60 seconds*

> "My workflow starts before I open anything.
>
> **I design the architecture myself.** Which services, what runs when, what
> talks to what. On paper first.
>
> Then I show Claude the diagram and talk it through — not as a prompt, as a
> design I already have an opinion about.
>
> That difference matters more than I expected. If I say *build me an MLOps
> pipeline*, I get something generic and I've learned nothing. If I show it a
> diagram and say *here's why I put the Lambda in front of the model* — it
> engages with my reasoning instead of replacing it."

---

### Slide 4 — Persona review · *75 seconds*

> "Then we do something I now use on everything.
>
> I ask Claude to take four roles in turn — ML Engineer, Data Scientist, Data
> Engineer, and the customer — and attack my architecture from each one. Properly
> attack it, not be nice about it.
>
> Every role sees different holes. The Data Engineer asked what happens when
> Yahoo Finance changes its schema. The customer asked what the prediction is
> actually *for*. The first run produced **twenty-seven open questions, three of
> which were real blockers.**
>
> And I decide what to change. Not everything is worth fixing before a deadline —
> but now I know what I'm choosing not to fix.
>
> **This is now a saved skill.** One command, `/persona-review`, and I get the
> same four roles on any architecture, in any project. That's the part I'd
> recommend to all of you — when something works twice, make it a skill."

---

### Slide 5 — Why the CLI · *75 seconds*

> "Then the infrastructure, and this part is **entirely mine.** Every AWS service,
> by hand, through the CLI.
>
> Partly because I just love the terminal. But there's a real reason: **interfaces
> hang.** They change, they move things, buttons get renamed. The CLI is always
> there, and it's the same on every machine.
>
> And the bigger reason — in the console you click. In the CLI you *write*. My
> permissions aren't checkboxes, they're **JSON files I wrote myself**: a trust
> policy saying who is allowed to wear this role, a permission policy saying what
> that role may touch, a lifecycle rule for the bucket.
>
> Writing an IAM policy by hand taught me more about IAM than any tutorial. You
> cannot fake understanding a trust policy — either you know why
> `lambda.amazonaws.com` is in there, or your function can't start."

---

### Slide 6 — The milestone · *90 seconds — this is the heart of the talk*

> "And now the thing that was genuinely a milestone for me.
>
> For days I was typing these long AWS commands straight into the terminal. Ten
> lines, backslashes at the end of each one. And if you make a typo on line
> three — **you can't go back.** You retype the whole thing. I did that more
> times than I want to admit.
>
> Then Claude pointed out something that is completely obvious in hindsight and
> that nobody had told me:
>
> **Write the bash script in VS Code. Run it in the terminal.**
>
> That's it. That's the whole insight. And it changed how the rest of the project
> went.
>
> Because suddenly: it's **reproducible** — I can run it again and get the same
> infrastructure. It's **documented** — the script *is* the record of what I
> built, sitting in the repo next to the code. And it's **understandable** — I can
> read it back in three weeks and see exactly what I did.
>
> Honestly, this was the moment the project stopped feeling like I was flailing at
> a terminal and started feeling like engineering."

---

### Slide 7 — The code · *60 seconds*

> "Here's what one looks like — this is the script that created my ingestion
> Lambda.
>
> You can see the whole thing: the image it runs, the role it wears, arm64, the
> memory, the timeout, the environment variables.
>
> And look at the bottom. **I paste AWS's answer back into the script as a
> comment.** So weeks later I don't just see what I ran — I see what AWS replied.
> That the function went to Pending, that it really got arm64, which handler it's
> pointed at.
>
> All of these live in `infra/manual/` in the repo. That folder is the honest
> record of how this infrastructure came to exist."

---

### Slide 8 — Honesty about the app · *60 seconds*

> "Now the part where I should be straight with you.
>
> **The application itself isn't mine.** I said what the API should do — send a
> date, get a forecast back, features computed on the server. Claude wrote the
> FastAPI app, the Lambda adapter, the demo page, the tests.
>
> And honestly — at the start I didn't really understand what FastAPI *was*. I
> knew it was a web framework and that was about it.
>
> It explained it to me afterwards, and the explanation stuck: FastAPI reads your
> Python type hints and turns them into three things at once — the validation, the
> documentation, and the contract other software reads. Write the data structure
> once, get all three.
>
> **I understand it now. I still didn't write it.** Those are different things and
> I'd rather say so."

---

### Slide 9 — Lessons & flaws · *90 seconds*

> "So — what I take away.
>
> **The good.** The persona review became a reusable skill instead of a one-off
> conversation. Building AWS through the CLI with hand-written policies gave me
> real understanding of IAM, S3, ECR and Lambda — the kind that survives a
> question. And bash scripts in the editor made the whole build reproducible and
> documented.
>
> The thread through all of it: **I stayed the person who can explain the
> infrastructure.** That was the actual goal.
>
> **And the honest part.** Machine learning notebooks are still hard for me.
> Building and training models, evaluating them properly, the maths underneath —
> I'm not there. I can read the results, I can defend the decisions, I can tell
> you why we measure against a naive baseline. **I could not have derived any of
> it on my own.**
>
> That's the gap, and naming it is more useful than pretending.
>
> But I know exactly which half of this I could rebuild from scratch — and that's
> a lot more than I could have said two weeks ago."

---

## If there are questions

**"Didn't it just do everything for you?"**
> "It did, once — early on it built the entire Terraform stack and I couldn't
> explain a line of it. That's why I changed how we work. Now the rule is: it
> never builds something I couldn't rebuild afterwards."

**"How do you check what it tells you?"**
> "Ask AWS, not the agent. `aws iam get-role-policy` shows what's actually there.
> Its summary is a claim, the API response is evidence."

**"Was it ever confidently wrong?"**
> "Yes. My API had a 46-second cold start and it gave me a detailed, plausible,
> wrong diagnosis from the logs. A controlled re-measurement showed the real cause
> and the real number was 2.1 seconds. If I'd believed the first answer I'd have
> over-provisioned memory forever."

**"Would you recommend it?"**
> "For producing, obviously. The thing to watch is that it's fast enough to
> outrun your understanding — and you only notice that when someone asks you a
> question."

---

## Timing

| | |
|---|---|
| Slides 1–2 | 1:15 |
| Slides 3–4 | 2:15 |
| Slides 5–7 | 3:45 |
| Slides 8–9 | 2:30 |
| **Total** | **≈ 9:45** |

Running short? Cut slide 3 to one sentence and trim slide 7.
