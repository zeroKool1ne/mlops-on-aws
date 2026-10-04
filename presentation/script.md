# The Weather Service for Gold
### Ten minutes for someone who has to approve this and does not work in tech

> **The one rule:** no technical term without a picture in front of it. Not
> "Lambda" — "a courier who comes when the alarm rings and leaves again". If you
> catch yourself using a word that does not exist in a weather service, cut it.

---

## Tone — the narrow line

Your audience is **unfamiliar with the field, not slow**, and probably holds the
budget. The distance between "explained well" and "he thinks I'm stupid" is
short, and it is decided almost entirely by tone.

**The stance:** the metaphor is here because *the subject* is unfamiliar, not
because the listener is. So use it naturally and never apologise for it.

**Do not say:**

| Not this | Because |
|---|---|
| "Put very simply…" | announces that you are dialling down |
| "This is heavily simplified" | sounds like *the children's version will do for you* |
| "Does that make sense so far?" | tests them like a classroom |
| "You don't need to understand this" | the opposite of what you want |
| "It's basically like…" | *basically* weakens you along with it |

**Instead** just use the picture without announcing it. "Every evening five
instruments are read" needs no *imagine, in simple terms*.

**The one sentence that defuses the whole problem** — in the first minute, right
after the opening:

> "I'll explain this along a picture, because it's the shortest route. If at any
> point you want the technical detail, say so — I have it with me."

That hands over control. Someone who gets to choose the altitude does not feel
talked down to. And you show in passing that there is something underneath.

---

## The thread

We built **a weather service. Just not for rain — for the price of gold.**

All twelve slides live in that one world. No second metaphor, no switching.

---

## 0:00 – 1:00 · What this is

> "Picture a small weather service.
>
> Every evening, measuring stations are read. The values go into an archive. A
> forecaster has learned to judge tomorrow's weather from those values. And
> anyone who wants to know looks at the app.
>
> That is exactly what we built — except our weather is **the price of gold**."

**Then the control sentence from the Tone section.**

---

## 1:00 – 2:30 · What it can do, and what it honestly cannot

The most important part. It makes you credible before you promise anything.

> "First I have to tell you something unusual for a presentation like this.
>
> **Whether the gold price goes up or down tomorrow, we cannot predict.** Nobody
> can. We tried four different methods, and every one of them was worse than
> guessing.
>
> But — and this is the interesting part:
>
> **How much it moves, we can predict.**
>
> It's the same with weather. Whether a drop falls at two o'clock tomorrow, no
> one knows. Whether tomorrow is calm or stormy — a forecaster can tell you that
> perfectly well.
>
> So the system does not tell you *which way*. It tells you: **tomorrow will be
> quiet**, or **tomorrow will be wild**. For anyone dealing with risk, that is
> the more useful half."

**The number:** *"Today it says: plus or minus 33 dollars. A quiet day."*

---

## 2:30 – 3:30 · The numbers behind it *(fact slide)*

Straight after the picture, the plain slide. The switch is deliberate: picture
first, then the evidence.

> "Here are the numbers.
>
> We measure against a rule of thumb — *tomorrow will be like today*. With
> financial data that is surprisingly hard to beat.
>
> Our model beats it by **2.9 percent**. Tested on **126 trading days it had
> never seen** — that is the point, not the 2.9.
>
> On direction we are at fifty percent. That is a coin flip, and it is on the
> slide because it belongs there."

**If someone pushes on why only 2.9 %:** *"Because that is the honest number. I
could show you a prettier one by testing the model on the same data it learned
from. It would just be worthless."*

---

## 3:30 – 6:30 · How it is built — six stations

Per station: **one sentence of picture, one of substance, one of why.** No more.

### 1. The measuring stations
> "Every evening at half past eleven, five instruments are read: the gold price,
> the dollar, oil, the equity markets, and an index that measures how nervous
> markets are — a **barometer for fear**.
>
> This happens on its own. Nobody presses a button in the morning."

### 2. The alarm clock
> "An alarm clock in the station house rings on weekdays at half past eleven at
> night — after the New York close, so the day is complete. At weekends it does
> not ring. There is nothing to measure."

### 3. The courier who only comes when needed
> "When the alarm rings, a courier collects the values, carries them to the
> archive, and leaves.
>
> **This is the trick that makes the whole thing cheap.** We do not rent an
> office where somebody sits and waits all day. We pay the courier for the thirty
> seconds he is out. The rest of the day he costs nothing."

