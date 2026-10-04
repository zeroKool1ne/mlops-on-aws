# Der Wetterdienst für Gold
### 10 Minuten für jemanden, der es absegnen muss und nichts von Technik versteht

> **Die eine Regel für diesen Vortrag:** Kein einziges Fachwort ohne Bild davor.
> Nicht „Lambda", sondern „ein Bote, der nur kommt, wenn der Wecker klingelt —
> und sofort wieder geht". Wenn du merkst, dass du ein Wort benutzt, das es im
> Wetterdienst nicht gibt, streich es.

---

## Der rote Faden

Wir haben **einen Wetterdienst gebaut. Nur nicht für Regen, sondern für den Goldpreis.**

Alles im Vortrag spielt in dieser einen Welt. Keine zweite Metapher, kein Wechsel.

---

## 0:00 – 1:00 · Was ist das überhaupt

> „Stellen Sie sich einen kleinen Wetterdienst vor.
>
> Jeden Abend lesen Messstationen ihre Geräte ab. Die Werte wandern in ein
> Archiv. Ein Meteorologe hat gelernt, aus diesen Werten das Wetter von morgen
> abzuschätzen. Und wer wissen will, wie morgen wird, schaut in die App.
>
> Genau das haben wir gebaut — nur ist unser Wetter der **Goldpreis**."

**Auf der Folie:** eine kleine Wetterstation auf einem Hügel, daneben ein Goldbarren statt einer Sonne.

---

## 1:00 – 2:30 · Was es kann — und was es ehrlicherweise nicht kann

Das ist der wichtigste Teil. Er macht dich glaubwürdig, bevor du irgendetwas versprichst.

> „Jetzt muss ich Ihnen zuerst etwas sagen, was ungewöhnlich ist für so eine
> Präsentation.
>
> **Ob der Goldpreis morgen steigt oder fällt, können wir nicht vorhersagen.**
> Niemand kann das. Wir haben es mit vier verschiedenen Verfahren versucht, und
> jedes einzelne war schlechter als raten.
>
> Aber — und das ist das Interessante:
>
> **Wie stark er sich bewegt, können wir vorhersagen.**
>
> Beim Wetter ist das genauso. Ob morgen genau um 14 Uhr ein Tropfen fällt,
> weiß kein Mensch. Ob morgen ein ruhiger Tag wird oder ein stürmischer — das
> sieht ein Meteorologe sehr wohl.
>
> Unser System sagt Ihnen also nicht *wohin*. Es sagt Ihnen: **morgen wird es
> ruhig** oder **morgen wird es wild**. Für jeden, der mit Risiko zu tun hat,
> ist das die wichtigere Hälfte."

**Die Zahl dazu:** *„Heute sagt es: plus/minus 33 Dollar. Ein ruhiger Tag."*

**Auf der Folie:** links ein Pfeil nach oben und einer nach unten, beide durchgestrichen. Rechts eine ruhige Welle und eine wilde Welle, beide mit Haken.

---

## 2:30 – 6:00 · Wie es gebaut ist — sechs Stationen

Pro Station: **ein Satz Bild, ein Satz Technik, ein Satz Warum.** Nicht mehr.

### 1. Die Messstationen
> „Jeden Abend um halb zwölf werden fünf Messgeräte abgelesen: der Goldpreis,
> der Dollar, das Öl, die Aktienmärkte und ein Index, der misst, wie nervös die
> Märkte gerade sind — eine Art **Barometer für Angst**.
>
> Das passiert von allein. Niemand muss morgens einen Knopf drücken."

### 2. Der Wecker
> „Ein Wecker im Stationshaus klingelt werktags um halb zwölf abends. Nach
> Börsenschluss in New York, damit der Tag vollständig ist. Am Wochenende
> klingelt er nicht — da gibt es nichts zu messen."

### 3. Der Bote, der nur kommt wenn er gebraucht wird
> „Wenn der Wecker klingelt, kommt ein Bote, holt die Werte ab, trägt sie ins
> Archiv und geht wieder.
>
> **Das ist der Trick, der das Ganze so billig macht.** Wir mieten kein Büro,
> in dem jemand den ganzen Tag sitzt und wartet. Wir bezahlen den Boten für die
> dreißig Sekunden, die er unterwegs ist. Den Rest des Tages kostet er nichts."

**Das ist die wichtigste Kostenaussage des Vortrags. Langsam sprechen.**

### 4. Das Archiv
> „Alles wandert in ein Archiv im Keller. **Nichts wird je überschrieben.** Der
> Zettel von vorgestern liegt noch genau da, wo er hingehört.
>
> Warum das wichtig ist: Wenn in einem halben Jahr jemand fragt *‚wie seid ihr
> denn damals auf diese Vorhersage gekommen?'* — dann können wir den Tag genau
> nachstellen. Mit den Daten von damals, nicht mit den heutigen."

### 5. Der Meteorologe
> „Der Meteorologe hat zehn Jahre Wetter angeschaut und daraus Muster gelernt.
> Er sitzt nicht den ganzen Tag am Schreibtisch — er wird geweckt, wenn jemand
> fragt, beantwortet die Frage in einer halben Sekunde und schläft weiter.
>
> Auch er kostet nur, wenn er arbeitet."

### 6. Der Empfangsschalter
> „Vor dem Meteorologen sitzt jemand am Empfang. Der nimmt Anfragen an, prüft,
> ob sie Sinn ergeben, und lässt **höchstens zwei pro Sekunde** durch — damit
> niemand den Meteorologen überrennen kann.
>
> Dahinter liegt die App, die Sie gleich sehen."

