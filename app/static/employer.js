/* Личный кабинет «Работодатель» */
'use strict';

const specTitles = () => Object.fromEntries(Object.entries(S.tax.specs).map(([k, v]) => [k, v.title]));
const gradeTitles = () => Object.fromEntries(Object.entries(S.tax.grades).map(([k, g]) => [k, g.title]));

/* ---------- турнирная таблица кандидатов (общий компонент подборки и банка) ---------- */
function boardHtml(items, need) {
  if (!items.length) return empty('Подходящих кандидатов нет', 'Расширьте фильтры или опишите потребность иначе. Кандидаты появляются в банке после теста и согласия на публикацию.');
  return `<div class="board"><div class="board-head"><span>Место</span><span>Кандидат</span><span>Результат теста и ФСП</span><span>Подтверждено тестом</span><span style="text-align:right">Балл</span></div>
  ${items.map((c, i) => {
    const m = c.match;
    return `<div class="brow" data-code="${esc(c.code)}">
      <span class="rank">${i + 1}</span>
      <div><a class="code" href="#/e/candidate/${esc(c.code)}">${esc(c.code)}</a><div>${esc(c.category.label)}</div>
        <div class="muted small">${c.experience_years != null ? 'стаж ' + c.experience_years + ' г.' : ''}${c.city ? ' · ' + esc(c.city) : ''}</div></div>
      <div><div class="small"><b>Тест ${c.test_score}%</b></div>${bar(c.test_score, 'ok')}
        <div style="margin-top:6px">${c.fsp ? `<span class="chip fsp">ФСП: топ-${c.fsp.best_top_percent}%</span><span class="chip">${c.fsp.events_count} мероприятий</span>` : '<span class="chip dim">истории ФСП нет</span>'}</div></div>
      <div>${c.stack_confirmed.length ? chips(c.stack_confirmed, 'ok') : '<span class="muted small">нет подтверждённых технологий</span>'}${chips(c.stack_declared, 'dim')}</div>
      <div class="points">${m ? m.score : '—'}<small>${m ? `<button class="chip" data-act="why" data-i="${i}" aria-expanded="false">почему</button>` : ''}</small></div>
      <div class="why" hidden id="why${i}">${m ? m.reasons.map(r => `<div class="factor"><span><b>${esc(r.label)}</b></span><div>${bar(Math.max(0, r.value) * 100)}<span class="small muted">${esc(r.text)}</span></div></div>`).join('') : ''}
        <div class="row" style="margin-top:12px"><button class="btn small" data-act="inviteOpen" data-code="${esc(c.code)}" data-need="${need ? need.id : ''}">Пригласить</button><a class="btn ghost small" href="#/e/candidate/${esc(c.code)}">Открыть карточку</a></div></div>
    </div>`;
  }).join('')}</div>`;
}
acts.why = el => {
  const box = $('#why' + el.dataset.i); const open = box.hidden;
  box.hidden = !open; el.setAttribute('aria-expanded', open);
};

