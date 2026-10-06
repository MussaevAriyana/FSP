/* ФСП Карьера — ядро клиента: запросы, маршрутизация, утилиты, вход/регистрация, главная. Без сборки и зависимостей. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const S = { token: localStorage.getItem('fsp_token'), user: null, tax: null, badge: 0 };
const acts = {};      // data-act="имя"  → обработчик клика
const forms = {};     // data-form="имя" → обработчик submit
const routes = [];    // [RegExp, handler]

/* ---------- запросы ---------- */
async function api(path, { method = 'GET', body, form, blob } = {}) {
  const headers = {};
  if (S.token) headers.Authorization = 'Bearer ' + S.token;
  let payload;
  if (form) payload = form;
  else if (body !== undefined) { headers['Content-Type'] = 'application/json'; payload = JSON.stringify(body); }
  const res = await fetch(path, { method, headers, body: payload });
  if (res.status === 401 && S.token && !path.includes('/auth/login')) { logout(true); throw new Error('Сессия истекла — войдите снова'); }
  if (blob && res.ok) return res.blob();
  let data = null;
  try { data = await res.json(); } catch (_) { /* пустой ответ */ }
  if (!res.ok) {
    const e = new Error((data && data.message) || 'Ошибка запроса (' + res.status + ')');
    e.status = res.status; e.data = data || {}; throw e;
  }
  return data;
}
const qs = o => { const p = new URLSearchParams(); Object.entries(o).forEach(([k, v]) => { if (v !== '' && v != null && v !== false) p.set(k, v); }); const s = p.toString(); return s ? '?' + s : ''; };

/* ---------- уведомления и модальное окно ---------- */
function toast(msg, kind = '', details) {
  const t = document.createElement('div');
  t.className = 'toast ' + kind;
  t.innerHTML = esc(msg) + (details && details.length ? '<ul>' + details.map(d => `<li>${esc(d.message || d)}${d.field ? ' (' + esc(fieldName(d.field)) + ')' : ''}</li>`).join('') + '</ul>' : '');
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), kind === 'bad' ? 8000 : 4000);
}
const FIELD_RU = { email: 'e-mail', password: 'пароль', salary_from: 'зарплата от', salary_to: 'зарплата до', title: 'название', description: 'описание', contact_method: 'способ связи', consent_pd: 'согласие', company_name: 'компания', full_name: 'ФИО', answer: 'ответ' };
const fieldName = f => FIELD_RU[f] || f;
const fail = e => toast(e.message, 'bad', e.data && e.data.details);
function openModal(html) { const m = $('#modal'); m.innerHTML = html; if (!m.open) m.showModal(); const f = $('input,textarea,select', m); if (f) f.focus(); }
function closeModal() { const m = $('#modal'); if (m.open) m.close(); }
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });

/* ---------- форматирование ---------- */
const nf = new Intl.NumberFormat('ru-RU');
const money = n => nf.format(n) + ' ₽';
const salary = (a, b) => `${nf.format(a)} – ${nf.format(b)} ₽`;
const dt = s => s ? new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const dd = s => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).replace(/\s?г\.$/, '') : '';
const ST = { sent: 'Отправлено', viewed: 'Просмотрено', accepted: 'Принято', declined: 'Отклонено', withdrawn: 'Отозвано', published: 'Опубликована', closed: 'Закрыта', invited_to_talk: 'Приглашён на разговор', rejected: 'Отказ', assigned: 'Ждёт ответа', submitted: 'Отправлено', rated: 'Оценено' };
const stat = s => `<span class="status ${esc(s)}">${esc(ST[s] || s)}</span>`;
const specName = k => (S.tax && S.tax.specs[k]) ? S.tax.specs[k].short : k;
const gradeName = k => (S.tax && S.tax.grades[k]) ? S.tax.grades[k].title : k;
const catName = (s, g) => s && g ? `${specName(s)} · ${gradeName(g)}` : 'Не присвоена';
const chips = (arr, cls = '') => (arr || []).map(t => `<span class="chip ${cls}">${esc(t)}</span>`).join('');
const bar = (pct, cls = '') => `<div class="bar ${cls}" role="img" aria-label="${Math.round(pct)}%"><i style="width:${Math.max(0, Math.min(100, pct))}%"></i></div>`;
const opts = (obj, sel, empty) => (empty ? `<option value="">${esc(empty)}</option>` : '') + Object.entries(obj).map(([k, v]) => `<option value="${esc(k)}" ${k === sel ? 'selected' : ''}>${esc(typeof v === 'string' ? v : (v.title || v.short))}</option>`).join('');
const empty = (title, text, action = '') => `<div class="empty"><h3>${esc(title)}</h3><p>${text}</p>${action}</div>`;