**Auf der Folie:** alle sechs Stationen als ein Weg von links nach rechts, wie ein Brettspiel.

---

## 6:00 – 7:30 · Warum wir es so gebaut haben

> „Drei Entscheidungen, und alle drei sparen Geld oder Ärger."

### „Niemand sitzt herum und wartet"
> „Hätten wir einen festen Server gemietet, würde der Tag und Nacht laufen und
> jeden Monat Geld kosten — auch sonntags um drei Uhr nachts, wenn niemand
> fragt. Stattdessen zahlen wir pro Anfrage.
>
> **Unterschied: etwa 90 Dollar im Monat gegen 47 Cent.**"

### „Ein Rechenblatt, nicht zwei"
> „Der Meteorologe hat in der Ausbildung mit einem bestimmten Rechenblatt
> gearbeitet. Im Dienst benutzt er **genau dasselbe** — nicht eine Abschrift.
>
> Klingt pedantisch. Ist aber die häufigste Art, wie solche Systeme kaputtgehen:
> Zwei Rechenblätter sind am ersten Tag gleich und driften dann langsam
> auseinander. Die Vorhersagen werden still falsch. **Niemand merkt es**, weil
> nirgendwo eine Fehlermeldung erscheint."

### „Der Bauernregel-Opa muss geschlagen werden"
> „Es gibt in jedem Dorf einen alten Mann, der sagt: *‚Morgen wird's wie heute.'*
> Er hat erstaunlich oft recht.
>
> Wir haben die Regel aufgestellt: **Ein neuer Meteorologe kommt nur in den
> Dienst, wenn er den Opa um mindestens zwei Prozent schlägt.** Sonst behalten
> wir den alten.
>
> Unserer schlägt ihn um **2,9 Prozent** — gemessen an einem halben Jahr, das er
> vorher nie gesehen hat."

---

## 7:30 – 9:00 · Was es kostet und was passiert, wenn es kaputtgeht

### Die Kosten
> „**47 Cent im Monat.** Fertig ausgebaut etwa 1,40.
>
> Und jetzt das Komische daran: Der größte Posten sind nicht die Messungen und
> nicht der Meteorologe. **Der größte Posten sind die Rauchmelder** — die
> Überwachung kostet mehr als alles, was sie überwacht.
>
> Das ist bei kleinen Systemen normal. Wir könnten sie abschalten und auf zehn
> Cent kommen. Dann würde nur niemand merken, wenn etwas schiefgeht."

### Der Alarm, der zählt
> „Wir haben fünf Alarme. Vier davon melden, wenn etwas **kaputt** ist — das ist
> der einfache Fall.
>
> Der fünfte ist der wichtige: **er meldet, wenn nichts passiert.**
>
> Stellen Sie sich vor, die Messstationen hören auf zu senden. Nichts stürzt ab,
> keine Fehlermeldung, die App antwortet weiter freundlich. Nur: der Meteorologe
> sagt Ihnen das Wetter von letztem Monat, und niemand weiß es.
>
> **Das ist der gefährlichste Ausfall — der, der aussieht wie Normalbetrieb.**
> Deshalb schlägt ein Alarm, wenn vier Tage lang niemand die Stationen abgelesen
> hat."

**Auf der Folie:** ein Rauchmelder mit Spinnweben.

---

## 9:00 – 10:00 · Live zeigen und Schluss

**Browser öffnen, Datum stehen lassen, auf „Forecast" drücken.**

> „Das hier ist die App. Ein Knopf.
>
> Was in dieser halben Sekunde passiert: Der Empfang nimmt die Frage an, weckt
> den Meteorologen, der holt sich die aktuellen Messwerte, rechnet sein
> Rechenblatt durch, schaut auf seine gelernten Muster — und antwortet.
>
> **Plus/minus 33 Dollar.** Morgen wird ein ruhiger Tag."

### Der Schlusssatz
> „Das Besondere an diesem System ist nicht, dass es den Goldpreis vorhersagt.
> Das kann es nämlich nicht, und das sagt es auch.
>
> Das Besondere ist, dass es **jeden Tag von allein arbeitet, sich meldet wenn
> etwas nicht stimmt, und selbst sagen kann, wie gut es ist.**
>
> Für 47 Cent im Monat."

---

## Wenn Fragen kommen

**„Können wir damit Geld verdienen?"**
> „So nicht. Es sagt nicht, ob der Preis steigt. Es sagt, wie unruhig es wird —
> das ist nützlich, wenn man Risiko einschätzen muss, nicht wenn man wetten will."

**„Warum nur 2,9 Prozent besser? Das klingt wenig."**
> „Ist es auch. Es ist aber ein **ehrliches** Ergebnis, auf Daten, die das System
> nie gesehen hat. Mir wäre eine Zahl, die beeindruckend klingt und nicht hält,
> deutlich unangenehmer."

**„Was, wenn es ausfällt?"**
> „Dann bekomme ich eine Mail. Und das System hält nichts an, was Geld kostet —
> wenn niemand fragt, läuft auch nichts."

**„Wie lange hat das gedauert?"**
> „Zwei Wochen, allein, neben dem Kurs."

---

## Spickzettel: die vier Zahlen

| | |
|---|---|
| **47 Cent** | pro Monat, gemessen |
| **2,9 %** | besser als die Bauernregel, auf nie gesehenen Daten |
| **± 33 Dollar** | die heutige Vorhersage |
| **0,5 Sekunden** | bis die Antwort da ist |