/* ---------- обзор и потребность ---------- */
route(/^\/e$/, async () => {
  const [sm, nd, co] = await Promise.all([api('/api/employer/summary'), api('/api/employer/needs'), api('/api/employer/company')]);
  const inv = sm.invites;
  return `<div class="page-head"><div><h1>${esc(co.company_name)}</h1><p class="muted">Опишите, кого ищете, — мы подберём категории и кандидатов с объяснением, почему они подходят.</p></div></div>
    <section class="stats"><div class="stat"><b>${sm.candidates_in_bank}</b><span>кандидатов в банке</span></div>
      <div class="stat"><b>${sm.invites_total}</b><span>приглашений отправлено</span></div>
      <div class="stat"><b>${inv.accepted || 0}</b><span>приняли приглашение</span></div>
      <div class="stat"><b>${sm.applications_new}</b><span>новых откликов</span></div></section>
    <form class="panel" data-form="need"><h2>Новая потребность</h2>
      <label class="f">Кто нужен<input type="text" name="title" placeholder="Например: Backend-разработчик в платёжную команду" required minlength="3"></label>
      <div class="grid3"><label class="f">Специализация<select name="spec">${opts(specTitles(), 'backend')}</select></label>
        <label class="f">Грейд<select name="grade">${opts(gradeTitles(), 'middle')}</select></label>
        <label class="f">Формат работы<select name="work_format">${opts(S.tax.work_formats, '', 'Не важно')}</select></label></div>
      <label class="f">Требуемый стек<span class="hint">Через запятую. Учитывается только то, что кандидат подтвердил тестом: ${Object.values(S.tax.stack).flat().filter((v, i, a) => a.indexOf(v) === i).slice(0, 14).join(', ')}…</span><input type="text" name="stack" placeholder="python, sql, docker"></label>
      <label class="f">Чем занимается команда<textarea name="team_desc" placeholder="Продукт, задачи, размер команды"></textarea></label>
      <button class="btn" type="submit">Подобрать кандидатов</button></form>
    ${nd.items.length ? `<div class="panel"><h2>Мои потребности</h2><table class="t"><thead><tr><th>Потребность</th><th>Категория</th><th>Стек</th><th></th></tr></thead><tbody>
      ${nd.items.map(n => `<tr><td>${esc(n.title)}</td><td>${esc(n.category_label)}</td><td>${chips(n.stack)}</td><td class="row"><a class="btn small" href="#/e/need/${n.id}">Подборка</a><button class="btn danger small" data-act="delNeed" data-id="${n.id}">Удалить</button></td></tr>`).join('')}</tbody></table></div>` : ''}`;
}, 'employer');
forms.need = async (f, d) => {
  const n = await api('/api/employer/needs', { method: 'POST', body: { title: d.title, spec: d.spec, grade: d.grade, work_format: d.work_format, stack: csv(d.stack), team_desc: d.team_desc } });
  location.hash = '#/e/need/' + n.id;
};
acts.delNeed = async el => { if (!confirm('Удалить потребность?')) return; await api('/api/employer/needs/' + el.dataset.id, { method: 'DELETE' }); render(); };

/* ---------- подборка под потребность ---------- */
let SEARCH = { need: null, filters: {} };
const filterBar = (f, withSpec) => `<form class="panel" data-form="filters" style="padding:16px 20px">
  <div class="row" style="align-items:flex-end;gap:14px">
    ${withSpec ? `<label class="f" style="margin:0">Специализация<select name="spec">${opts(specTitles(), f.spec, 'Любая')}</select></label>` : ''}
    <label class="f" style="margin:0">Грейд<select name="grade">${opts(gradeTitles(), f.grade, 'Любой')}</select></label>
    <label class="f" style="margin:0;min-width:170px">Подтверждённый стек<input type="text" name="stack" value="${esc(f.stack || '')}" placeholder="python, sql"></label>
    <label class="f" style="margin:0">Тест не ниже<select name="min_score">${['', '65', '75', '85'].map(v => `<option value="${v}" ${String(f.min_score || '') === v ? 'selected' : ''}>${v ? v + '%' : 'любой'}</option>`).join('')}</select></label>
    ${withSpec ? `<label class="f" style="margin:0;min-width:130px">Город<input type="text" name="city" value="${esc(f.city || '')}"></label>` : ''}
    <label class="check" style="margin:0 0 4px"><input type="checkbox" name="has_fsp" ${f.has_fsp ? 'checked' : ''}><span>Есть достижения ФСП</span></label>
    <button class="btn" type="submit">Уточнить</button><button class="btn ghost" type="button" data-act="resetFilters">Сбросить</button></div></form>`;

async function loadResults(url, need, filters, withSpec) {
  const res = await api(url + qs({ ...filters, limit: 50 }));
  SEARCH = { need, filters, items: res.items, url, withSpec };
  return res;
}
const resultsHtml = res => `
  ${res.need ? `<p class="small muted">В исходной подборке <b>${res.base_total}</b> ${res.base_total === 1 ? 'кандидат' : 'кандидатов'}${Object.keys(res.filters).length ? `, после уточнения — <b>${res.total}</b>. Подборка не потеряна: «Сбросить» вернёт её целиком.` : '.'}</p>`
    : `<p class="small muted">Найдено: <b>${res.total}</b>${res.total !== res.base_total ? ' из ' + res.base_total : ''}.</p>`}
  ${boardHtml(res.items, res.need)}`;