/* Минимальный рендер Markdown для заданий: ``` код ```, `inline`, таблицы | a | b | */
function md(text) {
  const parts = String(text).split(/```(\w*)\n([\s\S]*?)```/g);
  let out = '';
  for (let i = 0; i < parts.length; i += 3) {
    out += mdText(parts[i]);
    if (i + 2 < parts.length) out += `<pre><code>${esc(parts[i + 2])}</code></pre>`;
  }
  return out;
}
function mdText(t) {
  const inline = s => esc(s).replace(/`([^`]+)`/g, '<code>$1</code>');
  return t.split(/\n{2,}/).map(block => {
    const lines = block.split('\n').filter(l => l.trim());
    if (!lines.length) return '';
    if (lines.every(l => l.trim().startsWith('|'))) {
      const rows = lines.filter(l => !/^\|[\s|:-]+\|?$/.test(l.trim())).map(l => l.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim()));
      const [head, ...body] = rows;
      return `<table><thead><tr>${head.map(c => `<th>${inline(c)}</th>`).join('')}</tr></thead><tbody>${body.map(r => `<tr>${r.map(c => `<td>${inline(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
    }
    return `<p>${lines.map(inline).join('<br>')}</p>`;
  }).join('');
}

function formData(form) {
  const o = {};
  $$('input,select,textarea', form).forEach(el => {
    if (!el.name) return;
    if (el.type === 'checkbox') o[el.name] = el.checked;
    else if (el.type === 'radio') { if (el.checked) o[el.name] = el.value; }
    else if (el.type === 'number') o[el.name] = el.value === '' ? null : Number(el.value);
    else o[el.name] = el.value;
  });
  return o;
}
const csv = s => String(s || '').split(',').map(x => x.trim().toLowerCase()).filter(Boolean);

/* ---------- маршрутизация ---------- */
const route = (re, handler, role) => routes.push([re, handler, role]);
function logout(silent) {
  S.token = null; S.user = null; localStorage.removeItem('fsp_token');
  if (!silent) toast('Вы вышли из аккаунта');
  location.hash = '#/login';
}
function home() { return !S.user ? '#/' : S.user.role === 'candidate' ? '#/c' : '#/e'; }

async function render() {
  const path = location.hash.slice(1) || '/';
  closeModal();
  for (const [re, handler, role] of routes) {
    const m = path.match(re);
    if (!m) continue;
    if (role && (!S.user || S.user.role !== role)) { location.hash = S.user ? home() : '#/login'; return; }
    const main = $('#app');
    try {
      const res = await handler(m);
      main.innerHTML = typeof res === 'string' ? res : res.html;
      if (res && res.after) res.after();
    } catch (e) {
      main.innerHTML = `<div class="notice bad"><b>Не удалось загрузить страницу.</b> ${esc(e.message)}</div>`;
    }
    drawNav(path);
    main.focus({ preventScroll: true });
    window.scrollTo(0, 0);
    return;
  }
  $('#app').innerHTML = empty('Страница не найдена', 'Проверьте адрес или вернитесь на главную.', `<a class="btn" href="${home()}">На главную</a>`);
  drawNav(path);
}