**The single most important cost statement. Say it slowly.**

### 4. The archive
> "Everything goes into an archive. **Nothing is ever overwritten.** The sheet
> from the day before yesterday is exactly where it belongs.
>
> Why that matters: if in six months somebody asks *how did you arrive at that
> forecast* — we can reconstruct the day exactly. With the data from then, not
> today's."

### 5. The forecaster
> "The forecaster has looked at ten years of weather and learned the patterns. He
> does not sit at his desk all day — he is woken when someone asks, answers in
> half a second, and goes back to sleep.
>
> He too only costs money while he works."

### 6. The front desk
> "In front of the forecaster sits a receptionist. He takes requests, checks they
> make sense, and lets through **at most two per second** — so nobody can
> overrun the forecaster.
>
> Behind that sits the app you'll see in a moment."

---

## 6:30 – 7:30 · Why we built it this way

> "Three decisions, and all three save money or trouble."

### "Nobody sits around waiting"
> "Had we rented a fixed server, it would run day and night and cost money every
> month — including three in the morning on a Sunday when nobody is asking.
> Instead we pay per request.
>
> **The difference: roughly 90 dollars a month against 47 cents.**"

### "One worksheet, not two"
> "The forecaster trained with a particular worksheet. On the job he uses
> **exactly the same one** — not a copy.
>
> It sounds pedantic. It is the most common way systems like this break: two
> worksheets that agree on day one and slowly drift apart. The forecasts become
> quietly wrong. **Nobody notices**, because no error message appears anywhere."

### "The rule of thumb has to be beaten first"
> "There is an old rule of thumb: *tomorrow will be like today.* It sounds like
> nothing and is surprisingly hard to beat.
>
> We turned it into an entrance exam: **a new model only goes into service if it
> beats the rule of thumb by at least two percent.** Otherwise the old one stays.
>
> That is the rule that stops us claiming progress where there is none."

---

## 7:30 – 9:00 · What it costs, and what happens when it breaks

### The cost *(fact slide)*
> "**47 cents a month.** Fully built out, about 1.40.
>
> And here is the odd part: the largest item is not the measuring and not the
> forecaster. **The largest item is the smoke detectors** — the monitoring costs
> more than everything it monitors.
>
> That is normal at this size. We could switch it off and get to ten cents. Then
> nobody would notice when something goes wrong."

### The alarm that matters
> "We have five alarms. Four report when something is **broken** — the easy case.
>
> The fifth is the important one: **it reports when nothing happens.**
>
> Imagine the measuring stations stop sending. Nothing crashes, no error, the app
> keeps answering politely. Only the forecaster is giving you last month's
> weather, and nobody knows.
>
> **That is the most dangerous failure — the one that looks like normal
> operation.** So an alarm fires if nobody has read the stations for four days."

---

## 9:00 – 10:00 · Show it live, and close

**Open the browser, leave the date empty, press Forecast.**

> "This is the app. One button.
>
> What happens in that half second: the front desk takes the question, wakes the
> forecaster, he pulls the current readings, works through his worksheet, looks
> at the patterns he learned — and answers.
>
> **Plus or minus 33 dollars.** Tomorrow will be a quiet day."

### The closing line
> "What is special about this system is not that it predicts the gold price. It
> cannot, and it says so.
>
> What is special is that it **works on its own every day, speaks up when
> something is wrong, and can tell you how good it is.**
>
> For 47 cents a month."

---

## If questions come

**"Can we make money with this?"**
> "Not like this. It doesn't say whether the price goes up. It says how unsettled
> it will be — useful for judging risk, not for betting."

**"Why only 2.9 percent better? That sounds small."**
> "It is small. But it is an **honest** number, on data the system never saw. A
> number that sounds impressive and doesn't hold would bother me a lot more."

**"What if it fails?"**
> "I get an email. And nothing it runs costs money while idle — if nobody asks,
> nothing runs."

**"How long did this take?"**
> "Two weeks, on my own, alongside the course."

---

## Cheat sheet: the four numbers

| | |
|---|---|
| **47 cents** | per month, measured |
| **2.9 %** | better than the rule of thumb, on data never seen |
| **± 33 dollars** | today's forecast |
| **0.5 seconds** | until the answer arrives |
