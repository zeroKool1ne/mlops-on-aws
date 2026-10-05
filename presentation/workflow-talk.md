# Working with an AI agent — what actually happened
### 7 minutes · what I learned building an MLOps pipeline with Claude Code

---

## 0:00 – 0:45 · The setup

> "I built an end-to-end MLOps pipeline on AWS — scheduled ingestion, a trained
> model, a REST API, monitoring. Two weeks, on my own.
>
> Except not on my own. I built it with an AI agent in my terminal.
>
> What I want to talk about is not the pipeline. It's **how we split the work —
> because I got that wrong twice before I got it right.**"

---

## 0:45 – 2:30 · Version 1: I let it do everything

> "We agreed a split: I'd do the AWS infrastructure, it would do the machine
> learning model.
>
> What actually happened: I asked for infrastructure as code, and forty seconds
> later I had a complete Terraform stack. Forty-six AWS resources. It ran.
>
> And I stared at it and realised **I could not explain a single line of it.**
>
> Four days before a presentation where I'd be asked exactly that. Plus I have an
> AWS certification exam coming up, and the exam asks about precisely these
> services.
>
> So I stopped it and said: *you have built everything yourself, I have little to
> no idea what you did there, this gives me nothing.*"

**The lesson, say it plainly:**

> "**The agent is fast enough to outrun your understanding.** That is not a bug.
> It is the thing you have to manage."

---

## 2:30 – 4:30 · Version 2: I build, it explains and checks

> "So we flipped it. New rule: **I build every AWS service myself, by hand, in the
> CLI. Claude writes the instructions and then verifies what I built.**
>
> Slower. Much better. I learned IAM roles, trust policies, ECR, Lambda — by
> typing them and breaking them.
>
> And here is where it got interesting, because the checking turned out to be the
> valuable half."

**Three things it caught that I would not have:**

### 1. A transposed digit
> "I wrote an IAM policy pointing at account `...4812` instead of `...4218`.
>
> **AWS accepts that without complaint.** It does not validate account numbers in
> policies. The policy is syntactically perfect and simply never applies.
> It would have failed silently, weeks later, and I'd have had no idea why."

### 2. A permission that covered half the job
> "The policy let the function write to one folder. The code writes to two.
>
> It would have run, done the expensive part, and died on the last step."

### 3. Logs that never appeared
> "My code had logging in it. Nothing showed up in CloudWatch. Not an error —
> just silence.
>
> Turns out `logging.basicConfig` does nothing inside Lambda, because the runtime
> has already configured the logger. So every log line was being thrown away.
>
> **None of these three produce an error message.** That is what they have in
> common. They are the failures that look like success."

---

## 4:30 – 6:00 · Version 3: stop making rules

> "Then the second mistake — and this one was mine.
>
> That rule, *I build everything myself*, became a stick to beat myself with. I'm
> a single parent, I'm doing this course alongside everything else, and some days
> there simply isn't the capacity to hand-build an API gateway.
>
> So I threw out the fixed agreement. Now we decide per situation: **when I have
> the energy, I build and it explains. When I don't, it builds and we walk through
> it afterwards.**
>
> Both are fine. What is not fine is a workflow that only works on a good day."

---

## 6:00 – 7:00 · What I actually learned

> "Three things.
>
> **One — the skill isn't prompting. The skill is verifying.** Anyone can get an
> agent to produce a Terraform file. Knowing whether that file is right is the
> job. Every real catch in this project came from checking, not from asking.
>
> **Two — the agent is confidently wrong sometimes, and you have to measure.**
> My API had a 46-second cold start. Claude read the logs and told me: 19 seconds
> of imports, 27 seconds loading the model. Plausible, detailed, wrong. A
> controlled re-measurement showed it was the one-time download of the container
> image. The real number was 2.1 seconds. **If I'd trusted the first answer I'd
> have paid for memory I didn't need, forever.**
>
> **Three — push back.** At one point it wanted to push a container image to a
> registry and I asked what was actually inside it. It didn't know in detail. So
> we opened it up first. *You can't ship something when you don't know what's in
> it* — that applies to an agent's output exactly as much as to anyone else's."

### The closing line

> "I didn't learn how to make an AI write code for me. That part is easy.
>
> **I learned how to stay the person who understands the system.** And that is a
> choice you make every few hours, not once at the start."

---

## If questions come

**"Did it make you faster?"**
> "Enormously — at producing. Not at understanding. Those are different speeds,
> and the second one is the one that matters for an exam or a job interview."

**"How do you check something you don't understand yet?"**
> "You make it explain first, then you look at the actual state yourself.
> `aws iam get-role-policy` tells you what is really there. The agent's summary is
> a claim; the API response is evidence."

**"Would you use it again?"**
> "Daily. But with the rule I ended up with: it never builds something I couldn't
> rebuild myself afterwards."

**"What surprised you most?"**
> "How convincing a wrong explanation sounds when it comes with log timestamps
> and a confident tone."

---

## Numbers you can quote

| | |
|---|---|
| **2 weeks** | solo, alongside the course |
| **15** | architecture decisions documented, with trade-offs |
| **60** | tests, all offline |
| **$0.47** | measured monthly cost of the running system |
| **2.9 %** | the model's honest margin over a naive baseline |
| **3** | silent failures caught by verification, none of which raised an error |

---

## Five slides, if you want them

1. **Title** — "Building with an agent: what I got wrong twice"
2. **Version 1** — one line: *"46 AWS resources. I could not explain one of them."*
3. **Version 2** — the three silent failures, as three short lines
4. **Version 3** — *"When I have the energy, I build. When I don't, it builds and I catch up."*
5. **The lesson** — *"The skill isn't prompting. The skill is verifying."*