function drawNav(path) {
  const cur = h => (path === h.slice(1) || (h.length > 4 && path.startsWith(h.slice(1) + '/'))) ? ' aria-current="page"' : '';
  const link = (h, t, extra = '') => `<a href="${h}"${cur(h)}>${t}${extra}</a>`;
  let items = '';
  if (!S.user) items = link('#/', 'О платформе') + link('#/login', 'Вход') + link('#/register/candidate', 'Регистрация');
  else if (S.user.role === 'candidate') {
    items = link('#/c', 'Обзор') + link('#/c/profile', 'Профиль') + link('#/c/test', 'Тест и категория')
      + link('#/c/invites', 'Приглашения', S.badge ? `<span class="badge-dot">${S.badge}</span>` : '') + link('#/c/vacancies', 'Вакансии')
      + link('#/c/tasks', 'Задания') + link('#/c/settings', 'Настройки') + '<button data-act="logout">Выйти</button>';
  } else {
    items = link('#/e', 'Обзор') + link('#/e/bank', 'Банк кандидатов') + link('#/e/invites', 'Приглашения') + link('#/e/vacancies', 'Вакансии')
      + link('#/e/tasks', 'Задания') + link('#/e/company', 'Компания') + '<button data-act="logout">Выйти</button>';
  }
  $('#topbar').innerHTML = `<a class="brand" href="${home()}" aria-label="ФСП Карьера — на главную">
    <svg width="38" height="38" viewBox="0 0 38 38" aria-hidden="true"><circle cx="19" cy="7" r="4" fill="#fff"/><circle cx="7" cy="28" r="4" fill="#fff"/><circle cx="31" cy="28" r="4" fill="#fff"/><circle cx="19" cy="21" r="3" fill="#c79bee"/><path d="M19 7L7 28h24z M19 21V7M19 21L7 28M19 21l12 7" stroke="#fff" stroke-width="1.6" fill="none"/></svg>
    <span>ФСП Карьера<small>федерация спортивного программирования</small></span></a><nav class="nav" aria-label="Основное меню">${items}</nav>`;
  if (S.user && S.user.role === 'candidate') refreshBadge();
}
let badgeBusy = false;
async function refreshBadge() {
  if (badgeBusy) return; badgeBusy = true;
  try {
    const r = await api('/api/candidate/invites');
    const n = r.items.filter(i => i.status === 'sent').length;
    if (n !== S.badge) { S.badge = n; const a = $('.nav a[href="#/c/invites"]'); if (a) a.innerHTML = 'Приглашения' + (n ? `<span class="badge-dot">${n}</span>` : ''); }
  } catch (_) { /* не критично */ } finally { badgeBusy = false; }
}

document.addEventListener('click', async e => {
  const el = e.target.closest('[data-act]');
  if (!el) return;
  const fn = acts[el.dataset.act];
  if (!fn) return;
  e.preventDefault();
  if (el.disabled) return;
  try { await fn(el, e); } catch (err) { fail(err); }
});
document.addEventListener('submit', async e => {
  const f = e.target.closest('[data-form]');
  if (!f) return;
  e.preventDefault();
  const fn = forms[f.dataset.form];
  if (!fn) return;
  const btn = $('button[type=submit]', f);
  if (btn) btn.disabled = true;
  try { await fn(f, formData(f)); } catch (err) { fail(err); } finally { if (btn) btn.disabled = false; }
});
acts.logout = () => logout();
acts.closeModal = () => closeModal();

/* ---------- главная ---------- */
route(/^\/$/, async () => {
  if (S.user) { location.hash = home(); return ''; }
  let st = { candidates_categorized: 0, employers: 0, vacancies_open: 0, invites_sent: 0 };
  try { st = await api('/api/stats'); } catch (_) { /* демо без статистики */ }
  const demo = [['C-7F3A9B', 'Backend · Middle', 91, 'топ-4% на кубке ФСП'], ['C-21D0C4', 'Backend · Middle', 84, 'топ-11%, 3 мероприятия'], ['C-9B15E2', 'Backend · Middle', 78, 'истории ФСП нет']];
  return `
  <section class="hero">
    <div>
      <h1>Работодатель пишет первым — и сразу с зарплатой</h1>
      <p class="lead">Категория кандидата определяется тестом и достижениями в ФСП, а не самоописанным резюме. Работодатель находит нужную категорию и направляет предложение конкретному человеку.</p>
      <div class="row"><a class="btn" href="#/register/candidate">Я ищу работу</a><a class="btn ghost" href="#/register/employer">Я ищу специалистов</a></div>
    </div>
    <div class="board-demo" aria-label="Пример подборки">
      <div class="bd-head"><span>Подборка: Backend в платёжную команду</span><span>балл</span></div>
      ${demo.map((d, i) => `<div class="bd-row"><span class="bd-rank">${i + 1}</span><div><b style="font-family:var(--mono)">${d[0]}</b> <span style="opacity:.8">${d[1]}</span><div style="opacity:.75;font-size:.85rem">${d[3]}</div><div class="bd-bar"><i style="width:${d[2]}%"></i></div></div><span class="bd-score">${d[2]}</span></div>`).join('')}
      <div style="opacity:.7;font-size:.8rem;margin-top:10px">Имена и контакты скрыты, пока кандидат не примет приглашение.</div>
    </div>
  </section>
  <section class="principles">
    <div><h3>Категорию даёт тест</h3><p>У каждого кандидата уникальные задания: параметры и данные генерируются под попытку, поэтому ответы нельзя передать другому.</p></div>
    <div><h3>Первым пишет работодатель</h3><p>Он смотрит категоризированную базу, видит, почему кандидат попал в подборку, и сам отправляет приглашение.</p></div>
    <div><h3>Условия видны до разговора</h3><p>В каждом приглашении и вакансии указана вилка зарплаты в рублях. Контакты кандидата открываются только после его согласия.</p></div>
  </section>
  <section class="stats" aria-label="Платформа в цифрах">
    <div class="stat"><b>${st.candidates_categorized}</b><span>кандидатов с категорией</span></div>
    <div class="stat"><b>${st.employers}</b><span>работодателей</span></div>
    <div class="stat"><b>${st.vacancies_open}</b><span>открытых вакансий</span></div>
    <div class="stat"><b>${st.invites_sent}</b><span>приглашений отправлено</span></div>
  </section>`;
});

