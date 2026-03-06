(function () {
  const tg = window.Telegram?.WebApp;
  if (!tg) {
    document.getElementById('loading').textContent = 'Откройте приложение через Telegram';
    return;
  }

  tg.ready();
  tg.expand();

  const API_BASE = (() => {
    const href = window.location.href;
    const base = href.replace(/\/miniapp\/?.*$/, '');
    return base + '/api/v1';
  })();

  let token = null;
  let me = null;

  function setToken(t) {
    token = t;
  }

  async function api(path, options = {}) {
    const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    };
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const res = await fetch(url, { ...options, headers });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.error || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function apiBlob(path) {
    const url = path.startsWith('http') ? path : `${API_BASE}${path}`;
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;
    const res = await fetch(url, { headers });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.blob();
  }

  async function auth() {
    const initData = tg.initData;
    if (!initData) {
      throw new Error('initData отсутствует');
    }
    const data = await api('/auth/telegram', {
      method: 'POST',
      body: JSON.stringify({ initData }),
    });
    setToken(data.token);
    return data;
  }

  function showScreen(id) {
    document.querySelectorAll('.screen').forEach((s) => s.classList.add('hidden'));
    const el = document.getElementById('screen-' + id);
    if (el) el.classList.remove('hidden');
  }

  function showHome() {
    showScreen('home');
  }

  async function loadMe() {
    me = await api('/me');
    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = me.first_name ? `, ${me.first_name}` : '';

    const statsEl = document.getElementById('stats');
    if (statsEl) {
      statsEl.textContent = `Воспоминаний: ${me.memories_count || 0}`;
    }

    const subEl = document.getElementById('sub-status');
    if (subEl) subEl.textContent = me.is_premium ? 'Активна' : 'Оформить';
  }

  document.querySelectorAll('[data-screen]').forEach((btn) => {
    btn.addEventListener('click', () => showScreen(btn.dataset.screen));
  });

  document.querySelectorAll('[data-back]').forEach((btn) => {
    btn.addEventListener('click', showHome);
  });

  // Hold-to-record voice (home + record screen)
  function setupRecordButton(btn, statusEl) {
    if (!btn) return;
    if (!window.MediaRecorder) {
      if (statusEl) statusEl.textContent = 'Запись недоступна';
      btn.disabled = true;
      return;
    }

    const defaultLabel = statusEl ? statusEl.textContent : 'Записать';
    let mediaRecorder = null;
    let chunks = [];

    async function uploadAudioBlob(blob) {
      const url = `${API_BASE}/memories/audio`;
      const formData = new FormData();
      const ext = blob.type.includes('webm') ? 'webm' : 'ogg';
      formData.append('audio', blob, `voice.${ext}`);
      const headers = {};
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const res = await fetch(url, { method: 'POST', headers, body: formData });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      return res.json();
    }

    function startRecord() {
      if (mediaRecorder && mediaRecorder.state === 'recording') return;
      navigator.mediaDevices.getUserMedia({ audio: true })
        .then((stream) => {
          const mime = MediaRecorder.isTypeSupported('audio/webm;codecs=opus') ? 'audio/webm;codecs=opus' : 'audio/webm';
          mediaRecorder = new MediaRecorder(stream);
          chunks = [];
          mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data); };
          mediaRecorder.onstop = async () => {
            stream.getTracks().forEach((t) => t.stop());
            if (chunks.length === 0) return;
            const blob = new Blob(chunks, { type: mime });
            try {
              await uploadAudioBlob(blob);
              tg.showAlert('Воспоминание сохранено');
              loadMe();
            } catch (e) {
              tg.showAlert(e.message || 'Ошибка');
            }
          };
          mediaRecorder.start();
          btn.classList.add('recording');
          statusEl.textContent = 'Идёт запись…';
        })
        .catch(() => tg.showAlert('Нет доступа к микрофону'));
    }

    function stopRecord() {
      if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
        btn.classList.remove('recording');
        if (statusEl) statusEl.textContent = defaultLabel;
      }
    }

    btn.addEventListener('mousedown', (e) => { e.preventDefault(); startRecord(); });
    btn.addEventListener('mouseup', stopRecord);
    btn.addEventListener('mouseleave', stopRecord);
    btn.addEventListener('touchstart', (e) => { e.preventDefault(); startRecord(); }, { passive: false });
    btn.addEventListener('touchend', (e) => { e.preventDefault(); stopRecord(); }, { passive: false });
    btn.addEventListener('touchcancel', stopRecord);
  }

  setupRecordButton(document.getElementById('btn-record-home'), document.getElementById('home-record-status'));
  setupRecordButton(document.getElementById('btn-record-voice'), document.getElementById('record-status'));

  document.getElementById('btn-save-memory')?.addEventListener('click', async () => {
    const textarea = document.getElementById('memory-text');
    const text = (textarea?.value || '').trim();
    if (!text) {
      tg.showAlert('Введите текст воспоминания');
      return;
    }
    try {
      tg.MainButton?.showProgress();
      await api('/memories/text', {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      textarea.value = '';
      tg.showAlert('Воспоминание сохранено');
      loadMe();
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    } finally {
      tg.MainButton?.hideProgress?.();
    }
  });

  document.getElementById('btn-add-chapter')?.addEventListener('click', async () => {
    const input = document.getElementById('new-chapter-title');
    const title = (input?.value || '').trim();
    if (!title) {
      tg.showAlert('Введите название главы');
      return;
    }
    try {
      await api('/chapters', {
        method: 'POST',
        body: JSON.stringify({ title }),
      });
      input.value = '';
      tg.showAlert('Глава добавлена');
      loadChapters();
      loadMe();
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  async function loadBook() {
    const container = document.getElementById('book-content');
    try {
      const data = await api('/book');
      if (!data.chapters?.length) {
        container.innerHTML = '<p class="empty-state">Пока нет глав. Добавьте воспоминания!</p>';
        return;
      }
      container.innerHTML = data.chapters
        .map(
          (ch) => `
        <div class="chapter-block">
          <div class="chapter-title">${escapeHtml(ch.title)}</div>
          ${(ch.memories || [])
            .map(
              (m) => `
            <div class="memory-block">
              <div class="memory-title">${escapeHtml(m.title || 'Без названия')}</div>
              <div class="memory-text">${escapeHtml(m.text || '').replace(/\n/g, '<br>')}</div>
            </div>
          `
            )
            .join('')}
        </div>
      `
        )
        .join('');
    } catch (e) {
      container.innerHTML = '<p class="empty-state">Ошибка загрузки</p>';
    }
  }

  let sortableChapters = null;

  async function loadChapters() {
    const container = document.getElementById('chapters-list');
    try {
      const data = await api('/chapters');
      if (!data.chapters?.length) {
        container.innerHTML = '<p class="empty-state">Нет глав. Добавьте первую!</p>';
        if (sortableChapters) {
          sortableChapters.destroy();
          sortableChapters = null;
        }
        return;
      }
      container.innerHTML = data.chapters
        .map(
          (ch) => `
        <div class="chapter-item" data-id="${ch.id}">
          <span class="chapter-item-title">${escapeHtml(ch.title)}</span>
          <span class="chapter-item-count">${ch.memories_count || 0} воспоминаний</span>
        </div>
      `
        )
        .join('');

      if (sortableChapters) sortableChapters.destroy();
      sortableChapters = new Sortable(container, {
        animation: 150,
        ghostClass: 'sortable-ghost',
        onEnd: async (evt) => {
          const items = container.querySelectorAll('.chapter-item');
          const chapterIds = [...items].map((el) => parseInt(el.dataset.id, 10));
          try {
            await api('/chapters/reorder', {
              method: 'POST',
              body: JSON.stringify({ chapter_ids: chapterIds }),
            });
            tg.showAlert('Порядок сохранён');
          } catch (e) {
            tg.showAlert(e.message || 'Ошибка');
            loadChapters();
          }
        },
      });
    } catch (e) {
      container.innerHTML = '<p class="empty-state">Ошибка загрузки</p>';
    }
  }

  async function loadSubscription() {
    const container = document.getElementById('sub-info');
    try {
      const data = await api('/subscription');
      container.innerHTML = `
        <p><strong>Статус:</strong> ${data.is_premium ? 'Премиум активна' : 'Бесплатный тариф'}</p>
        <p>Воспоминаний: ${data.memories_count} / ${data.free_memories_limit}</p>
        <p>Глав: до ${data.free_chapters_limit}</p>
        ${data.premium_until ? `<p>Премиум до: ${new Date(data.premium_until).toLocaleDateString('ru')}</p>` : ''}
      `;
    } catch (e) {
      container.innerHTML = '<p class="empty-state">Ошибка загрузки</p>';
    }
  }

  document.getElementById('btn-download-pdf')?.addEventListener('click', async () => {
    try {
      const blob = await apiBlob('/book/pdf');
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'memoir_book.pdf';
      a.click();
      URL.revokeObjectURL(url);
      tg.showAlert('PDF скачивается');
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка скачивания');
    }
  });

  document.getElementById('btn-redeem')?.addEventListener('click', async () => {
    const input = document.getElementById('promo-code');
    const code = (input?.value || '').trim();
    if (!code) {
      tg.showAlert('Введите промокод');
      return;
    }
    try {
      const data = await api('/subscription/promo', {
        method: 'POST',
        body: JSON.stringify({ code }),
      });
      input.value = '';
      tg.showAlert(data.message || 'Промокод активирован');
      loadSubscription();
      loadMe();
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  document.getElementById('screen-book')?.addEventListener('transitionend', () => {
    if (!document.getElementById('screen-book').classList.contains('hidden')) {
      loadBook();
    }
  });

  document.querySelector('[data-screen="book"]')?.addEventListener('click', loadBook);
  document.querySelector('[data-screen="chapters"]')?.addEventListener('click', loadChapters);
  document.querySelector('[data-screen="subscription"]')?.addEventListener('click', loadSubscription);

  function escapeHtml(s) {
    const div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
  }

  async function init() {
    const loadingEl = document.getElementById('loading');
    try {
      await auth();
      loadingEl.classList.add('hidden');
      document.getElementById('screens').classList.remove('hidden');
      await loadMe();
    } catch (e) {
      loadingEl.textContent = 'Ошибка: ' + (e.message || 'Не удалось войти');
      loadingEl.style.color = '#c00';
      loadingEl.style.padding = '16px';
      console.error('Mini App init error:', e);
    }
  }

  init();
})();
