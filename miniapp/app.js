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

    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 90000);
    try {
      const res = await fetch(url, { ...options, headers, signal: controller.signal });
      clearTimeout(timeout);
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${res.status}`);
      }
      return res.json();
    } catch (e) {
      clearTimeout(timeout);
      if (e.name === 'AbortError') throw new Error('Превышено время ожидания. Проверьте интернет.');
      if (e.message === 'Failed to fetch' || e.message === 'Load failed') {
        throw new Error('Ошибка сети. Проверьте интернет и попробуйте снова.');
      }
      throw e;
    }
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
    if (id === 'home' && me) {
      const w = document.getElementById('home-welcome');
      if (w) w.textContent = me.first_name ? `Добро пожаловать, ${me.first_name}` : 'Добро пожаловать';
    }
  }

  function showHome() {
    showScreen('home');
  }

  async function loadMe() {
    me = await api('/me');
    const welcomeEl = document.getElementById('home-welcome');
    if (welcomeEl) welcomeEl.textContent = me.first_name ? `Добро пожаловать, ${me.first_name}` : 'Добро пожаловать';

    const nameEl = document.getElementById('user-name');
    if (nameEl) nameEl.textContent = me.first_name ? `, ${me.first_name}` : '';

    const statsEl = document.getElementById('stats');
    if (statsEl) statsEl.textContent = `Воспоминаний: ${me.memories_count || 0}`;

    const subEl = document.getElementById('sub-status');
    if (subEl) subEl.textContent = me.is_premium ? 'Активна' : 'Оформить';
  }

  document.querySelectorAll('[data-screen]').forEach((btn) => {
    btn.addEventListener('click', () => {
      showScreen(btn.dataset.screen);
      document.getElementById('home-dropdown')?.classList.add('hidden');
    });
  });

  document.getElementById('btn-burger')?.addEventListener('click', (e) => {
    e.stopPropagation();
    const dd = document.getElementById('home-dropdown');
    dd?.classList.toggle('hidden');
  });
  document.addEventListener('click', () => {
    document.getElementById('home-dropdown')?.classList.add('hidden');
  });

  document.querySelectorAll('[data-back]').forEach((btn) => {
    btn.addEventListener('click', showHome);
  });

  let currentMemoryId = null;
  let currentPreviewData = null;

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
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 120000);
      try {
        const res = await fetch(url, { method: 'POST', headers, body: formData, signal: controller.signal });
        clearTimeout(timeout);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.error || `HTTP ${res.status}`);
        }
        return res.json();
      } catch (e) {
        clearTimeout(timeout);
        if (e.name === 'AbortError') throw new Error('Загрузка заняла слишком много времени. Проверьте интернет.');
        if (e.message === 'Failed to fetch' || e.message === 'Load failed') {
          throw new Error('Ошибка сети. Проверьте интернет.');
        }
        throw e;
      }
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
            if (chunks.length === 0) {
              btn.classList.remove('recording');
              if (statusEl) statusEl.textContent = defaultLabel;
              tg.showAlert('Запись слишком короткая. Удерживайте кнопку дольше.');
              return;
            }
            const blob = new Blob(chunks, { type: mime });
            try {
              const data = await uploadAudioBlob(blob);
              await runMemoryPipeline(data.memory_id);
            } catch (e) {
              tg.showAlert(e.message || 'Ошибка');
            }
          };
          mediaRecorder.start(250);
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
      tg.MainButton?.showProgress?.();
      const data = await api('/memories/text', {
        method: 'POST',
        body: JSON.stringify({ text }),
      });
      textarea.value = '';
      await runMemoryPipeline(data.memory_id);
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    } finally {
      tg.MainButton?.hideProgress?.();
    }
  });

  async function runMemoryPipeline(memoryId) {
    try {
      const result = await api(`/memories/${memoryId}/confirm-transcript`, { method: 'POST' });
      if (result.status === 'clarification') {
        currentMemoryId = memoryId;
        showClarification(result.question);
        return;
      }
      if (result.status === 'preview') {
        currentMemoryId = memoryId;
        await showPreview(result);
        return;
      }
      tg.showAlert('Воспоминание сохранено');
      loadMe();
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  }

  async function showPreview(data) {
    currentPreviewData = data;
    document.getElementById('preview-title').textContent = data.title || 'Воспоминание';
    let displayText = data.preview || '';
    if (data.memory_id) {
      try {
        const mem = await api(`/memories/${data.memory_id}`);
        displayText = mem.edited_memoir_text || mem.cleaned_transcript || mem.raw_transcript || displayText;
      } catch (_) {}
    }
    document.getElementById('preview-text').value = displayText;
    document.getElementById('preview-chapter-hint').textContent =
      data.chapter_suggestion ? `Предлагаемая глава: ${data.chapter_suggestion}` : '';
    showScreen('preview');
  }

  function showClarification(question) {
    document.getElementById('clarification-question').textContent = question;
    document.getElementById('clarification-answer').value = '';
    showScreen('clarification');
  }

  document.getElementById('btn-preview-back')?.addEventListener('click', showHome);

  document.getElementById('btn-save-preview')?.addEventListener('click', async () => {
    const text = document.getElementById('preview-text').value.trim();
    if (!text || !currentMemoryId) return;
    try {
      const chapters = await api('/chapters');
      if (!chapters.chapters?.length) {
        tg.showAlert('Сначала добавьте главу в «Моя книга»');
        return;
      }
      const ch = chapters.chapters.find((c) => c.title === (currentPreviewData?.chapter_suggestion || ''))
        || chapters.chapters[0];
      const mem = await api(`/memories/${currentMemoryId}`);
      const originalText = mem.edited_memoir_text || mem.cleaned_transcript || mem.raw_transcript || '';
      if (text !== originalText) {
        await api(`/memories/${currentMemoryId}/edit`, {
          method: 'POST',
          body: JSON.stringify({ instruction: `Замени весь текст на следующий:\n\n${text}` }),
        });
      }
      await api(`/memories/${currentMemoryId}/save`, {
        method: 'POST',
        body: JSON.stringify({ chapter_id: ch.id }),
      });
      tg.showAlert('Воспоминание сохранено');
      currentMemoryId = null;
      currentPreviewData = null;
      loadMe();
      showHome();
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  document.getElementById('btn-fantasy')?.addEventListener('click', async () => {
    if (!currentMemoryId) return;
    try {
      const data = await api(`/memories/${currentMemoryId}/fantasy`, { method: 'POST' });
      if (data.fantasy_memoir_text) {
        document.getElementById('preview-text').value = data.fantasy_memoir_text;
        tg.showAlert('Творческая версия загружена');
      } else {
        tg.showAlert('Не удалось создать творческую версию');
      }
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  document.getElementById('btn-clarification-back')?.addEventListener('click', () => {
    currentMemoryId = null;
    showHome();
  });

  document.getElementById('btn-send-clarification')?.addEventListener('click', async () => {
    const answer = document.getElementById('clarification-answer').value.trim();
    if (!answer || !currentMemoryId) {
      tg.showAlert('Введите ответ');
      return;
    }
    try {
      const result = await api(`/memories/${currentMemoryId}/clarification`, {
        method: 'POST',
        body: JSON.stringify({ answer }),
      });
      if (result.status === 'clarification') {
        document.getElementById('clarification-question').textContent = result.question;
        document.getElementById('clarification-answer').value = '';
        return;
      }
      if (result.status === 'preview') {
        await showPreview(result);
        return;
      }
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  document.getElementById('btn-skip-clarification')?.addEventListener('click', async () => {
    if (!currentMemoryId) return;
    try {
      const result = await api(`/memories/${currentMemoryId}/skip-clarification`, { method: 'POST' });
      if (result.status === 'preview') {
        await showPreview(result);
      } else {
        tg.showAlert(result.error || 'Ошибка');
      }
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  document.getElementById('btn-skip-all-clarification')?.addEventListener('click', async () => {
    if (!currentMemoryId) return;
    try {
      const result = await api(`/memories/${currentMemoryId}/skip-all-clarification`, { method: 'POST' });
      if (result.status === 'preview') {
        await showPreview(result);
      } else {
        tg.showAlert(result.error || 'Ошибка');
      }
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
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
      loadBook();
      loadMe();
    } catch (e) {
      tg.showAlert(e.message || 'Ошибка');
    }
  });

  let sortableChapters = null;
  let lastChapterOrder = [];

  async function loadBook() {
    const container = document.getElementById('book-chapters');
    try {
      const bookData = await api('/book');
      const chapters = bookData.chapters || [];
      if (!chapters.length) {
        container.innerHTML = '<p class="empty-state">Нет глав. Добавьте первую ниже!</p>';
        if (sortableChapters) {
          sortableChapters.destroy();
          sortableChapters = null;
        }
        return;
      }
      lastChapterOrder = chapters.map((c) => c.id);
      container.innerHTML = chapters
        .map((ch) => {
          const memories = ch.memories || [];
          return `
        <div class="book-chapter-block" data-id="${ch.id}">
          <div class="book-chapter-header">
            <span class="chapter-item-title">${escapeHtml(ch.title)}</span>
            <span class="chapter-item-count">${memories.length} воспоминаний</span>
            <span class="chapter-drag-handle" aria-label="Перетащить">⋮⋮</span>
          </div>
          <div class="book-chapter-memories">
            ${memories.length
              ? memories
                  .map(
                    (m) => `
              <div class="memory-block">
                <div class="memory-title">${escapeHtml(m.title || 'Без названия')}</div>
                <div class="memory-text">${escapeHtml(m.text || '').replace(/\n/g, '<br>')}</div>
              </div>
            `
                  )
                  .join('')
              : '<p class="empty-state">Пока пусто</p>'}
          </div>
        </div>
      `;
        })
        .join('');

      if (sortableChapters) sortableChapters.destroy();
      sortableChapters = new Sortable(container, {
        animation: 150,
        ghostClass: 'sortable-ghost',
        draggable: '.book-chapter-block',
        handle: '.chapter-drag-handle',
        onEnd: async (evt) => {
          const items = container.querySelectorAll('.book-chapter-block');
          const newOrder = [...items].map((el) => parseInt(el.dataset.id, 10));
          const orderChanged = newOrder.length !== lastChapterOrder.length ||
            newOrder.some((id, i) => id !== lastChapterOrder[i]);
          if (!orderChanged) return;
          lastChapterOrder = newOrder;
          try {
            await api('/chapters/reorder', {
              method: 'POST',
              body: JSON.stringify({ chapter_ids: newOrder }),
            });
            await loadBook();
          } catch (e) {
            tg.showAlert(e.message || 'Ошибка');
            await loadBook();
          }
        },
      });

      container.querySelectorAll('.book-chapter-header').forEach((el) => {
        el.addEventListener('click', (e) => {
          if (e.target.closest('.chapter-drag-handle')) return;
          el.closest('.book-chapter-block').classList.toggle('expanded');
        });
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
