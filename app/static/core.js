/* ФСП Карьера — ядро клиента: запросы, маршрутизация, утилиты, вход/регистрация, главная. Без сборки и зависимостей. */
'use strict';

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const nf = new Intl.NumberFormat('ru-RU');
const BUILD = '2026.10.11-7';   // должна совпадать с app.BUILD на сервере
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
  /* поверх открытого окна (dialog) обычный слой не виден — показываем сообщение внутри него */
  const dlg = [...document.querySelectorAll('dialog[open]')].pop();
  let box = dlg ? dlg.querySelector(':scope > .toasts') : $('#toasts');
  if (!box) { box = document.createElement('div'); box.className = 'toasts'; box.setAttribute('role', 'status'); dlg.appendChild(box); }
  box.appendChild(t);
  setTimeout(() => { t.remove(); if (box.classList.contains('toasts') && !box.children.length) box.remove(); }, kind === 'bad' ? 8000 : 4000);
}
const FIELD_RU = { email: 'e-mail', password: 'пароль', salary_from: 'зарплата от', salary_to: 'зарплата до', title: 'название', description: 'описание', contact_method: 'способ связи', consent_pd: 'согласие', company_name: 'компания', full_name: 'ФИО', answer: 'ответ' };
const fieldName = f => FIELD_RU[f] || f;
const fail = e => toast(e.message, 'bad', e.data && e.data.details);
function openModal(html) { const m = $('#modal'); m.innerHTML = html; if (!m.open) m.showModal(); if (typeof tpInit === 'function') tpInit(); const f = $('input,textarea,select', m); if (f) f.focus(); }
function closeModal() { const m = $('#modal'); if (m.open) m.close(); }
/* собственное окно подтверждения вместо системного confirm() */
function confirmBox(title, text, okLabel = 'Подтвердить', danger = false) {
  return new Promise(res => {
    const d = $('#confirm');
    d.innerHTML = `<form method="dialog" class="modal-body"><h2>${esc(title)}</h2><p>${esc(text)}</p>
      <div class="row" style="margin-top:16px"><button class="btn ${danger ? 'danger' : ''}" value="ok" autofocus>${esc(okLabel)}</button><button class="btn ghost" value="cancel">Отмена</button></div></form>`;
    d.onclose = () => res(d.returnValue === 'ok');
    d.returnValue = 'cancel';
    d.showModal();
  });
}
/* поля с деньгами: можно вводить любое число, пробелы-разделители добавляются сами */
const moneyField = (name, label, val, extra = '') => `<label class="f">${label}<input type="text" inputmode="numeric" autocomplete="off" data-money name="${name}" value="${val ? nf.format(val) : ''}" ${extra}></label>`;
const moneyNum = v => Number(String(v ?? '').replace(/\D/g, '')) || 0;
document.addEventListener('input', e => {
  const t = e.target;
  if (t.dataset && 'money' in t.dataset) { const n = String(t.value).replace(/\D/g, '').slice(0, 9); t.value = n ? nf.format(Number(n)) : ''; }
});
$('#modal').addEventListener('click', e => { if (e.target.id === 'modal') closeModal(); });

