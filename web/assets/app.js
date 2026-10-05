'use strict';
const $ = (id) => document.getElementById(id);
let polling = false;
let activeId = null;
const labels = { queued: 'Preparing your archive…', running: 'Collecting pages & assets…', rewriting: 'Connecting your local files…', complete: 'Your archive is ready.', failed: 'Archive could not be completed.' };
const bytes = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB` : `${Math.ceil(n / 1024)} KB`;
function showError(message) { $('error').textContent = message; $('error').hidden = false; }
function display(state) {
  $('idle').hidden = true;
  $('job').hidden = false;
  $('state-tag').textContent = state.status.toUpperCase();
  $('job-title').textContent = labels[state.status] || state.status;
  $('copied').textContent = state.copied || 0;
  $('failed').textContent = state.failed || 0;
  $('size').textContent = bytes(state.bytes || 0);
  $('elapsed').textContent = `${Math.round(state.elapsed || 0)}s`;
  const rows = (state.logs || []).slice(-40).reverse().map((event) => {
    const row = document.createElement('div');
    row.className = `log-row ${['copied', 'skipped', 'failed'].includes(event.status) ? event.status : ''}`;
    const badge = document.createElement('span'); badge.textContent = event.status === 'copied' ? '✓' : event.status === 'failed' ? '×' : '−';
    const detail = document.createElement('div');
    const url = document.createElement('div'); url.className = 'log-url'; url.textContent = event.url; url.title = event.url;
    const note = document.createElement('small'); note.textContent = event.message;
    detail.append(url, note); row.append(badge, detail); return row;
  });
  $('logs').replaceChildren(...rows);
  const done = ['complete', 'failed'].includes(state.status);
  $('activity').parentElement.classList.toggle('done', state.status === 'complete');
  $('activity').parentElement.classList.toggle('failed', state.status === 'failed');
  if (done) {
    $('submit').disabled = false;
    sessionStorage.removeItem('wcl-job');
    $('result-note').textContent = state.status === 'complete'
      ? `${state.skipped || 0} skipped · ${state.failed || 0} failed. Extract the ZIP and open index.html. The crawl report includes any missing resources.`
      : state.error || 'The starting page was not available. Check the activity log.';
    if (state.status === 'complete') {
      $('download').href = `download.php?id=${encodeURIComponent(activeId)}`;
      $('download').hidden = false;
    }
  }
  return done;
}
async function poll() {
  if (polling || !activeId) return;
  polling = true;
  try {
    const response = await fetch(`api.php?action=status&id=${encodeURIComponent(activeId)}`, { cache: 'no-store' });
    const state = await response.json();
    if (!response.ok) throw new Error(state.error || 'Could not retrieve archive status.');
    if (!display(state)) setTimeout(poll, 1200);
  } catch (error) {
    showError(`${error.message} Reload this page to reconnect to your archive.`);
    $('submit').disabled = false;
  } finally { polling = false; }
}
$('archive-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  $('error').hidden = true; $('submit').disabled = true; $('download').hidden = true;
  $('result-note').textContent = '';
  const input = { csrf: document.querySelector('meta[name="csrf-token"]').content, url: $('url').value.trim(), depth: Number($('depth').value), max_resources: Number($('max-resources').value), delay: Number($('delay').value), user_agent: $('user-agent').value, authorized: $('authorized').checked };
  try {
    const response = await fetch('api.php?action=start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || 'Could not start archive.');
    activeId = data.id; sessionStorage.setItem('wcl-job', JSON.stringify({ id: activeId, url: input.url }));
    $('job-url').textContent = input.url; display({ status: 'queued' }); poll();
  } catch (error) { showError(error.message); $('submit').disabled = false; }
});
try {
  const saved = JSON.parse(sessionStorage.getItem('wcl-job'));
  if (saved && /^[a-f0-9]{32}$/.test(saved.id)) {
    activeId = saved.id; $('job-url').textContent = saved.url; $('submit').disabled = true; display({ status: 'queued' }); poll();
  }
} catch { sessionStorage.removeItem('wcl-job'); }
