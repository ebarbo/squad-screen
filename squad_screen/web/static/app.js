const form = document.getElementById("brief-form");
const statusEl = document.getElementById("status");
const reportEl = document.getElementById("report");
const runBtn = document.getElementById("run");

const SLOT_ROWS = [
  ["LW", "ST", "RW"],
  ["LCM", "CM", "RCM"],
  ["LB", "LCB", "RCB", "RB"],
  ["GK"],
];

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const payload = {
    team: document.getElementById("team").value.trim(),
    mode: document.getElementById("mode").value,
    days: Number(document.getElementById("days").value),
  };
  runBtn.disabled = true;
  statusEl.hidden = false;
  statusEl.textContent = "Starting…";
  reportEl.hidden = true;
  try {
    const started = await fetch("/api/screen", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!started.ok) {
      throw new Error("Could not start screen");
    }
    const job = await started.json();
    const result = await pollJob(job.id);
    renderReport(result);
  } catch (error) {
    statusEl.textContent = error.message || "Failed";
  } finally {
    runBtn.disabled = false;
  }
});

async function pollJob(id) {
  for (;;) {
    const response = await fetch(`/api/jobs/${id}`);
    const job = await response.json();
    statusEl.textContent = job.message || job.status;
    if (job.status === "done") {
      return job.result;
    }
    if (job.status === "error") {
      throw new Error(job.error || "Screen failed");
    }
    await new Promise((resolve) => setTimeout(resolve, 800));
  }
}

function esc(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function groupSocial(items) {
  const grouped = new Map();
  for (const item of items) {
    const platform = item.platform || "other";
    if (!grouped.has(platform)) grouped.set(platform, []);
    grouped.get(platform).push(item);
  }
  const preferred = ["Instagram", "X"];
  const ordered = [];
  for (const name of preferred) {
    if (grouped.has(name)) ordered.push([name, grouped.get(name)]);
  }
  for (const [name, rows] of grouped) {
    if (!preferred.includes(name)) ordered.push([name, rows]);
  }
  return ordered;
}

function renderReport(report) {
  reportEl.hidden = false;
  const demoBanner =
    report.mode === "demo"
      ? `<div class="banner">DEMO DATA — bundled fixtures, not live coverage of these players.</div>`
      : "";
  const xi = report.lineup.starting_xi || [];
  const bySlot = Object.fromEntries(xi.map((s) => [s.slot, s]));
  const pitch = SLOT_ROWS.map((row) => {
    const shirts = row
      .map((slot) => {
        const item = bySlot[slot];
        if (!item) return "";
        const num = item.player.shirt_number ?? "";
        return `<div class="shirt"><span class="slot-pos">${esc(slot)} ${esc(num)}</span><strong>${esc(item.player.name)}</strong></div>`;
      })
      .join("");
    return `<div class="pitch-row">${shirts}</div>`;
  }).join("");

  const assessments = (report.assessments || [])
    .map(
      (a) => `
      <div class="player-row">
        <div><strong>${esc(a.player_name)}</strong><div class="slot-pos">${esc(a.position || "")}</div></div>
        <div class="role ${esc(a.recommended_role)}">${esc(a.recommended_role)}</div>
        <div>${esc(a.estimated_impact)}</div>
        <div>${esc(a.injury_risk)}</div>
        <div>${esc(a.rationale)}</div>
      </div>`
    )
    .join("");

  const signals = (report.signals || [])
    .map(
      (s) => `
      <div class="card">
        <span class="sev ${esc(s.severity)}">${esc(s.severity)}</span>
        <strong> ${esc(s.player_name)}</strong> · ${esc(s.category)}
        <p class="evidence">“${esc(s.evidence)}”</p>
      </div>`
    )
    .join("") || `<p class="form-note">No signals extracted.</p>`;

  const articles = (report.articles || [])
    .map(
      (a) => `
      <article class="article">
        <a href="${esc(a.url)}" target="_blank" rel="noopener">${esc(a.title)}</a>
        <div class="slot-pos">${esc(a.source)} · ${esc(a.fetch_status)}${a.paywalled ? " · paywalled" : ""}${a.demo ? " · demo" : ""}</div>
        <p>${esc(a.snippet || "")}</p>
      </article>`
    )
    .join("") || `<p class="form-note">No articles collected.</p>`;

  const socialItems = report.social_items || [];
  const social = socialItems.length
    ? groupSocial(socialItems)
        .map(([platform, rows]) => {
          const cards = rows
            .map((s) => {
              const link = s.url
                ? `<p><a href="${esc(s.url)}" target="_blank" rel="noopener">permalink</a></p>`
                : "";
              return `
      <div class="social" data-platform="${esc(s.platform)}">
        <strong>${esc(s.player_name)}</strong> · ${esc(s.platform)} · ${esc(s.media_type)} · ${esc(s.fetch_status)}
        <p>${esc(s.content)}</p>
        ${link}
      </div>`;
            })
            .join("");
          return `<h3 class="social-platform">${esc(platform)}</h3>${cards}`;
        })
        .join("")
    : `<p class="form-note">No social items collected.</p>`;

  const gaps = (report.coverage_gaps || [])
    .map(
      (g) => `<div class="gap"><strong>${esc(g.area)}</strong><p>${esc(g.reason)}</p><p class="form-note">${esc(g.impact)}</p></div>`
    )
    .join("");

  reportEl.innerHTML = `
    ${demoBanner}
    <div class="meta-row">
      <div class="stat"><span>Roster</span><b>${report.roster.length}</b></div>
      <div class="stat"><span>Articles</span><b>${report.articles.length}</b></div>
      <div class="stat"><span>Social</span><b>${report.social_items.length}</b></div>
      <div class="stat"><span>Signals</span><b>${report.signals.length}</b></div>
    </div>
    <h2>Recommended ${esc(report.lineup.formation)}</h2>
    <p>${esc(report.lineup.summary)}</p>
    <div class="pitch">${pitch}</div>
    <h2>Bench</h2>
    ${(report.lineup.bench || [])
      .map(
        (s) =>
          `<div class="card"><strong>${esc(s.player.name)}</strong> · ${esc(s.recommended_role)}<p>${esc(s.rationale)}</p></div>`
      )
      .join("") || "<p class='form-note'>Empty bench.</p>"}
    <h2>Rest</h2>
    ${(report.lineup.rest || [])
      .map((s) => `<div class="card"><strong>${esc(s.player.name)}</strong><p>${esc(s.rationale)}</p></div>`)
      .join("") || "<p class='form-note'>Nobody flagged for rest.</p>"}
    <h2>Assessments</h2>
    ${assessments}
    <h2>Signals</h2>
    <div class="cards">${signals}</div>
    <h2>Articles</h2>
    ${articles}
    <h2>Social</h2>
    ${social}
    <h2>Coverage gaps</h2>
    <div class="gaps">${gaps}</div>
  `;
  statusEl.textContent = "Complete — scroll the briefing.";
}
