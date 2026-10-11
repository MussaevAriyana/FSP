/* Личный кабинет «Работодатель» */
'use strict';

const specTitles = () => Object.fromEntries(Object.entries(S.tax.specs).map(([k, v]) => [k, v.title]));
const gradeTitles = () => Object.fromEntries(Object.entries(S.tax.grades).map(([k, g]) => [k, g.title]));

const badgeChips = b => !b ? '' : (b.expert ? '<span class="chip fsp" title="Прошёл экспертный тест">Expert</span>' : '') + (b.pro ? '<span class="chip">Pro</span>' : '') + (b.boosted ? '<span class="chip warn">Продвигается</span>' : '');

/* ---------- турнирная таблица кандидатов (общий компонент подборки и банка) ---------- */
function boardHtml(items, need) {
  if (!items.length) return empty('Подходящих кандидатов нет', 'Расширьте фильтры или опишите потребность иначе. Кандидаты появляются в банке после теста и согласия на публикацию.');
  return `<div class="board"><div class="board-head"><span>Место</span><span>Кандидат</span><span>Результат теста и ФСП</span><span>Подтверждено тестом</span><span style="text-align:right">Балл</span></div>
  ${items.map((c, i) => {
    const m = c.match;
    return `<div class="brow" data-code="${esc(c.code)}">
      <span class="rank">${i + 1}</span>
      <div><a class="code" href="#/e/candidate/${esc(c.code)}">${esc(c.code)}</a> ${badgeChips(c.badges)}<div>${esc(c.category.label)}</div>
        <div class="muted small">${c.experience_years != null ? 'стаж ' + c.experience_years + ' г.' : ''}${c.city ? ' · ' + esc(c.city) : ''}</div></div>
      <div><div class="small"><b>Тест ${c.test_score}%</b></div>${bar(c.test_score, 'ok')}
        <div style="margin-top:6px">${c.fsp ? `<span class="chip fsp">ФСП: топ-${c.fsp.best_top_percent}%</span><span class="chip">${c.fsp.events_count} мероприятий</span>` : '<span class="chip dim">истории ФСП нет</span>'}</div></div>
      <div>${c.stack_confirmed.length ? chips(c.stack_confirmed, 'ok') : '<span class="muted small">нет подтверждённых технологий</span>'}${chips(c.stack_declared, 'dim')}</div>
      <div class="points">${m ? m.score : '—'}<small>${m ? `<button class="chip" data-act="why" data-i="${i}" aria-expanded="false">Подробнее</button>` : ''}</small></div>
      <div class="why" hidden id="why${i}">${m ? m.reasons.map(r => `<div class="factor"><span><b>${esc(r.label)}</b></span><div>${bar(Math.max(0, r.value) * 100)}<span class="small muted">${esc(r.text)}</span></div></div>`).join('') : ''}
        </div>
      <div class="row brow-actions"><button class="btn small" data-act="inviteOpen" data-code="${esc(c.code)}" data-need="${need ? need.id : ''}">Пригласить</button><a class="btn ghost small" href="#/e/candidate/${esc(c.code)}">Открыть карточку</a></div>
    </div>`;
  }).join('')}</div>`;
}
acts.why = el => {
  const box = $('#why' + el.dataset.i); const open = box.hidden;
  box.hidden = !open; el.setAttribute('aria-expanded', open);
};

