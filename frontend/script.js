const ICONS = {
  check: '<svg class="answer-mark" viewBox="0 0 24 24" fill="none"><path d="m5 12.5 4.2 4.2L19 7" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  cross: '<svg class="answer-mark" viewBox="0 0 24 24" fill="none"><path d="m7 7 10 10M17 7 7 17" stroke="currentColor" stroke-width="2.3" stroke-linecap="round"/></svg>',
  play: '<svg class="icon" viewBox="0 0 24 24" fill="none"><path d="m9 7 8 5-8 5V7Z" fill="currentColor"/></svg>',
  exam: '<svg class="icon" viewBox="0 0 24 24" fill="none"><path d="M7 3h10v4H7V3Z" stroke="currentColor" stroke-width="1.8"/><path d="M5 5h14v16H5V5Z" stroke="currentColor" stroke-width="1.8"/></svg>'
};

const SESSION_ICONS = {
  practice: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m9 6.5 9 5.5-9 5.5v-11Z" fill="currentColor"/></svg>',
  exam: '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M7 3h10v4H7V3Z" stroke="currentColor" stroke-width="1.8"/><path d="M5 5h14v16H5V5Z" stroke="currentColor" stroke-width="1.8"/></svg>'
};

const state = {
  user: null,
  csrf: null,
  home: null,
  stats: null,
  statsScope: { mode: 'self', userId: null, users: null, search: '' },
  currentView: 'home',
  session: null,
  examReview: null,
  legalReturnPath: null,
  pendingExam: { kind: 'exam', mode: 'multi', topicIds: [], questionCount: 30, countMode: 'preset', customQuestionCount: null },
  admin: {
    tab: 'topics',
    data: { topics: null, questions: null, users: null },
    editing: null,
    deleting: null,
    filters: {
      topics: { search: '', content: 'all', sort: 'number', direction: 'asc' },
      questions: { search: '', topic: 'all', sort: 'topic', direction: 'asc' },
      users: { search: '', role: 'all', status: 'all', sort: 'name', direction: 'asc' }
    }
  }
};

let toastTimer = null;
let resizeTimer = null;
let usernameSuggestionSeq = 0;
let attachmentUploadSeq = 0;
const byId = id => document.getElementById(id);
const backgroundWrites = new Set();
const practicePreload = {
  mode: null,
  ready: false,
  questionsByTopic: new Map(),
  promise: null,
  generation: 0
};

function trackBackgroundWrite(promise) {
  backgroundWrites.add(promise);
  promise.finally(() => backgroundWrites.delete(promise));
  return promise;
}

async function flushBackgroundWrites() {
  if (!backgroundWrites.size) return;
  await Promise.allSettled([...backgroundWrites]);
}


function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  }[char]));
}

function safeColor(value) {
  return /^#[0-9a-f]{6}$/i.test(String(value || '')) ? value : '#0f766e';
}

function colorSoft(hex, alpha = .12) {
  const color = safeColor(hex).slice(1);
  const r = parseInt(color.slice(0, 2), 16);
  const g = parseInt(color.slice(2, 4), 16);
  const b = parseInt(color.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function completionColor(percent) {
  const value = Math.max(0, Math.min(100, Number(percent) || 0));
  const hue = Math.round(value * 1.2);
  return `hsl(${hue} 70% 44%)`;
}

function formatNumber(value) {
  return new Intl.NumberFormat('es-ES').format(Number(value) || 0);
}

function formatDecimal(value) {
  return Number(value || 0).toFixed(1).replace('.', ',');
}

function formatAdminDate(value) {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return new Intl.DateTimeFormat('es-ES', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Madrid' }).format(date);
}

function formatFileSize(bytes) {
  const value = Math.max(0, Number(bytes) || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 ** 2) return `${(value / 1024).toFixed(value < 10 * 1024 ? 1 : 0).replace('.', ',')} KB`;
  return `${(value / 1024 ** 2).toFixed(value < 10 * 1024 ** 2 ? 1 : 0).replace('.', ',')} MB`;
}

function fileKind(name = '', mime = '') {
  const lower = String(name).toLowerCase();
  const type = String(mime || '').toLowerCase();
  if (type === 'application/pdf' || lower.endsWith('.pdf')) return 'pdf';
  if (type.startsWith('image/') || /\.(png|jpe?g|gif|webp|svg|bmp|heic)$/i.test(lower)) return 'image';
  if (/\.(docx?|odt|rtf)$/i.test(lower) || /word|officedocument\.word/.test(type)) return 'doc';
  if (/\.(xlsx?|ods|csv)$/i.test(lower) || /excel|spreadsheet|csv/.test(type)) return 'sheet';
  if (/\.(pptx?|odp)$/i.test(lower) || /powerpoint|presentation/.test(type)) return 'presentation';
  if (type.startsWith('audio/') || /\.(mp3|wav|ogg|m4a|aac|flac)$/i.test(lower)) return 'audio';
  if (type.startsWith('video/') || /\.(mp4|webm|mov|avi|mkv)$/i.test(lower)) return 'video';
  if (/\.(zip|rar|7z|tar|gz)$/i.test(lower) || /zip|compressed|archive/.test(type)) return 'archive';
  if (/\.(py|js|ts|json|html?|css|xml|ya?ml|sql|sh)$/i.test(lower)) return 'code';
  if (type.startsWith('text/') || /\.(txt|md|log)$/i.test(lower)) return 'text';
  return 'file';
}

function libraryIcon(name, style = 'solid', className = '') {
  const iconClass = `fa-svg-${style}-${name}`;
  return `<span class="fa-svg-icon ${escapeHtml(iconClass)} ${escapeHtml(className)}" aria-hidden="true"></span>`;
}

function fileTypeIcon(name, mime) {
  const kind = fileKind(name, mime);
  const icon = {
    pdf: 'file-pdf',
    image: 'file-image',
    doc: 'file-word',
    sheet: 'file-excel',
    presentation: 'file-powerpoint',
    audio: 'file-audio',
    video: 'file-video',
    archive: 'file-zipper',
    code: 'file-code',
    text: 'file-lines',
    file: 'file'
  }[kind] || 'file';
  return `<span class="file-type-icon file-type-${kind}" aria-hidden="true">${libraryIcon(icon)}</span>`;
}

const DOWNLOAD_ICON = '<svg class="icon attachment-download-svg" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 3v11m0 0 4-4m-4 4-4-4M5 17v3h14v-3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
const UPLOAD_ICON = libraryIcon('cloud-arrow-up');
const DELETE_ICON = libraryIcon('trash-can');
const CANCEL_ICON = libraryIcon('xmark');
const FOLDER_ICON = libraryIcon('folder', 'regular');
const CHEVRON_ICON = libraryIcon('chevron-down');
const MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024;
const MAX_ATTACHMENTS_PER_TOPIC = 12;
const MAX_TOPIC_ATTACHMENTS_BYTES = 200 * 1024 * 1024;

function timestampValue(value) {
  const parsed = Date.parse(value || '');
  return Number.isNaN(parsed) ? 0 : parsed;
}

const TOPIC_COLOR_PALETTE = [
  '#0F766E', '#2563EB', '#7C3AED', '#BE123C', '#C2410C', '#0369A1',
  '#4D7C0F', '#A16207', '#0E7490', '#9333EA', '#B45309', '#475569'
];

function randomTopicColor() {
  const used = new Set((state.admin?.data?.topics || []).map(topic => safeColor(topic.color).toUpperCase()));
  const available = TOPIC_COLOR_PALETTE.filter(color => !used.has(color.toUpperCase()));
  const pool = available.length ? available : TOPIC_COLOR_PALETTE;
  return pool[Math.floor(Math.random() * pool.length)];
}

function topicLabel(topic) {
  return `${topic.number} - ${topic.name}`;
}


function legalKindFromPath(path = location.pathname) {
  if (path === '/aviso-legal') return 'notice';
  if (path === '/politica-privacidad') return 'privacy';
  return null;
}

function legalPath(kind) {
  return kind === 'privacy' ? '/politica-privacidad' : '/aviso-legal';
}

function viewFromPath(path = location.pathname) {
  if (path === '/statistics') return 'stats';
  if (path === '/admin') return 'admin';
  if (path === '/questions' && state.examReview) return 'review';
  if (path === '/questions' && state.session) return 'question';
  return 'home';
}

function updateAppVersion() {
  const node = byId('appVersion');
  if (!node) return;
  const version = typeof window.BOMBAVTEST_VERSION === 'string' && window.BOMBAVTEST_VERSION.trim()
    ? window.BOMBAVTEST_VERSION.trim()
    : 'dev';
  node.textContent = version;
  const revision = typeof window.BOMBAVTEST_REVISION === 'string' ? window.BOMBAVTEST_REVISION.trim() : '';
  node.title = revision && revision !== 'unknown'
    ? `BombAvTest ${version} · ${revision.slice(0, 12)}`
    : `BombAvTest ${version}`;
}

function updateFooterVisibility() {
  const footer = byId('siteFooter');
  if (!footer) return;
  const legalOpen = !byId('legalShell')?.hidden;
  footer.hidden = !legalOpen && state.user && state.currentView === 'question';
}

function showLegalPage(kind, push = true) {
  if (!['notice', 'privacy'].includes(kind)) return;
  if (byId('legalShell')?.hidden) {
    state.legalReturnPath = state.user ? navPath(state.currentView) : '/login';
  }
  byId('loginView').hidden = true;
  byId('appShell').hidden = true;
  byId('legalShell').hidden = false;
  byId('legalNoticeView').hidden = kind !== 'notice';
  byId('privacyPolicyView').hidden = kind !== 'privacy';
  byId('siteFooter').hidden = false;
  window.scrollTo({ top: 0, behavior: 'auto' });
  if (push && location.pathname !== legalPath(kind)) history.pushState({ legal: kind }, '', legalPath(kind));
}

async function leaveLegalPage() {
  const target = state.legalReturnPath || (state.user ? '/' : '/login');
  state.legalReturnPath = null;
  byId('legalShell').hidden = true;
  if (!state.user) {
    showLogin();
    return;
  }
  showApp();
  await setView(viewFromPath(target), false);
  if (location.pathname !== target) history.replaceState({}, '', target);
}

function topicOptionHtml(topic, selected = false) {
  const color = safeColor(topic.color);
  return `<option value="${topic.id}" data-color="${color}" ${selected ? 'selected' : ''}>${escapeHtml(topic.number)} - ${escapeHtml(topic.name)}</option>`;
}

function syncTopicSelectStyle(select) {
  if (!select) return;
  select.style.color = '';
  const option = select.options?.[select.selectedIndex];
  const dot = select.closest('.topic-select-control')?.querySelector('.topic-select-dot');
  if (dot) dot.style.background = safeColor(option?.dataset?.color || '#0f766e');
}

function localDateKey(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Europe/Madrid',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(value);
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]));
  return `${values.year}-${values.month}-${values.day}`;
}

async function api(path, options = {}) {
  const method = options.method || 'GET';
  const headers = { Accept: 'application/json', ...(options.headers || {}) };
  const requestOptions = { method, headers, credentials: 'same-origin' };

  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    requestOptions.body = JSON.stringify(options.body);
  }
  if (method !== 'GET' && method !== 'HEAD' && state.csrf && path !== '/api/login') {
    headers['X-CSRF-Token'] = state.csrf;
  }

  let response;
  try {
    response = await fetch(path, requestOptions);
  } catch {
    throw new Error('No se ha podido conectar con el servidor.');
  }

  let payload = null;
  try { payload = await response.json(); } catch { /* response without JSON */ }

  if (!response.ok || !payload?.ok) {
    if (response.status === 401 && path !== '/api/login') {
      showLogin();
    }
    const error = new Error(payload?.error || 'Ha ocurrido un error.');
    error.code = payload?.code;
    error.status = response.status;
    throw error;
  }
  return payload.data;
}

async function apiForm(path, formData, method = 'POST') {
  const headers = { Accept: 'application/json' };
  if (state.csrf) headers['X-CSRF-Token'] = state.csrf;
  let response;
  try {
    response = await fetch(path, { method, headers, body: formData, credentials: 'same-origin' });
  } catch {
    throw new Error('No se ha podido conectar con el servidor.');
  }
  let payload = null;
  try { payload = await response.json(); } catch { /* response without JSON */ }
  if (!response.ok || !payload?.ok) {
    if (response.status === 401) showLogin();
    const error = new Error(payload?.error || 'Ha ocurrido un error.');
    error.code = payload?.code;
    error.status = response.status;
    throw error;
  }
  return payload.data;
}

function newSubmissionKey() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID();
  const random = Math.random().toString(36).slice(2);
  return `${Date.now().toString(36)}-${random}-${Math.random().toString(36).slice(2)}`;
}

function preparePracticeFeedback(question) {
  const correctOptionId = Number(question?.correct_option_id);
  if (!Number.isFinite(correctOptionId)) return null;
  return {
    correctOptionId,
    explanation: question?.explanation || ''
  };
}

function currentPracticeMode() {
  return byId('repeatCorrect')?.checked ? 'all' : 'pending';
}

function resetPracticePreload() {
  practicePreload.generation += 1;
  practicePreload.mode = null;
  practicePreload.ready = false;
  practicePreload.questionsByTopic = new Map();
  practicePreload.promise = null;
}

function practiceEntryFromQuestion(question) {
  if (!question) return null;
  return {
    question: { ...question, submissionKey: newSubmissionKey() },
    feedback: preparePracticeFeedback(question)
  };
}

async function primePracticePreload() {
  if (!state.user) return;
  const mode = currentPracticeMode();
  if (practicePreload.mode === mode && (practicePreload.ready || practicePreload.promise)) {
    return practicePreload.promise;
  }

  const generation = practicePreload.generation + 1;
  practicePreload.generation = generation;
  practicePreload.mode = mode;
  practicePreload.ready = false;
  practicePreload.questionsByTopic = new Map();

  const promise = api(`/api/practice/preload?mode=${encodeURIComponent(mode)}`)
    .then(data => {
      if (practicePreload.generation !== generation || practicePreload.mode !== mode) return;
      const entries = new Map();
      (data?.questions || []).forEach(question => {
        const topicId = Number(question?.topic?.id);
        if (Number.isFinite(topicId)) entries.set(topicId, question);
      });
      practicePreload.questionsByTopic = entries;
      practicePreload.ready = true;
    })
    .catch(error => {
      if (error.status !== 401) console.warn('No se pudo precargar la práctica:', error.message);
    })
    .finally(() => {
      if (practicePreload.generation === generation) practicePreload.promise = null;
    });

  practicePreload.promise = promise;
  return promise;
}

function practiceAvailableCount(topicIds) {
  const selected = new Set((topicIds || []).map(Number));
  return (state.home?.topics || [])
    .filter(topic => selected.has(Number(topic.id)))
    .reduce((sum, topic) => sum + practiceTopicAvailableCount(topic), 0);
}

function practiceTopicAvailableCount(topic) {
  const total = Math.max(0, Number(topic?.total) || 0);
  if (currentPracticeMode() === 'all') return total;
  const correct = Math.max(0, Number(topic?.correct) || 0);
  return Math.max(0, total - correct);
}

async function preloadedPracticeEntry(topicIds) {
  const mode = currentPracticeMode();
  if (practicePreload.mode !== mode || (!practicePreload.ready && !practicePreload.promise)) {
    resetPracticePreload();
    await primePracticePreload();
  } else if (practicePreload.promise) {
    await practicePreload.promise;
  }

  if (!practicePreload.ready || practicePreload.mode !== mode) return null;
  const candidates = (topicIds || [])
    .map(Number)
    .filter(Number.isFinite)
    .map(topicId => {
      const question = practicePreload.questionsByTopic.get(topicId);
      const topic = state.home?.topics?.find(item => Number(item.id) === topicId);
      return { question, weight: practiceTopicAvailableCount(topic) };
    })
    .filter(item => item.question && item.weight > 0);
  if (!candidates.length) return null;
  const totalWeight = candidates.reduce((sum, item) => sum + item.weight, 0);
  let target = Math.random() * totalWeight;
  for (const item of candidates) {
    target -= item.weight;
    if (target < 0) return practiceEntryFromQuestion(item.question);
  }
  return practiceEntryFromQuestion(candidates[candidates.length - 1].question);
}


function safeStorageGet(key) {
  try { return localStorage.getItem(key); } catch { return null; }
}

function safeStorageSet(key, value) {
  try { localStorage.setItem(key, value); } catch { /* optional preference */ }
}

function applyTheme(theme) {
  const dark = theme === 'dark';
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  byId('themeToggle').setAttribute('aria-label', dark ? 'Activar modo claro' : 'Activar modo oscuro');
  document.querySelector('meta[name="theme-color"]').setAttribute('content', dark ? '#0d1517' : '#0f766e');
}

function updateQuestionModeLabel(showAll) {
  byId('questionModeLabel').textContent = showAll ? 'Todas las preguntas' : 'Solo pendientes y falladas';
  byId('questionModeControl').title = showAll
    ? 'También pueden aparecer preguntas que ya has acertado'
    : 'Se omiten las preguntas que ya has acertado';
}

function showToast(message) {
  const toast = byId('toast');
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3000);
}

function skeletonLine(width = '100%', height = '12px') {
  return `<span class="skeleton-block" style="width:${width};height:${height}"></span>`;
}

function skeletonKpi() {
  return `<article class="panel kpi skeleton-card" aria-hidden="true">
    ${skeletonLine('54%', '10px')}
    ${skeletonLine('42%', '30px')}
    ${skeletonLine('68%', '9px')}
  </article>`;
}

function skeletonHeatmapHtml() {
  const labels = ['L', 'M', 'X', 'J', 'V', 'S', 'D']
    .map(label => `<div class="calendar-day-label loading-day-label">${label}</div>`)
    .join('');
  const days = Array.from({ length: 28 }, () => '<span class="heat-day heat-day-loading" aria-hidden="true"></span>').join('');
  return labels + days;
}

function renderHomeSkeleton() {
  const title = byId('homeTitle');
  const total = byId('totalAnsweredValue');
  const heatmap = byId('homeHeatmap');
  const range = byId('homeHeatmapRange');
  const grid = byId('topicsGrid');
  if (title) title.innerHTML = '<span class="skeleton-block skeleton-home-title"></span>';
  if (total) total.innerHTML = '<span class="skeleton-block skeleton-number"></span>';
  if (heatmap) {
    heatmap.classList.add('is-loading-heatmap');
    heatmap.innerHTML = skeletonHeatmapHtml();
  }
  if (range) range.innerHTML = `${skeletonLine('54px', '8px')}${skeletonLine('54px', '8px')}`;
  if (grid) {
    grid.innerHTML = Array.from({ length: 6 }, () => `<article class="topic-card skeleton-card" aria-hidden="true">
      <div class="skeleton-topic-head"><span class="skeleton-block skeleton-square"></span>${skeletonLine('62%', '15px')}</div>
      ${skeletonLine('100%', '52px')}
      <div class="skeleton-topic-actions">${skeletonLine('47%', '38px')}${skeletonLine('47%', '38px')}</div>
    </article>`).join('');
  }
}

function renderQuestionSkeleton() {
  const topicMeta = byId('questionTopicMeta');
  if (topicMeta) topicMeta.hidden = true;
  byId('questionTitle').innerHTML = `<span class="skeleton-question-lines">${skeletonLine('94%', '18px')}${skeletonLine('70%', '18px')}</span>`;
  byId('answersContainer').innerHTML = Array.from({ length: 4 }, () => `<div class="skeleton-answer" aria-hidden="true"><span class="skeleton-block skeleton-answer-letter"></span>${skeletonLine('72%', '13px')}</div>`).join('');
  byId('questionFeedback').className = 'feedback';
  byId('questionFeedback').innerHTML = '';
}

function skeletonTopicMetricChart() {
  return `<div class="skeleton-topic-metric" aria-hidden="true">
    <div class="topic-metric-rows">
      ${Array.from({ length: 6 }, (_, row) => {
        const nameWidth = 58 + (row % 3) * 11;
        const barWidth = 42 + (row % 4) * 12;
        return `<div class="topic-metric-row skeleton-topic-metric-row">
          <div class="topic-metric-label">
            <span class="topic-icon skeleton-block skeleton-topic-icon"></span>
            <span class="skeleton-topic-name">${skeletonLine(`${nameWidth}%`, '10px')}</span>
          </div>
          <div class="topic-metric-plot">
            <span class="topic-metric-bar skeleton-block skeleton-topic-bar" style="width:${barWidth}%"></span>
          </div>
          <div class="topic-metric-value">${skeletonLine('36px', '10px')}</div>
        </div>`;
      }).join('')}
    </div>
    <div class="topic-metric-axis skeleton-topic-metric-axis">
      <span></span>
      <div>${skeletonLine('20px', '7px')}${skeletonLine('32px', '7px')}</div>
      <span></span>
    </div>
  </div>`;
}

