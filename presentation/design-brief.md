# Design brief — to hand to Claude Design

> **For Daniel:** select everything below the line, copy it, paste it into Claude
> Design. The spoken text lives in [`script.md`](script.md) and is **not** sent —
> the slides should work with almost no text.

---

Please build me a **12-slide deck** for a ten-minute talk to a decision-maker
with no technical background. **All slide text in English.**

## First: what this deck must NOT be

The audience is unfamiliar with the field, **not slow** — and probably holds the
budget. That difference decides the whole style:

| Not this | This instead |
|---|---|
| Children's book, cartoon, comic faces | **Editorial illustration**, as in a good weekly paper |
| Googly eyes, speech bubbles, exclamation marks | Restrained, adult figures |
| Bright primary colours | Muted, coordinated palette |
| "Explained really simply" | Explained simply, without saying so |

**The bar stays:** someone should look at the image and understand what is
happening without reading a word. But the image must not look as if it were made
for children. The metaphor is there because **the subject** is unfamiliar, not
because the viewer is slow.

Reference point: the illustrations accompanying a long feature in *The Economist*
or *The New Yorker*. Hand-drawn and warm, but calm, precise and grown-up.

## The style

- **Illustration, not infographic.** No boxes with arrows, no flowcharts, no icon
  grids. Drawn scenes.
- **Technique:** ink line with flat watercolour or gouache. Visible stroke, slight
  irregularity — handmade, not vector-smooth.
- **Palette:** muted gold/ochre, slate blue, sage green, warm paper white. One
  stronger accent (muted red), used sparingly.
- **Figures:** stylised, seen from behind or half-turned, faces suggested rather
  than drawn. No cartoon expressions.
- **No logos, no product or brand names** — not in the images, not in the text.

## How every illustrated slide is built

Ten of the twelve slides are illustrated. All the same structure:

```
┌───────────────────────────────────────┐
│                                       │
│          ILLUSTRATION                 │   about 70 % of the area
│                                       │
├───────────────────────────────────────┤
│  $0.47 / month       ·   0.5 seconds  │   fact strip
└───────────────────────────────────────┘
```

The **fact strip** is a narrow line along the bottom: one or two hard figures,
plain sans-serif, no decoration, clearly separated from the image. It ensures
**no slide is without a checkable number**.

Above the image, a headline of **at most six words**.

## The continuous world

Every illustrated slide is set in **one small weather service** — same landscape,
same figures, recognisable from slide to slide.

**The recurring cast:**
- **The forecaster** — calm older person, cardigan, reading glasses. Competent and
  unhurried. No mad-professor cliché, no chaotic desk.
- **The courier** — brisk figure with a satchel and a bicycle, usually in motion or
  cropped at the edge.
- **The older observer** — sits on a fence looking at the sky. Stands for the rule
  of thumb. **Dignified, never a joke.**
- **The decision-maker** — the person who uses the app at the end.

Instead of rain and sun, this is about gold: where a real weather service would
have a cloud, this has a gold coin.

---

## The twelve slides

### 1 — Title · *The Weather Service for Gold*
A small weather station on a hilltop, early evening. In the sky, instead of the
sun, a low gold coin.
**Fact strip:** *Gold/USD · 10 years of data · 29 measurements*

### 2 — *Which way? No. How much? Yes.*
Split image, calmly composed. Left: two arrows, up and down, both finely struck
through. Right: two wave lines, one calm, one agitated, each with a plain check.
No figures — pure sign language.
**Fact strip:** *Direction: 50 % hit rate. Magnitude: 2.9 % better than the rule of thumb.*

### 3 — **FACT SLIDE: The results**
No image. Calm typography, generous white space, one table:

| | Model | Rule of thumb | Difference |
|---|---|---|---|
| Accuracy (RMSE) | 0.00958 | 0.00987 | **+2.9 %** |
| Direction | 49–51 % | 50 % | **no advantage** |

Below, in small type: *Tested on 126 trading days the model had never seen. Four
methods tried; three were worse than doing nothing. That is here because it
belongs here.*
**This slide may be dense and plain — the contrast with the illustrations is the point.**

### 4 — *Five stations, every evening*
Five plain measuring huts along a ridge at dusk, each with a different
instrument. One of them measures nervousness — as a delicate, trembling
barometer, **not** a joke.
**Fact strip:** *Gold · Dollar · Oil · Equities · Volatility index*

### 5 — *An alarm clock, and nobody has to remember*
Interior, night. An alarm clock at half past eleven. The courier reaches for her
satchel. Through the window, the dark measuring huts.
**Fact strip:** *23:30 UTC · Monday to Friday · after the New York close*

### 6 — *Paid for the ride, not for existing*
Two scenes side by side. Left: a lit, empty office building at night. Right: the
courier on her bicycle, a single coin in the air behind her. The contrast carries
the image — no explanatory labels, no arrows.
**Fact strip:** *Own server: about $90/month. This way: $0.47/month.*

### 7 — *Nothing is ever overwritten*
An archive room with dated drawers, warm light. The courier files a new sheet. In
the corner, incidentally, an empty and dusty wastebasket.
**Fact strip:** *Every day filed separately · every forecast reproducible*

### 8 — *One worksheet, not two*
Left, the forecaster learning; right, the same person on the job — and between
them one single large worksheet both are using. Below, small and faint, the wrong
version: two sheets drifting apart.
**Fact strip:** *Same calculation in training and in service · covered by tests*

### 9 — *Beat the rule of thumb first*
The older observer on the fence, looking at the sky. Beside her, as an equal, the
forecaster with an examination sheet. No contest, no winner's face.
**Fact strip:** *Released only above 2 % improvement · achieved: 2.9 % · measured, not estimated*

### 10 — *The worst failure looks like normal operation*
The station house looks peaceful. The measuring huts on the ridge are dark and
overgrown. Inside, a small warning light. Tension through contrast, not drama.
**Fact strip:** *5 alarms · one fires when nothing has happened for four days*

### 11 — **FACT SLIDE: Cost and operations**
No image. Left a cost table, right a short operations summary.

| Item | per month |
|---|---|
| Monitoring | $0.40 |
| Storing the program | $0.07 |
| Compute | $0.004 |
| Data storage | $0.0001 |
| **Total** | **$0.47** |

Beside it: *Response time 0.5 s · 5 alarms · no server billed while idle ·
Same solution on an own server: about $90/month*

One line below, small: *The largest item is the monitoring. It costs more than
everything it monitors — normal and intended at this size.*

### 12 — *One button*
The decision-maker with a phone in hand, the display showing a large **± $33** and
a calm wave. Through the window behind her, small, the weather station on the
hill.
**Fact strip:** *0.5 seconds from question to answer*

---

## Format

- **16:9**
- Illustrated slides: image ~70 %, headline on top (max 6 words), fact strip at
  the bottom
- Fact slides: no illustration, generous white space, one clear table, same
  typeface as the fact strips — the two registers should visibly belong together
- All type legible from ten metres