/* ---------- вход и регистрация ---------- */
route(/^\/login$/, () => `
  <div class="page-head"><h1>Вход</h1></div>
  <div class="panel" style="max-width:460px">
    <form data-form="login">
      <label class="f">Электронная почта<input type="email" name="email" autocomplete="username" required></label>
      <label class="f">Пароль<input type="password" name="password" autocomplete="current-password" required></label>
      <button class="btn" type="submit">Войти</button>
    </form>
    <p class="small muted" style="margin-top:16px">Нет аккаунта? <a href="#/register/candidate">Зарегистрироваться как кандидат</a> или <a href="#/register/employer">как работодатель</a>.</p>
  </div>`);
forms.login = async (f, d) => {
  const r = await api('/api/auth/login', { method: 'POST', body: d });
  await startSession(r);
};
async function startSession(r) {
  S.token = r.token; S.user = r.user; localStorage.setItem('fsp_token', r.token);
  if (!S.tax) S.tax = await api('/api/taxonomy');
  location.hash = home();
}

route(/^\/register\/(candidate|employer)$/, m => {
  const emp = m[1] === 'employer';
  return `
  <div class="page-head"><h1>${emp ? 'Регистрация работодателя' : 'Регистрация кандидата'}</h1>
    <a href="#/register/${emp ? 'candidate' : 'employer'}">${emp ? 'Я кандидат' : 'Я работодатель'}</a></div>
  <div class="panel" style="max-width:520px">
    <form data-form="register" data-role="${m[1]}">
      ${emp ? '<label class="f">Название компании<input type="text" name="company_name" required></label>' : ''}
      <label class="f">${emp ? 'Контактное лицо' : 'ФИО'}<input type="text" name="full_name" autocomplete="name"></label>
      <label class="f">Электронная почта<input type="email" name="email" autocomplete="username" required>
        <span class="hint">Мы отправим ссылку для подтверждения адреса.</span></label>
      <label class="f">Пароль<input type="password" name="password" autocomplete="new-password" minlength="8" required>
        <span class="hint">Не короче 8 символов, буквы и цифры.</span></label>
      <label class="check"><input type="checkbox" name="consent_pd" required>
        <span>Даю согласие на обработку персональных данных в соответствии с Федеральным законом № 152-ФЗ. Согласие можно отозвать, удалив аккаунт в настройках.</span></label>
      <button class="btn" type="submit">Создать аккаунт</button>
    </form>
  </div>`;
});
forms.register = async (f, d) => {
  const r = await api('/api/auth/register', { method: 'POST', body: { ...d, role: f.dataset.role } });
  $('#app').innerHTML = `
    <div class="page-head"><h1>Проверьте почту</h1></div>
    <div class="panel" style="max-width:560px">
      <p>${esc(r.message)} Перейдите по ссылке из письма, чтобы войти.</p>
      ${r.dev_token ? `<div class="notice warn"><b>Демо-режим.</b> Почта не отправляется, подтвердите адрес кнопкой ниже.</div>
        <button class="btn" data-act="confirmDev" data-token="${esc(r.dev_token)}">Подтвердить адрес</button>` : ''}
    </div>`;
};
acts.confirmDev = async el => { location.hash = '#/confirm/' + el.dataset.token; };
route(/^\/confirm\/(.+)$/, async m => {
  try {
    const r = await api('/api/auth/confirm', { method: 'POST', body: { token: m[1] } });
    toast('Адрес подтверждён', 'ok');
    await startSession(r);
    return '';
  } catch (e) {
    return `<div class="notice bad"><b>${esc(e.message)}</b></div><a class="btn" href="#/login">К входу</a>`;
  }
});

/* ---------- старт ---------- */
async function boot() {
  try { S.tax = await api('/api/taxonomy'); } catch (e) { /* покажем ошибку на странице */ }
  if (S.token) {
    try { S.user = await api('/api/auth/me'); } catch (_) { S.token = null; localStorage.removeItem('fsp_token'); }
  }
  window.addEventListener('hashchange', render);
  render();
}