function renderStatsSkeleton() {
  const target = byId('statsSummary');
  const isAll = state.user?.role === 'admin' && state.statsScope.mode === 'all';
  const progressPanel = byId('progressChartPanel');
  if (progressPanel) progressPanel.hidden = isAll;
  const winratePanel = byId('winrateChartPanel');
  if (winratePanel) winratePanel.hidden = false;
  if (target) {
    if (isAll) {
      target.innerHTML = `<div class="stats-cohort-overview skeleton-stats-overview">
        <div class="stats-cohort-kpis">${Array.from({ length: 6 }, skeletonKpi).join('')}</div>
        <article class="panel kpi cohort-heatmap-kpi skeleton-card skeleton-activity-card" aria-hidden="true">
          <div class="kpi-label skeleton-activity-label">Actividad</div>
          <div class="heatmap-wrap stats-cohort-heatmap-wrap skeleton-cohort-heatmap-wrap">
            <div class="calendar-heatmap is-loading-heatmap">${skeletonHeatmapHtml()}</div>
            <div class="calendar-range skeleton-calendar-range"><span class="range-ghost"></span><span class="range-ghost"></span></div>
          </div>
          <div class="kpi-trend neutral skeleton-activity-footer">Actividad conjunta de todos los alumnos</div>
        </article>
      </div>`;
    } else {
      target.innerHTML = `<div class="stats-kpis">${Array.from({ length: 4 }, skeletonKpi).join('')}</div>`;
    }
  }
  ['topicBarChart', 'topicAccuracyBarChart', 'progressChart', 'winrateChart'].forEach((id, index) => {
    const node = byId(id);
    if (!node) return;
    node.innerHTML = index < 2
      ? skeletonTopicMetricChart()
      : `<div class="skeleton-chart" aria-hidden="true">${skeletonLine('100%', '100%')}</div>`;
  });
}

function renderStatsUserSkeleton() {
  const target = byId('statsUserResults');
  if (!target) return;
  target.innerHTML = Array.from({ length: 5 }, () => `<div class="stats-student-row skeleton-student-row" aria-hidden="true">
    <span class="skeleton-block skeleton-avatar"></span>
    <span class="skeleton-student-copy">${skeletonLine('150px', '12px')}${skeletonLine('105px', '9px')}</span>
    ${skeletonLine('54px', '22px')}
  </div>`).join('');
}

function renderAdminSkeleton() {
  const target = byId('adminList');
  if (!target) return;
  const tab = state.admin.tab;
  const counter = byId('adminResultCount');
  if (counter) counter.innerHTML = skeletonLine('74px', '10px');
  const exportButton = byId('adminExportBtn');
  if (exportButton) exportButton.disabled = true;

  const head = width => skeletonLine(width, '14px');
  const line = (width, height = '10px') => skeletonLine(width, height);
  const actions = count => `<div class="admin-row-actions skeleton-admin-actions">${
    Array.from({ length: count }, (_, index) => `<span class="skeleton-block skeleton-admin-action skeleton-admin-action-${index + 1}"></span>`).join('')
  }</div>`;

  if (tab === 'topics') {
    target.innerHTML = `<div class="admin-table-wrap" aria-hidden="true"><table class="admin-table admin-table-topics skeleton-admin-table">
      <thead><tr>
        <th class="admin-number-col">${head('26px')}</th>
        <th>${head('76px')}</th>
        <th>${head('62px')}</th>
        <th>${head('58px')}</th>
        <th class="admin-actions-col">${head('62px')}</th>
      </tr></thead>
      <tbody>${Array.from({ length: 7 }, (_, row) => `<tr>
        <td><span class="admin-topic-number skeleton-block skeleton-admin-topic-number"></span></td>
        <td><span class="admin-cell-title skeleton-admin-cell-title">${line(`${58 + (row % 3) * 12}%`, '11px')}</span></td>
        <td><span class="admin-count-badge skeleton-block skeleton-admin-count"></span></td>
        <td>${line(`${62 + (row % 2) * 14}%`, '10px')}</td>
        <td>${actions(2)}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;
    return;
  }

  if (tab === 'questions') {
    target.innerHTML = `<div class="admin-table-wrap" aria-hidden="true"><table class="admin-table admin-table-questions skeleton-admin-table">
      <thead><tr>
        <th>${head('72px')}</th>
        <th>${head('54px')}</th>
        <th>${head('68px')}</th>
        <th>${head('60px')}</th>
        <th>${head('58px')}</th>
        <th class="admin-actions-col">${head('62px')}</th>
      </tr></thead>
      <tbody>${Array.from({ length: 7 }, (_, row) => `<tr>
        <td><span class="skeleton-admin-question">${line(`${78 + (row % 2) * 12}%`, '10px')}${line(`${52 + (row % 3) * 10}%`, '10px')}</span></td>
        <td><span class="admin-topic-label skeleton-admin-topic-label"><span class="admin-topic-dot skeleton-block"></span>${line(`${56 + (row % 3) * 10}%`, '10px')}</span></td>
        <td><span class="admin-count-badge skeleton-block skeleton-admin-count"></span></td>
        <td>${line('44px', '10px')}</td>
        <td>${line(`${62 + (row % 2) * 14}%`, '10px')}</td>
        <td>${actions(2)}</td>
      </tr>`).join('')}</tbody>
    </table></div>`;
    return;
  }

  target.innerHTML = `<div class="admin-table-wrap" aria-hidden="true"><table class="admin-table admin-table-users skeleton-admin-table">
    <thead><tr>
      <th>${head('66px')}</th>
      <th>${head('32px')}</th>
      <th>${head('60px')}</th>
      <th>${head('60px')}</th>
      <th>${head('34px')}</th>
      <th>${head('34px')}</th>
      <th class="admin-actions-col">${head('62px')}</th>
    </tr></thead>
    <tbody>${Array.from({ length: 7 }, (_, row) => `<tr>
      <td><div class="admin-cell-main">
        <div class="admin-user-identity">
          <span class="admin-user-avatar skeleton-block skeleton-admin-avatar"></span>
          <span class="skeleton-admin-user-copy">${line(`${92 + (row % 2) * 18}px`, '11px')}${line(`${70 + (row % 3) * 12}px`, '9px')}</span>
        </div>
        <span class="user-state-badge skeleton-block skeleton-admin-state"></span>
      </div></td>
      <td><span class="role-badge skeleton-block skeleton-admin-role"></span></td>
      <td>${line(`${72 + (row % 3) * 8}px`, '10px')}</td>
      <td>${line('44px', '10px')}</td>
      <td>${line(`${58 + (row % 2) * 12}px`, '10px')}</td>
      <td>${line(`${58 + ((row + 1) % 2) * 12}px`, '10px')}</td>
      <td>${actions(3)}</td>
    </tr>`).join('')}</tbody>
  </table></div>`;
}

function updateLoginState() {
  const button = byId('loginSubmit');
  if (!button) return;
  const username = byId('loginUsername')?.value.trim() || '';
  const password = byId('loginPassword')?.value || '';
  button.disabled = !(username && password);
}

function toggleLoginPasswordVisibility() {
  const input = byId('loginPassword');
  const button = byId('loginPasswordToggle');
  if (!input || !button) return;
  const reveal = input.type === 'password';
  input.type = reveal ? 'text' : 'password';
  button.setAttribute('aria-pressed', String(reveal));
  button.setAttribute('aria-label', reveal ? 'Ocultar contraseña' : 'Mostrar contraseña');
  button.classList.toggle('revealed', reveal);
  input.focus({ preventScroll: true });
}

function resetAdminWorkspace() {
  state.admin.tab = 'topics';
  state.admin.editing = null;
  state.admin.deleting = null;
  state.admin.filters = {
    topics: { search: '', content: 'all', sort: 'number', direction: 'asc' },
    questions: { search: '', topic: 'all', sort: 'topic', direction: 'asc' },
    users: { search: '', role: 'all', status: 'all', sort: 'name', direction: 'asc' }
  };
  document.querySelectorAll('[data-admin-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.adminTab === 'topics');
  });
  const create = byId('adminCreateBtn');
  if (create) create.textContent = ADMIN_META.topics.create;
}

function resetStatsWorkspace() {
  state.statsScope.mode = 'self';
  state.statsScope.userId = null;
  state.statsScope.search = '';
  const search = byId('statsUserSearch');
  if (search) search.value = '';
  document.querySelectorAll('[data-stats-scope]').forEach(button => {
    button.classList.toggle('active', button.dataset.statsScope === 'self');
  });
}


function showLogin() {
  resetPracticePreload();
  state.user = null;
  state.csrf = null;
  state.home = null;
  state.stats = null;
  state.statsScope = { mode: 'self', userId: null, users: null, search: '' };
  state.session = null;
  state.pendingExam = { kind: 'exam', mode: 'multi', topicIds: [], questionCount: 30, countMode: 'preset', customQuestionCount: null };
  state.admin = {
    tab: 'topics', data: { topics: null, questions: null, users: null }, editing: null, deleting: null,
    filters: {
      topics: { search: '', content: 'all', sort: 'number', direction: 'asc' },
      questions: { search: '', topic: 'all', sort: 'topic', direction: 'asc' },
      users: { search: '', role: 'all', status: 'all', sort: 'name', direction: 'asc' }
    }
  };
  byId('adminNavBtn').hidden = true;
  document.querySelector('.nav-center')?.classList.remove('has-admin');
  byId('appShell').hidden = true;
  byId('legalShell').hidden = true;
  byId('loginView').hidden = false;
  byId('siteFooter').hidden = false;
  byId('loginPassword').value = '';
  byId('loginPassword').type = 'password';
  byId('loginPasswordToggle')?.classList.remove('revealed');
  byId('loginPasswordToggle')?.setAttribute('aria-pressed', 'false');
  byId('loginPasswordToggle')?.setAttribute('aria-label', 'Mostrar contraseña');
  byId('loginError').textContent = '';
  updateLoginState();
  document.querySelector('.topbar')?.classList.remove('topbar-hidden');
  history.replaceState({}, '', '/login');
  setTimeout(() => {
    updateLoginState();
    byId('loginUsername').focus();
  }, 0);
  setTimeout(updateLoginState, 250);
}

function updateRoleUI() {
  const isAdmin = state.user?.role === 'admin';
  byId('adminNavBtn').hidden = !isAdmin;
  document.querySelector('.nav-center')?.classList.toggle('has-admin', isAdmin);
  const statsTabs = byId('statsScopeTabs');
  if (statsTabs) statsTabs.hidden = !isAdmin;
  if (!isAdmin) {
    state.statsScope.mode = 'self';
    state.statsScope.userId = null;
  }
}

function showApp() {
  byId('loginView').hidden = true;
  byId('legalShell').hidden = true;
  byId('appShell').hidden = false;
  updateRoleUI();
  updateFooterVisibility();
}

async function handleLogin(event) {
  event.preventDefault();
  const button = byId('loginSubmit');
  const errorNode = byId('loginError');
  errorNode.textContent = '';
  button.disabled = true;
  try {
    const data = await api('/api/login', {
      method: 'POST',
      body: {
        username: byId('loginUsername').value.trim(),
        password: byId('loginPassword').value
      }
    });
    state.user = data.user;
    state.csrf = data.csrf_token;
    state.home = null;
    state.stats = null;
    showApp();
    await setView('home', true);
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    updateLoginState();
  }
}

async function handleLogout() {
  try {
    await api('/api/logout', { method: 'POST', body: {} });
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  } finally {
    showLogin();
  }
}

function topicById(id) {
  return state.home?.topics?.find(topic => Number(topic.id) === Number(id))
    || state.stats?.topics?.find(topic => Number(topic.id) === Number(id))
    || state.admin?.data?.topics?.find(topic => Number(topic.id) === Number(id));
}

function navPath(view) {
  if (view === 'stats') return '/statistics';
  if (view === 'question' || view === 'review') return '/questions';
  if (view === 'admin') return '/admin';
  return '/';
}

async function setView(view, push = true) {
  if (!state.user) return showLogin();
  const previousView = state.currentView;
  if (view === 'question' && !state.session) view = 'home';
  if (view === 'review' && !state.examReview) view = 'home';
  if (view === 'admin' && state.user.role !== 'admin') {
    showToast('No tienes permisos de administrador.');
    if (!push && location.pathname === '/admin') history.replaceState({}, '', '/');
    view = 'home';
  }

  if (view === 'admin' && previousView !== 'admin') resetAdminWorkspace();
  if (view === 'stats' && previousView !== 'stats') resetStatsWorkspace();
  state.currentView = view;
  byId('appShell').classList.toggle('focus-session', view === 'question');
  updateFooterVisibility();
  document.querySelectorAll('.view').forEach(node => node.classList.remove('active'));
  byId(`${view}View`).classList.add('active');
  document.querySelectorAll('[data-nav]').forEach(node => {
    node.classList.toggle('active', node.dataset.nav === view);
  });
  byId('topbar').classList.remove('topbar-hidden');
  window.scrollTo({ top: 0, behavior: 'auto' });
  if (push && location.pathname !== navPath(view)) history.pushState({ view }, '', navPath(view));

  if (view === 'home') await loadHome();
  if (view === 'stats') await loadStats();
  if (view === 'admin') await loadAdmin();
  if (view === 'review') renderExamReview();
}