const categoriesHtml = (res, need) => res.recommended_categories.length ? `<div class="panel tint"><h3>${need ? 'Рекомендованные категории' : 'Категории в банке'}</h3>
  <div>${res.recommended_categories.map(c => `<button class="chip" data-act="pickCat" data-spec="${c.spec}" data-grade="${c.grade}" title="${esc(c.why || '')}">${esc(c.label)}: ${c.count}${c.fit != null && c.fit < 1 ? ` (подходит на ${Math.round(c.fit * 100)}%)` : ''}</button>`).join('')}</div>
  ${need ? '<p class="small muted" style="margin:8px 0 0">Кандидат точно нужной категории получает полный вес, соседний грейд и смежные специализации — частичный.</p>' : ''}</div>` : '';

route(/^\/e\/need\/(\d+)$/, async m => {
  const needs = await api('/api/employer/needs');
  const need = needs.items.find(n => n.id === Number(m[1]));
  if (!need) return empty('Потребность не найдена', '', '<a class="btn" href="#/e">К обзору</a>');
  const url = `/api/employer/needs/${need.id}/matches`;
  const res = await loadResults(url, need, {}, false);
  return `<div class="page-head"><div><h1>Подборка: ${esc(need.title)}</h1><p class="muted">${esc(need.category_label)}${need.stack.length ? ' · нужен стек: ' + esc(need.stack.join(', ')) : ''}</p></div><a class="btn ghost" href="#/e">Все потребности</a></div>
    <div id="cats">${categoriesHtml(res, need)}</div>${filterBar({}, false)}<div id="results">${resultsHtml(res)}</div>`;
}, 'employer');

route(/^\/e\/bank$/, async () => {
  const res = await loadResults('/api/employer/candidates', null, {}, true);
  return `<div class="page-head"><div><h1>Банк кандидатов</h1><p class="muted">Все кандидаты с категорией и согласием на публикацию. Имена и контакты скрыты до принятия приглашения.</p></div></div>
    <div id="cats">${categoriesHtml(res, null)}</div>${filterBar({}, true)}<div id="results">${resultsHtml(res)}</div>`;
}, 'employer');

async function refilter(filters) {
  const res = await loadResults(SEARCH.url, SEARCH.need, filters, SEARCH.withSpec);
  $('#results').innerHTML = resultsHtml(res);
}
forms.filters = async (f, d) => {
  const filters = { spec: d.spec || '', grade: d.grade || '', stack: csv(d.stack).join(','), min_score: d.min_score || '', city: d.city || '', has_fsp: d.has_fsp ? 'true' : '' };
  await refilter(filters);
};
acts.resetFilters = async () => { const f = $('[data-form=filters]'); f.reset(); $$('input[type=text]', f).forEach(i => i.value = ''); await refilter({}); };
acts.pickCat = async el => {
  const f = $('[data-form=filters]');
  const s = $('[name=spec]', f), g = $('[name=grade]', f);
  if (s) s.value = SEARCH.need ? '' : el.dataset.spec;
  g.value = el.dataset.grade;
  const cur = { ...SEARCH.filters, grade: el.dataset.grade };
  if (!SEARCH.need) cur.spec = el.dataset.spec;
  await refilter(cur);
};

