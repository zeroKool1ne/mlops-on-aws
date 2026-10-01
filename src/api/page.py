"""The demo page.

Deliberately one file with no build step, no framework and no assets: it has to
survive being served from a Lambda container and still work when the wifi in
the presentation room does not. Everything it needs is inline.
"""

from __future__ import annotations

STYLE = """
:root {
  --bg: #0f1115; --panel: #171a21; --line: #262b36;
  --fg: #e8eaed; --muted: #9aa2b1; --gold: #d4a339; --ok: #4fb286;
  --mono: ui-monospace, SFMono-Regular, Menlo, monospace;
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--fg);
  font: 16px/1.6 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
.wrap { max-width: 760px; margin: 0 auto; padding: 56px 16px 80px; }
h1 { font-size: 28px; letter-spacing: -0.02em; margin: 0 0 8px; }
h1 span { color: var(--gold); }
.sub { color: var(--muted); margin: 0 0 40px; }
.panel {
  background: var(--panel); border: 1px solid var(--line);
  border-radius: 12px; padding: 24px; margin-bottom: 20px;
}
.row { display: flex; gap: 12px; flex-wrap: wrap; align-items: flex-end; }
label { display: block; font-size: 13px; color: var(--muted); margin-bottom: 6px; }
input[type=date] {
  background: #0f1115; color: var(--fg); border: 1px solid var(--line);
  border-radius: 8px; padding: 10px 12px; font: inherit; min-width: 180px;
}
button {
  background: var(--gold); color: #1b1200; border: 0; border-radius: 8px;
  padding: 11px 20px; font: 600 15px/1 inherit; cursor: pointer;
}
button:disabled { opacity: 0.5; cursor: wait; }
.result { margin-top: 24px; display: none; }
.big { font-size: 34px; font-weight: 600; letter-spacing: -0.02em; }
.big small { font-size: 15px; font-weight: 400; color: var(--muted); }
.grid {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 16px; margin-top: 20px;
}
.cell { border-top: 1px solid var(--line); padding-top: 10px; }
.cell b { display: block; font-size: 12px; color: var(--muted); font-weight: 500;
          text-transform: uppercase; letter-spacing: 0.05em; }
.note { color: var(--muted); font-size: 14px; margin-top: 20px;
        border-left: 2px solid var(--line); padding-left: 14px; }
.meta { font-family: var(--mono); font-size: 13px; color: var(--muted); }
.meta span { color: var(--ok); }
.err { color: #e0707a; }
a { color: var(--gold); }
footer { color: var(--muted); font-size: 13px; margin-top: 40px; }
@media (prefers-color-scheme: light) {
  :root { --bg: #fbfbfc; --panel: #fff; --line: #e3e5ea; --fg: #14161a; --muted: #6a7280; }
  input[type=date] { background: #fff; }
}
"""

SCRIPT = """
const out = document.getElementById('result');
const btn = document.getElementById('go');

function cell(label, value) {
  return `<div class="cell"><b>${label}</b>${value}</div>`;
}

btn.onclick = async () => {
  const date = document.getElementById('date').value;
  btn.disabled = true; btn.textContent = 'Forecasting\\u2026';
  out.style.display = 'block';
  out.innerHTML = '<p class="meta">calling /predict \\u2026</p>';

  try {
    const res = await fetch('predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(date ? { date } : {}),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || res.statusText);

    const move = data.predicted_move_usd;
    const vol = data.predicted_volatility;
    out.innerHTML = `
      <div class="big">&plusmn;$${move?.toFixed(2) ?? '\\u2014'}
        <small>expected move, next trading day</small></div>
      <div class="grid">
        ${cell('Volatility', (vol * 100).toFixed(3) + ' %')}
        ${cell('Gold close', '$' + data.current_price.toFixed(2))}
        ${cell('Features as of', data.feature_date)}
        ${cell('Served by', data.served_by)}
        ${cell('Latency', data.latency_ms + ' ms')}
      </div>
      ${data.note ? `<p class="note">${data.note}</p>` : ''}`;
  } catch (e) {
    out.innerHTML = `<p class="err">${e.message}</p>`;
  } finally {
    btn.disabled = false; btn.textContent = 'Forecast';
  }
};
"""


def render(metadata: dict | None, mode: str) -> str:
    """Build the page. Model facts come from the artifact, never hard-coded."""
    if metadata:
        window = " to ".join(metadata["training_window"])
        status = (f'model <span>loaded</span> &middot; target '
                  f'<span>{metadata["target"]}</span> &middot; '
                  f'{len(metadata["feature_columns"])} features &middot; '
                  f'{metadata["n_training_rows"]:,} training rows &middot; {window} &middot; '
                  f'serving <span>{mode}</span>')
    else:
        status = '<span class="err">no model artifact loaded</span>'

    return f"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gold/USD Forecasting</title>
<style>{STYLE}</style>
</head><body><div class="wrap">

<h1>Gold/USD <span>Volatility Forecast</span></h1>
<p class="sub">How violently does gold move tomorrow? Ten years of market data,
one model, measured against a naive baseline.</p>

<div class="panel">
  <div class="row">
    <div>
      <label for="date">Forecast from (optional)</label>
      <input type="date" id="date">
    </div>
    <button id="go">Forecast</button>
  </div>
  <div class="result" id="result"></div>
</div>

<p class="meta">{status}</p>

<footer>
  <a href="docs">API documentation</a> &middot;
  <a href="model">model card (JSON)</a> &middot;
  <a href="health">health</a> &middot;
  <a href="https://github.com/zeroKool1ne/mlops-on-aws">source</a>
  <br><br>
  Educational project. Not investment advice.
</footer>

</div><script>{SCRIPT}</script></body></html>"""
