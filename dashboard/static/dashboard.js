const POLL_MS = 8000;
let priceChart;

function fmt(n, decimals = 2) {
  if (n === null || n === undefined || isNaN(n)) return '--';
  return Number(n).toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

async function refreshSignal() {
  const res = await fetch('/api/current_signal');
  if (!res.ok) return;
  const s = await res.json();

  const actionEl = document.getElementById('signalAction');
  actionEl.textContent = s.action;
  actionEl.className = 'signal-action ' + s.action.toLowerCase();
  document.getElementById('signalConfidence').textContent = 'confidence: ' + fmt(s.confidence, 0) + '%';
  document.getElementById('signalPrice').textContent = s.price ? (s.symbol + ' @ ' + fmt(s.price, 4)) : '';

  const buy = s.buy_score || 0, sell = s.sell_score || 0;
  document.getElementById('buyBar').style.width = buy + '%';
  document.getElementById('sellBar').style.width = sell + '%';
  document.getElementById('buyScoreLabel').textContent = fmt(buy, 0);
  document.getElementById('sellScoreLabel').textContent = fmt(sell, 0);

  const render = (id, notes) => {
    document.getElementById(id).innerHTML = (notes || []).map(n => `<div>${n}</div>`).join('') || '<div>No data</div>';
  };
  render('technicalNotes', s.technical_notes);
  render('mtfNotes', s.mtf_notes);
  render('orderbookNotes', s.orderbook_notes);
  render('marketStructureNotes', s.market_structure_notes);
}

async function refreshAccuracy() {
  const res = await fetch('/api/accuracy');
  if (!res.ok) return;
  const a = await res.json();
  document.getElementById('statAccuracy').textContent = a.accuracy_pct !== null ? a.accuracy_pct + '%' : '--';
  document.getElementById('statCorrect').textContent = a.correct;
  document.getElementById('statIncorrect').textContent = a.incorrect;
  document.getElementById('statPending').textContent = a.pending;
}

async function refreshSignalsTable() {
  const res = await fetch('/api/signals?limit=30');
  if (!res.ok) return;
  const rows = await res.json();
  const body = document.querySelector('#signalsTable tbody');
  body.innerHTML = rows.map(r => `
    <tr>
      <td>${(r.created_at || '').replace('T', ' ').slice(0, 16)}</td>
      <td class="${r.action.toLowerCase()}">${r.action}</td>
      <td>${fmt(r.confidence, 0)}%</td>
      <td>${fmt(r.price_at_signal, 4)}</td>
      <td class="${r.status}">${r.status}</td>
      <td>${r.pct_move !== null ? fmt(r.pct_move, 2) + '%' : '--'}</td>
    </tr>
  `).join('') || '<tr><td colspan="6" style="color:var(--muted)">No signals yet</td></tr>';
}

async function refreshLogs() {
  const res = await fetch('/api/logs');
  if (!res.ok) return;
  const logs = await res.json();
  const box = document.getElementById('logBox');
  box.innerHTML = logs.map(l => `<div class="entry ${l.level}">[${(l.timestamp.split('T')[1] || '').slice(0,8)}] ${l.message}</div>`).join('');
  box.scrollTop = box.scrollHeight;
}

async function refreshChart() {
  const res = await fetch('/api/candles');
  if (!res.ok) return;
  const rows = await res.json();
  const labels = rows.map((r, i) => i);
  const datasets = [
    { label: 'Close', data: rows.map(r => r.close), borderColor: '#E7ECF1', borderWidth: 1.5, pointRadius: 0 },
    { label: 'EMA9', data: rows.map(r => r.ema_fast), borderColor: '#E8A33D', borderWidth: 1, pointRadius: 0 },
    { label: 'EMA21', data: rows.map(r => r.ema_slow), borderColor: '#4E8CFF', borderWidth: 1, pointRadius: 0 },
  ];
  if (!priceChart) {
    priceChart = new Chart(document.getElementById('priceChart'), {
      type: 'line',
      data: { labels, datasets },
      options: {
        responsive: true, animation: false, interaction: { mode: 'index', intersect: false },
        scales: { x: { display: false }, y: { grid: { color: '#232A33' }, ticks: { color: '#7C8B9A' } } },
        plugins: { legend: { labels: { color: '#7C8B9A', boxWidth: 10, font: { size: 10 } } } },
      },
    });
  } else {
    priceChart.data.labels = labels;
    datasets.forEach((d, i) => { priceChart.data.datasets[i].data = d.data; });
    priceChart.update('none');
  }
}

function tick() {
  refreshSignal();
  refreshAccuracy();
  refreshSignalsTable();
  refreshLogs();
  refreshChart();
}

tick();
setInterval(tick, POLL_MS);