/* ---------- карточка кандидата ---------- */
route(/^\/e\/candidate\/([A-Za-z0-9-]+)$/, async m => {
  const c = await api('/api/employer/candidates/' + m[1]);
  const f = c.fsp;
  return `<div class="page-head"><div><h1><span class="code">${esc(c.code)}</span></h1><p class="muted">${esc(c.category.label)}${c.headline ? ' · ' + esc(c.headline) : ''}</p></div>
    <div class="row"><a class="btn ghost" href="javascript:history.back()">Назад</a>${c.revealed ? '' : `<button class="btn" data-act="inviteOpen" data-code="${esc(c.code)}">Пригласить</button>`}</div></div>
    ${c.revealed ? `<div class="notice ok"><b>Контакты открыты.</b> ${esc(c.contacts.full_name)} · <a href="mailto:${esc(c.contacts.email)}">${esc(c.contacts.email)}</a>${c.contacts.phone ? ' · ' + esc(c.contacts.phone) : ''}</div>`
      : '<div class="notice">Имя и контакты откроются, когда кандидат примет ваше приглашение или откликнется сам.</div>'}
    <div class="panel"><div class="row" style="gap:36px;align-items:center"><div class="score-big">${c.test_score}<small>%</small></div><div><b>Результат теста на грейд</b><br><span class="muted">порог зачёта 65%</span></div></div>
      <p style="margin:16px 0 4px"><b>Подтверждено тестом:</b> ${c.stack_confirmed.length ? chips(c.stack_confirmed, 'ok') : '<span class="muted">нет данных</span>'}</p>
      ${c.stack_declared.length ? `<p style="margin:4px 0"><b>Заявлено кандидатом (не подтверждено):</b> ${chips(c.stack_declared, 'dim')}</p>` : ''}
      ${c.experience_years != null ? `<p style="margin:4px 0"><b>Стаж:</b> ${c.experience_years} лет</p>` : ''}</div>
    <div class="panel"><h2>Достижения ФСП</h2>${f ? `<p>${f.events_count} мероприятий, лучший результат — <b>топ-${f.best_top_percent}%</b> (${esc(f.best_event)}, место ${esc(f.best_place)}). Последнее участие: ${dd(f.last_event_date)}.</p>
      <table class="t"><thead><tr><th>Мероприятие</th><th>Тип</th><th>Дата</th><th>Место</th></tr></thead><tbody>${f.recent.map(e => `<tr><td>${esc(e.title)}</td><td>${esc({ contest: 'соревнование', hackathon: 'хакатон', training: 'обучение' }[e.type] || e.type)}</td><td>${dd(e.date)}</td><td>${esc(e.place)}</td></tr>`).join('')}</tbody></table>`
      : '<p class="muted">Истории участия в ФСП нет или кандидат её скрыл. На категорию и допуск к подборкам это не влияет.</p>'}</div>
    ${c.about || c.roles.length || c.soft_skills.length ? `<div class="panel"><h2>О кандидате</h2>${c.about ? `<p>${esc(c.about)}</p>` : ''}${c.roles.length ? `<p><b>Роли:</b> ${esc(c.roles.join('; '))}</p>` : ''}${c.soft_skills.length ? `<p>${chips(c.soft_skills)}</p>` : ''}
      <p class="small muted">Раздел заполнен самим кандидатом и не влияет на ранжирование.</p></div>` : ''}`;
}, 'employer');