/* ---------- обзор и потребность ---------- */
route(/^\/e$/, async () => {
  const [sm, nd, co, vc] = await Promise.all([api('/api/employer/summary'), api('/api/employer/needs'), api('/api/employer/company'), api('/api/employer/vacancies')]);
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
      <div class="f"><b style="font-size:.92rem">Требуемый стек</b><span class="hint">До 12 из ${S.tax.tech.length} технологий. Учитывается только то, что кандидат подтвердил тестом.</span><div style="margin-top:8px">${techPicker('stack', [], '', 12)}</div></div>
      <label class="f">Чем занимается команда<textarea name="team_desc" placeholder="Продукт, задачи, размер команды"></textarea></label>
      <button class="btn" type="submit">Подобрать кандидатов</button></form>
    ${nd.items.length ? `<div class="panel"><h2>Мои потребности</h2><table class="t"><thead><tr><th>Потребность</th><th>Категория</th><th>Стек</th><th></th></tr></thead><tbody>
      ${nd.items.map(n => `<tr><td>${esc(n.title)}</td><td>${esc(n.category_label)}</td><td>${chips(n.stack)}</td><td class="row"><a class="btn small" href="#/e/need/${n.id}">Подборка</a><button class="btn danger small" data-act="delNeed" data-id="${n.id}">Удалить</button></td></tr>`).join('')}</tbody></table></div>` : ''}
    <div class="panel"><div class="row" style="justify-content:space-between"><h2 style="margin:0">Мои вакансии</h2><a class="btn small ghost" href="#/e/vacancies/new">Новая вакансия</a></div>
      ${vc.items.length ? `<table class="t" style="margin-top:10px"><thead><tr><th>Вакансия</th><th>Категория</th><th>Зарплата</th><th>Статус</th><th></th></tr></thead><tbody>
        ${vc.items.map(v => `<tr><td>${esc(v.title)}</td><td>${esc(v.category_label)}</td><td>${salary(v.salary_from, v.salary_to)}</td><td>${stat(v.status)}</td>
          <td class="row"><a class="btn small" href="#/e/vacancies/${v.id}/edit">Редактировать</a><a class="btn ghost small" href="#/e/vacancies">Отклики</a></td></tr>`).join('')}</tbody></table>`
        : '<p class="muted" style="margin:10px 0 0">Вакансий пока нет. Опубликуйте первую — кандидаты увидят её в своём разделе «Вакансии».</p>'}</div>`;
}, 'employer');
acts.editNeed = async el => {
  const nd = await api('/api/employer/needs'), n = nd.items.find(x => String(x.id) === el.dataset.id); if (!n) return;
  openModal(`<form data-form="needEdit" data-id="${n.id}" class="modal-body"><h2>Изменить потребность</h2>
    <label class="f">Кто нужен<input type="text" name="title" value="${esc(n.title)}" required minlength="3"></label>
    <div class="grid3"><label class="f">Специализация<select name="spec">${opts(specTitles(), n.spec)}</select></label>
      <label class="f">Грейд<select name="grade">${opts(gradeTitles(), n.grade)}</select></label>
      <label class="f">Формат работы<select name="work_format">${opts(S.tax.work_formats, n.work_format, 'Не важно')}</select></label></div>
    <div class="f"><b style="font-size:.92rem">Требуемый стек</b><div style="margin-top:8px">${techPicker('stack', n.stack, '', 12)}</div></div>
    <label class="f">Чем занимается команда<textarea name="team_desc">${esc(n.team_desc)}</textarea></label>
    <div class="row"><button class="btn" type="submit">Сохранить</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
};
forms.needEdit = async (f, d) => {
  await api('/api/employer/needs/' + f.dataset.id, { method: 'PUT', body: { title: d.title, spec: d.spec, grade: d.grade, work_format: d.work_format, stack: pickedTech(f), team_desc: d.team_desc } });
  closeModal(); toast('Потребность обновлена', 'ok'); render();
};
forms.need = async (f, d) => {
  const n = await api('/api/employer/needs', { method: 'POST', body: { title: d.title, spec: d.spec, grade: d.grade, work_format: d.work_format, stack: pickedTech(f), team_desc: d.team_desc } });
  location.hash = '#/e/need/' + n.id;
};
acts.delNeed = async el => { if (!(await confirmBox('Удалить потребность?', 'Подборка по ней будет удалена.', 'Удалить', true))) return; await api('/api/employer/needs/' + el.dataset.id, { method: 'DELETE' }); render(); };

/* ---------- подборка под потребность ---------- */
let SEARCH = { need: null, filters: {} };
const filterBar = (f, withSpec) => `<form class="panel" data-form="filters" style="padding:16px 20px">
  <div class="row" style="align-items:flex-end;gap:14px">
    ${withSpec ? `<label class="f" style="margin:0">Специализация<select name="spec">${opts(specTitles(), f.spec, 'Любая')}</select></label>` : ''}
    <label class="f" style="margin:0">Грейд<select name="grade">${opts(gradeTitles(), f.grade, 'Любой')}</select></label>
    <details class="f tp-drop" style="margin:0"><summary>Подтверждённый стек${f.stack ? ': ' + f.stack.split(',').length : ''}</summary>${techPicker('stack', (f.stack || '').split(',').filter(Boolean), '', 12)}</details>
    <label class="f" style="margin:0">Тест не ниже<select name="min_score">${['', '65', '75', '85'].map(v => `<option value="${v}" ${String(f.min_score || '') === v ? 'selected' : ''}>${v ? v + '%' : 'любой'}</option>`).join('')}</select></label>
    ${withSpec ? `<label class="f" style="margin:0;min-width:130px">Город<input type="text" name="city" value="${esc(f.city || '')}"></label>` : ''}
    <label class="check" style="margin:0 0 4px"><input type="checkbox" name="has_fsp" ${f.has_fsp ? 'checked' : ''}><span>Есть достижения ФСП</span></label>
    <label class="check" style="margin:0 0 4px" title="Платная услуга «Поиск среди Expert»"><input type="checkbox" name="expert_only" ${f.expert_only ? 'checked' : ''}><span>Только Expert</span></label>
    <button class="btn" type="submit">Поиск</button><button class="btn ghost" type="button" data-act="resetFilters">Сбросить</button></div></form>`;

async function loadResults(url, need, filters, withSpec) {
  const res = await api(url + qs({ ...filters, limit: 50 }));
  SEARCH = { need, filters, items: res.items, url, withSpec };
  return res;
}
const resultsHtml = res => `
  ${res.need ? `<p class="small muted">В исходной подборке <b>${res.base_total}</b> ${res.base_total === 1 ? 'кандидат' : 'кандидатов'}${Object.keys(res.filters).length ? `, после поиска — <b>${res.total}</b>. Подборка не потеряна: «Сбросить» вернёт её целиком.` : '.'}</p>`
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
  const filters = { spec: d.spec || '', grade: d.grade || '', stack: pickedTech(f).join(','), min_score: d.min_score || '', city: d.city || '', has_fsp: d.has_fsp ? 'true' : '', expert_only: d.expert_only ? 'true' : '' };
  await refilter(filters);
};
acts.resetFilters = async () => { const f = $('[data-form=filters]'); f.reset(); $$('input[type=text]', f).forEach(i => i.value = ''); $$('.tp input[value]', f).forEach(i => { i.checked = false; }); tpInit(); await refilter({}); };
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
  return `<div class="page-head"><div><h1><span class="code">${esc(c.code)}</span> ${badgeChips(c.badges)}</h1><p class="muted">${esc(c.category.label)}${c.headline ? ' · ' + esc(c.headline) : ''}</p></div>
    <div class="row"><a class="btn ghost" href="javascript:history.back()">Назад</a><button class="btn ghost" data-act="scrollResume">Резюме</button><button class="btn ghost" data-act="resumePdf" data-code="${esc(c.code)}">Резюме в PDF</button>${c.revealed ? '' : `<button class="btn" data-act="inviteOpen" data-code="${esc(c.code)}">Пригласить</button>`}</div></div>
    ${c.revealed ? `<div class="notice ok"><b>Контакты открыты.</b> ${esc(c.contacts.full_name)} · <a href="mailto:${esc(c.contacts.email)}">${esc(c.contacts.email)}</a>${c.contacts.phone ? ' · ' + esc(c.contacts.phone) : ''}</div>`
      : '<div class="notice">Имя и контакты откроются, когда кандидат примет ваше приглашение или откликнется сам.</div>'}
    <div class="panel"><div class="row" style="gap:36px;align-items:center"><div class="score-big">${c.test_score}<small>%</small></div><div><b>Результат теста на грейд</b><br><span class="muted">порог зачёта 65%</span></div></div>
      <p style="margin:16px 0 4px"><b>Подтверждено тестом:</b> ${c.stack_confirmed.length ? chips(c.stack_confirmed, 'ok') : '<span class="muted">нет данных</span>'}</p>
      ${c.stack_declared.length ? `<p style="margin:4px 0"><b>Заявлено кандидатом (не подтверждено):</b> ${chips(c.stack_declared, 'dim')}</p>` : ''}
      ${c.experience_years != null ? `<p style="margin:4px 0"><b>Стаж:</b> ${c.experience_years} лет</p>` : ''}</div>
    ${briefHtml(c)}
    <div class="panel"><h2>Достижения ФСП</h2>${f ? `<p>${f.events_count} мероприятий, лучший результат — <b>топ-${f.best_top_percent}%</b> (${esc(f.best_event)}, место ${esc(f.best_place)}). Последнее участие: ${dd(f.last_event_date)}.</p>
      <table class="t"><thead><tr><th>Мероприятие</th><th>Тип</th><th>Дата</th><th>Место</th></tr></thead><tbody>${f.recent.map(e => `<tr><td>${esc(e.title)}</td><td>${esc({ contest: 'соревнование', hackathon: 'хакатон', training: 'обучение' }[e.type] || e.type)}</td><td>${dd(e.date)}</td><td>${esc(e.place)}</td></tr>`).join('')}</tbody></table>`
      : '<p class="muted">Истории участия в ФСП нет или кандидат её скрыл. На категорию и допуск к подборкам это не влияет.</p>'}</div>
    ${c.about || c.roles.length || c.soft_skills.length ? `<div class="panel"><h2>О кандидате</h2>${c.about ? `<p>${esc(c.about)}</p>` : ''}${c.roles.length ? `<p><b>Роли:</b> ${esc(c.roles.join('; '))}</p>` : ''}${c.soft_skills.length ? `<p>${chips(c.soft_skills)}</p>` : ''}
      <p class="small muted">Раздел заполнен самим кандидатом и не влияет на ранжирование.</p></div>` : ''}<div id="resume">${resumeHtml(c.resume, c.revealed)}</div>`;
}, 'employer');

const EMP_RU = { full: 'полная занятость', part: 'частичная', project: 'проект', internship: 'стажировка' };
const SCH_RU = { office: 'офис', remote: 'удалённо', hybrid: 'гибрид', shift: 'сменный график' };
const YN = { no: 'нет', yes: 'да', maybe: 'рассмотрит', rarely: 'редко' };
const EDU_RU = { secondary: 'Среднее общее', college: 'Среднее профессиональное', bachelor: 'Бакалавриат', specialist: 'Специалитет', master: 'Магистратура', phd: 'Аспирантура', courses: 'Курсы' };
const MAR = { single: 'не женат / не замужем', married: 'женат / замужем', divorced: 'разведён / разведена', widowed: 'вдовец / вдова' };
const KIDS = { none: 'нет', one: 'один ребёнок', two: 'двое', three_plus: 'трое и более' };
const MIL = { served: 'служил(а)', reserve: 'в запасе', exempt: 'освобождён(а)', not_liable: 'не военнообязан(а)', student: 'отсрочка (учёба)' };
const fact = (t, v) => v ? `<div><span>${t}</span><b>${esc(v)}</b></div>` : '';
function briefHtml(c) {
  const r = c.resume || {}, edu = (r.education || [])[0], pr = r.personal || {};
  const facts = [fact('Желаемая должность', r.desired_position), fact('Желаемая зарплата', r.salary_expectation ? 'от ' + money(r.salary_expectation) : ''),
    fact('Стаж', c.experience_years != null ? c.experience_years + ' лет' : ''), fact('Город', c.city), fact('Возраст', pr.age ? pr.age + ' лет' : ''),
    fact('Последнее место работы', (r.experience || [])[0] ? [(r.experience[0].position), r.experience[0].company].filter(Boolean).join(', ') : ''),
    fact('Образование', edu ? [EDU_RU[edu.level], edu.specialty].filter(Boolean).join(' · ') || edu.institution : ''), fact('Языки', (r.languages || []).map(x => x.name + ' ' + x.level).join(', ')),
    fact('Формат работы', (r.schedules || []).map(x => SCH_RU[x]).join(', ')), fact('Семейное положение', MAR[pr.marital_status])].join('');
  return facts ? `<div class="panel"><h2>Кратко о кандидате</h2><div class="facts">${facts}</div></div>` : '';
}
function resumeHtml(r, revealed) {
  if (!r) return '';
  const has = r.summary || r.experience.length || r.projects.length || r.education.length || r.certificates.length || r.languages.length || r.salary_expectation;
  if (!has) return '<div class="panel"><h2>Резюме</h2><p class="muted">Кандидат пока не заполнил резюме или скрыл его.</p></div>';
  const per = x => `${esc(x.start || '')}${x.start ? ' — ' : ''}${x.start ? esc(x.end || 'по настоящее время') : ''}`;
  const kinds = { certificate: 'Сертификат', diploma: 'Диплом', award: 'Награда' };
  const lang = { native: 'родной' };
  const wishes = [fact('Желаемая зарплата', r.salary_expectation ? 'от ' + money(r.salary_expectation) : ''), fact('Занятость', (r.employment_types || []).map(x => EMP_RU[x]).join(', ')),
    fact('Формат работы', (r.schedules || []).map(x => SCH_RU[x]).join(', ')), fact('Переезд', YN[r.relocation]), fact('Командировки', YN[r.business_trips])].join('');
  const pr = r.personal ? [fact('Возраст', r.personal.age ? r.personal.age + ' лет' : ''), fact('Гражданство', r.personal.citizenship), fact('Семейное положение', MAR[r.personal.marital_status]), fact('Дети', KIDS[r.personal.children]),
    fact('Воинская обязанность', MIL[r.personal.military]), fact('Водительские права', r.personal.driving)].join('') : '';
  const links = Object.entries(r.links || {}).map(([k, v]) => `<a href="${esc(v.startsWith('http') ? v : (k === 'telegram' ? 'https://t.me/' + v.replace('@', '') : 'https://' + v))}" target="_blank" rel="noopener noreferrer" class="chip">${esc(k)}</a>`).join('');
  return `<div class="panel"><h2>Резюме${r.desired_position ? ' · ' + esc(r.desired_position) : ''}</h2>${r.summary ? `<p>${esc(r.summary)}</p>` : ''}
    ${wishes ? `<div class="facts" style="margin:12px 0">${wishes}</div>` : ''}
    ${r.experience.length ? '<h3>Опыт работы</h3>' + r.experience.map(e => `<p><b>${esc(e.position)}</b>${e.company ? ', ' + esc(e.company) : ''} <span class="muted small">${per(e)}</span>${e.description ? '<br><span class="muted">' + esc(e.description) + '</span>' : ''}</p>`).join('') : ''}
    ${r.education.length ? '<h3>Образование</h3>' + r.education.map(x => `<p><b>${esc(x.institution)}</b>${EDU_RU[x.level] ? ' · ' + EDU_RU[x.level] : ''}${x.specialty ? ' · ' + esc(x.specialty) : ''} ${x.degree ? '· ' + esc(x.degree) : ''} <span class="muted small">${esc(x.year_from)}–${esc(x.year_to)}</span></p>`).join('') : ''}
    ${r.projects.length ? '<h3>Проекты</h3>' + r.projects.map(x => `<p><b>${esc(x.name)}</b>${x.role ? ' — ' + esc(x.role) : ''}${x.link ? ` · <a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">ссылка</a>` : ''}${x.description ? '<br><span class="muted">' + esc(x.description) + '</span>' : ''}${x.stack.length ? '<br>' + chips(x.stack, 'dim') : ''}</p>`).join('') : ''}
    ${r.certificates.length ? '<h3>Дипломы и сертификаты</h3>' + r.certificates.map(x => `<p><span class="chip">${kinds[x.kind] || ''}</span> ${esc(x.name)} <span class="muted small">${esc(x.issuer)} ${esc(x.year)}</span>${x.link ? ` · <a href="${esc(x.link)}" target="_blank" rel="noopener noreferrer">документ</a>` : ''}</p>`).join('') : ''}
    ${r.languages.length ? '<h3>Языки</h3><p>' + r.languages.map(x => `<span class="chip">${esc(x.name)} — ${esc(lang[x.level] || x.level)}</span>`).join('') + '</p>' : ''}
    ${pr ? `<h3>Личные сведения</h3><div class="facts">${pr}</div><p class="small muted">Показаны, потому что кандидат разрешил.</p>` : ''}
    ${links ? `<h3>Ссылки</h3><p>${links}</p>` : ''}
    ${revealed ? '' : '<p class="small muted">Названия компаний и учебных заведений, ссылки скрыты до принятия приглашения.</p>'}</div>`;
}
acts.scrollResume = () => { const e = $('#resume'); if (e) e.scrollIntoView({ behavior: 'smooth', block: 'start' }); };
acts.resumePdf = async el => {
  const b = await api(`/api/employer/candidates/${el.dataset.code}/resume.pdf`, { blob: true });
  const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = `resume-${el.dataset.code}.pdf`; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};

/* ---------- приглашение ---------- */
const STAGES = { considering: 'На рассмотрении', interview: 'Собеседование', test_task: 'Тестовое задание', offer: 'Оффер', hired: 'Принят на работу', rejected: 'Отказ' };
const STAGE_FLOW = ['considering', 'interview', 'test_task', 'offer', 'hired'];
/* шкала: этап приглашения (отправлено → просмотрено → принято) + этапы работодателя */
function pipeline(i) {
  const st = i.status, flow = [['sent', 'Отправлено'], ['viewed', 'Просмотрено кандидатом'], ['accepted', 'Кандидат согласился']];
  if (st === 'declined' || st === 'withdrawn') return `<div class="pipe">${st === 'declined' ? '<span class="done">Отправлено</span>' : ''}<span class="bad">${st === 'declined' ? 'Кандидат отклонил' : 'Отозвано'}</span></div>`;
  const rank = { sent: 0, viewed: 1, accepted: 2 }[st] ?? 0;
  const first = flow.map(([k, t], n) => `<span class="${n < rank ? 'done' : n === rank && !i.stage ? 'now' : n === rank ? 'done' : ''}">${t}</span>`).join('');
  const second = i.stage === 'rejected' ? `<span class="bad">Отказ</span>` : STAGE_FLOW.map(k => { const cur = STAGE_FLOW.indexOf(i.stage), me = STAGE_FLOW.indexOf(k); return `<span class="${me < cur ? 'done' : me === cur ? 'now' : ''}">${STAGES[k]}</span>`; }).join('');
  return `<div class="pipe">${first}</div>${rank >= 1 || i.stage ? `<div class="pipe">${second}</div>` : ''}`;
}
acts.inviteOpen = async el => {
  const [co, vac, needs, card] = await Promise.all([api('/api/employer/company'), api('/api/employer/vacancies'), api('/api/employer/needs'), api('/api/employer/candidates/' + el.dataset.code)]);
  const open = vac.items.filter(v => v.status === 'published');
  window.INV_SRC = { ...Object.fromEntries(open.map(v => [`v:${v.id}`, { kind: 'v', ...v }])), ...Object.fromEntries(needs.items.map(n => [`n:${n.id}`, { kind: 'n', ...n }])) };
  /* что подставить сразу: потребность, с которой пришли, иначе самая свежая опубликованная вакансия */
  const startKey = el.dataset.need ? `n:${el.dataset.need}` : open.length ? `v:${open[0].id}` : '';
  const start = window.INV_SRC[startKey] || null;
  const srcOpts = (open.length ? `<optgroup label="Вакансии">${open.map(v => `<option value="v:${v.id}" ${startKey === 'v:' + v.id ? 'selected' : ''}>${esc(v.title)}</option>`).join('')}</optgroup>` : '')
    + (needs.items.length ? `<optgroup label="Потребности">${needs.items.map(n => `<option value="n:${n.id}" ${startKey === 'n:' + n.id ? 'selected' : ''}>${esc(n.title)}</option>`).join('')}</optgroup>` : '');
  openModal(`<form data-form="invite" data-code="${esc(el.dataset.code)}" data-need="${esc(el.dataset.need || '')}" class="modal-body invite-form">
    <h2>Приглашение кандидату</h2>
    <div class="inv-who"><span class="code">${esc(card.code)}</span> <b>${esc(card.category.label)}</b> · тест ${card.test_score}%${card.has_fsp ? ' <span class="chip fsp">ФСП</span>' : ''}<div class="small muted">Имя и контакты кандидата откроются, когда он примет приглашение.</div></div>
    <label class="f">Приглашение по вакансии или потребности <span class="hint">данные подставятся автоматически, их можно изменить</span><select name="source" data-onchange="invVac"><option value="">Без привязки — заполню сам</option>${srcOpts}</select></label>
    <label class="f">Должность<input type="text" name="title" value="${esc(start ? start.title : '')}" required minlength="3" maxlength="160"></label>
    <fieldset class="salary-box"><legend>Зарплата в месяц, ₽</legend>
      <div class="grid2">${moneyField('salary_from', 'От', start && start.salary_from || '', 'required placeholder="например, 180 000"')}${moneyField('salary_to', 'До', start && start.salary_to || '', 'required placeholder="например, 260 000"')}</div>
      <p class="small muted" id="salHint" style="margin:0">Укажите диапазон — кандидат увидит его сразу. Можно вводить любые числа.</p></fieldset>
    <label class="f">Что предлагаете<span class="hint">Задачи, команда, условия — коротко и по делу</span><textarea name="description" required minlength="10" rows="5">${esc(start ? srcText(start) : '')}</textarea></label>
    <label class="f">Как с вами связаться<input type="text" name="contact_method" value="${esc(co.contact_method || co.email)}" required></label>
    <div class="row"><button class="btn" type="submit">Отправить приглашение</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
};
const srcText = s => {
  let t = (s.kind === 'v' ? [s.description, s.requirements && 'Требования: ' + s.requirements, s.conditions && 'Условия: ' + s.conditions].filter(Boolean).join('\n\n') : s.team_desc || '').trim();
  if (t.length < 10) {   /* в вакансии или потребности нет описания — собираем текст из того, что заполнено */
    t = [`Приглашаем вас на позицию «${s.title}».`, s.category_label && `Категория: ${s.category_label}.`, (s.stack || []).length && `Технологии: ${s.stack.join(', ')}.`, s.city && `Город: ${s.city}.`].filter(Boolean).join(' ');
  }
  return t.slice(0, 3000);
};
acts.invVac = el => {
  const v = (window.INV_SRC || {})[el.value], f = el.form; if (!v) return;
  f.title.value = v.title;
  if (v.kind === 'v') { f.salary_from.value = nf.format(v.salary_from); f.salary_to.value = nf.format(v.salary_to); }
  f.description.value = srcText(v) || f.description.value;
  salHint(f);
};
function salHint(f) {
  const a = moneyNum(f.salary_from.value), b = moneyNum(f.salary_to.value), h = $('#salHint');
  if (!h) return;
  if (a && b && b < a) { h.textContent = 'Значение «До» не может быть меньше «От».'; h.className = 'small'; h.style.color = 'var(--bad)'; }
  else { h.style.color = ''; h.className = 'small muted'; h.textContent = a && b ? `Кандидат увидит: ${salary(a, b)} в месяц` : 'Укажите диапазон — кандидат увидит его сразу. Можно вводить любые числа.'; }
}
document.addEventListener('input', e => { const f = e.target.form; if (f && f.dataset && f.dataset.form === 'invite' && e.target.name && e.target.name.startsWith('salary_')) salHint(f); });
forms.invite = async (f, d) => {
  const from = moneyNum(d.salary_from), to = moneyNum(d.salary_to);
  if (from < 1000 || to < 1000) { toast('Укажите зарплату «от» и «до» — не меньше 1 000 ₽', 'bad'); return; }
  if (to < from) { toast('Зарплата «до» не может быть меньше «от»', 'bad'); return; }
  const body = { candidate_code: f.dataset.code, title: d.title, description: d.description, contact_method: d.contact_method, salary_from: from, salary_to: to };
  const [kind, id] = (d.source || '').split(':');
  if (kind === 'v') body.vacancy_id = Number(id);
  if (kind === 'n') body.need_id = Number(id);
  if (f.dataset.need && !body.need_id) body.need_id = Number(f.dataset.need);
  await api('/api/employer/invites', { method: 'POST', body });
  closeModal(); toast('Приглашение отправлено', 'ok');
  if (location.hash.startsWith('#/e/candidate')) render();
};

const INV_TABS = { all: 'Все', wait: 'Ждут ответа', accepted: 'Приняли', closed: 'Отклонены и отозваны' };
route(/^\/e\/invites(?:\?.*)?$/, async () => {
  const tab = (location.hash.split('?')[1] || '').replace('tab=', '') || 'all';
  const r = await api('/api/employer/invites');
  const match = i => tab === 'wait' ? ['sent', 'viewed'].includes(i.status) : tab === 'accepted' ? i.status === 'accepted' : tab === 'closed' ? ['declined', 'withdrawn'].includes(i.status) : true;
  const list = r.items.filter(match), cnt = k => r.items.filter(i => k === 'all' || (k === 'wait' ? ['sent', 'viewed'].includes(i.status) : k === 'accepted' ? i.status === 'accepted' : ['declined', 'withdrawn'].includes(i.status))).length;
  if (!r.items.length) return `<div class="page-head"><h1>Приглашения</h1></div>` + empty('Вы пока никого не приглашали', 'Откройте подборку или банк кандидатов и нажмите «Пригласить» у подходящего человека.', '<a class="btn" href="#/e/bank">Банк кандидатов</a>');
  return `<div class="page-head"><div><h1>Приглашения</h1><p class="muted">Следите за этапами: кандидат открыл приглашение, согласился, а дальше вы сами отмечаете, как продвигается работа с ним.</p></div></div>
    <div class="tabs">${Object.entries(INV_TABS).map(([k, t]) => `<a class="tab ${k === tab ? 'on' : ''}" href="#/e/invites?tab=${k}">${t} · ${cnt(k)}</a>`).join('')}</div>
    ${list.length ? list.map(i => `<div class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start"><div><h3 style="margin:0">${esc(i.title)}</h3>
        <div class="small muted"><a class="code" href="#/e/candidate/${esc(i.candidate.code)}">${esc(i.candidate.code)}</a> · ${esc(i.candidate.category ? i.candidate.category.label : '')} · отправлено ${dt(i.created_at)}</div>
        <div class="small src-note">${i.vacancy_title ? 'Вакансия: <b>' + esc(i.vacancy_title) + '</b>' : i.need_title ? 'Потребность: <b>' + esc(i.need_title) + '</b>' : '<span class="muted">Без привязки к вакансии</span>'}</div></div>
        <span class="salary">${salary(i.salary_from, i.salary_to)}</span></div>
      ${pipeline(i)}
      ${i.stage ? `<p class="small" style="margin:0">Сейчас: <b>${esc(STAGES[i.stage])}</b>${i.stage_at ? ' с ' + dt(i.stage_at) : ''}${(i.stage_log[i.stage_log.length - 1] || {}).note ? ' — «' + esc(i.stage_log[i.stage_log.length - 1].note) + '»' : ''}</p>` : ''}
      ${i.candidate.contacts ? `<p class="small"><b>${esc(i.candidate.contacts.full_name)}</b> · ${esc(i.candidate.contacts.email)}${i.candidate.contacts.phone ? ' · ' + esc(i.candidate.contacts.phone) : ''}</p>` : '<p class="small muted">Контакты откроются после согласия кандидата.</p>'}
      <div class="row">${!['declined', 'withdrawn'].includes(i.status) ? `<button class="btn small" data-act="stageOpen" data-id="${i.id}" data-stage="${esc(i.stage)}" data-vac="${i.vacancy_id || ''}">Сменить этап</button>` : ''}
        <a class="btn ghost small" href="#/e/candidate/${esc(i.candidate.code)}">Карточка кандидата</a>
        ${['sent', 'viewed'].includes(i.status) ? `<button class="btn danger small" data-act="withdraw" data-id="${i.id}">Отозвать</button>` : ''}
        ${i.status === 'withdrawn' ? `<button class="btn ok small" data-act="restoreInvite" data-id="${i.id}">Вернуть приглашение</button>` : ''}
        <button class="btn danger small" data-act="purgeInvite" data-id="${i.id}" style="margin-left:auto" title="Удалить без возможности вернуть">Удалить кандидата</button></div></div>`).join('') : empty('Здесь пусто', 'В этом разделе приглашений нет.')}`;
}, 'employer');
acts.stageOpen = async el => {
  /* если приглашение не привязано к вакансии, для этапа «Принят на работу» нужно выбрать вакансию */
  const vac = el.dataset.vac ? { items: [] } : await api('/api/employer/vacancies');
  openModal(`<form data-form="stage" data-id="${esc(el.dataset.id)}" class="modal-body"><h2>Этап работы с кандидатом</h2>
  <p class="muted small">Кандидат увидит этап и ваш комментарий в своих приглашениях.</p>
  <div class="f">${Object.entries(STAGES).map(([k, t]) => `<label class="choice"><input type="radio" name="stage" value="${k}" ${el.dataset.stage === k ? 'checked' : ''} required><b>${t}</b></label>`).join('')}</div>
  ${vac.items.length ? `<label class="f">Вакансия, на которую принят кандидат <span class="hint">Нужна для этапа «Принят на работу»: кандидат появится в откликах этой вакансии</span><select name="vacancy_id"><option value="">Выберите вакансию</option>${vac.items.map(v => `<option value="${v.id}">${esc(v.title)}</option>`).join('')}</select></label>` : ''}
  <label class="f">Комментарий (по желанию)<input type="text" name="note" maxlength="500" placeholder="Например: созвон в четверг в 15:00"></label>
  <div class="row"><button class="btn" type="submit">Сохранить этап</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
};
forms.stage = async (f, d) => {
  const body = { stage: d.stage, note: d.note || '' };
  if (d.vacancy_id) body.vacancy_id = Number(d.vacancy_id);
  const r = await api(`/api/employer/invites/${f.dataset.id}/stage`, { method: 'POST', body });
  closeModal(); toast(r.placed_in_vacancy ? `Кандидат принят и добавлен в отклики вакансии «${r.placed_in_vacancy}»` : 'Этап обновлён', 'ok'); render();
};
acts.restoreInvite = async el => { await api(`/api/employer/invites/${el.dataset.id}/restore`, { method: 'POST' }); toast('Приглашение возвращено — кандидат увидит его снова', 'ok'); render(); };
acts.purgeInvite = async el => {
  if (!(await confirmBox('Удалить кандидата?', 'Приглашение будет удалено навсегда, вернуть его не получится. Кандидат больше не увидит его у себя.', 'Удалить', true))) return;
  await api(`/api/employer/invites/${el.dataset.id}/permanent`, { method: 'DELETE' }); toast('Кандидат удалён из приглашений'); render();
};
acts.withdraw = async el => { if (!(await confirmBox('Отозвать приглашение?', 'Кандидат больше не сможет его принять.', 'Отозвать', true))) return; await api('/api/employer/invites/' + el.dataset.id, { method: 'DELETE' }); toast('Приглашение отозвано'); render(); };

/* ---------- отклики на вакансии (список вакансий и редактор — extra.js) ---------- */
acts.loadApps = async el => {
  const box = $('#apps' + el.dataset.id);
  const r = await api(`/api/employer/vacancies/${el.dataset.id}/applications`);
  box.innerHTML = r.items.length ? `<table class="t"><thead><tr><th>Кандидат</th><th>Профиль</th><th>Статус</th><th></th></tr></thead><tbody>${r.items.map(a => {
    const c = a.candidate, ct = c.contacts;
    return `<tr><td><b>${esc(ct ? ct.full_name : c.code)}</b><div class="small">${ct ? esc(ct.email) + (ct.phone ? '<br>' + esc(ct.phone) : '') : ''}</div>${a.message ? `<div class="small muted">«${esc(a.message)}»</div>` : ''}</td>
      <td>${c.category ? `${esc(c.category.label)}, тест ${c.test_score}%${c.has_fsp ? ' <span class="chip fsp">ФСП</span>' : ''}${c.match ? `<div class="small muted">соответствие вакансии: ${c.match.score}</div>` : ''}` : '<span class="muted">без категории</span>'}</td>
      <td>${stat(a.status)}</td>
      <td class="row">${[['hired', 'Принят', ' ok'], ['rejected', 'Отказ', '']].map(([s, t, k]) => `<button class="btn ghost small${k}${a.status === s ? ' on' : ''}" data-act="appStatus" data-id="${a.id}" data-s="${s}" data-v="${el.dataset.id}">${t}</button>`).join('')}<button class="btn danger small" data-act="appDelete" data-id="${a.id}" data-v="${el.dataset.id}">Удалить</button></td></tr>`;
  }).join('')}</tbody></table>` : '<p class="muted">Откликов пока нет.</p>';
};
acts.appDelete = async el => {
  if (!(await confirmBox('Удалить отклик?', 'Кандидат исчезнет из откликов этой вакансии. Это действие нельзя отменить.', 'Удалить', true))) return;
  await api(`/api/employer/applications/${el.dataset.id}`, { method: 'DELETE' }); toast('Отклик удалён'); await acts.loadApps({ dataset: { id: el.dataset.v } });
};
acts.appStatus = async el => { await api(`/api/employer/applications/${el.dataset.id}/status`, { method: 'POST', body: { status: el.dataset.s } }); toast('Статус обновлён', 'ok'); await acts.loadApps({ dataset: { id: el.dataset.v } }); };

/* ---------- регулярные задания ---------- */
route(/^\/e\/tasks$/, async () => {
  const r = await api('/api/employer/microtasks');
  return `<div class="page-head"><div><h1>Задания для кандидатов</h1><p class="muted">Короткие задачи от вашей команды. Система сама предлагает их кандидатам подходящей категории, вы получаете свежий сигнал об их уровне.</p></div>
    <button class="btn" data-act="taskForm">Новое задание</button></div>
    ${r.items.length ? r.items.map(t => `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t.title)}</h3><span class="chip">${t.fsp_ids && t.fsp_ids.length ? 'Адресное' : esc(catName(t.spec, t.grade))}</span></div>
      ${t.fsp_ids && t.fsp_ids.length ? `<p class="small muted" style="margin:6px 0 0">Отправлено по FSP ID: ${t.fsp_ids.map(x => `<span class="chip dim">${esc(x)}</span>`).join(' ')}</p>` : ''}
      <p style="margin-top:8px">${esc(t.body).replace(/\n/g, '<br>')}</p><p class="small muted">Назначено: ${t.assigned} · ответили: ${t.answered}</p>
      <button class="btn small ghost" data-act="loadSubs" data-id="${t.id}">Показать ответы</button><div id="subs${t.id}" style="margin-top:10px"></div></div>`).join('')
      : empty('Заданий пока нет', 'Создайте задание — например, небольшой кейс из вашей практики. Кандидаты ответят текстом: решением или подходом.')}`;
}, 'employer');
acts.taskForm = () => openModal(`<form data-form="task"><h2>Новое задание</h2>
  <label class="f">Название<input type="text" name="title" required minlength="3"></label>
  <label class="f">Условие<textarea name="body" required minlength="10" placeholder="Например: как бы вы реализовали идемпотентность платёжного API?"></textarea></label>
  <div class="grid3"><label class="f">Специализация<select name="spec">${opts(specTitles(), 'backend')}</select></label><label class="f">Грейд<select name="grade">${opts(gradeTitles(), 'middle')}</select></label>
  <label class="f">Что требуется<select name="kind"><option value="approach">Предложить подход</option><option value="solve">Решить задачу</option></select></label></div>
  <label class="f">Кому отправить — FSP ID <span class="hint">Необязательно. Один или несколько через запятую или пробел, например FSP-100001. Пусто — задание получат кандидаты выбранной категории. Адресат должен привязать FSP ID в профиле.</span><input type="text" name="fsp_ids" placeholder="FSP-100001, FSP-100002" autocomplete="off"></label>
  <div class="row"><button class="btn" type="submit">Создать</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
forms.task = async (f, d) => {
  const r = await api('/api/employer/microtasks', { method: 'POST', body: { ...d, fsp_ids: (d.fsp_ids || '').split(/[\s,;]+/).filter(Boolean) } });
  if (r.not_found && r.not_found.length) { closeModal(); toast(`Задание создано. Не нашли кандидатов с FSP ID: ${r.not_found.join(', ')} — они не привязали ID в профиле`, 'bad'); render(); return; }
  closeModal(); toast(r.delivered && r.delivered.length ? `Задание отправлено кандидатам: ${r.delivered.length}` : 'Задание создано', 'ok'); render();
};
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
forms.company = async (f, d) => { await api('/api/employer/company', { method: 'PUT', body: d }); S.user.name = d.company_name; drawNav(location.hash.slice(1)); toast('Профиль компании сохранён', 'ok'); };
acts.deleteAccount = acts.deleteAccount || (async () => {
  const pw = prompt('Удаление необратимо. Введите пароль для подтверждения:'); if (!pw) return;
  await api('/api/auth/account', { method: 'DELETE', body: { password: pw } }); logout(true); toast('Аккаунт удалён');
});