async function loadHome() {
  const refreshPracticePreload = !state.home;
  if (!state.home) renderHomeSkeleton();
  if (refreshPracticePreload) resetPracticePreload();
  void primePracticePreload();
  try {
    state.home = await api('/api/home');
    renderHome();
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
}

function renderHome() {
  const data = state.home;
  if (!data) return;
  byId('homeTitle').textContent = `Hola, ${data.user.display_name}.`;
  byId('totalAnsweredValue').textContent = formatNumber(data.total_answered);
  renderHeatmap(data.activity);
  renderTopics(data.topics);
}

function renderHeatmap(days, targetId = 'homeHeatmap', rangeId = 'homeHeatmapRange') {
  const target = byId(targetId);
  const range = byId(rangeId);
  if (!target || !range) return;
  target.classList.remove('is-loading-heatmap');
  const labels = ['L', 'M', 'X', 'J', 'V', 'S', 'D'];
  target.innerHTML = labels.map(label => `<div class="calendar-day-label">${label}</div>`).join('');
  const maxCount = Math.max(1, ...days.filter(day => !day.future).map(day => day.count));
  days.forEach(day => {
    const level = day.future || day.count === 0 ? 0 : Math.max(1, Math.ceil(day.count / maxCount * 4));
    const cell = document.createElement('div');
    const isToday = day.date === localDateKey();
    cell.className = `heat-day${day.future ? ' future' : ''}${isToday ? ' today' : ''}`;
    cell.dataset.level = String(level);
    cell.dataset.tooltip = day.future
      ? `${day.label} · próximo día`
      : `${day.label} · ${day.count} ${day.count === 1 ? 'respuesta' : 'respuestas'}`;
    cell.setAttribute('aria-label', cell.dataset.tooltip);
    target.appendChild(cell);
  });
  const first = days[0]?.label || '';
  const last = days[days.length - 1]?.label || '';
  range.innerHTML = `<span>${escapeHtml(first)}</span><span>${escapeHtml(last)}</span>`;
}

function renderTopics(topics) {
  const topicsGrid = byId('topicsGrid');
  topicsGrid.innerHTML = topics.map(topic => {
    const topicColor = safeColor(topic.color);
    const soft = colorSoft(topicColor);
    const ring = completionColor(topic.completion);
    const attachments = Array.isArray(topic.attachments) ? topic.attachments : [];
    const attachmentHtml = `
      <div class="attachment-disclosure topic-attachment-disclosure">
        <button class="attachment-disclosure-toggle" type="button" data-attachment-toggle aria-expanded="false">
          <span class="attachment-disclosure-label">${FOLDER_ICON}<span>Archivos adjuntos</span></span>
          <span class="attachment-disclosure-chevron">${CHEVRON_ICON}</span>
        </button>
        <div class="attachment-disclosure-panel" hidden>
          <div class="topic-attachments" aria-label="Adjuntos de ${escapeHtml(topic.name)}">
            ${attachments.length ? attachments.map(file => `
              <div class="topic-attachment-row">
                ${fileTypeIcon(file.name, file.mime_type)}
                <div class="topic-attachment-main">
                  <span class="topic-attachment-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
                  <small>${formatFileSize(file.size_bytes)}</small>
                </div>
                <a class="attachment-icon-action attachment-download-action" href="${escapeHtml(file.download_url)}" aria-label="Descargar ${escapeHtml(file.name)}" title="Descargar">${DOWNLOAD_ICON}</a>
              </div>`).join('') : '<div class="attachment-empty">No hay archivos adjuntos.</div>'}
          </div>
        </div>
      </div>`;
    return `
      <article class="topic-card" style="--topic-color:${topicColor}; --topic-soft:${soft}">
        <div class="topic-heading-row">
          <div class="topic-icon">${escapeHtml(topic.number)}</div>
          <h3>${escapeHtml(topic.name)}</h3>
          <div class="topic-ring" style="--completion-color:${ring}">
            <svg class="topic-ring-svg" viewBox="0 0 44 44" aria-hidden="true">
              <circle class="topic-ring-track" cx="22" cy="22" r="18" pathLength="100"></circle>
              <circle class="topic-ring-progress${Number(topic.completion) <= 0 ? ' is-zero' : ''}" cx="22" cy="22" r="18" pathLength="100" stroke-dasharray="${Math.max(0, Math.min(100, Number(topic.completion) || 0))} ${Math.max(0, 100 - Math.max(0, Math.min(100, Number(topic.completion) || 0)))}"></circle>
            </svg>
            <span>${Math.round(topic.completion)}%</span>
          </div>
        </div>
        ${attachmentHtml}
        <div class="topic-stats">
          <div class="topic-stat"><b>${topic.answered} / ${topic.total}</b><span>respondidas</span></div>
          <div class="topic-stat"><b>${topic.correct} / ${topic.total}</b><span>acertadas</span></div>
        </div>
        <div class="topic-footer">
          <button class="btn btn-primary btn-small" type="button" data-topic-play="${topic.id}">${ICONS.play}Practicar</button>
          <button class="btn btn-secondary btn-small" type="button" data-topic-exam="${topic.id}">${ICONS.exam}Simulacro</button>
        </div>
      </article>`;
  }).join('');
}


async function startPractice(topicIds = []) {
  state.examReview = null;
  const normalized = Array.isArray(topicIds)
    ? [...new Set(topicIds.map(Number).filter(Number.isFinite))]
    : topicIds ? [Number(topicIds)] : [];

  if (!normalized.length || practiceAvailableCount(normalized) === 0) {
    showToast('No quedan preguntas disponibles con este filtro.');
    return;
  }

  let firstEntry = await preloadedPracticeEntry(normalized);
  if (!firstEntry) {
    const preloadSession = { mode: 'practice', topicIds: normalized };
    try {
      [firstEntry] = await fetchPracticeQuestions(preloadSession, 1, []);
    } catch (error) {
      if (error.status !== 401) showToast(error.message);
      return;
    }
  }
  if (!firstEntry) {
    showToast('No quedan preguntas disponibles con este filtro.');
    return;
  }

  state.session = {
    mode: 'practice',
    topicIds: normalized,
    currentQuestion: firstEntry.question,
    previousQuestionId: null,
    selectedOptionId: null,
    localFeedback: firstEntry.feedback,
    locked: false,
    submitting: false,
    prefetchQueue: [],
    prefetchPromise: null
  };
  await setView('question', true);
  renderQuestion();
  replenishPracticeBuffer();
}

function practiceRequestParams(session, count = 1, excludeIds = []) {
  const params = new URLSearchParams();
  params.set('mode', byId('repeatCorrect').checked ? 'all' : 'pending');
  if (session.topicIds?.length) params.set('topic_ids', session.topicIds.join(','));
  params.set('count', String(Math.max(1, Math.min(3, Number(count) || 1))));
  const excludes = [...new Set(excludeIds.map(Number).filter(Number.isFinite))];
  if (excludes.length) params.set('exclude_ids', excludes.join(','));
  return params;
}

async function fetchPracticeQuestions(session, count = 1, excludeIds = []) {
  const data = await api(`/api/practice/question?${practiceRequestParams(session, count, excludeIds)}`);
  const questions = Array.isArray(data?.questions) ? data.questions : data ? [data] : [];
  return questions.map(practiceEntryFromQuestion).filter(Boolean);
}

function setCurrentPracticeEntry(entry) {
  const session = state.session;
  if (!session || session.mode !== 'practice' || !entry) return;
  session.currentQuestion = entry.question;
  session.localFeedback = entry.feedback;
  session.selectedOptionId = null;
  session.locked = false;
  session.submitting = false;
}

async function replenishPracticeBuffer() {
  const session = state.session;
  if (!session || session.mode !== 'practice' || session.prefetchPromise || session.prefetchQueue.length >= 2) return;
  const needed = 2 - session.prefetchQueue.length;
  const excludeIds = [
    session.currentQuestion?.id,
    session.previousQuestionId,
    ...session.prefetchQueue.map(entry => entry.question?.id)
  ].filter(Boolean);
  const promise = fetchPracticeQuestions(session, needed, excludeIds)
    .then(entries => {
      if (state.session !== session || session.mode !== 'practice') return;
      const known = new Set([session.currentQuestion?.id, ...session.prefetchQueue.map(entry => entry.question?.id)].filter(Boolean).map(Number));
      entries.forEach(entry => {
        if (!known.has(Number(entry.question.id)) && session.prefetchQueue.length < 2) {
          known.add(Number(entry.question.id));
          session.prefetchQueue.push(entry);
        }
      });
    })
    .catch(error => {
      if (error.status !== 401 && error.status !== 404) console.warn('No se pudo reponer el buffer de práctica:', error.message);
    })
    .finally(() => {
      if (state.session === session) session.prefetchPromise = null;
    });
  session.prefetchPromise = promise;
  trackBackgroundWrite(promise);
}

async function advancePracticeInstantly() {
  const session = state.session;
  if (!session || session.mode !== 'practice') return;
  const previousId = session.currentQuestion?.id || null;
  let entry = session.prefetchQueue.shift() || null;

  // The normal path is fully local. This fallback is only for tiny banks or a
  // failed background prefetch, never the default navigation path.
  if (!entry) {
    if (session.prefetchPromise) await session.prefetchPromise;
    entry = session.prefetchQueue.shift() || null;
  }
  if (!entry) {
    try {
      [entry] = await fetchPracticeQuestions(session, 1, previousId ? [previousId] : []);
    } catch (error) {
      if (error.status !== 401) showToast(error.message);
      return;
    }
  }
  if (!entry) return;

  session.previousQuestionId = previousId;
  setCurrentPracticeEntry(entry);
  renderQuestion();
  replenishPracticeBuffer();
}


function renderExamNavigator() {
  const session = state.session;
  const card = byId('examNavCard');
  if (!session || session.mode !== 'exam' || !card) return;
  const answers = session.answers || [];
  byId('examNavGrid').innerHTML = session.questions.map((_, index) => {
    const isAnswered = answers[index] !== null && answers[index] !== undefined;
    return `<button type="button" class="exam-nav-item${isAnswered ? ' answered' : ''}${index === session.index ? ' current' : ''}" data-exam-nav-index="${index}" aria-label="Pregunta ${index + 1}${isAnswered ? ', respondida' : ', sin responder'}${index === session.index ? ', actual' : ''}">${index + 1}</button>`;
  }).join('');
}

function syncExamNavigatorStart() {
  const layout = byId('questionPageLayout');
  const nav = byId('examNavCard');
  const questionCard = byId('questionView')?.querySelector('.question-card');
  if (!layout || !nav || !questionCard || state.session?.mode !== 'exam' || window.innerWidth <= 720) {
    nav?.style.removeProperty('--exam-nav-start-offset');
    return;
  }
  requestAnimationFrame(() => {
    const layoutTop = layout.getBoundingClientRect().top;
    const questionTop = questionCard.getBoundingClientRect().top;
    nav.style.setProperty('--exam-nav-start-offset', `${Math.max(0, Math.round(questionTop - layoutTop))}px`);
  });
}

function renderQuestion() {
  const session = state.session;
  if (!session) return;
  const isExam = session.mode === 'exam';
  const question = isExam ? session.questions[session.index] : session.currentQuestion;
  if (!question) return;

  byId('questionPageLayout').classList.toggle('exam-active', isExam);
  byId('examNavCard').hidden = !isExam;

  const chip = byId('questionTopicChip');
  const topicMeta = byId('questionTopicMeta');
  chip.textContent = `${question.topic.number} - ${question.topic.name}`;
  chip.classList.add('topic-colored');
  chip.style.setProperty('--topic-color', safeColor(question.topic.color));
  chip.style.setProperty('--topic-soft', colorSoft(question.topic.color));
  chip.hidden = isExam;
  if (topicMeta) topicMeta.hidden = isExam;

  byId('questionModeChip').textContent = isExam ? 'Simulacro' : 'Práctica';
  byId('questionModeChip').classList.toggle('exam', isExam);
  byId('questionProgress').hidden = !isExam;

  if (isExam) {
    const total = session.questions.length;
    session.selectedOptionId = session.answers?.[session.index] ?? null;
    const answered = (session.answers || []).filter(value => value !== null && value !== undefined).length;
    byId('questionCounter').textContent = `Pregunta ${session.index + 1} de ${total}`;
    byId('questionSessionScore').textContent = `${answered} respondidas`;
    byId('questionProgressBar').style.width = `${((session.index + 1) / total) * 100}%`;
  }

  byId('questionTitle').textContent = question.text;
  byId('questionFeedback').className = 'feedback';
  byId('questionFeedback').innerHTML = '';
  byId('nextQuestionBtn').disabled = !isExam;
  byId('nextQuestionBtn').classList.toggle('exam-next-button', isExam);
  byId('nextQuestionBtn').innerHTML = isExam && session.index === session.questions.length - 1
    ? 'Finalizar <svg class="icon" viewBox="0 0 24 24" fill="none"><path d="m5 12 4 4L19 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>'
    : 'Siguiente <svg class="icon" viewBox="0 0 24 24" fill="none"><path d="m9 6 6 6-6 6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';

  const container = byId('answersContainer');
  container.innerHTML = '';
  question.options.forEach((option, index) => {
    const button = document.createElement('button');
    button.className = 'answer';
    if (isExam && Number(session.selectedOptionId) === Number(option.id)) button.classList.add('selected');
    button.type = 'button';
    button.dataset.optionId = String(option.id);
    button.innerHTML = `<span class="answer-letter">${String.fromCharCode(65 + index)}</span><span class="answer-text"></span>${ICONS.check}`;
    button.querySelector('.answer-text').textContent = option.text;
    container.appendChild(button);
  });
  if (isExam) {
    renderExamNavigator();
    syncExamNavigatorStart();
  }
}

function saveExamAnswer(optionId, buttons) {
  const session = state.session;
  if (!session || session.mode !== 'exam') return;
  const index = session.index;
  const current = session.answers[index];
  const nextValue = Number(current) === Number(optionId) ? null : optionId;
  session.answers[index] = nextValue;
  session.selectedOptionId = nextValue;
  buttons.forEach(node => node.classList.toggle('selected', nextValue !== null && Number(node.dataset.optionId) === Number(nextValue)));
  renderExamNavigator();
  byId('questionSessionScore').textContent = `${session.answers.filter(value => value !== null && value !== undefined).length} respondidas`;
}

function applyPracticeFeedback(optionId, result, buttons) {
  const session = state.session;
  if (!session || session.mode !== 'practice') return;
  const correctOptionId = Number(result.correctOptionId);
  const correct = Number(optionId) === correctOptionId;
  session.locked = true;
  session.selectedOptionId = optionId;
  byId('nextQuestionBtn').disabled = false;

  buttons.forEach(node => {
    node.disabled = true;
    node.classList.remove('selected');
    const id = Number(node.dataset.optionId);
    if (id === correctOptionId) {
      node.classList.add('correct');
      node.querySelector('.answer-mark').outerHTML = ICONS.check;
    } else if (id === optionId) {
      node.classList.add('incorrect');
      node.querySelector('.answer-mark').outerHTML = ICONS.cross;
    }
  });

  const feedback = byId('questionFeedback');
  feedback.className = `feedback show ${correct ? 'success' : 'error'}`;
  const explanation = result.explanation
    ? `<p class="feedback-explanation">${escapeHtml(result.explanation)}</p>`
    : '';
  feedback.innerHTML = `${correct ? ICONS.check : ICONS.cross}<div><b>${correct ? 'Respuesta correcta' : 'Respuesta incorrecta'}</b>${explanation}</div>`;
  state.home = null;
  state.stats = null;
}

function persistPracticeAnswer(questionId, optionId, expectedCorrectOptionId, submissionKey) {
  const write = api('/api/answers', {
    method: 'POST',
    body: { question_id: questionId, selected_option_id: optionId, submission_key: submissionKey }
  }).then(result => {
    if (Number(result.correct_option_id) !== Number(expectedCorrectOptionId)) {
      console.warn('La validación local y el servidor no coinciden para la pregunta', questionId);
    }
  }).catch(error => {
    if (error.status !== 401) showToast('La respuesta se ha corregido, pero no se ha podido guardar en el historial.');
  });
  trackBackgroundWrite(write);
}

async function selectAnswer(button) {
  const session = state.session;
  if (!session) return;
  const optionId = Number(button.dataset.optionId);
  const buttons = [...document.querySelectorAll('.answer')];

  if (session.mode === 'exam') {
    saveExamAnswer(optionId, buttons);
    return;
  }
  if (session.locked || session.submitting) return;

  session.selectedOptionId = optionId;
  buttons.forEach(node => node.classList.toggle('selected', Number(node.dataset.optionId) === optionId));

  // Normal path: correction data was prepared locally when the question was loaded.
  // This keeps feedback and navigation instant while the authoritative write is sent
  // to the server in the background.
  if (session.localFeedback?.correctOptionId) {
    applyPracticeFeedback(optionId, session.localFeedback, buttons);
    persistPracticeAnswer(session.currentQuestion.id, optionId, session.localFeedback.correctOptionId, session.currentQuestion.submissionKey);
    return;
  }

  // Defensive fallback if local correction data is missing: ask the server.
  session.submitting = true;
  buttons.forEach(node => { node.disabled = true; });
  try {
    const result = await api('/api/answers', {
      method: 'POST',
      body: { question_id: session.currentQuestion.id, selected_option_id: optionId, submission_key: session.currentQuestion.submissionKey }
    });
    applyPracticeFeedback(optionId, {
      correctOptionId: result.correct_option_id,
      explanation: result.explanation || ''
    }, buttons);
  } catch (error) {
    buttons.forEach(node => { node.disabled = false; });
    if (error.status !== 401) showToast(error.message);
  } finally {
    session.submitting = false;
  }
}

function navigateExamQuestion(index) {
  const session = state.session;
  if (!session || session.mode !== 'exam') return;
  const target = Number(index);
  if (!Number.isInteger(target) || target < 0 || target >= session.questions.length) return;
  session.index = target;
  session.selectedOptionId = session.answers[target] ?? null;
  renderQuestion();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

async function nextQuestion() {
  const session = state.session;
  if (!session) return;
  const nextButton = byId('nextQuestionBtn');
  if (nextButton.disabled) return;

  if (session.mode === 'practice') {
    if (!session.locked) return;
    await advancePracticeInstantly();
    return;
  }

  if (session.index === session.questions.length - 1) {
    await finishExam();
    return;
  }
  session.index += 1;
  session.selectedOptionId = session.answers[session.index] ?? null;
  renderQuestion();
}

function topicPickerOptionsHtml(topics, selectedIds, dataAttribute) {
  const selected = new Set((selectedIds || []).map(Number));
  return topics.map(topic => `
    <button class="exam-topic-option ${selected.has(Number(topic.id)) ? 'selected' : ''}" type="button"
            ${dataAttribute}="${topic.id}" style="--topic-color:${safeColor(topic.color)}; --topic-soft:${colorSoft(topic.color)}">
      <span class="exam-topic-number">${escapeHtml(topic.number)}</span>
      <span class="exam-topic-name" title="${escapeHtml(topic.name)}">${escapeHtml(topic.name)}</span>
      <span class="exam-topic-check">${ICONS.check}</span>
    </button>`).join('');
}

function examTopics() {
  return state.home?.topics || [];
}

function examAvailableCount() {
  const topics = examTopics();
  const pending = state.pendingExam;
  const selected = new Set(pending.topicIds.map(Number));
  if (pending.kind === 'practice') return practiceAvailableCount(pending.topicIds);
  return topics.filter(topic => selected.has(Number(topic.id))).reduce((sum, topic) => sum + Number(topic.total || 0), 0);
}

function renderExamTopicPicker() {
  const picker = byId('examTopicPicker');
  if (!picker) return;
  picker.innerHTML = topicPickerOptionsHtml(examTopics(), state.pendingExam.topicIds, 'data-exam-topic');
}

function updateExamConfig() {
  const pending = state.pendingExam;
  const topics = examTopics();
  const available = examAvailableCount();
  const isPractice = pending.kind === 'practice';
  const input = byId('examQuestionCount');
  const customWrap = input.closest('.exam-count-input-wrap');

  if (!isPractice) {
    const raw = input.value.trim();
    if (pending.countMode === 'custom') {
      const customRaw = raw === '' ? NaN : Number(raw);
      if (Number.isFinite(customRaw) && customRaw >= 1) {
        pending.customQuestionCount = Math.max(1, Math.round(customRaw));
        pending.questionCount = pending.customQuestionCount;
      } else {
        pending.questionCount = 0;
      }
    }
    const count = Math.max(0, Math.round(Number(pending.questionCount || 0)));
    pending.questionCount = count;

    // Presets and the custom field are parallel choices. The custom value is never rewritten.
    input.max = String(Math.max(1, topics.reduce((sum, topic) => sum + Number(topic.total || 0), 0)));
    customWrap?.classList.toggle('active', pending.countMode === 'custom');

    document.querySelectorAll('[data-exam-count]').forEach(button => {
      const value = Number(button.dataset.examCount);
      button.classList.toggle('active', pending.countMode === 'preset' && value === count);
      button.disabled = false;
    });
  }


  const count = Number(pending.questionCount || 0);
  const validTopics = pending.mode === 'single' || pending.topicIds.length > 0;
  const validCount = isPractice || (available > 0 && count >= 1 && count <= available);
  byId('confirmExamBtn').disabled = !(validTopics && available > 0 && validCount);
  const error = byId('examConfigError');
  if (!validTopics) error.textContent = 'Selecciona al menos un tema.';
  else if (available === 0) error.textContent = 'No hay preguntas disponibles para esta selección.';
  else if (!isPractice && pending.countMode === 'custom' && count < 1) error.textContent = 'Escribe el número de preguntas.';
  else if (!isPractice && count > available) error.textContent = `Has elegido ${count} preguntas, pero esta selección contiene ${available}. Añade temas o reduce el número de preguntas.`;
  else error.textContent = '';
}

function setSessionConfigIcon(kind) {
  const node = byId('sessionConfigIcon');
  if (!node) return;
  node.innerHTML = kind === 'practice' ? SESSION_ICONS.practice : SESSION_ICONS.exam;
  node.classList.toggle('practice', kind === 'practice');
}

function setSessionConfigTitle(topic, fallback) {
  const title = byId('examIntroTitle');
  if (!title) return;
  if (!topic) {
    title.textContent = fallback;
    title.classList.remove('exam-config-topic-heading');
    return;
  }
  const color = safeColor(topic.color);
  title.classList.add('exam-config-topic-heading');
  title.innerHTML = `<span class="topic-icon" style="--topic-color:${color}; --topic-soft:${colorSoft(color)}">${escapeHtml(topic.number)}</span><span>${escapeHtml(topic.name)}</span>`;
}

function prepareExam(topicId = null, mode = null) {
  const topic = topicId ? topicById(Number(topicId)) : null;
  const topics = examTopics();
  const isMulti = mode === 'multi' || !topic;
  state.pendingExam = {
    kind: 'exam',
    mode: isMulti ? 'multi' : 'single',
    topicIds: topic ? [Number(topic.id)] : topics.map(item => Number(item.id)),
    questionCount: 30,
    countMode: 'preset',
    customQuestionCount: null
  };
  setSessionConfigIcon('exam');
  byId('sessionConfigEyebrow').textContent = 'Modo simulacro';
  byId('sessionConfigCopy').textContent = 'Las respuestas se corregirán al finalizar y las preguntas sin marcar contarán como no respondidas.';
  const examCountInput = byId('examQuestionCount');
  examCountInput.blur();
  examCountInput.value = '';
  examCountInput.setAttribute('placeholder', examCountInput.dataset.placeholderText || 'Personalizado...');
  examCountInput.closest('.exam-count-input-wrap')?.classList.remove('active');
  byId('examCountSection').hidden = false;
  byId('examTopicsSection').hidden = !isMulti;
  setSessionConfigTitle(topic, 'Simulacro por temas');
  byId('confirmExamBtn').textContent = 'Empezar simulacro';
  if (isMulti) renderExamTopicPicker();
  updateExamConfig();
  openModal('examIntroModal');
}

function preparePractice() {
  const topics = examTopics();
  state.pendingExam = {
    kind: 'practice',
    mode: 'multi',
    topicIds: topics.map(topic => Number(topic.id)),
    questionCount: 30,
    countMode: 'preset',
    customQuestionCount: null
  };
  setSessionConfigIcon('practice');
  byId('sessionConfigEyebrow').textContent = 'Modo práctica';
  byId('sessionConfigCopy').textContent = 'Elige los temas que quieres practicar. La práctica continuará hasta que decidas salir.';
  byId('examCountSection').hidden = true;
  byId('examTopicsSection').hidden = false;
  setSessionConfigTitle(null, 'Practicar por temas');
  byId('confirmExamBtn').textContent = 'Empezar práctica';
  renderExamTopicPicker();
  updateExamConfig();
  openModal('examIntroModal');
}

function toggleExamTopic(topicId) {
  if (state.pendingExam.mode !== 'multi') return;
  const id = Number(topicId);
  const selected = new Set(state.pendingExam.topicIds.map(Number));
  if (selected.has(id)) selected.delete(id); else selected.add(id);
  state.pendingExam.topicIds = [...selected];
  renderExamTopicPicker();
  updateExamConfig();
}

function toggleAllExamTopics() {
  if (state.pendingExam.mode !== 'multi') return;
  state.pendingExam.topicIds = examTopics().map(topic => Number(topic.id));
  renderExamTopicPicker();
  updateExamConfig();
}

function deselectAllExamTopics() {
  if (state.pendingExam.mode !== 'multi') return;
  state.pendingExam.topicIds = [];
  renderExamTopicPicker();
  updateExamConfig();
}

async function startExam() {
  const button = byId('confirmExamBtn');
  const pending = state.pendingExam;
  updateExamConfig({ clamp: false });
  if (button.disabled) return;
  button.disabled = true;

  if (pending.kind === 'practice') {
    closeModal('examIntroModal');
    await startPractice(pending.topicIds);
    button.disabled = false;
    return;
  }

  try {
    state.examReview = null;
    const data = await api('/api/simulations', {
      method: 'POST',
      body: {
        topic_ids: pending.topicIds,
        question_count: pending.questionCount
      }
    });
    state.session = {
      mode: 'exam',
      submissionId: data.submission_id,
      topicIds: data.topic_ids || [],
      questions: data.questions,
      index: 0,
      selectedOptionId: null,
      answers: Array(data.questions.length).fill(null),
      submitting: false,
      locked: false
    };
    closeModal('examIntroModal');
    await setView('question', true);
    renderQuestion();
  } catch (error) {
    byId('examConfigError').textContent = error.message;
  } finally {
    button.disabled = false;
    updateExamConfig({ clamp: false });
  }
}

async function finishExam() {
  const session = state.session;
  if (!session || session.mode !== 'exam' || session.submitting) return;
  session.submitting = true;
  const nextButton = byId('nextQuestionBtn');
  nextButton.disabled = true;
  try {
    const result = await api('/api/simulations/finish', {
      method: 'POST',
      body: {
        submission_id: session.submissionId,
        answers: session.questions.map((question, index) => ({
          question_id: question.id,
          selected_option_id: session.answers[index] ?? null
        }))
      }
    });
    state.home = null;
    state.stats = null;
    state.examReview = { ...result, collapsedCorrect: true };
    state.session = null;
    await setView('review', true);
  } catch (error) {
    session.submitting = false;
    nextButton.disabled = false;
    if (error.status !== 401) showToast(error.message);
  }
}

function reviewStatusLabel(outcome) {
  if (outcome === 'correct') return 'Correcta';
  if (outcome === 'incorrect') return 'Incorrecta';
  return 'En blanco';
}

function renderReviewSummary(review) {
  const pct = review.total ? Math.round((review.correct / review.total) * 100) : 0;
  const fraction = value => `<span class="review-score-number">${value}<small>/ ${review.total}</small></span>`;
  byId('reviewSummary').innerHTML = `
    <article class="panel review-summary-card"><span>Resultado</span><b>${pct} %</b></article>
    <article class="panel review-summary-card success"><span>Correctas</span><b>${fraction(review.correct)}</b></article>
    <article class="panel review-summary-card danger"><span>Incorrectas</span><b>${fraction(review.incorrect)}</b></article>
    <article class="panel review-summary-card skipped"><span>En blanco</span><b>${fraction(review.skipped)}</b></article>`;
}

function reviewOptionHtml(question, option, index) {
  const selected = Number(question.selected_option_id) === Number(option.id);
  const correct = Number(question.correct_option_id) === Number(option.id);
  let cls = '';
  let label = '';
  if (correct) {
    cls = ' correct';
    label = selected ? 'Tu respuesta · Correcta' : 'Respuesta correcta';
  } else if (selected) {
    cls = ' incorrect';
    label = 'Tu respuesta';
  }
  return `<div class="review-option${cls}">
    <span class="answer-letter">${String.fromCharCode(65 + index)}</span>
    <span class="review-option-text">${escapeHtml(option.text)}</span>
    ${label ? `<span class="review-option-label">${label}</span>` : ''}
  </div>`;
}

function reviewQuestionHtml(question, collapseCorrect) {
  const collapsed = collapseCorrect && question.outcome === 'correct';
  const color = safeColor(question.topic.color);
  return `<article class="panel review-question-card outcome-${question.outcome}${collapsed ? ' collapsed' : ''}" id="reviewQuestion${question.position}" data-review-position="${question.position}" data-review-outcome="${question.outcome}">
    <button class="review-question-head" type="button" data-review-toggle="${question.position}" aria-expanded="${!collapsed}">
      <span class="review-question-index">${question.position}</span>
      <span class="review-question-heading"><strong>${escapeHtml(question.text)}</strong></span>
      <span class="review-question-meta">
        <span class="review-status ${question.outcome}">${reviewStatusLabel(question.outcome)}</span>
        <span class="topic-chip topic-colored review-topic-chip" style="--topic-color:${color};--topic-soft:${colorSoft(color)}">${escapeHtml(question.topic.number)} - ${escapeHtml(question.topic.name)}</span>
      </span>
      <svg class="review-collapse-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="m6 9 6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
    </button>
    <div class="review-question-body">
      <div class="review-options">${question.options.map((option, index) => reviewOptionHtml(question, option, index)).join('')}</div>
      ${question.explanation ? `<div class="review-explanation"><strong>Explicación</strong><p>${escapeHtml(question.explanation)}</p></div>` : ''}
    </div>
  </article>`;
}

function renderReviewNavigator() {
  const review = state.examReview;
  if (!review) return;
  byId('reviewNavGrid').innerHTML = review.review.map(question => `
    <button type="button" class="exam-nav-item ${question.outcome}"
      data-review-nav-index="${question.position}" aria-label="Pregunta ${question.position}, ${reviewStatusLabel(question.outcome)}">${question.position}</button>`).join('');
}

function renderExamReview() {
  const review = state.examReview;
  if (!review?.review) return;
  review.collapsedCorrect = true;
  renderReviewSummary(review);
  byId('reviewList').innerHTML = review.review.map(question => reviewQuestionHtml(question, true)).join('');
  renderReviewNavigator();
}

function toggleReviewQuestion(position) {
  const card = byId(`reviewQuestion${position}`);
  if (!card) return;
  const collapsed = !card.classList.contains('collapsed');
  card.classList.toggle('collapsed', collapsed);
  card.querySelector('[data-review-toggle]')?.setAttribute('aria-expanded', String(!collapsed));
}

function goToReviewQuestion(position) {
  const card = byId(`reviewQuestion${position}`);
  if (!card) return;
  card.classList.remove('collapsed');
  card.querySelector('[data-review-toggle]')?.setAttribute('aria-expanded', 'true');
  card.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function exitQuestions() {
  state.session = null;
  await flushBackgroundWrites();
  setView('home', true);
}

async function ensureStatsUsers() {
  if (state.user?.role !== 'admin') return [];
  if (!state.statsScope.users) {
    renderStatsUserSkeleton();
    const users = await api('/api/admin/users');
    state.statsScope.users = users.filter(user => user.role === 'user');
  }
  return state.statsScope.users;
}

function filteredStatsUsers() {
  const term = state.statsScope.search.trim().toLocaleLowerCase('es');
  return (state.statsScope.users || [])
    .filter(user => `${user.display_name} ${user.username}`.toLocaleLowerCase('es').includes(term))
    .sort((a, b) => {
      if (a.is_active !== b.is_active) return a.is_active ? -1 : 1;
      return a.display_name.localeCompare(b.display_name, 'es', { sensitivity: 'base' });
    });
}

function renderStatsUserResults() {
  const target = byId('statsUserResults');
  if (!target) return;
  const filtered = filteredStatsUsers();

  if (!filtered.length) {
    target.innerHTML = '<div class="stats-student-empty">No hay alumnos que coincidan con la búsqueda.</div>';
    return;
  }

  target.innerHTML = filtered.map(user => `
    <button class="stats-student-row" type="button" data-stats-user-id="${user.id}" role="listitem">
      <span class="admin-user-identity${user.is_active ? '' : ' is-inactive'}">
        <span class="admin-user-avatar">${escapeHtml(user.display_name.slice(0, 1).toUpperCase())}</span>
        <span class="stats-student-table-user">
          <strong>${escapeHtml(user.display_name)}</strong>
          <span>@${escapeHtml(user.username)}</span>
        </span>
      </span>
      <span class="user-state-badge ${user.is_active ? 'active' : 'inactive'}">${user.is_active ? 'Activo' : 'De baja'}</span>
    </button>`).join('');
}

function renderSelectedStatsUser(user) {
  const card = byId('statsSelectedUserCard');
  if (!card) return;
  if (!user) {
    card.hidden = true;
    return;
  }
  card.hidden = false;
  byId('statsSelectedUserAvatar').textContent = user.display_name.slice(0, 1).toUpperCase();
  byId('statsSelectedUserName').textContent = user.display_name;
  byId('statsSelectedUserMeta').textContent = `@${user.username}`;
  const status = byId('statsSelectedUserStatus');
  status.textContent = user.is_active ? 'Activo' : 'De baja';
  status.className = `user-state-badge ${user.is_active ? 'active' : 'inactive'}`;
  card.querySelector('.stats-selected-student-main')?.classList.toggle('is-inactive', !user.is_active);
}

async function renderStatsScopeUI() {
  const isAdmin = state.user?.role === 'admin';
  const tabs = byId('statsScopeTabs');
  const picker = byId('statsUserPicker');
  const selectedCard = byId('statsSelectedUserCard');
  const content = byId('statsContent');
  if (tabs) tabs.hidden = !isAdmin;

  document.querySelectorAll('[data-stats-scope]').forEach(button => {
    button.classList.toggle('active', button.dataset.statsScope === state.statsScope.mode);
  });

  const needsStudent = isAdmin && state.statsScope.mode === 'student';
  if (!needsStudent) {
    if (picker) picker.hidden = true;
    if (selectedCard) selectedCard.hidden = true;
    if (content) content.hidden = false;
    return;
  }

  try {
    await ensureStatsUsers();
    const selected = (state.statsScope.users || []).find(user => Number(user.id) === Number(state.statsScope.userId));
    if (picker) picker.hidden = Boolean(selected);
    if (content) content.hidden = !selected;
    renderSelectedStatsUser(selected || null);
    if (!selected) {
      byId('statsUserSearch').value = state.statsScope.search;
      renderStatsUserResults();
    }
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
}

async function setStatsScope(mode) {
  if (!['self', 'student', 'all'].includes(mode)) return;
  state.statsScope.mode = mode;
  if (mode !== 'student') state.statsScope.userId = null;
  state.stats = null;
  await renderStatsScopeUI();
  if (mode !== 'student' || state.statsScope.userId) await loadStats();
}

async function selectStatsUser(id) {
  const users = await ensureStatsUsers();
  const user = users.find(item => Number(item.id) === Number(id));
  if (!user) return;
  state.statsScope.userId = Number(user.id);
  state.stats = null;
  await renderStatsScopeUI();
  await loadStats();
}

async function changeStatsUser() {
  state.statsScope.userId = null;
  state.stats = null;
  await renderStatsScopeUI();
  setTimeout(() => byId('statsUserSearch')?.focus(), 0);
}

async function loadStats() {
  await renderStatsScopeUI();
  if (state.user?.role === 'admin' && state.statsScope.mode === 'student' && !state.statsScope.userId) return;

  try {
    renderStatsSkeleton();
    const params = new URLSearchParams();
    if (state.user?.role === 'admin') {
      params.set('scope', state.statsScope.mode);
      if (state.statsScope.mode === 'student') params.set('user_id', String(state.statsScope.userId));
    }
    state.stats = await api(`/api/statistics?${params.toString()}`);
    renderStats();
    await renderStatsScopeUI();
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
}

function statCard(label, value, detail = '', detailClass = 'neutral') {
  return `<article class="panel kpi">
    <div class="kpi-label">${escapeHtml(label)}</div>
    <div class="kpi-value">${value}</div>
    ${detail ? `<div class="kpi-trend ${detailClass}">${detail}</div>` : ''}
  </article>`;
}

function renderStatsSummary(data) {
  const target = byId('statsSummary');
  if (!target) return;
  const k = data.kpis;
  const allStudents = data.subject?.scope === 'all';

  if (!allStudents) {
    target.innerHTML = `<div class="stats-kpis">
      ${statCard('Preguntas respondidas', formatNumber(k.total_answered), `${formatNumber(k.answered_this_month)} este mes`)}
      ${statCard('Aciertos totales', formatNumber(k.correct_attempts), `${formatDecimal(k.accuracy)} % de acierto`, 'positive')}
      ${statCard('Racha actual', `<span>${formatNumber(k.current_streak)}</span> <small>días</small>`, `Mejor racha: ${formatNumber(k.best_streak)} días`)}
      ${statCard('Porcentaje de acierto reciente', `<span>${formatDecimal(k.recent_accuracy)}</span> <small>%</small>`, 'Últimas 30 respuestas')}
    </div>`;
    return;
  }

  const cohort = data.cohort || {};
  target.innerHTML = `
    <div class="stats-cohort-overview">
      <div class="stats-cohort-kpis">
        ${statCard('Alumnos', formatNumber(cohort.total_students), `${formatNumber(cohort.active_students)} activos · ${formatNumber(cohort.students_with_activity)} con actividad`)}
        ${statCard('Respuestas totales', formatNumber(k.total_answered), `${formatNumber(k.answered_this_month)} este mes`)}
        ${statCard('Aciertos totales', formatNumber(k.correct_attempts), 'Intentos correctos acumulados')}
        ${statCard('Cobertura del banco', `${formatNumber(cohort.unique_questions_correct)} <small>de ${formatNumber(cohort.bank_questions)}</small>`, `${formatDecimal(cohort.coverage)} % del banco`, 'positive')}
        ${statCard('Respuestas por alumno', formatDecimal(cohort.avg_answered_per_student), 'Media acumulada')}
        ${statCard('Acierto reciente', `<span>${formatDecimal(cohort.avg_recent_accuracy_30)}</span> <small>%</small>`, 'Media de las últimas 30 por alumno')}
      </div>
      <article class="panel kpi cohort-heatmap-kpi" aria-label="Actividad conjunta de las últimas cuatro semanas">
        <div class="kpi-label">Actividad</div>
        <div class="heatmap-wrap stats-cohort-heatmap-wrap">
          <div class="calendar-heatmap" id="cohortHeatmap"></div>
          <div class="calendar-range" id="cohortHeatmapRange"></div>
        </div>
        <div class="kpi-trend neutral">Actividad conjunta de todos los alumnos</div>
      </article>
    </div>`;
}

function renderStats() {
  const data = state.stats;
  if (!data) return;
  const isAll = data.subject?.scope === 'all';
  const isSelectedStudent = data.subject?.scope === 'student';
  const isSelf = data.subject?.scope === 'self';
  renderStatsSummary(data);

  byId('topicBarTitle').textContent = isAll ? 'Promedio de respuestas por tema' : 'Preguntas respondidas por tema';
  byId('topicAccuracyBarTitle').textContent = isAll ? 'Porcentaje de acierto medio por tema' : 'Porcentaje de acierto por tema';
  byId('progressChartTitle').textContent = 'Aciertos acumulados';
  byId('winrateChartTitle').textContent = isAll ? 'Porcentaje de acierto global' : 'Porcentaje de acierto reciente';
  byId('winrateWindowLabel').textContent = `Media móvil de ${data.winrate_window || (isAll ? 120 : 30)} respuestas`;

  renderTopicMetricChart('topicBarChart', data.bar, isAll ? 'average_answered' : 'unique_answered', {
    showReference: isSelectedStudent,
    showEndAxis: !isSelf
  });
  renderTopicMetricChart('topicAccuracyBarChart', data.bar, isAll ? 'average_accuracy' : 'accuracy', { showReference: isSelectedStudent });

  const progressPanel = byId('progressChartPanel');
  if (progressPanel) progressPanel.hidden = isAll;
  if (isAll) {
    renderHeatmap(data.activity || [], 'cohortHeatmap', 'cohortHeatmapRange');
  }

  populateStatsSelects(data.topics);
  updateCharts();
}

function renderTopicMetricChart(targetId, items, mode, options = {}) {
  const target = byId(targetId);
  if (!items.length) {
    target.innerHTML = '<div class="empty-chart">Todavía no hay datos.</div>';
    return;
  }

  const isAccuracy = mode === 'accuracy' || mode === 'average_accuracy';
  const isAverage = mode === 'average_answered' || mode === 'average_accuracy';
  const showEndAxis = options.showEndAxis !== false;
  const valueFor = item => {
    if (mode === 'accuracy') return Number(item.accuracy || 0);
    if (mode === 'average_accuracy') return Number(item.average_accuracy || 0);
    if (mode === 'average_answered') return Number(item.average_answered || 0);
    if (mode === 'unique_answered') return Number(item.unique_answered || 0);
    return Number(item.value || 0);
  };
  const errorFor = item => mode === 'average_accuracy'
    ? Number(item.accuracy_std || 0)
    : mode === 'average_answered' ? Number(item.answered_std || 0) : 0;
  const referenceFor = item => mode === 'accuracy'
    ? Number(item.reference_avg_accuracy || 0)
    : mode === 'unique_answered' ? Number(item.reference_avg_unique_answered || 0)
    : mode === 'count' ? Number(item.reference_avg_unique_correct || 0) : null;

  const niceAxisMax = value => {
    const raw = Math.max(1, Number(value) || 1);
    const magnitude = 10 ** Math.floor(Math.log10(raw));
    const step = magnitude / 2;
    return Math.ceil(raw / step) * step;
  };
  const maxValue = isAccuracy
    ? 100
    : (mode === 'count' || mode === 'unique_answered')
      ? Math.max(1, ...items.map(item => Number(item.total) || valueFor(item) || 0))
      : niceAxisMax(Math.max(1, ...items.map(item => valueFor(item) + errorFor(item))));
  const axisEnd = isAccuracy ? '100 %' : (mode === 'count' || mode === 'unique_answered') ? formatNumber(maxValue) : formatDecimal(maxValue);

  const tooltipText = item => {
    const value = valueFor(item);
    const error = errorFor(item);
    const reference = options.showReference ? referenceFor(item) : null;
    let main = '';
    if (mode === 'average_answered') main = `Media: ${formatDecimal(value)} respuestas`;
    else if (mode === 'average_accuracy') main = `Media: ${formatDecimal(value)} %`;
    else if (mode === 'unique_answered') main = `Respondidas: ${formatNumber(value)} de ${formatNumber(item.total)}`;
    else if (mode === 'accuracy') main = Number(item.answered || 0) ? `Porcentaje de acierto: ${formatDecimal(value)} %` : 'Sin respuestas registradas';
    else main = `Valor: ${formatNumber(value)}`;

    const details = [];
    if (isAverage && error > 0) details.push(`Dispersión: ±${formatDecimal(error)}${isAccuracy ? ' %' : ' respuestas'} (desv. estándar)`);
    if (mode === 'average_accuracy' && Number(item.students_with_activity || 0) > 0) details.push(`${formatNumber(item.students_with_activity)} alumnos con respuestas en el tema`);
    if (reference != null) details.push(`Media de alumnos: ${formatDecimal(reference)}${isAccuracy ? ' %' : ' preguntas'}`);
    return { main, details };
  };

  target.innerHTML = `
    <div class="topic-metric-rows">
      ${items.map((item, index) => {
        const rawValue = valueFor(item);
        const error = errorFor(item);
        const width = Math.max(0, Math.min(100, rawValue / maxValue * 100));
        const hasValue = isAccuracy ? Number(item.answered || item.students_with_activity || 0) > 0 : true;
        const valueText = isAccuracy ? (hasValue ? `${formatDecimal(rawValue)} %` : '—') : (mode === 'count' || mode === 'unique_answered') ? formatNumber(rawValue) : formatDecimal(rawValue);
        const topicColor = safeColor(item.color);
        const lower = Math.max(0, rawValue - error);
        const upper = Math.min(maxValue, rawValue + error);
        const errorLeft = lower / maxValue * 100;
        const errorWidth = Math.max(0, (upper - lower) / maxValue * 100);
        const reference = options.showReference ? referenceFor(item) : null;
        const referencePos = reference == null ? null : Math.max(0, Math.min(100, reference / maxValue * 100));
        const tt = tooltipText(item);
        return `<div class="topic-metric-row" data-topic-bar-index="${index}" tabindex="0" aria-label="${escapeHtml(item.number)} - ${escapeHtml(item.name)}. ${escapeHtml(tt.main)}${tt.details.length ? '. ' + escapeHtml(tt.details.join('. ')) : ''}">
          <div class="topic-metric-label" title="${escapeHtml(item.number)} - ${escapeHtml(item.name)}">
            <span class="topic-icon" style="--topic-color:${topicColor}; --topic-soft:${colorSoft(topicColor)}">${escapeHtml(item.number)}</span>
            <span class="topic-metric-name">${escapeHtml(item.name)}</span>
          </div>
          <div class="topic-metric-plot${showEndAxis ? '' : ' no-end-axis'}">
            <span class="topic-metric-bar topic-metric-bar-soft" style="width:${width.toFixed(1)}%; --metric-color:${topicColor}"></span>
            ${(isAverage && error > 0) || referencePos != null ? `<svg class="topic-metric-overlay" viewBox="0 0 100 20" preserveAspectRatio="none" aria-hidden="true">
              ${isAverage && error > 0 ? `
                <line class="topic-error-range" x1="${errorLeft.toFixed(2)}" y1="10" x2="${(errorLeft + errorWidth).toFixed(2)}" y2="10" vector-effect="non-scaling-stroke"></line>
                <line class="topic-error-cap" x1="${errorLeft.toFixed(2)}" y1="3" x2="${errorLeft.toFixed(2)}" y2="17" vector-effect="non-scaling-stroke"></line>
                <line class="topic-error-cap" x1="${(errorLeft + errorWidth).toFixed(2)}" y1="3" x2="${(errorLeft + errorWidth).toFixed(2)}" y2="17" vector-effect="non-scaling-stroke"></line>` : ''}
              ${referencePos != null ? `
                <line class="topic-reference-halo" x1="${referencePos.toFixed(2)}" y1="1" x2="${referencePos.toFixed(2)}" y2="19" vector-effect="non-scaling-stroke"></line>
                <line class="topic-reference-marker" x1="${referencePos.toFixed(2)}" y1="1" x2="${referencePos.toFixed(2)}" y2="19" vector-effect="non-scaling-stroke" stroke="${topicColor}"></line>` : ''}
            </svg>` : ''}
          </div>
          <div class="topic-metric-value"><b>${valueText}</b>${isAverage && error > 0 ? `<small>± ${formatDecimal(error)}${isAccuracy ? ' %' : ''}</small>` : ''}</div>
        </div>`;
      }).join('')}
    </div>
    <div class="topic-metric-axis${showEndAxis ? '' : ' no-end-axis'}" aria-hidden="true">
      <span></span>
      <div><span>${isAccuracy ? '0 %' : '0'}</span>${showEndAxis ? `<span>${axisEnd}</span>` : ''}</div>
      <span></span>
    </div>
    <div class="topic-bar-tooltip" role="status" aria-live="polite" hidden></div>`;

  const tooltip = target.querySelector('.topic-bar-tooltip');
  const rows = [...target.querySelectorAll('[data-topic-bar-index]')];
  const showTooltip = (row, event = null) => {
    const index = Number(row.dataset.topicBarIndex);
    const item = items[index];
    if (!item || !tooltip) return;
    const tt = tooltipText(item);
    tooltip.innerHTML = `<strong>${escapeHtml(item.number)} - ${escapeHtml(item.name)}</strong><span>${escapeHtml(tt.main)}</span>${tt.details.map(detail => `<small>${escapeHtml(detail)}</small>`).join('')}`;
    tooltip.hidden = false;
    const chartRect = target.getBoundingClientRect();
    const rowRect = row.getBoundingClientRect();
    const desiredX = event ? event.clientX - chartRect.left : rowRect.left - chartRect.left + rowRect.width * .62;
    const rawY = rowRect.top - chartRect.top + rowRect.height / 2;
    const desiredY = Math.max(38, Math.min(chartRect.height - 38, rawY));
    tooltip.style.left = `${Math.max(8, Math.min(chartRect.width - 8, desiredX))}px`;
    tooltip.style.top = `${desiredY}px`;
    tooltip.classList.toggle('flip-x', desiredX > chartRect.width * .64);
  };
  const hideTooltip = () => { if (tooltip) tooltip.hidden = true; };
  rows.forEach(row => {
    row.addEventListener('pointermove', event => showTooltip(row, event));
    row.addEventListener('pointerdown', event => showTooltip(row, event));
    row.addEventListener('pointerleave', hideTooltip);
    row.addEventListener('focus', () => showTooltip(row));
    row.addEventListener('blur', hideTooltip);
  });

  // On touch screens the finger can travel from one bar to another while the
  // original pointer target remains unchanged. Resolve the row under the finger
  // on every touchmove so the tooltip follows the gesture naturally.
  const showTooltipAtTouch = touch => {
    if (!touch) return;
    const element = document.elementFromPoint(touch.clientX, touch.clientY);
    const row = element?.closest?.('[data-topic-bar-index]');
    if (row && target.contains(row)) showTooltip(row, { clientX: touch.clientX });
  };
  target.addEventListener('touchstart', event => showTooltipAtTouch(event.touches[0]), { passive: true });
  target.addEventListener('touchmove', event => showTooltipAtTouch(event.touches[0]), { passive: true });
  target.addEventListener('touchend', () => window.setTimeout(hideTooltip, 240), { passive: true });
  target.addEventListener('touchcancel', hideTooltip, { passive: true });
}

function populateStatsSelects(topics) {
  const progress = byId('progressTopicSelect');
  const winrate = byId('winrateTopicSelect');
  const pValue = progress.value || 'all';
  const wValue = winrate.value || 'all';
  const options = ['<option value="all" data-color="#0f766e">Todos los temas</option>', ...topics.map(topic => topicOptionHtml(topic))].join('');
  progress.innerHTML = options;
  winrate.innerHTML = options;
  progress.value = [...progress.options].some(option => option.value === pValue) ? pValue : 'all';
  winrate.value = [...winrate.options].some(option => option.value === wValue) ? wValue : 'all';
  syncTopicSelectStyle(progress);
  syncTopicSelectStyle(winrate);
}

function renderLineChart(targetId, series, options = {}) {
  const target = byId(targetId);
  if (!series?.length) {
    target.innerHTML = '<div class="empty-chart">Aún no hay suficientes respuestas para mostrar este gráfico.</div>';
    return;
  }

  const width = Math.max(280, Math.round(target.getBoundingClientRect().width || 700));
  const height = width < 520 ? 228 : 260;
  const pad = { left: width < 420 ? 36 : 44, right: 16, top: 16, bottom: 30 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const values = series.map(point => Number(point.value) || 0);
  let min = options.min ?? Math.min(...values);
  let max = options.max ?? Math.max(...values);
  if (!options.percent) min = Math.min(0, min);
  if (max === min) max = min + 1;
  if (options.percent) { min = Math.min(min, 40); max = Math.max(max, 100); }
  else max = Math.ceil(max * 1.08 || 1);

  const x = index => pad.left + (series.length === 1 ? plotW / 2 : index / (series.length - 1) * plotW);
  const y = value => pad.top + (1 - (value - min) / (max - min)) * plotH;
  const linePath = values.map((value, index) => `${index ? 'L' : 'M'} ${x(index).toFixed(1)} ${y(value).toFixed(1)}`).join(' ');
  const areaPath = `${linePath} L ${x(values.length - 1).toFixed(1)} ${pad.top + plotH} L ${x(0).toFixed(1)} ${pad.top + plotH} Z`;
  const color = safeColor(options.color || '#0f766e');
  const gradientId = `gradient-${targetId}`;

  const grid = Array.from({ length: 5 }, (_, index) => {
    const gy = pad.top + index * plotH / 4;
    const label = max - index * (max - min) / 4;
    return `<line class="chart-grid-line" x1="${pad.left}" y1="${gy}" x2="${width - pad.right}" y2="${gy}"/><text class="chart-axis-label" x="${pad.left - 8}" y="${gy + 3}" text-anchor="end">${options.percent ? Math.round(label) + '%' : Math.round(label)}</text>`;
  }).join('');

  const labelIndexes = [...new Set([0, Math.round((series.length - 1) * .25), Math.round((series.length - 1) * .5), Math.round((series.length - 1) * .75), series.length - 1])];
  const xLabels = labelIndexes.map(index => `<text class="chart-axis-label" x="${x(index)}" y="${height - 6}" text-anchor="middle">${escapeHtml(series[index].label)}</text>`).join('');

  target.innerHTML = `
    <svg class="chart-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Gráfico de evolución">
      <defs><linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".28"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs>
      ${grid}${xLabels}
      <path d="${areaPath}" fill="url(#${gradientId})"></path>
      <path class="chart-line" stroke="${color}" d="${linePath}"></path>
      <g class="chart-hover-marker" hidden>
        <line class="chart-hover-guide" x1="0" y1="${pad.top}" x2="0" y2="${pad.top + plotH}"></line>
        <circle class="chart-hover-dot" stroke="${color}" cx="0" cy="0" r="4"></circle>
      </g>
      <rect class="chart-hover-surface" x="${pad.left}" y="${pad.top}" width="${plotW}" height="${plotH}" fill="transparent"></rect>
    </svg>
    <div class="chart-tooltip" role="status" aria-live="polite" hidden></div>`;

  const svg = target.querySelector('.chart-svg');
  const surface = target.querySelector('.chart-hover-surface');
  const marker = target.querySelector('.chart-hover-marker');
  const guide = target.querySelector('.chart-hover-guide');
  const dot = target.querySelector('.chart-hover-dot');
  const tooltip = target.querySelector('.chart-tooltip');

  const showPoint = clientX => {
    const rect = svg.getBoundingClientRect();
    const svgX = (clientX - rect.left) * width / rect.width;
    const ratio = Math.max(0, Math.min(1, (svgX - pad.left) / plotW));
    const index = series.length === 1 ? 0 : Math.round(ratio * (series.length - 1));
    const point = series[index];
    const px = x(index);
    const py = y(point.value);
    guide.setAttribute('x1', px); guide.setAttribute('x2', px);
    dot.setAttribute('cx', px); dot.setAttribute('cy', py);
    marker.removeAttribute('hidden');
    tooltip.hidden = false;
    tooltip.innerHTML = `<strong>${escapeHtml(point.label)}</strong><span>${options.percent ? formatDecimal(point.value) + ' %' : formatNumber(point.value)}</span>`;
    const localX = px / width * rect.width;
    const localY = py / height * rect.height;
    tooltip.style.left = `${localX}px`;
    tooltip.style.top = `${localY}px`;
    tooltip.classList.toggle('flip', localX > rect.width * .72);
  };
  const hidePoint = () => { marker.setAttribute('hidden', ''); tooltip.hidden = true; };
  surface.addEventListener('pointermove', event => showPoint(event.clientX));
  surface.addEventListener('pointerdown', event => showPoint(event.clientX));

  // Native touch tracking for mobile: horizontal dragging reveals the nearest
  // data point while vertical page scrolling remains available.
  const showTouchPoint = event => {
    const touch = event.touches?.[0];
    if (touch) showPoint(touch.clientX);
  };
  surface.addEventListener('touchstart', showTouchPoint, { passive: true });
  surface.addEventListener('touchmove', showTouchPoint, { passive: true });
  surface.addEventListener('touchend', () => window.setTimeout(hidePoint, 280), { passive: true });
  surface.addEventListener('touchcancel', hidePoint, { passive: true });
  svg.addEventListener('pointerleave', hidePoint);
}

function updateCharts() {
  if (!state.stats) return;
  const isAll = state.stats.subject?.scope === 'all';
  const pKey = byId('progressTopicSelect').value || 'all';
  const wKey = byId('winrateTopicSelect').value || 'all';
  const pTopic = pKey === 'all' ? null : topicById(Number(pKey));
  const wTopic = wKey === 'all' ? null : topicById(Number(wKey));
  if (!isAll) renderLineChart('progressChart', state.stats.progress[pKey] || [], { color: pTopic?.color || '#0f766e' });
  renderLineChart('winrateChart', state.stats.winrate[wKey] || [], { percent: true, color: wTopic?.color || '#0f766e' });
}


const ADMIN_META = {
  topics: { singular: 'tema', plural: 'Temas', create: 'Nuevo tema', search: 'Buscar por número o nombre' },
  questions: { singular: 'pregunta', plural: 'Preguntas', create: 'Nueva pregunta', search: 'Buscar en las preguntas' },
  users: { singular: 'usuario', plural: 'Usuarios', create: 'Nuevo usuario', search: 'Buscar por nombre o usuario' }
};

function adminEndpoint(type, id = null) {
  const base = `/api/admin/${type}`;
  return id == null ? base : `${base}/${id}`;
}

function invalidateAdmin(type) {
  state.admin.data[type] = null;
  if (type === 'topics') { state.admin.data.questions = null; state.admin.data.users = null; }
  if (type === 'topics' || type === 'questions') {
    state.home = null;
    state.stats = null;
  }
  if (type === 'users') {
    state.statsScope.users = null;
    state.stats = null;
  }
}

async function loadAdmin(force = false) {
  if (state.user?.role !== 'admin') return;
  const tab = state.admin.tab;
  if (tab === 'questions' && !state.admin.data.topics) {
    try { state.admin.data.topics = await api('/api/admin/topics'); }
    catch (error) { if (error.status !== 401) showToast(error.message); return; }
  }
  if (!state.admin.data[tab] || force) {
    renderAdminSkeleton();
    try {
      state.admin.data[tab] = await api(adminEndpoint(tab));
    } catch (error) {
      if (error.status !== 401) showToast(error.message);
      return;
    }
  }
  renderAdminControls();
  renderAdmin();
}

async function ensureAdminTopics() {
  if (!state.admin.data.topics) state.admin.data.topics = await api('/api/admin/topics');
  return state.admin.data.topics;
}

function setAdminTab(tab) {
  if (!ADMIN_META[tab]) return;
  state.admin.tab = tab;
  document.querySelectorAll('[data-admin-tab]').forEach(button => {
    button.classList.toggle('active', button.dataset.adminTab === tab);
  });
  byId('adminCreateBtn').textContent = ADMIN_META[tab].create;
  loadAdmin();
}

function adminActions(type, item) {
  if (type === 'users') {
    const selfDisabled = item.is_self;
    const statusAction = item.is_active
      ? `<button class="admin-action danger" type="button" data-admin-deactivate-user="${item.id}" ${selfDisabled ? 'disabled title="No puedes dar de baja tu propio usuario"' : ''}>Dar de baja</button>`
      : `<button class="admin-action success" type="button" data-admin-activate-user="${item.id}">Dar de alta</button>`;
    return `<div class="admin-row-actions">
      <button class="admin-action" type="button" data-admin-edit="users" data-admin-id="${item.id}">Editar</button>
      ${statusAction}
      <button class="admin-action danger admin-action-delete" type="button" data-admin-delete="users" data-admin-id="${item.id}" ${selfDisabled ? 'disabled title="No puedes eliminar tu propio usuario"' : ''}>Eliminar</button>
    </div>`;
  }
  return `<div class="admin-row-actions">
    <button class="admin-action" type="button" data-admin-edit="${type}" data-admin-id="${item.id}">Editar</button>
    <button class="admin-action danger" type="button" data-admin-delete="${type}" data-admin-id="${item.id}">Eliminar</button>
  </div>`;
}

function renderAdminControls() {
  const tab = state.admin.tab;
  const filter = state.admin.filters[tab];
  const search = byId('adminSearch');
  const searchLabel = byId('adminSearchLabel');
  search.placeholder = ADMIN_META[tab].search;
  search.value = filter.search;
  searchLabel.textContent = tab === 'questions' ? 'Pregunta' : tab === 'users' ? 'Nombre o usuario' : 'Nombre o número';

  let controls = '';
  if (tab === 'topics') {
    controls = `
      <label class="admin-filter"><span>Contenido</span><select data-admin-filter-key="content">
        <option value="all" ${filter.content === 'all' ? 'selected' : ''}>Todos</option>
        <option value="with" ${filter.content === 'with' ? 'selected' : ''}>Con preguntas</option>
        <option value="empty" ${filter.content === 'empty' ? 'selected' : ''}>Sin preguntas</option>
      </select></label>`;
  } else if (tab === 'questions') {
    const topics = state.admin.data.topics || [];
    controls = `
      <label class="admin-filter"><span>Tema</span><span class="topic-select-control"><span class="topic-select-dot" aria-hidden="true"></span><select data-admin-filter-key="topic" class="topic-aware-select">
        <option value="all" data-color="#0f766e" ${filter.topic === 'all' ? 'selected' : ''}>Todos los temas</option>
        ${topics.map(topic => topicOptionHtml(topic, String(filter.topic) === String(topic.id))).join('')}
      </select></span></label>`;
  } else {
    controls = `
      <label class="admin-filter"><span>Rol</span><select data-admin-filter-key="role">
        <option value="all" ${filter.role === 'all' ? 'selected' : ''}>Todos</option>
        <option value="admin" ${filter.role === 'admin' ? 'selected' : ''}>Administradores</option>
        <option value="user" ${filter.role === 'user' ? 'selected' : ''}>Usuarios</option>
      </select></label>
      <label class="admin-filter"><span>Estado</span><select data-admin-filter-key="status">
        <option value="all" ${filter.status === 'all' ? 'selected' : ''}>Todos</option>
        <option value="active" ${filter.status === 'active' ? 'selected' : ''}>Activos</option>
        <option value="inactive" ${filter.status === 'inactive' ? 'selected' : ''}>De baja</option>
      </select></label>`;
  }
  const group = byId('adminFilters');
  group.dataset.columns = tab === 'users' ? '2' : '1';
  group.innerHTML = controls;
  group.querySelectorAll('.topic-aware-select').forEach(syncTopicSelectStyle);
}

function filteredAdminItems() {
  const tab = state.admin.tab;
  const filter = state.admin.filters[tab];
  const term = filter.search.trim().toLocaleLowerCase('es');
  let items = [...(state.admin.data[tab] || [])];

  if (term) {
    items = items.filter(item => {
      if (tab === 'topics') return `${item.number} ${item.name}`.toLocaleLowerCase('es').includes(term);
      if (tab === 'questions') return `${item.text} ${item.topic.number} ${item.topic.name}`.toLocaleLowerCase('es').includes(term);
      return `${item.display_name} ${item.username}`.toLocaleLowerCase('es').includes(term);
    });
  }

  if (tab === 'topics') {
    if (filter.content === 'with') items = items.filter(item => item.question_count > 0);
    if (filter.content === 'empty') items = items.filter(item => item.question_count === 0);
  } else if (tab === 'questions') {
    if (filter.topic !== 'all') items = items.filter(item => String(item.topic_id ?? item.topic?.id) === String(filter.topic));
  } else {
    if (filter.role !== 'all') items = items.filter(item => item.role === filter.role);
    if (filter.status === 'active') items = items.filter(item => item.is_active);
    if (filter.status === 'inactive') items = items.filter(item => !item.is_active);
  }

  const direction = filter.direction === 'desc' ? -1 : 1;
  const textCompare = (a, b) => String(a ?? '').localeCompare(String(b ?? ''), 'es', { sensitivity: 'base', numeric: true });
  items.sort((a, b) => {
    let result = 0;
    if (tab === 'topics') {
      if (filter.sort === 'name') result = textCompare(a.name, b.name);
      else if (filter.sort === 'questions') result = Number(a.question_count) - Number(b.question_count);
      else if (filter.sort === 'created') result = timestampValue(a.created_at) - timestampValue(b.created_at);
      else result = textCompare(a.number, b.number);
      if (!result) result = textCompare(a.number, b.number);
    } else if (tab === 'questions') {
      if (filter.sort === 'text') result = textCompare(a.text, b.text);
      else if (filter.sort === 'options') result = Number(a.options.length) - Number(b.options.length);
      else if (filter.sort === 'accuracy') result = Number(a.accuracy) - Number(b.accuracy);
      else if (filter.sort === 'created') result = timestampValue(a.created_at) - timestampValue(b.created_at);
      else result = textCompare(a.topic.number, b.topic.number) || Number(a.id) - Number(b.id);
      if (!result) result = Number(a.id) - Number(b.id);
    } else {
      if (filter.sort === 'role') result = textCompare(a.role, b.role);
      else if (filter.sort === 'activity') result = Number(a.attempt_count) - Number(b.attempt_count);
      else if (filter.sort === 'accuracy') result = Number(a.accuracy) - Number(b.accuracy);
      else if (filter.sort === 'created') result = timestampValue(a.created_at) - timestampValue(b.created_at);
      else if (filter.sort === 'deactivated') result = timestampValue(a.deactivated_at) - timestampValue(b.deactivated_at);
      else result = textCompare(a.display_name, b.display_name) || textCompare(a.username, b.username);
      if (!result) result = Number(a.id) - Number(b.id);
    }
    return result * direction;
  });
  return items;
}

function adminSortHeader(label, key) {
  const filter = state.admin.filters[state.admin.tab];
  const active = filter.sort === key;
  const currentDirection = active ? filter.direction : '';
  const nextDirection = active && filter.direction === 'asc' ? 'desc' : 'asc';
  return `<button class="admin-sort-button${active ? ' active' : ''}" type="button" data-admin-sort="${key}" aria-label="Ordenar ${escapeHtml(label)} ${nextDirection === 'asc' ? 'ascendente' : 'descendente'}">
    <span>${escapeHtml(label)}</span>
    <span class="admin-sort-arrows" aria-hidden="true"><span class="${currentDirection === 'asc' ? 'active' : ''}">↑</span><span class="${currentDirection === 'desc' ? 'active' : ''}">↓</span></span>
  </button>`;
}

function updateAdminCount(items) {
  const meta = ADMIN_META[state.admin.tab];
  const noun = items.length === 1 ? meta.singular : meta.plural.toLocaleLowerCase('es');
  byId('adminResultCount').textContent = `${formatNumber(items.length)} ${noun}`;
  byId('adminExportBtn').disabled = items.length === 0;
}

function renderAdmin() {
  const tab = state.admin.tab;
  const allItems = state.admin.data[tab] || [];
  const items = filteredAdminItems();
  updateAdminCount(items);

  if (!items.length) {
    byId('adminList').innerHTML = '<div class="admin-empty">No hay resultados con estos filtros.</div>';
    return;
  }

  if (tab === 'topics') {
    byId('adminList').innerHTML = `<div class="admin-table-wrap"><table class="admin-table admin-table-topics">
      <thead><tr><th class="admin-number-col">${adminSortHeader('Nº', 'number')}</th><th>${adminSortHeader('Tema', 'name')}</th><th>${adminSortHeader('Preguntas', 'questions')}</th><th>${adminSortHeader('Creación', 'created')}</th><th class="admin-actions-col">Acciones</th></tr></thead>
      <tbody>${items.map(item => `<tr>
        <td data-label="Nº"><span class="admin-topic-number" style="--admin-color:${safeColor(item.color)}">${escapeHtml(item.number)}</span></td>
        <td data-label="Tema"><span class="admin-cell-title">${escapeHtml(item.name)}</span></td>
        <td data-label="Preguntas"><span class="admin-count-badge">${formatNumber(item.question_count)}</span></td>
        <td data-label="Creación"><span class="admin-date">${formatAdminDate(item.created_at)}</span></td>
        <td data-label="Acciones">${adminActions('topics', item)}</td>
      </tr>`).join('')}</tbody></table></div>`;
    return;
  }

  if (tab === 'questions') {
    byId('adminList').innerHTML = `<div class="admin-table-wrap"><table class="admin-table admin-table-questions">
      <thead><tr><th>${adminSortHeader('Pregunta', 'text')}</th><th>${adminSortHeader('Tema', 'topic')}</th><th>${adminSortHeader('Respuestas', 'options')}</th><th>${adminSortHeader('% acierto', 'accuracy')}</th><th>${adminSortHeader('Creación', 'created')}</th><th class="admin-actions-col">Acciones</th></tr></thead>
      <tbody>${items.map(item => `<tr>
        <td data-label="Pregunta"><span class="admin-question-text">${escapeHtml(item.text)}</span></td>
        <td data-label="Tema"><span class="admin-topic-label"><span class="admin-topic-dot" style="background:${safeColor(item.topic.color)}"></span>${escapeHtml(item.topic.number)} - ${escapeHtml(item.topic.name)}</span></td>
        <td data-label="Respuestas"><span class="admin-count-badge">${item.options.length}</span></td>
        <td data-label="% acierto"><span class="admin-accuracy">${item.answered_count ? formatDecimal(item.accuracy) + ' %' : '—'}</span></td>
        <td data-label="Creación"><span class="admin-date">${formatAdminDate(item.created_at)}</span></td>
        <td data-label="Acciones">${adminActions('questions', item)}</td>
      </tr>`).join('')}</tbody></table></div>`;
    return;
  }

  byId('adminList').innerHTML = `<div class="admin-table-wrap"><table class="admin-table admin-table-users">
    <thead><tr><th>${adminSortHeader('Usuario', 'name')}</th><th>${adminSortHeader('Rol', 'role')}</th><th>${adminSortHeader('Actividad', 'activity')}</th><th>${adminSortHeader('% acierto', 'accuracy')}</th><th>${adminSortHeader('Alta', 'created')}</th><th>${adminSortHeader('Baja', 'deactivated')}</th><th class="admin-actions-col">Acciones</th></tr></thead>
    <tbody>${items.map(item => `<tr class="${item.is_active ? '' : 'admin-row-inactive'}">
      <td data-label="Usuario"><div class="admin-cell-main"><div class="admin-user-identity${item.is_active ? '' : ' is-inactive'}"><div class="admin-user-avatar">${escapeHtml(item.display_name.slice(0, 1).toUpperCase())}</div><div><div class="admin-cell-title">${escapeHtml(item.display_name)}${item.is_self ? ' <span class="self-label">Tú</span>' : ''}</div><div class="admin-row-meta">@${escapeHtml(item.username)}</div></div></div><span class="user-state-badge ${item.is_active ? 'active' : 'inactive'}">${item.is_active ? 'Activo' : 'De baja'}</span></div></td>
      <td data-label="Rol"><span class="role-badge ${item.role === 'admin' ? 'admin' : ''}">${item.role === 'admin' ? 'Admin' : 'Usuario'}</span></td>
      <td data-label="Actividad"><span class="admin-activity-value">${formatNumber(item.attempt_count)} respuestas</span></td>
      <td data-label="% acierto"><span class="admin-accuracy">${item.attempt_count ? formatDecimal(item.accuracy) + ' %' : '—'}</span></td>
      <td data-label="Alta"><span class="admin-date">${formatAdminDate(item.created_at)}</span></td>
      <td data-label="Baja"><span class="admin-date">${formatAdminDate(item.deactivated_at)}</span></td>
      <td data-label="Acciones">${adminActions('users', item)}</td>
    </tr>`).join('')}</tbody></table></div>`;
}

function csvCell(value) {
  let text = String(value ?? '');
  if (/^[\t\r\n ]*[=+\-@]/.test(text)) text = `'${text}`;
  text = text.replace(/"/g, '""');
  return `"${text}"`;
}

function exportAdminCsv() {
  const tab = state.admin.tab;
  const items = filteredAdminItems();
  if (!items.length) return showToast('No hay datos que exportar.');

  let rows = [];
  if (tab === 'topics') {
    rows = [
      ['Número', 'Tema', 'Color', 'Preguntas', 'Fecha de creación'],
      ...items.map(item => [item.number, item.name, item.color, item.question_count, formatAdminDate(item.created_at)])
    ];
  } else if (tab === 'questions') {
    rows = [
      ['ID', 'Pregunta', 'Número de tema', 'Tema', 'Respuestas', 'Respuesta correcta', 'Respuestas incorrectas', 'Porcentaje de acierto', 'Fecha de creación'],
      ...items.map(item => [
        item.id, item.text, item.topic.number, item.topic.name, item.options.length,
        item.options.find(option => option.is_correct)?.text || '',
        item.options.filter(option => !option.is_correct).map(option => option.text).join(' | '),
        item.answered_count ? formatDecimal(item.accuracy) + ' %' : '',
        formatAdminDate(item.created_at)
      ])
    ];
  } else {
    rows = [
      ['ID', 'Nombre', 'Usuario', 'Rol', 'Estado', 'Respuestas', 'Porcentaje de acierto', 'Fecha de alta', 'Fecha de baja'],
      ...items.map(item => [
        item.id, item.display_name, item.username, item.role, item.is_active ? 'Activo' : 'De baja',
        item.attempt_count, item.attempt_count ? formatDecimal(item.accuracy) + ' %' : '',
        formatAdminDate(item.created_at), formatAdminDate(item.deactivated_at)
      ])
    ];
  }

  const csv = '\uFEFF' + rows.map(row => row.map(csvCell).join(';')).join('\r\n');
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${ADMIN_META[tab].plural.toLocaleLowerCase('es')}-${localDateKey()}.csv`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  showToast(`CSV de ${ADMIN_META[tab].plural.toLocaleLowerCase('es')} exportado.`);
}


function topicFormHtml(item = null) {
  const color = item?.color ? safeColor(item.color) : randomTopicColor();
  return `
    <div class="admin-form-grid two">
      <label class="field"><span>Número</span><input id="adminTopicNumber" type="text" maxlength="32" value="${escapeHtml(item?.number || '')}" required autocomplete="off"></label>
      <label class="field"><span>Color</span><input id="adminTopicColor" class="color-input" type="color" value="${color}" required></label>
      <label class="field full"><span>Nombre</span><input id="adminTopicName" maxlength="160" value="${escapeHtml(item?.name || '')}" required></label>
      <div class="field full admin-attachments-field">
        <span>Archivos adjuntos</span>
        <div class="attachment-drop-zone" id="adminAttachmentDropZone" role="button" tabindex="0" aria-label="Añadir archivos adjuntos">
          <input class="sr-only" id="adminAttachmentInput" type="file" multiple tabindex="-1">
          <span class="attachment-drop-icon">${UPLOAD_ICON}</span>
          <span class="attachment-drop-title">Arrastra archivos aquí</span>
          <small>o haz clic para seleccionarlos · máximo 100 MB por archivo · 12 archivos y 200 MB por tema</small>
        </div>
        <div class="admin-attachment-list" id="adminAttachmentList"></div>
      </div>
    </div>`;
}

function optionRowHtml(option = {}, kind = 'incorrect', required = false) {
  const isCorrect = kind === 'correct';
  const optionId = option?.id ? ` data-option-id="${Number(option.id)}"` : '';
  return `
    <div class="admin-option-row ${isCorrect ? 'admin-option-correct' : 'admin-option-incorrect'}" data-option-kind="${kind}"${optionId}>
      <span class="admin-option-role ${isCorrect ? 'correct' : 'incorrect'}">${isCorrect ? 'Correcta' : 'Incorrecta'}</span>
      <input class="admin-option-text" maxlength="1000" value="${escapeHtml(option.text || '')}" placeholder="${isCorrect ? 'Escribe la respuesta correcta' : 'Escribe una respuesta incorrecta'}" ${required ? 'required' : ''}>
      ${isCorrect ? '<span class="option-remove-spacer" aria-hidden="true"></span>' : '<button class="option-remove" type="button" data-remove-admin-option aria-label="Eliminar respuesta incorrecta">×</button>'}
    </div>`;
}

function questionFormHtml(item = null, topics = []) {
  const sourceOptions = item?.options?.length ? [...item.options] : [];
  const correct = sourceOptions.find(option => option.is_correct) || { text: '', is_correct: true };
  const incorrect = sourceOptions.filter(option => !option.is_correct);
  if (!incorrect.length) incorrect.push({ text: '', is_correct: false });
  return `
    <div class="admin-form-grid">
      <label class="field"><span>Tema</span><span class="topic-select-control"><span class="topic-select-dot" aria-hidden="true"></span><select class="select admin-select topic-aware-select" id="adminQuestionTopic" required>${topics.map(topic => topicOptionHtml(topic, Number(topic.id) === Number(item?.topic_id || topics[0]?.id))).join('')}</select></span></label>
      <label class="field"><span>Pregunta</span><textarea id="adminQuestionText" maxlength="2000" rows="4" required>${escapeHtml(item?.text || '')}</textarea></label>
      <div class="field admin-options-block">
        <span>Respuestas</span>
        <div class="admin-options-editor" id="adminOptionsEditor">
          ${optionRowHtml(correct, 'correct', true)}
          ${incorrect.map((option, index) => optionRowHtml(option, 'incorrect', index === 0)).join('')}
        </div>
      </div>
      <label class="field"><span>Explicación <small class="field-optional">opcional</small></span><textarea id="adminQuestionExplanation" maxlength="4000" rows="4" placeholder="Explicación de la respuesta">${escapeHtml(item?.explanation || '')}</textarea></label>
    </div>`;
}

function userFormHtml(item = null, topics = []) {
  const isAdmin = item?.role === 'admin';
  return `
    <div class="admin-form-grid two user-form-grid">
      <label class="field full"><span>Nombre</span><input id="adminUserDisplayName" maxlength="100" value="${escapeHtml(item?.display_name || '')}" required></label>
      <label class="field full"><span>Usuario</span>
        <div class="username-control">
          <input id="adminUsername" maxlength="50" value="${escapeHtml(item?.username || '')}" required autocomplete="off">
          <span class="username-status" id="adminUsernameStatus" aria-live="polite"></span>
        </div>
      </label>
      <label class="field"><span>Rol</span><select class="select admin-select" id="adminUserRole" required><option value="user" ${!isAdmin ? 'selected' : ''}>Usuario</option><option value="admin" ${isAdmin ? 'selected' : ''}>Administrador</option></select></label>
      <label class="field"><span>${item ? 'Nueva contraseña' : 'Contraseña'}</span>
        <input id="adminUserPassword" type="password" minlength="8" pattern="(?=.*[A-ZÁÉÍÓÚÜÑ])(?=.*[0-9]).{8,}" title="Mínimo 8 caracteres, una mayúscula y un número" ${item ? 'placeholder="Dejar en blanco para mantenerla"' : 'required'} autocomplete="new-password">
        <small class="field-hint password-requirement" id="adminPasswordRequirement" hidden>Mínimo 8 caracteres, una mayúscula y un número.</small>
      </label>
      <div class="field full admin-user-topics-field" id="adminUserTopicsField" ${isAdmin ? 'hidden' : ''}>
        <div class="admin-field-heading admin-user-topics-head">
          <span>Temas disponibles</span>
          <div class="exam-topic-actions">
            <button class="exam-topic-bulk-btn" type="button" data-admin-user-topics-all>Seleccionar todos</button>
            <button class="exam-topic-bulk-btn" type="button" data-admin-user-topics-none>Deseleccionar todos</button>
          </div>
        </div>
        <div class="exam-topic-picker admin-user-topic-picker" id="adminUserTopicPicker">
          ${topicPickerOptionsHtml(topics, state.admin.editing?.topicIds || [], 'data-admin-user-topic')}
        </div>
      </div>
    </div>`;
}

function attachmentProgressHtml(upload) {
  const total = Math.max(1, Number(upload.total) || 1);
  const loaded = Math.max(0, Math.min(total, Number(upload.loaded) || 0));
  const percent = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
  return `<div class="attachment-upload-progress" aria-label="Subiendo ${percent}%" title="${percent}%">
    <svg viewBox="0 0 40 40" aria-hidden="true">
      <circle class="attachment-progress-track" cx="20" cy="20" r="16" pathLength="100"></circle>
      <circle class="attachment-progress-value" cx="20" cy="20" r="16" pathLength="100" stroke-dasharray="${percent} ${100 - percent}"></circle>
    </svg>
    <span>${percent}%</span>
  </div>`;
}

function attachmentActionsHtml(file, options = {}) {
  const downloadUrl = file?.download_url || '';
  const deleteAttr = options.draft
    ? `data-delete-draft-attachment="${Number(options.clientId)}"`
    : `data-delete-existing-attachment="${Number(file.id)}"`;
  return `<div class="attachment-actions admin-attachment-actions">
    <a class="attachment-icon-action attachment-download-action" href="${escapeHtml(downloadUrl)}" aria-label="Descargar ${escapeHtml(file.name)}" title="Descargar">${DOWNLOAD_ICON}</a>
    <button class="admin-action danger attachment-delete-text" type="button" ${deleteAttr} aria-label="Eliminar ${escapeHtml(file.name)}">Eliminar</button>
  </div>`;
}

function renderAdminTopicAttachments() {
  const editing = state.admin.editing;
  const list = byId('adminAttachmentList');
  if (!list || editing?.type !== 'topics') return;
  const existing = editing.existingAttachments || [];
  const uploads = editing.uploads || [];
  const rows = [
    ...existing.map(file => `
      <div class="topic-attachment-row admin-attachment-row">
        ${fileTypeIcon(file.name, file.mime_type)}
        <div class="topic-attachment-main"><span class="topic-attachment-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span><small>${formatFileSize(file.size_bytes)}</small></div>
        ${attachmentActionsHtml(file)}
      </div>`),
    ...uploads.map(upload => {
      if (upload.status === 'uploading') return `
        <div class="topic-attachment-row admin-attachment-row is-uploading" data-upload-client-id="${upload.clientId}">
          ${fileTypeIcon(upload.file.name, upload.file.type)}
          <div class="topic-attachment-main"><span class="topic-attachment-name" title="${escapeHtml(upload.file.name)}">${escapeHtml(upload.file.name)}</span><small class="attachment-upload-bytes">${formatFileSize(upload.loaded)} / ${formatFileSize(upload.total)}</small></div>
          <div class="attachment-actions">
            ${attachmentProgressHtml(upload)}
            <button class="admin-action danger attachment-cancel-text" type="button" data-cancel-attachment-upload="${upload.clientId}" aria-label="Cancelar subida de ${escapeHtml(upload.file.name)}">Cancelar</button>
          </div>
        </div>`;
      const file = upload.draft;
      if (!file) return '';
      return `
        <div class="topic-attachment-row admin-attachment-row is-draft" data-upload-client-id="${upload.clientId}">
          ${fileTypeIcon(file.name, file.mime_type)}
          <div class="topic-attachment-main"><span class="topic-attachment-name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span><small>${formatFileSize(file.size_bytes)}</small></div>
          ${attachmentActionsHtml(file, { draft: true, clientId: upload.clientId })}
        </div>`;
    })
  ].filter(Boolean);
  list.innerHTML = rows.length ? rows.join('') : '<div class="attachment-empty">No hay archivos adjuntos.</div>';
}

function updateTopicUploadProgress(upload) {
  const row = document.querySelector(`[data-upload-client-id="${upload.clientId}"]`);
  if (!row) return;
  const total = Math.max(1, Number(upload.total) || 1);
  const loaded = Math.max(0, Math.min(total, Number(upload.loaded) || 0));
  const percent = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
  const bytes = row.querySelector('.attachment-upload-bytes');
  if (bytes) bytes.textContent = `${formatFileSize(loaded)} / ${formatFileSize(total)}`;
  const progress = row.querySelector('.attachment-upload-progress');
  const circle = progress?.querySelector('.attachment-progress-value');
  const label = progress?.querySelector('span');
  if (circle) circle.setAttribute('stroke-dasharray', `${percent} ${100 - percent}`);
  if (label) label.textContent = `${percent}%`;
  if (progress) {
    progress.setAttribute('aria-label', `Subiendo ${percent}%`);
    progress.title = `${percent}%`;
  }
}

function removeTopicUpload(editing, upload) {
  if (!editing?.uploads) return;
  editing.uploads = editing.uploads.filter(item => item !== upload);
  if (state.admin.editing === editing) {
    renderAdminTopicAttachments();
    updateAdminSaveState();
  }
}

function startTopicFileUpload(file) {
  const editing = state.admin.editing;
  if (editing?.type !== 'topics') return;
  const uploads = editing.uploads || (editing.uploads = []);
  const key = `${file.name}::${file.size}::${file.lastModified}`;
  if (uploads.some(item => item.key === key && item.status !== 'cancelled')) return;
  const existing = editing.existingAttachments || [];
  if (existing.length + uploads.length >= MAX_ATTACHMENTS_PER_TOPIC) {
    showToast(`Puedes guardar como máximo ${MAX_ATTACHMENTS_PER_TOPIC} archivos por tema.`);
    return;
  }
  const currentBytes = [...existing, ...uploads].reduce(
    (total, item) => total + Number(item.size_bytes ?? item.total ?? item.file?.size ?? 0),
    0
  );
  if (currentBytes + Number(file.size || 0) > MAX_TOPIC_ATTACHMENTS_BYTES) {
    showToast('Los archivos adjuntos de un tema no pueden superar 200 MB en total.');
    return;
  }

  const upload = {
    clientId: ++attachmentUploadSeq,
    key,
    file,
    status: 'uploading',
    loaded: 0,
    total: Number(file.size) || 0,
    xhr: null,
    draft: null
  };
  uploads.push(upload);
  renderAdminTopicAttachments();
  updateAdminSaveState();

  const xhr = new XMLHttpRequest();
  upload.xhr = xhr;
  const formData = new FormData();
  formData.append('file', file, file.name);

  xhr.upload.addEventListener('progress', event => {
    if (upload.status !== 'uploading') return;
    upload.loaded = Math.min(upload.total, Number(event.loaded) || 0);
    updateTopicUploadProgress(upload);
  });
  xhr.addEventListener('load', () => {
    if (upload.status !== 'uploading') return;
    let payload = null;
    try { payload = JSON.parse(xhr.responseText || 'null'); } catch { /* invalid JSON */ }
    if (xhr.status >= 200 && xhr.status < 300 && payload?.ok && payload.data) {
      upload.status = 'done';
      upload.loaded = upload.total;
      upload.draft = payload.data;
      upload.xhr = null;
      if (state.admin.editing === editing) {
        renderAdminTopicAttachments();
        updateAdminSaveState();
      }
      return;
    }
    if (xhr.status === 401) showLogin();
    const message = payload?.error || 'No se ha podido subir el archivo.';
    removeTopicUpload(editing, upload);
    showToast(message);
  });
  xhr.addEventListener('error', () => {
    if (upload.status !== 'uploading') return;
    removeTopicUpload(editing, upload);
    showToast(`No se ha podido subir «${file.name}».`);
  });
  xhr.addEventListener('abort', () => {
    upload.status = 'cancelled';
    removeTopicUpload(editing, upload);
  });

  xhr.open('POST', '/api/admin/topic-attachment-drafts', true);
  xhr.setRequestHeader('Accept', 'application/json');
  if (state.csrf) xhr.setRequestHeader('X-CSRF-Token', state.csrf);
  xhr.send(formData);
}

function stageTopicFiles(fileList) {
  const editing = state.admin.editing;
  if (editing?.type !== 'topics') return;
  const incoming = [...(fileList || [])].filter(file => file && file.name);
  const existing = editing.existingAttachments || [];
  const uploads = editing.uploads || [];
  let available = Math.max(0, MAX_ATTACHMENTS_PER_TOPIC - existing.length - uploads.length);
  let totalBytes = [...existing, ...uploads].reduce(
    (total, item) => total + Number(item.size_bytes ?? item.total ?? item.file?.size ?? 0),
    0
  );
  for (const file of incoming) {
    if (file.size <= 0) { showToast(`«${file.name}» está vacío.`); continue; }
    if (file.size > MAX_ATTACHMENT_BYTES) { showToast(`«${file.name}» supera 100 MB.`); continue; }
    if (available <= 0) { showToast(`Puedes guardar como máximo ${MAX_ATTACHMENTS_PER_TOPIC} archivos por tema.`); break; }
    if (totalBytes + file.size > MAX_TOPIC_ATTACHMENTS_BYTES) {
      showToast('Los archivos adjuntos de un tema no pueden superar 200 MB en total.');
      continue;
    }
    const before = (editing.uploads || []).length;
    startTopicFileUpload(file);
    if ((editing.uploads || []).length > before) {
      available -= 1;
      totalBytes += file.size;
    }
  }
}

function cancelTopicUpload(clientId) {
  const editing = state.admin.editing;
  const upload = editing?.type === 'topics' ? (editing.uploads || []).find(item => Number(item.clientId) === Number(clientId)) : null;
  if (!upload || upload.status !== 'uploading') return;
  upload.xhr?.abort();
}

async function deleteDraftTopicAttachment(clientId) {
  const editing = state.admin.editing;
  const upload = editing?.type === 'topics' ? (editing.uploads || []).find(item => Number(item.clientId) === Number(clientId)) : null;
  if (!upload?.draft?.id || upload.status !== 'done') return;
  const originalIndex = (editing.uploads || []).indexOf(upload);
  editing.uploads = (editing.uploads || []).filter(item => item !== upload);
  editing.attachmentDeletePending = Number(editing.attachmentDeletePending || 0) + 1;
  renderAdminTopicAttachments();
  updateAdminSaveState();
  try {
    await api(`/api/admin/topic-attachment-drafts/${Number(upload.draft.id)}`, { method: 'DELETE' });
  } catch (error) {
    if (state.admin.editing === editing) {
      editing.uploads.splice(Math.max(0, originalIndex), 0, upload);
      renderAdminTopicAttachments();
    }
    if (error.status !== 401) showToast(error.message);
  } finally {
    editing.attachmentDeletePending = Math.max(0, Number(editing.attachmentDeletePending || 0) - 1);
    if (state.admin.editing === editing) updateAdminSaveState();
  }
}

async function deleteExistingTopicAttachment(attachmentId) {
  const editing = state.admin.editing;
  if (editing?.type !== 'topics' || !editing.id) return;
  const file = (editing.existingAttachments || []).find(item => Number(item.id) === Number(attachmentId));
  if (!file) return;
  try {
    await api(`/api/admin/topics/${Number(editing.id)}/attachments/${Number(attachmentId)}`, { method: 'DELETE' });
    editing.existingAttachments = (editing.existingAttachments || []).filter(item => Number(item.id) !== Number(attachmentId));
    const topic = (state.admin.data.topics || []).find(item => Number(item.id) === Number(editing.id));
    if (topic) topic.attachments = (topic.attachments || []).filter(item => Number(item.id) !== Number(attachmentId));
    state.home = null;
    renderAdminTopicAttachments();
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
}

function setupTopicAttachmentEditor() {
  const zone = byId('adminAttachmentDropZone');
  const input = byId('adminAttachmentInput');
  const field = zone?.closest('.admin-attachments-field');
  if (!zone || !input || !field) return;
  let dragDepth = 0;
  const openPicker = () => input.click();
  zone.addEventListener('click', openPicker);
  zone.addEventListener('keydown', event => {
    if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); openPicker(); }
  });
  input.addEventListener('change', () => {
    stageTopicFiles(input.files);
    input.value = '';
  });
  field.addEventListener('dragenter', event => {
    event.preventDefault();
    dragDepth += 1;
    field.classList.add('is-dragging');
    zone.classList.add('is-dragging');
  });
  field.addEventListener('dragover', event => {
    event.preventDefault();
    if (event.dataTransfer) event.dataTransfer.dropEffect = 'copy';
  });
  field.addEventListener('dragleave', event => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) {
      field.classList.remove('is-dragging');
      zone.classList.remove('is-dragging');
    }
  });
  field.addEventListener('drop', event => {
    event.preventDefault();
    event.stopPropagation();
    dragDepth = 0;
    field.classList.remove('is-dragging');
    zone.classList.remove('is-dragging');
    stageTopicFiles(event.dataTransfer?.files);
  });
}

function toggleAttachmentDisclosure(button) {
  const disclosure = button?.closest('.attachment-disclosure');
  const panel = disclosure?.querySelector('.attachment-disclosure-panel');
  if (!disclosure || !panel) return;
  const expanded = button.getAttribute('aria-expanded') === 'true';
  const willOpen = !expanded;

  if (willOpen && disclosure.classList.contains('topic-attachment-disclosure')) {
    document.querySelectorAll('.topic-attachment-disclosure').forEach(other => {
      if (other === disclosure) return;
      const otherButton = other.querySelector('.attachment-disclosure-toggle');
      const otherPanel = other.querySelector('.attachment-disclosure-panel');
      if (otherButton) otherButton.setAttribute('aria-expanded', 'false');
      if (otherPanel) otherPanel.hidden = true;
    });
  }

  button.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
  panel.hidden = !willOpen;
}

function renderAdminUserTopicPicker() {
  const editing = state.admin.editing;
  const picker = byId('adminUserTopicPicker');
  if (!picker || editing?.type !== 'users') return;
  picker.innerHTML = topicPickerOptionsHtml(state.admin.data.topics || [], editing.topicIds || [], 'data-admin-user-topic');
  updateAdminSaveState();
}

function updateAdminUserTopicsVisibility() {
  const role = byId('adminUserRole')?.value || 'user';
  const field = byId('adminUserTopicsField');
  if (field) field.hidden = role === 'admin';
  updateAdminSaveState();
}


function setUsernameStatus(text = '', mode = '') {
  const node = byId('adminUsernameStatus');
  if (!node) return;
  node.className = `username-status${mode ? ' ' + mode : ''}`;
  node.textContent = text;
  const input = byId('adminUsername');
  if (input) input.dataset.availability = mode === 'available' ? 'available' : mode === 'unavailable' ? 'unavailable' : mode === 'checking' ? 'checking' : '';
  updateAdminSaveState();
}

function setupUserFormAutomation(item = null) {
  const nameInput = byId('adminUserDisplayName');
  const usernameInput = byId('adminUsername');
  if (!nameInput || !usernameInput) return;
  let manual = Boolean(item);
  usernameInput.dataset.originalUsername = item?.username || '';
  usernameInput.dataset.availability = item ? 'available' : '';
  let timer = null;
  const formSeq = ++usernameSuggestionSeq;

  const checkManual = () => {
    clearTimeout(timer);
    const value = usernameInput.value.trim();
    if (!value) return setUsernameStatus('', '');
    setUsernameStatus('Comprobando', 'checking');
    timer = setTimeout(async () => {
      if (formSeq !== usernameSuggestionSeq) return;
      try {
        const params = new URLSearchParams({ username: value });
        if (item?.id) params.set('exclude_id', String(item.id));
        const result = await api(`/api/admin/users/username-check?${params}`);
        if (formSeq !== usernameSuggestionSeq || usernameInput.value.trim() !== value) return;
        setUsernameStatus(result.available ? 'Disponible' : 'Ya existe', result.available ? 'available' : 'unavailable');
      } catch (error) {
        if (formSeq === usernameSuggestionSeq) setUsernameStatus('No válido', 'unavailable');
      }
    }, 280);
  };

  usernameInput.addEventListener('input', () => {
    manual = true;
    checkManual();
  });
  usernameInput.addEventListener('focus', () => usernameInput.select());

  if (item) return;
  const suggest = () => {
    clearTimeout(timer);
    if (manual) return;
    const displayName = nameInput.value.trim();
    if (!displayName) {
      usernameInput.value = '';
      setUsernameStatus('', '');
      return;
    }
    setUsernameStatus('Comprobando', 'checking');
    timer = setTimeout(async () => {
      if (manual || formSeq !== usernameSuggestionSeq) return;
      try {
        const params = new URLSearchParams({ display_name: displayName });
        const result = await api(`/api/admin/users/username-suggestion?${params}`);
        if (manual || formSeq !== usernameSuggestionSeq || nameInput.value.trim() !== displayName) return;
        usernameInput.value = result.username;
        setUsernameStatus('Disponible', 'available');
      } catch (error) {
        if (formSeq === usernameSuggestionSeq) setUsernameStatus(error.message, 'unavailable');
      }
    }, 320);
  };
  nameInput.addEventListener('input', suggest);
}

function setupFormUx(root = document) {
  root.querySelectorAll?.('input[placeholder], textarea[placeholder]').forEach(control => {
    if (control.dataset.placeholderText === undefined) {
      control.dataset.placeholderText = control.getAttribute('placeholder') || '';
    }
  });
  updateRequiredMarkers(root);
}

function updateRequiredMarkers(root = document) {
  root.querySelectorAll?.('label.field, .admin-options-block.field').forEach(field => {
    // Login uses disabled-submit validation but intentionally no required asterisks.
    if (field.closest('#loginForm')) {
      field.classList.remove('required-empty');
      return;
    }
    const required = [...field.querySelectorAll('input[required], textarea[required], select[required]')];
    if (!required.length) {
      field.classList.remove('required-empty');
      return;
    }
    const missing = required.some(control => {
      if (control.type === 'checkbox' || control.type === 'radio') return !control.checked;
      return String(control.value ?? '').trim() === '';
    });
    field.classList.toggle('required-empty', missing);
  });
}


function passwordIsValid(value) {
  if (!value) return false;
  return value.length >= 8 && /[A-ZÁÉÍÓÚÜÑ]/u.test(value) && /\d/u.test(value);
}

function updatePasswordRequirement() {
  const input = byId('adminUserPassword');
  const hint = byId('adminPasswordRequirement');
  if (!input || !hint) return;
  const value = input.value || '';
  hint.hidden = !value || passwordIsValid(value);
}

function updateAdminSaveState() {
  const button = byId('adminSaveBtn');
  const editing = state.admin.editing;
  const form = byId('adminForm');
  if (!button || !editing || !form) return;
  updateRequiredMarkers(byId('adminEditorModal'));
  updatePasswordRequirement();

  let valid = form.checkValidity();
  if (editing.type === 'topics') {
    const uploading = (editing.uploads || []).some(upload => upload.status === 'uploading');
    valid = Boolean(valid && !uploading && !(editing.attachmentDeletePending > 0));
  }
  if (editing.type === 'questions') {
    const text = byId('adminQuestionText')?.value.trim() || '';
    const rows = [...document.querySelectorAll('#adminOptionsEditor .admin-option-row')];
    const filled = rows.filter(row => row.querySelector('.admin-option-text')?.value.trim());
    const correctFilled = rows[0]?.querySelector('.admin-option-text')?.value.trim();
    valid = Boolean(text && correctFilled && filled.length >= 2 && valid);
  } else if (editing.type === 'users') {
    const username = byId('adminUsername');
    const password = byId('adminUserPassword');
    const role = byId('adminUserRole')?.value || 'user';
    const topicField = byId('adminUserTopicsField');
    const topicsOk = role === 'admin' || (editing.topicIds || []).length > 0;
    topicField?.classList.toggle('required-empty', role !== 'admin' && !topicsOk);
    const isCreate = editing.id == null;
    const original = username?.dataset.originalUsername || '';
    const usernameUnchanged = !isCreate && username?.value.trim() === original;
    const availabilityOk = usernameUnchanged || username?.dataset.availability === 'available';
    const passwordOk = isCreate ? passwordIsValid(password?.value || '') : (!password?.value || passwordIsValid(password.value));
    valid = Boolean(valid && availabilityOk && passwordOk && topicsOk);
  }
  button.disabled = !valid;
}

async function openAdminEditor(type, id = null) {
  const items = state.admin.data[type] || [];
  const item = id == null ? null : items.find(entry => Number(entry.id) === Number(id));
  if (id != null && !item) return;
  byId('adminFormError').textContent = '';
  byId('adminModalEyebrow').textContent = item ? 'Editar' : 'Crear';
  byId('adminModalTitle').textContent = `${item ? 'Editar' : type === 'questions' ? 'Nueva' : 'Nuevo'} ${ADMIN_META[type].singular}`;

  try {
    if (type === 'topics') {
      state.admin.editing = {
        type, id: item?.id ?? null,
        existingAttachments: [...(item?.attachments || [])],
        uploads: [],
        attachmentDeletePending: 0,
        draftsClaimed: false
      };
      byId('adminFormFields').innerHTML = topicFormHtml(item);
      setupTopicAttachmentEditor();
      renderAdminTopicAttachments();
    }
    if (type === 'questions') {
      state.admin.editing = { type, id: item?.id ?? null };
      byId('adminFormFields').innerHTML = questionFormHtml(item, await ensureAdminTopics());
      normalizeAdminOptions();
      const topicSelect = byId('adminQuestionTopic');
      syncTopicSelectStyle(topicSelect);
      topicSelect?.addEventListener('change', () => syncTopicSelectStyle(topicSelect));
    }
    if (type === 'users') {
      const topics = await ensureAdminTopics();
      const defaultTopicIds = topics.map(topic => Number(topic.id));
      state.admin.editing = {
        type, id: item?.id ?? null,
        topicIds: item ? [...(item.role === 'admin' ? defaultTopicIds : (item.topic_ids || []))].map(Number) : defaultTopicIds
      };
      byId('adminFormFields').innerHTML = userFormHtml(item, topics);
      setupUserFormAutomation(item);
      byId('adminUserRole')?.addEventListener('change', updateAdminUserTopicsVisibility);
      updateAdminUserTopicsVisibility();
    }
  } catch (error) {
    state.admin.editing = null;
    showToast(error.message);
    return;
  }
  openModal('adminEditorModal');
  setupFormUx(byId('adminEditorModal'));
  updateAdminSaveState();
  setTimeout(() => byId('adminFormFields').querySelector('input:not([type="file"]), textarea, select')?.focus(), 0);
}

function normalizeAdminOptions() {
  const editor = byId('adminOptionsEditor');
  if (!editor) return;
  let rows = [...editor.querySelectorAll('.admin-option-row')];
  const correctRow = rows.find(row => row.dataset.optionKind === 'correct');
  if (correctRow && editor.firstElementChild !== correctRow) editor.prepend(correctRow);

  rows = [...editor.querySelectorAll('.admin-option-row')];
  const incorrectRows = rows.filter(row => row.dataset.optionKind === 'incorrect');
  if (!incorrectRows.length) {
    editor.insertAdjacentHTML('beforeend', optionRowHtml({}, 'incorrect', true));
    rows = [...editor.querySelectorAll('.admin-option-row')];
  }

  let incorrect = [...editor.querySelectorAll('.admin-option-row[data-option-kind="incorrect"]')];
  // Keep only one empty trailing row; it is the implicit “add another” control.
  while (incorrect.length > 1) {
    const last = incorrect.at(-1);
    const previous = incorrect.at(-2);
    if (last.querySelector('.admin-option-text').value.trim() || previous.querySelector('.admin-option-text').value.trim()) break;
    last.remove();
    incorrect = [...editor.querySelectorAll('.admin-option-row[data-option-kind="incorrect"]')];
  }

  const lastIncorrect = incorrect.at(-1);
  if (lastIncorrect?.querySelector('.admin-option-text').value.trim() && editor.querySelectorAll('.admin-option-row').length < 10) {
    editor.insertAdjacentHTML('beforeend', optionRowHtml({}, 'incorrect', false));
  }

  incorrect = [...editor.querySelectorAll('.admin-option-row[data-option-kind="incorrect"]')];
  incorrect.forEach((row, index) => {
    const input = row.querySelector('.admin-option-text');
    const isTrailingAutoRow = index === incorrect.length - 1 && !input.value.trim() && incorrect.length > 1;
    input.required = index === 0;
    row.classList.toggle('is-auto-row', isTrailingAutoRow);
    const remove = row.querySelector('[data-remove-admin-option]');
    if (remove) {
      remove.disabled = incorrect.length <= 1;
      remove.hidden = isTrailingAutoRow;
    }
    row.classList.toggle('required-empty', input.required && !input.value.trim());
  });
  const correctInput = editor.querySelector('.admin-option-row[data-option-kind="correct"] .admin-option-text');
  editor.querySelector('.admin-option-row[data-option-kind="correct"]')?.classList.toggle('required-empty', !correctInput?.value.trim());
  updateAdminSaveState();
}

function handleAdminOptionInput(input) {
  const editor = byId('adminOptionsEditor');
  if (!editor || !input?.classList.contains('admin-option-text')) return;
  normalizeAdminOptions();
}

function removeAdminOption(button) {
  const editor = byId('adminOptionsEditor');
  if (!editor) return;
  const row = button.closest('.admin-option-row');
  if (!row || row.dataset.optionKind !== 'incorrect') return;
  const incorrectRows = editor.querySelectorAll('.admin-option-row[data-option-kind="incorrect"]');
  if (incorrectRows.length <= 1) return;
  row.remove();
  normalizeAdminOptions();
}

function adminFormPayload(type) {
  if (type === 'topics') return {
    number: byId('adminTopicNumber').value.trim(),
    name: byId('adminTopicName').value.trim(),
    color: byId('adminTopicColor').value,
    attachment_draft_ids: (state.admin.editing?.uploads || [])
      .filter(upload => upload.status === 'done' && upload.draft?.id)
      .map(upload => Number(upload.draft.id))
  };
  if (type === 'questions') {
    const rows = [...document.querySelectorAll('#adminOptionsEditor .admin-option-row')];
    const options = rows.map((row, index) => ({
      id: row.dataset.optionId ? Number(row.dataset.optionId) : null,
      text: row.querySelector('.admin-option-text').value.trim(),
      is_correct: index === 0
    })).filter(option => option.text);
    return {
      topic_id: Number(byId('adminQuestionTopic').value),
      text: byId('adminQuestionText').value.trim(),
      explanation: byId('adminQuestionExplanation').value.trim(),
      options
    };
  }
  const role = byId('adminUserRole').value;
  return {
    display_name: byId('adminUserDisplayName').value.trim(),
    username: byId('adminUsername').value.trim(),
    role,
    password: byId('adminUserPassword').value,
    topic_ids: role === 'user' ? [...(state.admin.editing?.topicIds || [])] : []
  };
}

async function saveAdminForm(event) {
  event.preventDefault();
  const editing = state.admin.editing;
  if (!editing) return;
  const button = byId('adminSaveBtn');
  const errorNode = byId('adminFormError');
  const wasCreate = editing.id == null;
  const payload = adminFormPayload(editing.type);
  const selfEdited = editing.type === 'users' && Number(editing.id) === Number(state.user.id);
  const selfPasswordChanged = selfEdited && Boolean(payload.password);
  errorNode.textContent = '';
  button.disabled = true;
  try {
    const saved = await api(adminEndpoint(editing.type, editing.id), {
      method: wasCreate ? 'POST' : 'PUT',
      body: payload
    });

    if (editing.type === 'topics') {
      editing.id = Number(saved.id || editing.id);
      editing.draftsClaimed = true;
    }

    closeModal('adminEditorModal');
    invalidateAdmin(editing.type);
    if (editing.type === 'topics') {
      state.home = null;
      state.stats = null;
    }
    if (editing.type === 'users') state.stats = null;

    if (selfEdited) {
      state.user = {
        ...state.user,
        username: payload.username || state.user.username,
        display_name: payload.display_name || state.user.display_name,
        role: payload.role || state.user.role
      };
      updateRoleUI();
      if (state.user.role !== 'admin') return setView('home', true);
      if (selfPasswordChanged) {
        showToast('Contraseña cambiada. La sesión se cerrará en la próxima acción.');
        return;
      }
    }

    await loadAdmin(true);
    showToast(wasCreate ? 'Creado correctamente.' : 'Cambios guardados.');
  } catch (error) {
    errorNode.textContent = error.message;
  } finally {
    updateAdminSaveState();
  }
}

function requestAdminDelete(type, id, action = 'delete') {
  const item = (state.admin.data[type] || []).find(entry => Number(entry.id) === Number(id));
  if (!item) return;
  state.admin.deleting = { type, id: item.id, action };
  const label = type === 'topics' ? `${item.number} - ${item.name}` : type === 'questions' ? item.text : item.display_name;
  if (type === 'users' && action === 'deactivate') {
    byId('adminDeleteTitle').textContent = 'Dar de baja usuario';
    byId('adminDeleteText').textContent = `Se dará de baja a “${label}”. Su historial se conservará y podrá volver a darse de alta más adelante.`;
    byId('adminConfirmDeleteBtn').textContent = 'Dar de baja';
  } else if (type === 'users') {
    byId('adminDeleteTitle').textContent = 'Eliminar usuario definitivamente';
    byId('adminDeleteText').textContent = `Se eliminarán definitivamente “${label}”, sus sesiones, asignaciones e historial de respuestas. Esta acción no se puede deshacer.`;
    byId('adminConfirmDeleteBtn').textContent = 'Eliminar definitivamente';
  } else if (type === 'topics') {
    byId('adminDeleteTitle').textContent = 'Eliminar tema definitivamente';
    byId('adminDeleteText').textContent = `Se eliminará “${label}” junto con todas sus preguntas, respuestas/opciones, historial de respuestas de los alumnos y archivos adjuntos. Esta acción no se puede deshacer.`;
    byId('adminConfirmDeleteBtn').textContent = 'Eliminar definitivamente';
  } else {
    byId('adminDeleteTitle').textContent = 'Eliminar pregunta definitivamente';
    byId('adminDeleteText').textContent = `Se eliminará “${label}” junto con todas sus respuestas/opciones y todo el historial de respuestas asociado. Esta acción no se puede deshacer.`;
    byId('adminConfirmDeleteBtn').textContent = 'Eliminar definitivamente';
  }
  openModal('adminDeleteModal');
}

async function confirmAdminDelete() {
  const deleting = state.admin.deleting;
  if (!deleting) return;
  const button = byId('adminConfirmDeleteBtn');
  button.disabled = true;
  try {
    if (deleting.type === 'users' && deleting.action === 'deactivate') {
      await api(`/api/admin/users/${deleting.id}/deactivate`, { method: 'POST', body: {} });
    } else {
      await api(adminEndpoint(deleting.type, deleting.id), { method: 'DELETE', body: {} });
    }
    closeModal('adminDeleteModal');
    invalidateAdmin(deleting.type);
    const wasDeactivation = deleting.type === 'users' && deleting.action === 'deactivate';
    state.admin.deleting = null;
    await loadAdmin(true);
    showToast(wasDeactivation ? 'Usuario dado de baja correctamente.' : 'Eliminado correctamente.');
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
}

async function activateAdminUser(id) {
  try {
    await api(`/api/admin/users/${id}/activate`, { method: 'POST', body: {} });
    invalidateAdmin('users');
    await loadAdmin(true);
    showToast('Usuario dado de alta correctamente.');
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
  }
}

const MODAL_FADE_DISTANCE = 44;
const MODAL_FADE_EPSILON = 1;
let modalFadeFrame = 0;

function clampModalFade(value) {
  return Math.max(0, Math.min(1, value));
}

function updateModalScrollFades(shell) {
  if (!shell) return;
  const area = shell.querySelector('[data-scroll-fade-area]');
  if (!area) return;
  const maxScroll = Math.max(0, area.scrollHeight - area.clientHeight);
  const top = Math.max(0, area.scrollTop);
  const remaining = Math.max(0, maxScroll - top);
  const topOpacity = maxScroll <= MODAL_FADE_EPSILON ? 0 : clampModalFade(top / MODAL_FADE_DISTANCE);
  const bottomOpacity = maxScroll <= MODAL_FADE_EPSILON ? 0 : clampModalFade(remaining / MODAL_FADE_DISTANCE);
  shell.style.setProperty('--modal-top-fade', topOpacity.toFixed(3));
  shell.style.setProperty('--modal-bottom-fade', bottomOpacity.toFixed(3));
}

function refreshModalScrollFades() {
  document.querySelectorAll('[data-scroll-fade-shell]').forEach(updateModalScrollFades);
}

function requestModalFadeUpdate() {
  if (modalFadeFrame) return;
  modalFadeFrame = requestAnimationFrame(() => {
    modalFadeFrame = 0;
    refreshModalScrollFades();
  });
}

function setupModalScrollFades() {
  document.querySelectorAll('[data-scroll-fade-shell]').forEach(shell => {
    const area = shell.querySelector('[data-scroll-fade-area]');
    if (!area || area.dataset.scrollFadeReady === 'true') return;
    area.dataset.scrollFadeReady = 'true';
    area.addEventListener('scroll', requestModalFadeUpdate, { passive: true });
    if ('ResizeObserver' in window) {
      const resizeObserver = new ResizeObserver(requestModalFadeUpdate);
      resizeObserver.observe(area);
    }
    if ('MutationObserver' in window) {
      const mutationObserver = new MutationObserver(requestModalFadeUpdate);
      mutationObserver.observe(area, { childList: true, subtree: true, characterData: true });
    }
  });
  window.addEventListener('resize', requestModalFadeUpdate, { passive: true });
  requestModalFadeUpdate();
}

function resetModalScroll(modalBackdrop) {
  if (!modalBackdrop) return;
  modalBackdrop.scrollTop = 0;
  modalBackdrop.querySelectorAll('.modal, [data-scroll-fade-area]').forEach(scroller => {
    scroller.scrollTop = 0;
  });
  requestModalFadeUpdate();
}

function openModal(id) {
  const backdrop = byId(id);
  if (!backdrop) return;
  resetModalScroll(backdrop);
  backdrop.classList.add('open');
  requestAnimationFrame(() => {
    resetModalScroll(backdrop);
    requestModalFadeUpdate();
  });
}

function cleanupTopicEditorDrafts(editing) {
  if (editing?.type !== 'topics' || editing.draftsClaimed) return;
  for (const upload of editing.uploads || []) {
    if (upload.status === 'uploading') {
      try { upload.xhr?.abort(); } catch { /* already closed */ }
      continue;
    }
    if (upload.status === 'done' && upload.draft?.id) {
      api(`/api/admin/topic-attachment-drafts/${Number(upload.draft.id)}`, { method: 'DELETE' }).catch(() => {});
    }
  }
}

function closeModal(id) {
  const backdrop = byId(id);
  if (!backdrop) return;
  backdrop.classList.remove('open');
  resetModalScroll(backdrop);
  if (id === 'adminEditorModal') {
    usernameSuggestionSeq += 1;
    cleanupTopicEditorDrafts(state.admin.editing);
    state.admin.editing = null;
    byId('adminForm')?.reset();
    if (byId('adminFormFields')) byId('adminFormFields').innerHTML = '';
    if (byId('adminFormError')) byId('adminFormError').textContent = '';
  }
  if (id === 'adminDeleteModal') {
    state.admin.deleting = null;
  }
  if (id === 'examIntroModal') {
    state.pendingExam = { kind: 'exam', mode: 'multi', topicIds: [], questionCount: 30, countMode: 'preset', customQuestionCount: null };
    const countInput = byId('examQuestionCount');
    if (countInput) {
      countInput.blur();
      countInput.value = '';
      countInput.setAttribute('placeholder', countInput.dataset.placeholderText || 'Personalizado...');
      countInput.closest('.exam-count-input-wrap')?.classList.remove('active');
    }
    document.querySelectorAll('[data-exam-count]').forEach(button => button.classList.remove('active'));
    if (byId('examConfigError')) byId('examConfigError').textContent = '';
  }
}


function setupNavbarScroll() {
  const topbar = byId('topbar');
  let lastY = Math.max(0, window.scrollY);
  let downward = 0;
  let upward = 0;
  let ticking = false;
  let lastLayoutWidth = document.documentElement.clientWidth;
  let viewportResizeUntil = 0;

  const markVisualViewportResize = () => {
    // Mobile browser chrome changes the visual viewport height while scrolling.
    // Preserve the current navbar state during that transient resize.
    viewportResizeUntil = performance.now() + 220;
  };
  window.visualViewport?.addEventListener('resize', markVisualViewportResize, { passive: true });

  window.addEventListener('scroll', () => {
    if (ticking || byId('appShell').hidden) return;
    ticking = true;
    requestAnimationFrame(() => {
      const y = Math.max(0, window.scrollY);
      const delta = y - lastY;
      const mobile = document.documentElement.clientWidth <= 720;

      if (!mobile || y <= 8) {
        topbar.classList.remove('topbar-hidden');
        downward = 0;
        upward = 0;
      } else if (delta > 0.5) {
        downward += delta;
        upward = 0;
        if (y > 48 && downward >= 12) topbar.classList.add('topbar-hidden');
      } else if (delta < -0.5) {
        downward = 0;
        upward += Math.abs(delta);
        // Ignore tiny synthetic upward deltas caused by mobile browser chrome.
        if (performance.now() > viewportResizeUntil && upward >= 12) {
          topbar.classList.remove('topbar-hidden');
          upward = 0;
        }
      }
      lastY = y;
      ticking = false;
    });
  }, { passive: true });

  window.addEventListener('resize', () => {
    const layoutWidth = document.documentElement.clientWidth;
    const widthChanged = Math.abs(layoutWidth - lastLayoutWidth) > 2;
    if (widthChanged) {
      topbar.classList.remove('topbar-hidden');
      downward = 0;
      upward = 0;
      lastY = Math.max(0, window.scrollY);
      lastLayoutWidth = layoutWidth;
    }
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (state.currentView === 'stats') updateCharts();
      if (state.currentView === 'question' && state.session?.mode === 'exam') syncExamNavigatorStart();
    }, 120);
  });
}

function bindEvents() {
  byId('loginForm').addEventListener('submit', handleLogin);
  byId('loginUsername').addEventListener('input', updateLoginState);
  byId('loginUsername').addEventListener('change', updateLoginState);
  byId('loginPassword').addEventListener('input', updateLoginState);
  byId('loginPassword').addEventListener('change', updateLoginState);
  byId('loginPasswordToggle').addEventListener('click', toggleLoginPasswordVisibility);
  byId('logoutBtn').addEventListener('click', handleLogout);
  byId('adminCreateBtn').addEventListener('click', () => openAdminEditor(state.admin.tab));
  byId('adminForm').addEventListener('submit', saveAdminForm);
  byId('adminForm').addEventListener('input', updateAdminSaveState);
  byId('adminForm').addEventListener('change', updateAdminSaveState);
  byId('adminConfirmDeleteBtn').addEventListener('click', confirmAdminDelete);
  byId('themeToggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    safeStorageSet('opotest-theme', next);
  });
  byId('repeatCorrect').addEventListener('change', event => {
    updateQuestionModeLabel(event.target.checked);
    safeStorageSet('opotest-repeat-correct', String(event.target.checked));
    resetPracticePreload();
    void primePracticePreload();
    showToast(event.target.checked ? 'Se mostrarán todas las preguntas.' : 'Se ocultarán las preguntas ya acertadas.');
  });
  byId('playAllBtn').addEventListener('click', preparePractice);
  byId('startTopicExamBtn').addEventListener('click', () => prepareExam(null, 'multi'));
  byId('confirmExamBtn').addEventListener('click', startExam);
  byId('examSelectAllTopicsBtn').addEventListener('click', toggleAllExamTopics);
  byId('examDeselectAllTopicsBtn').addEventListener('click', deselectAllExamTopics);
  byId('reviewHomeBtn').addEventListener('click', async () => { state.examReview = null; await setView('home', true); });
  byId('reviewStatsBtn').addEventListener('click', async () => { state.examReview = null; await setView('stats', true); });
  const customCountInput = byId('examQuestionCount');
  const activateCustomCount = () => {
    if (state.pendingExam.kind !== 'exam') return;
    state.pendingExam.countMode = 'custom';
    const raw = customCountInput.value.trim();
    const value = raw === '' ? NaN : Number(raw);
    if (Number.isFinite(value) && value >= 1) {
      state.pendingExam.customQuestionCount = Math.max(1, Math.round(value));
      state.pendingExam.questionCount = state.pendingExam.customQuestionCount;
    } else {
      state.pendingExam.questionCount = 0;
    }
    updateExamConfig();
  };
  customCountInput.addEventListener('focus', activateCustomCount);
  customCountInput.addEventListener('click', activateCustomCount);
  customCountInput.addEventListener('input', () => {
    state.pendingExam.countMode = 'custom';
    const raw = customCountInput.value.trim();
    const value = raw === '' ? NaN : Number(raw);
    if (Number.isFinite(value) && value >= 1) {
      state.pendingExam.customQuestionCount = Math.max(1, Math.round(value));
      state.pendingExam.questionCount = state.pendingExam.customQuestionCount;
    } else {
      state.pendingExam.questionCount = 0;
    }
    updateExamConfig();
  });
  customCountInput.addEventListener('change', updateExamConfig);
  byId('adminSearch').addEventListener('input', event => {
    state.admin.filters[state.admin.tab].search = event.target.value;
    renderAdmin();
  });
  byId('adminFilters').addEventListener('change', event => {
    const key = event.target.dataset.adminFilterKey;
    if (!key) return;
    state.admin.filters[state.admin.tab][key] = event.target.value;
    if (event.target.classList.contains('topic-aware-select')) syncTopicSelectStyle(event.target);
    renderAdmin();
  });
  byId('adminExportBtn').addEventListener('click', exportAdminCsv);
  byId('statsUserSearch').addEventListener('input', event => {
    state.statsScope.search = event.target.value;
    renderStatsUserResults();
  });
  byId('exitQuestionBtn').addEventListener('click', exitQuestions);
  byId('nextQuestionBtn').addEventListener('click', nextQuestion);
  byId('progressTopicSelect').addEventListener('change', event => { syncTopicSelectStyle(event.target); updateCharts(); });
  byId('winrateTopicSelect').addEventListener('change', event => { syncTopicSelectStyle(event.target); updateCharts(); });

  document.addEventListener('focusin', event => {
    const control = event.target.closest?.('input[placeholder], textarea[placeholder]');
    if (!control) return;
    if (control.dataset.placeholderText === undefined) control.dataset.placeholderText = control.getAttribute('placeholder') || '';
    control.setAttribute('placeholder', '');
  });
  document.addEventListener('focusout', event => {
    const control = event.target.closest?.('input[placeholder], textarea[placeholder]');
    if (!control) return;
    if (!String(control.value ?? '').trim()) control.setAttribute('placeholder', control.dataset.placeholderText || '');
  });

  document.addEventListener('input', event => {
    if (event.target.classList.contains('admin-option-text')) handleAdminOptionInput(event.target);
    updateRequiredMarkers(event.target.closest?.('form') || document);
    if (event.target.id === 'adminUserPassword') updatePasswordRequirement();
  });
  document.addEventListener('change', event => {
    updateRequiredMarkers(event.target.closest?.('form') || document);
  });

  document.addEventListener('click', event => {
    const legalLink = event.target.closest('[data-legal-page]');
    if (legalLink) {
      showLegalPage(legalLink.dataset.legalPage, true);
      return;
    }
    if (event.target.closest('#legalBackBtn')) {
      leaveLegalPage();
      return;
    }
    const attachmentToggle = event.target.closest('[data-attachment-toggle]');
    if (attachmentToggle) {
      toggleAttachmentDisclosure(attachmentToggle);
      return;
    }
    const nav = event.target.closest('[data-nav]');
    if (nav) {
      event.preventDefault();
      setView(nav.dataset.nav, true);
      return;
    }
    const statsScope = event.target.closest('[data-stats-scope]');
    if (statsScope) {
      setStatsScope(statsScope.dataset.statsScope);
      return;
    }
    const statsUser = event.target.closest('[data-stats-user-id]');
    if (statsUser) {
      selectStatsUser(Number(statsUser.dataset.statsUserId));
      return;
    }
    const statsChangeUser = event.target.closest('[data-stats-change-user]');
    if (statsChangeUser) {
      changeStatsUser();
      return;
    }
    const adminTab = event.target.closest('[data-admin-tab]');
    if (adminTab) {
      setAdminTab(adminTab.dataset.adminTab);
      return;
    }
    const adminSort = event.target.closest('[data-admin-sort]');
    if (adminSort) {
      const filter = state.admin.filters[state.admin.tab];
      const key = adminSort.dataset.adminSort;
      if (filter.sort === key) filter.direction = filter.direction === 'asc' ? 'desc' : 'asc';
      else {
        filter.sort = key;
        filter.direction = 'asc';
      }
      renderAdmin();
      return;
    }
    const adminEdit = event.target.closest('[data-admin-edit]');
    if (adminEdit) {
      openAdminEditor(adminEdit.dataset.adminEdit, Number(adminEdit.dataset.adminId));
      return;
    }
    const adminDelete = event.target.closest('[data-admin-delete]');
    if (adminDelete && !adminDelete.disabled) {
      requestAdminDelete(adminDelete.dataset.adminDelete, Number(adminDelete.dataset.adminId));
      return;
    }
    const adminDeactivate = event.target.closest('[data-admin-deactivate-user]');
    if (adminDeactivate && !adminDeactivate.disabled) {
      requestAdminDelete('users', Number(adminDeactivate.dataset.adminDeactivateUser), 'deactivate');
      return;
    }
    const adminActivate = event.target.closest('[data-admin-activate-user]');
    if (adminActivate) {
      activateAdminUser(Number(adminActivate.dataset.adminActivateUser));
      return;
    }
    const removeOption = event.target.closest('[data-remove-admin-option]');
    if (removeOption) {
      removeAdminOption(removeOption);
      return;
    }
    const userTopic = event.target.closest('[data-admin-user-topic]');
    if (userTopic && state.admin.editing?.type === 'users') {
      const id = Number(userTopic.dataset.adminUserTopic);
      const selected = new Set((state.admin.editing.topicIds || []).map(Number));
      if (selected.has(id)) selected.delete(id); else selected.add(id);
      state.admin.editing.topicIds = [...selected];
      renderAdminUserTopicPicker();
      return;
    }
    if (event.target.closest('[data-admin-user-topics-all]') && state.admin.editing?.type === 'users') {
      state.admin.editing.topicIds = (state.admin.data.topics || []).map(topic => Number(topic.id));
      renderAdminUserTopicPicker();
      return;
    }
    if (event.target.closest('[data-admin-user-topics-none]') && state.admin.editing?.type === 'users') {
      state.admin.editing.topicIds = [];
      renderAdminUserTopicPicker();
      return;
    }
    const deleteExistingAttachment = event.target.closest('[data-delete-existing-attachment]');
    if (deleteExistingAttachment && state.admin.editing?.type === 'topics') {
      deleteExistingTopicAttachment(Number(deleteExistingAttachment.dataset.deleteExistingAttachment));
      return;
    }
    const cancelAttachmentUpload = event.target.closest('[data-cancel-attachment-upload]');
    if (cancelAttachmentUpload && state.admin.editing?.type === 'topics') {
      cancelTopicUpload(Number(cancelAttachmentUpload.dataset.cancelAttachmentUpload));
      return;
    }
    const deleteDraftAttachment = event.target.closest('[data-delete-draft-attachment]');
    if (deleteDraftAttachment && state.admin.editing?.type === 'topics') {
      deleteDraftTopicAttachment(Number(deleteDraftAttachment.dataset.deleteDraftAttachment));
      return;
    }
    const examCount = event.target.closest('[data-exam-count]');
    if (examCount && !examCount.disabled) {
      state.pendingExam.countMode = 'preset';
      state.pendingExam.questionCount = Number(examCount.dataset.examCount);
      updateExamConfig();
      return;
    }
    const examNav = event.target.closest('[data-exam-nav-index]');
    if (examNav) {
      navigateExamQuestion(Number(examNav.dataset.examNavIndex));
      return;
    }
    const reviewNav = event.target.closest('[data-review-nav-index]');
    if (reviewNav) {
      goToReviewQuestion(Number(reviewNav.dataset.reviewNavIndex));
      return;
    }
    const reviewToggle = event.target.closest('[data-review-toggle]');
    if (reviewToggle) {
      toggleReviewQuestion(Number(reviewToggle.dataset.reviewToggle));
      return;
    }
    const examTopic = event.target.closest('[data-exam-topic]');
    if (examTopic) {
      toggleExamTopic(Number(examTopic.dataset.examTopic));
      return;
    }
    const practice = event.target.closest('[data-topic-play]');
    if (practice) return startPractice(Number(practice.dataset.topicPlay));
    const exam = event.target.closest('[data-topic-exam]');
    if (exam) return prepareExam(Number(exam.dataset.topicExam));
    const answer = event.target.closest('.answer');
    if (answer) return selectAnswer(answer);
    const close = event.target.closest('[data-close-modal]');
    if (close) closeModal(close.dataset.closeModal);
  });

  document.addEventListener('dragover', event => {
    if (state.admin.editing?.type === 'topics' && [...(event.dataTransfer?.types || [])].includes('Files')) {
      event.preventDefault();
    }
  });
  document.addEventListener('drop', event => {
    if (state.admin.editing?.type === 'topics' && event.dataTransfer?.files?.length && !event.target.closest?.('#adminAttachmentDropZone')) {
      event.preventDefault();
    }
  });

  document.querySelectorAll('.modal-backdrop').forEach(backdrop => {
    backdrop.addEventListener('click', event => {
      if (event.target === backdrop && ['examIntroModal', 'adminEditorModal', 'adminDeleteModal'].includes(backdrop.id)) closeModal(backdrop.id);
    });
  });

  window.addEventListener('pageshow', () => {
    updateLoginState();
    document.querySelectorAll('.modal-backdrop').forEach(resetModalScroll);
  });

  window.addEventListener('popstate', () => {
    const legalKind = legalKindFromPath();
    if (legalKind) {
      showLegalPage(legalKind, false);
      return;
    }
    if (!state.user) {
      showLogin();
      return;
    }
    byId('legalShell').hidden = true;
    showApp();
    setView(viewFromPath(), false);
  });

  setupNavbarScroll();
}

async function init() {
  const savedTheme = safeStorageGet('opotest-theme');
  const prefersDark = window.matchMedia?.('(prefers-color-scheme: dark)').matches;
  applyTheme(savedTheme || (prefersDark ? 'dark' : 'light'));

  const savedRepeat = safeStorageGet('opotest-repeat-correct') === 'true';
  byId('repeatCorrect').checked = savedRepeat;
  updateQuestionModeLabel(savedRepeat);
  bindEvents();
  setupModalScrollFades();
  setupFormUx(document);
  updateLoginState();

  updateAppVersion();

  const initialLegal = legalKindFromPath();
  try {
    const data = await api('/api/me');
    state.user = data.user;
    state.csrf = data.csrf_token;
    if (initialLegal) {
      state.legalReturnPath = '/';
      showLegalPage(initialLegal, false);
    } else {
      showApp();
      await setView(viewFromPath(), false);
    }
  } catch (error) {
    if (error.status !== 401) showToast(error.message);
    if (initialLegal) {
      state.user = null;
      state.csrf = null;
      state.legalReturnPath = '/login';
      showLegalPage(initialLegal, false);
    } else {
      showLogin();
    }
  }
}

init();