/* ---------- форматирование ---------- */
const money = n => nf.format(n) + ' ₽';
const salary = (a, b) => `${nf.format(a)} – ${nf.format(b)} ₽`;
const dt = s => s ? new Date(s).toLocaleString('ru-RU', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const dd = s => s ? new Date(s).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' }).replace(/\s?г\.$/, '') : '';
const ST = { sent: 'Отправлено', viewed: 'Просмотрено', accepted: 'Принято', declined: 'Отклонено', withdrawn: 'Отозвано', published: 'Опубликована', closed: 'Закрыта', invited_to_talk: 'Приглашён на разговор', call_passed: 'Успешно прошёл созвон — принят', hired: 'Принят', rejected: 'Отказ', assigned: 'Ждёт ответа', submitted: 'Отправлено', rated: 'Оценено' };
const stat = s => `<span class="status ${esc(s)}">${esc(ST[s] || s)}</span>`;
const specName = k => (S.tax && S.tax.specs[k]) ? S.tax.specs[k].short : k;
const gradeName = k => (S.tax && S.tax.grades[k]) ? S.tax.grades[k].title : k;
const catName = (s, g) => s && g ? `${specName(s)} · ${gradeName(g)}` : 'Не присвоена';
const techLabel = id => (S.techMap && S.techMap[id]) ? S.techMap[id].label : id;
const chips = (arr, cls = '') => (arr || []).map(t => `<span class="chip ${cls}">${esc(techLabel(t))}</span>`).join('');
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

/* ---------- выбор технологий из каталога (~160) ---------- */
function techIndex() {
  if (!S.techMap && S.tax && S.tax.tech) { S.techMap = {}; S.tax.tech.forEach(t => { S.techMap[t.id] = t; }); }
}
function techPicker(name, picked = [], spec = '', max = 25) {
  techIndex();
  const sel = new Set(picked);
  const groups = (S.tax.tech_groups || []).map(g => {
    const items = S.tax.tech.filter(t => t.group === g);
    return `<section class="tp-group" data-g="${esc(g)}"><h4>${esc(g)}</h4><div class="tp-items">${items.map(t => `<label class="tp-item" data-specs="${esc(t.specs.join(' '))}" data-q="${esc((t.label + ' ' + t.id + ' ' + t.aliases.join(' ')).toLowerCase())}">
      <input type="checkbox" name="${esc(name)}" value="${esc(t.id)}" ${sel.has(t.id) ? 'checked' : ''}><span>${esc(t.label)}</span></label>`).join('')}</div></section>`;
  }).join('');
  return `<div class="tp" data-max="${max}" data-spec="${esc(spec)}">
    <div class="tp-bar"><input type="search" class="tp-q" placeholder="Найти технологию: python, docker, react…" aria-label="Поиск по технологиям" autocomplete="off">
      ${spec ? '<label class="check tp-only"><input type="checkbox" class="tp-spec"><span>Только для моей специализации</span></label>' : ''}
      <span class="tp-count small muted"></span></div>
    <div class="tp-sel" aria-live="polite"></div>
    <div class="tp-list">${groups}</div></div>`;
}
function tpRefresh(tp) {
  const q = ($('.tp-q', tp).value || '').trim().toLowerCase();
  const only = $('.tp-spec', tp) && $('.tp-spec', tp).checked;
  const spec = tp.dataset.spec;
  $$('.tp-item', tp).forEach(it => {
    const ok = (!q || it.dataset.q.includes(q)) && (!only || it.dataset.specs.split(' ').includes(spec));
    it.hidden = !ok;
  });
  $$('.tp-group', tp).forEach(g => { g.hidden = !$$('.tp-item', g).some(i => !i.hidden); });
  const on = $$('input[type=checkbox][value]:checked', tp);
  $('.tp-count', tp).textContent = `выбрано ${on.length} из ${tp.dataset.max}`;
  $('.tp-sel', tp).innerHTML = on.map(i => `<button type="button" class="chip ok tp-x" data-v="${esc(i.value)}" title="Убрать">${esc(techLabel(i.value))} ×</button>`).join('');
}
document.addEventListener('input', e => { const tp = e.target.closest && e.target.closest('.tp'); if (tp && e.target.classList.contains('tp-q')) tpRefresh(tp); });
document.addEventListener('change', e => {
  const tp = e.target.closest && e.target.closest('.tp'); if (!tp) return;
  if (e.target.value && e.target.name && e.target.checked && $$('input[value]:checked', tp).length > Number(tp.dataset.max)) {
    e.target.checked = false; toast('Можно выбрать не больше ' + tp.dataset.max + ' технологий'); }
  tpRefresh(tp);
});
document.addEventListener('click', e => {
  const x = e.target.closest('.tp-x'); if (!x) return;
  const tp = x.closest('.tp'); const cb = $$('input[value]', tp).find(i => i.value === x.dataset.v); if (cb) { cb.checked = false; tpRefresh(tp); }
});
const pickedTech = root => $$('.tp input[value]:checked', root).map(i => i.value);
const tpInit = () => $$('.tp').forEach(tpRefresh);

/* ---------- маршрутизация ---------- */
const route = (re, handler, role) => routes.push([re, handler, role]);
function logout(silent) {
  S.token = null; S.user = null; localStorage.removeItem('fsp_token');
  if (!silent) toast('Вы вышли из аккаунта');
  location.hash = '#/login';
}
function home() { return !S.user ? '#/' : S.user.role === 'candidate' ? '#/c' : S.user.role === 'moderator' ? '#/m' : '#/e'; }

async function render() {
  const path = location.hash.slice(1) || '/';
  closeModal();
  for (const [re, handler, role] of routes) {
    const m = path.match(re);
    if (!m) continue;
    const okRole = !role || (S.user && (role === 'any' ? S.user.role !== 'moderator' : role === 'staff' ? true : S.user.role === role));
    if (!okRole) { location.hash = S.user ? home() : '#/login'; return; }
    const main = $('#app');
    try {
      const res = await handler(m);
      main.innerHTML = typeof res === 'string' ? res : res.html;
      tpInit();
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

const initials = u => ((u.name || u.email || '?').replace(/[^\p{L}\p{N}\s]/gu, '').trim().split(/\s+/).slice(0, 2).map(w => w[0]).join('') || '?').toUpperCase();
const avatarHtml = (u, cls = '') => u.avatar ? `<img class="ava ${cls}" src="${esc(u.avatar)}" alt="">` : `<span class="ava ${cls}" aria-hidden="true">${esc(initials(u))}</span>`;
function drawNav(path) {
  const cur = h => (path === h.slice(1) || (h.length > 4 && path.startsWith(h.slice(1) + '/'))) ? ' aria-current="page"' : '';
  const link = (h, t, extra = '') => `<a href="${h}"${cur(h)}>${t}${extra}</a>`;
  let items = '', menu = '';
  const mi = (h, t) => `<a href="${h}" role="menuitem">${t}</a>`;
  if (!S.user) items = link('#/login', 'Вход') + '<a class="btn small" href="#/register/candidate">Регистрация</a>';
  else if (S.user.role === 'candidate') {
    items = link('#/c', 'Обзор') + link('#/c/test', 'Тесты') + link('#/c/practice', 'Тренировка')
      + link('#/c/vacancies', 'Вакансии') + link('#/c/invites', 'Приглашения', S.badge ? `<span class="badge-dot">${S.badge}</span>` : '');
    menu = mi('#/c/resume', 'Моё резюме') + mi('#/c/profile', 'Профиль') + mi('#/c/rewards', 'Мои награды') + mi('#/c/tasks', 'Задания от компаний')
      + mi('#/wallet', 'Кошелёк и услуги') + mi('#/c/settings', 'Настройки') + mi('#/support', 'Связь с поддержкой');
  } else if (S.user.role === 'moderator') {
    items = link('#/m', 'Проверка тестов') + link('#/m/support', 'Поддержка');
  } else {
    items = link('#/e', 'Обзор') + link('#/e/bank', 'Кандидаты') + link('#/e/vacancies', 'Вакансии') + link('#/e/invites', 'Приглашения');
    menu = mi('#/e/company', 'Компания') + mi('#/e/tasks', 'Задания') + mi('#/wallet', 'Кошелёк и услуги') + mi('#/support', 'Связь с поддержкой');
  }
  const acc = S.user ? `<div class="acct"><button class="ava-btn" data-act="menu" aria-haspopup="menu" aria-expanded="false" aria-label="Меню аккаунта">${avatarHtml(S.user)}</button>
    <div class="menu" id="acctMenu" role="menu" hidden>
      <div class="menu-head">${avatarHtml(S.user, 'big')}<div><b>${esc(S.user.name || (S.user.role === 'moderator' ? 'Модератор' : 'Без имени'))}</b><div class="small muted">${esc(S.user.email)}</div></div></div>
      ${menu}${S.user.role !== 'moderator' ? '<button role="menuitem" data-act="avatarPick">' + (S.user.role === 'employer' ? 'Сменить логотип' : 'Сменить фото') + '</button>' : ''}
      <hr><button role="menuitem" data-act="logout">Выйти</button></div></div>` : '';
  $('#topbar').innerHTML = `<a class="brand" href="${home()}" aria-label="ФСП Карьера — на главную">
    <img class="brand-mark" src="/static/brand/fsp-mark.svg" alt="" width="34" height="34">
    <span>ФСП Карьера<small>федерация спортивного программирования</small></span></a><nav class="nav" aria-label="Основное меню">${items}</nav>${acc}`;
  if (S.user && S.user.role === 'candidate') refreshBadge();
}
acts.menu = el => { const m = $('#acctMenu'); const open = m.hidden; m.hidden = !open; el.setAttribute('aria-expanded', open); };
acts.menuClose = () => { const m = $('#acctMenu'); if (m) m.hidden = true; };
document.addEventListener('click', e => { const m = $('#acctMenu'); if (m && !m.hidden && !e.target.closest('.acct')) m.hidden = true; });
document.addEventListener('keydown', e => { if (e.key === 'Escape') { const m = $('#acctMenu'); if (m && !m.hidden) { m.hidden = true; const b = $('.ava-btn'); if (b) b.focus(); } } });
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

/* ---------- главная (коротко) ---------- */
const discTitle = d => typeof d === 'string' ? d : d.title;
const discText = d => typeof d === 'string' ? '' : (d.text || '');
route(/^\/$/, async () => {
  if (S.user) { location.hash = home(); return ''; }
  let st = { candidates_categorized: 0, employers: 0, vacancies_open: 0 }, show = { candidates: [], vacancies: [] }, about = { disciplines: [] };
  await Promise.all([api('/api/stats').then(r => { st = r; }).catch(() => 0), api('/api/public/showcase').then(r => { show = r; }).catch(() => 0), api('/api/about').then(r => { about = r; }).catch(() => 0)]);
  const fm = { office: 'офис', remote: 'удалённо', hybrid: 'гибрид' };
  return `
  <section class="hero solo">
    <img class="hero-logo" src="/static/brand/fsp-logo.svg" alt="Федерация спортивного программирования" width="120">
    <h1>Работодатель пишет первым — и сразу называет зарплату</h1>
    <p class="lead">Категорию кандидата определяет тест и опыт в ФСП, а не резюме. Условия видны до разговора.</p>
    <div class="row"><a class="btn big" href="#/register/candidate">Перейти к решению тестов</a><a class="btn ghost big" href="#/register/employer">Найти специалистов</a></div>
    <p class="small muted" style="margin-top:14px">Уже есть аккаунт? <a href="#/login">Войти</a></p>
  </section>
  <section class="stats" aria-label="Платформа в цифрах">
    <div class="stat"><b>${st.candidates_categorized}</b><span>кандидатов с категорией</span></div>
    <div class="stat"><b>${st.employers}</b><span>работодателей</span></div>
    <div class="stat"><b>${st.vacancies_open}</b><span>открытых вакансий</span></div>
  </section>
  ${about.disciplines.length ? `<section class="block"><div class="block-head"><h2>Направления ФСП</h2><a href="#/directions">Все направления</a></div>
    <div class="dirs">${about.disciplines.map((d, i) => `<a class="dir" href="#/directions"><b>${esc(discTitle(d))}</b><span>${esc(discText(d))}</span></a>`).join('')}</div></section>` : ''}
  ${show.candidates.length ? `<section class="block"><div class="block-head"><h2>Кандидаты в банке</h2><a href="#/register/employer">Смотреть всех</a></div>
    <div class="cards">${show.candidates.map(c => `<div class="panel mini2"><div class="row" style="justify-content:space-between"><span class="code">${esc(c.code)}</span><b class="num">${c.score}%</b></div>
      <div>${esc(c.category)}</div><div style="margin-top:6px">${chips(c.stack, 'ok')}${c.fsp ? '<span class="chip fsp">ФСП</span>' : ''}</div></div>`).join('')}</div>
    <p class="small muted">Имена и контакты скрыты, пока кандидат не примет приглашение.</p></section>` : ''}
  ${show.vacancies.length ? `<section class="block"><div class="block-head"><h2>Свежие вакансии</h2><a href="#/register/candidate">Все вакансии</a></div>
    <div class="cards">${show.vacancies.map(v => `<div class="panel mini2"><b>${esc(v.title)}</b><div class="muted small">${esc(v.company)} · ${esc(v.category)}${v.work_format ? ' · ' + fm[v.work_format] : ''}${v.city ? ' · ' + esc(v.city) : ''}</div>
      <div class="salary" style="margin:6px 0">${salary(v.salary_from, v.salary_to)}</div><div>${chips(v.stack)}</div></div>`).join('')}</div></section>` : ''}
  <section class="principles">
    <div><h3>Категорию даёт тест</h3><p>Задания уникальны для каждой попытки, ответы не передать.</p></div>
    <div><h3>Первым пишет работодатель</h3><p>Он находит нужную категорию и сам отправляет приглашение.</p></div>
    <div><h3>Зарплата известна заранее</h3><p>В каждом приглашении и вакансии работодатель указывает, сколько готов платить: «от» и «до», в рублях.</p></div>
  </section>`;
});

route(/^\/directions$/, async () => {
  let a = { disciplines: [], links: [] };
  try { a = await api('/api/about'); } catch (_) { /* покажем пустую страницу */ }
  return `<div class="page-head"><div><h1>Направления ФСП</h1><p class="muted">Федерация развивает несколько видов спортивного программирования. Результаты участия можно привязать к профилю через ФСП ID — они учитываются при подборе.</p></div></div>
    <div class="cards">${a.disciplines.map(d => `<div class="panel"><h3>${esc(discTitle(d))}</h3><p class="muted">${esc(discText(d))}</p></div>`).join('')}</div>
    <div class="row"><a class="btn" href="#/register/candidate">Пройти тест</a>${(a.links || [])[0] ? `<a class="btn ghost" href="${esc(a.links[0].url)}" target="_blank" rel="noopener noreferrer">${esc(a.links[0].label)}</a>` : ''}</div>`;
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
  try { S.user = await api('/api/auth/me'); } catch (_) { /* останемся с краткими данными */ }
  if (!S.tax) S.tax = await api('/api/taxonomy');
  techIndex();
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

/* ---------- подвал: сведения о ФСП (данные — data/fsp_about.json, /api/about) ---------- */
async function drawFooter() {
  let a = { name: 'Федерация спортивного программирования', short: 'ФСП' };
  try { a = await api('/api/about'); } catch (_) { /* покажем базовые сведения */ }
  const c = a.contacts || {}, l = a.legal || {};
  const contacts = [c.address && `<li>${esc(c.address)}</li>`, c.phone && `<li><a href="tel:${esc(c.phone.replace(/[^+\d]/g, ''))}">${esc(c.phone)}</a></li>`,
    c.email && `<li><a href="mailto:${esc(c.email)}">${esc(c.email)}</a></li>`, c.press_email && `<li>Пресс-служба: <a href="mailto:${esc(c.press_email)}">${esc(c.press_email)}</a></li>`, c.hours && `<li>${esc(c.hours)}</li>`].filter(Boolean);
  const links = (a.links || []).map(x => `<li><a href="${esc(x.url)}" target="_blank" rel="noopener noreferrer">${esc(x.label)}</a></li>`).join('');
  const legal = [l.full_name, l.ogrn && 'ОГРН ' + l.ogrn, l.inn && 'ИНН ' + l.inn].filter(Boolean).map(esc).join(' · ');
  $('#footer').innerHTML = `<div class="ft-inner">
    <div><div class="ft-brand"><img src="/static/brand/fsp-logo.svg" alt="${esc(a.short || 'ФСП')}" width="64"></div>
      <p><b>${esc(a.name)}</b></p>${a.description ? `<p>${esc(a.description)}</p>` : ''}</div>
    <div><h4>Направления</h4><ul>${(a.disciplines || []).map(d => `<li><a href="#/directions">${esc(discTitle(d))}</a></li>`).join('') || '<li>—</li>'}</ul></div>
    <div><h4>Платформа</h4><ul><li><a href="#/register/candidate">Кандидатам</a></li><li><a href="#/register/employer">Работодателям</a></li><li><a href="#/login">Вход</a></li><li><a href="/docs">Документация API</a></li></ul></div>
    <div><h4>Федерация на связи</h4><ul>${contacts.join('')}${links}</ul></div>
  </div>
  <div class="ft-bottom"><p>© ${new Date().getFullYear()} ${esc(a.name)}. ФСП Карьера — демонстрационная версия платформы подбора ИТ-специалистов.</p>
    <p>${legal ? legal + ' · ' : ''}Персональные данные обрабатываются по 152-ФЗ${l.privacy_url ? ` · <a href="${esc(l.privacy_url)}">Политика конфиденциальности</a>` : ''}${l.terms_url ? ` · <a href="${esc(l.terms_url)}">Условия использования</a>` : ''}</p></div>`;
}

/* ---------- старт ---------- */
async function boot() {
  try { S.tax = await api('/api/taxonomy'); techIndex(); } catch (e) { /* покажем ошибку на странице */ }
  try {
    const h = await api('/api/health');
    if (h.build !== BUILD) document.body.insertAdjacentHTML('afterbegin', `<div class="notice bad" style="margin:0;border-radius:0;text-align:center"><b>Запущена старая версия сервера</b> (сервер ${esc(h.build || 'неизвестно')}, интерфейс ${BUILD}). Остановите сервер (Ctrl+C), убедитесь, что запускаете <code>python run.py</code> из новой папки проекта, и откройте страницу заново (Ctrl+F5).</div>`);
  } catch (_) { /* не критично */ }
  if (S.token) {
    try { S.user = await api('/api/auth/me'); } catch (_) { S.token = null; localStorage.removeItem('fsp_token'); }
  }
  window.addEventListener('hashchange', render);
  render();
  drawFooter();
}