/* ---------- приглашение ---------- */
acts.inviteOpen = async el => {
  const [co, vac, needs] = await Promise.all([api('/api/employer/company'), api('/api/employer/vacancies'), api('/api/employer/needs')]);
  const need = needs.items.find(n => String(n.id) === el.dataset.need);
  openModal(`<form data-form="invite" data-code="${esc(el.dataset.code)}" data-need="${esc(el.dataset.need || '')}">
    <h2>Приглашение кандидату <span class="code">${esc(el.dataset.code)}</span></h2>
    <label class="f">Должность<input type="text" name="title" value="${esc(need ? need.title : '')}" required minlength="3"></label>
    <div class="grid2"><label class="f">Зарплата от, ₽<input type="number" name="salary_from" min="1000" step="1000" required></label>
      <label class="f">Зарплата до, ₽<input type="number" name="salary_to" min="1000" step="1000" required></label></div>
    <label class="f">Описание предложения<textarea name="description" required minlength="10" placeholder="Чем предстоит заниматься, команда, условия">${esc(need ? need.team_desc : '')}</textarea></label>
    <label class="f">Как с вами связаться<input type="text" name="contact_method" value="${esc(co.contact_method || co.email)}" required></label>
    ${vac.items.length ? `<label class="f">Связать с вакансией (по желанию)<select name="vacancy_id"><option value="">Без привязки к вакансии</option>${vac.items.map(v => `<option value="${v.id}">${esc(v.title)}</option>`).join('')}</select></label>` : ''}
    <p class="small muted">Кандидат увидит название компании, вилку и способ связи до начала общения. Его контакты откроются только после принятия.</p>
    <div class="row"><button class="btn" type="submit">Отправить приглашение</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
};
forms.invite = async (f, d) => {
  const body = { candidate_code: f.dataset.code, title: d.title, description: d.description, contact_method: d.contact_method, salary_from: d.salary_from, salary_to: d.salary_to };
  if (d.vacancy_id) body.vacancy_id = Number(d.vacancy_id);
  if (f.dataset.need) body.need_id = Number(f.dataset.need);
  await api('/api/employer/invites', { method: 'POST', body });
  closeModal(); toast('Приглашение отправлено', 'ok');
  if (location.hash.startsWith('#/e/candidate')) render();
};

route(/^\/e\/invites$/, async () => {
  const r = await api('/api/employer/invites');
  if (!r.items.length) return `<div class="page-head"><h1>Приглашения</h1></div>` + empty('Вы пока никого не приглашали', 'Откройте подборку или банк кандидатов и нажмите «Пригласить» у подходящего человека.', '<a class="btn" href="#/e/bank">Банк кандидатов</a>');
  return `<div class="page-head"><div><h1>Приглашения</h1><p class="muted">Статусы обновляются, когда кандидат открывает приглашение и принимает решение.</p></div></div>
    <div class="board">${r.items.map(i => `<div class="brow" style="grid-template-columns:1.3fr 1fr 1fr 1.3fr auto">
      <div><b>${esc(i.title)}</b><div class="muted small">${dt(i.created_at)}</div></div>
      <div><a class="code" href="#/e/candidate/${esc(i.candidate.code)}">${esc(i.candidate.code)}</a><div class="small">${esc(i.candidate.category ? i.candidate.category.label : '')}</div></div>
      <div class="salary" style="font-size:1.05rem">${salary(i.salary_from, i.salary_to)}</div>
      <div>${stat(i.status)}${i.candidate.contacts ? `<div class="small" style="margin-top:6px"><b>${esc(i.candidate.contacts.full_name)}</b><br>${esc(i.candidate.contacts.email)}${i.candidate.contacts.phone ? '<br>' + esc(i.candidate.contacts.phone) : ''}</div>` : '<div class="muted small" style="margin-top:6px">контакты скрыты</div>'}</div>
      <div>${['sent', 'viewed'].includes(i.status) ? `<button class="btn danger small" data-act="withdraw" data-id="${i.id}">Отозвать</button>` : ''}</div></div>`).join('')}</div>`;
}, 'employer');
acts.withdraw = async el => { if (!confirm('Отозвать приглашение?')) return; await api('/api/employer/invites/' + el.dataset.id, { method: 'DELETE' }); toast('Приглашение отозвано'); render(); };

/* ---------- вакансии ---------- */
route(/^\/e\/vacancies$/, async () => {
  const r = await api('/api/employer/vacancies');
  return `<div class="page-head"><div><h1>Вакансии</h1><p class="muted">Дополнительный сценарий: кандидаты тоже могут откликаться сами. Вилка зарплаты обязательна.</p></div>
    <button class="btn" data-act="vacancyForm">Новая вакансия</button></div>
    ${r.items.length ? r.items.map(v => `<div class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start"><div><h3 style="margin-bottom:2px">${esc(v.title)} ${stat(v.status)}</h3>
      <div class="muted small">${esc(v.category_label)}${v.stack.length ? ' · ' + esc(v.stack.join(', ')) : ''}</div></div><span class="salary">${salary(v.salary_from, v.salary_to)}</span></div>
      <div class="row" style="margin-top:12px"><button class="btn small" data-act="loadApps" data-id="${v.id}">Отклики: ${v.applications}${v.applications_new ? ` (новых ${v.applications_new})` : ''}</button>
        <button class="btn ghost small" data-act="vacancyToggle" data-id="${v.id}" data-s="${v.status === 'published' ? 'closed' : 'published'}">${v.status === 'published' ? 'Закрыть' : 'Опубликовать снова'}</button></div>
      <div id="apps${v.id}" style="margin-top:12px"></div></div>`).join('')
      : empty('Вакансий пока нет', 'Опубликуйте первую — она появится у кандидатов в разделе «Вакансии».')}`;
}, 'employer');
acts.vacancyForm = () => openModal(`<form data-form="vacancy"><h2>Новая вакансия</h2>
  <label class="f">Название<input type="text" name="title" required minlength="3"></label>
  <div class="grid2"><label class="f">Специализация<select name="spec">${opts(specTitles(), 'backend')}</select></label><label class="f">Грейд<select name="grade">${opts(gradeTitles(), 'middle')}</select></label></div>
  <div class="grid2"><label class="f">Зарплата от, ₽<input type="number" name="salary_from" min="1000" step="1000" required></label><label class="f">Зарплата до, ₽<input type="number" name="salary_to" min="1000" step="1000" required></label></div>
  <label class="f">Стек<input type="text" name="stack" placeholder="python, postgresql"></label>
  <label class="f">Описание<textarea name="description"></textarea></label>
  <div class="row"><button class="btn" type="submit">Опубликовать</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
forms.vacancy = async (f, d) => { await api('/api/employer/vacancies', { method: 'POST', body: { title: d.title, spec: d.spec, grade: d.grade, salary_from: d.salary_from, salary_to: d.salary_to, stack: csv(d.stack), description: d.description } }); closeModal(); toast('Вакансия опубликована', 'ok'); render(); };
acts.vacancyToggle = async el => { await api(`/api/employer/vacancies/${el.dataset.id}/status`, { method: 'PATCH', body: { status: el.dataset.s } }); render(); };
acts.loadApps = async el => {
  const box = $('#apps' + el.dataset.id);
  const r = await api(`/api/employer/vacancies/${el.dataset.id}/applications`);
  box.innerHTML = r.items.length ? `<table class="t"><thead><tr><th>Кандидат</th><th>Профиль</th><th>Статус</th><th></th></tr></thead><tbody>${r.items.map(a => {
    const c = a.candidate, ct = c.contacts;
    return `<tr><td><b>${esc(ct ? ct.full_name : c.code)}</b><div class="small">${ct ? esc(ct.email) + (ct.phone ? '<br>' + esc(ct.phone) : '') : ''}</div>${a.message ? `<div class="small muted">«${esc(a.message)}»</div>` : ''}</td>
      <td>${c.category ? `${esc(c.category.label)}, тест ${c.test_score}%${c.has_fsp ? ' <span class="chip fsp">ФСП</span>' : ''}${c.match ? `<div class="small muted">соответствие вакансии: ${c.match.score}</div>` : ''}` : '<span class="muted">без категории</span>'}</td>
      <td>${stat(a.status)}</td><td class="row">${['viewed', 'invited_to_talk', 'rejected'].map(s => `<button class="btn ghost small" data-act="appStatus" data-id="${a.id}" data-s="${s}" data-v="${el.dataset.id}">${esc(ST[s])}</button>`).join('')}</td></tr>`;
  }).join('')}</tbody></table>` : '<p class="muted">Откликов пока нет.</p>';
};
acts.appStatus = async el => { await api(`/api/employer/applications/${el.dataset.id}/status`, { method: 'POST', body: { status: el.dataset.s } }); toast('Статус обновлён', 'ok'); await acts.loadApps({ dataset: { id: el.dataset.v } }); };

/* ---------- регулярные задания ---------- */
route(/^\/e\/tasks$/, async () => {
  const r = await api('/api/employer/microtasks');
  return `<div class="page-head"><div><h1>Задания для кандидатов</h1><p class="muted">Короткие задачи от вашей команды. Система сама предлагает их кандидатам подходящей категории, вы получаете свежий сигнал об их уровне.</p></div>
    <button class="btn" data-act="taskForm">Новое задание</button></div>
    ${r.items.length ? r.items.map(t => `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t.title)}</h3><span class="chip">${esc(catName(t.spec, t.grade))}</span></div>
      <p style="margin-top:8px">${esc(t.body).replace(/\n/g, '<br>')}</p><p class="small muted">Назначено: ${t.assigned} · ответили: ${t.answered}</p>
      <button class="btn small ghost" data-act="loadSubs" data-id="${t.id}">Показать ответы</button><div id="subs${t.id}" style="margin-top:10px"></div></div>`).join('')
      : empty('Заданий пока нет', 'Создайте задание — например, небольшой кейс из вашей практики. Кандидаты ответят текстом: решением или подходом.')}`;
}, 'employer');
acts.taskForm = () => openModal(`<form data-form="task"><h2>Новое задание</h2>
  <label class="f">Название<input type="text" name="title" required minlength="3"></label>
  <label class="f">Условие<textarea name="body" required minlength="10" placeholder="Например: как бы вы реализовали идемпотентность платёжного API?"></textarea></label>
  <div class="grid3"><label class="f">Специализация<select name="spec">${opts(specTitles(), 'backend')}</select></label><label class="f">Грейд<select name="grade">${opts(gradeTitles(), 'middle')}</select></label>
  <label class="f">Что требуется<select name="kind"><option value="approach">Предложить подход</option><option value="solve">Решить задачу</option></select></label></div>
  <div class="row"><button class="btn" type="submit">Создать</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
forms.task = async (f, d) => { await api('/api/employer/microtasks', { method: 'POST', body: d }); closeModal(); toast('Задание создано', 'ok'); render(); };
acts.loadSubs = async el => {
  const r = await api(`/api/employer/microtasks/${el.dataset.id}/submissions`);
  $('#subs' + el.dataset.id).innerHTML = r.items.length ? r.items.map(s => `<div class="notice"><b class="code">${esc(s.candidate.code)}</b> ${s.candidate.category ? esc(s.candidate.category.label) : ''} · ${dt(s.submitted_at)}<br>${esc(s.answer).replace(/\n/g, '<br>')}
    ${s.rating ? `<br><b>Оценка: ${s.rating}/5</b>${s.feedback ? ' — ' + esc(s.feedback) : ''}` : `<form class="row" data-form="rate" data-id="${s.assignment_id}" style="margin-top:8px"><select name="rating" style="width:auto">${[5, 4, 3, 2, 1].map(n => `<option>${n}</option>`).join('')}</select><input type="text" name="feedback" placeholder="Комментарий" style="width:240px"><button class="btn small" type="submit">Оценить</button></form>`}</div>`).join('') : '<p class="muted">Ответов пока нет.</p>';
};
forms.rate = async (f, d) => { await api(`/api/employer/assignments/${f.dataset.id}/rate`, { method: 'POST', body: { rating: Number(d.rating), feedback: d.feedback } }); toast('Оценка сохранена', 'ok'); render(); };

/* ---------- компания ---------- */
route(/^\/e\/company$/, async () => {
  const c = await api('/api/employer/company');
  return `<div class="page-head"><h1>Профиль компании</h1></div>
    <form class="panel" data-form="company"><div class="grid2"><label class="f">Название<input type="text" name="company_name" value="${esc(c.company_name)}" required></label>
      <label class="f">Направление деятельности<input type="text" name="industry" value="${esc(c.industry)}"></label></div>
      <label class="f">Описание<textarea name="description">${esc(c.description)}</textarea></label>
      <div class="grid3"><label class="f">Сайт<input type="text" name="website" value="${esc(c.website)}"></label><label class="f">Контактное лицо<input type="text" name="contact_name" value="${esc(c.contact_name)}"></label>
        <label class="f">Способ связи<span class="hint">Подставляется в приглашения</span><input type="text" name="contact_method" value="${esc(c.contact_method)}" placeholder="hr@company.ru, Telegram"></label></div>
      <button class="btn" type="submit">Сохранить</button></form>
    <div class="panel"><h2>Аккаунт</h2><p class="muted">${esc(c.email)}</p><button class="btn danger small" data-act="deleteAccount">Удалить аккаунт</button></div>`;
}, 'employer');
forms.company = async (f, d) => { await api('/api/employer/company', { method: 'PUT', body: d }); toast('Профиль компании сохранён', 'ok'); };
acts.deleteAccount = acts.deleteAccount || (async () => {
  const pw = prompt('Удаление необратимо. Введите пароль для подтверждения:'); if (!pw) return;
  await api('/api/auth/account', { method: 'DELETE', body: { password: pw } }); logout(true); toast('Аккаунт удалён');
});

boot();
