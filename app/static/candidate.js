/* Личный кабинет «Кандидат» */
'use strict';

document.addEventListener('change', e => { const a = e.target.dataset && e.target.dataset.onchange; if (a && acts[a]) acts[a](e.target, e); });
const me = () => api('/api/candidate/me');

/* ---------- обзор ---------- */
const TOPIC_RU = { algorithms: 'Алгоритмы', backend_arch: 'Архитектура бэкенда', css: 'HTML и CSS', devops: 'DevOps', javascript: 'JavaScript', linux: 'Linux', ml: 'Машинное обучение', networks: 'Сети', python: 'Python', qa_theory: 'Теория тестирования', sql: 'SQL', statistics: 'Статистика', web: 'Веб и HTTP' };
route(/^\/c$/, async () => {
  const s = await me();
  const cat = s.category;
  const step = (n, done, title, desc, link, label) => `<li class="${done ? 'done' : ''}" data-step="${n}">
      <span class="dot">${done ? '✓' : n}</span><div><div class="t">${title}</div><div class="d">${desc}</div></div>
      ${link ? `<a class="btn ${done ? 'ghost' : ''} small" href="${link}">${label}</a>` : ''}</li>`;
  const st = s.steps;
  const nextIdx = [st.profile, st.survey && st.test, st.publish].findIndex(x => !x);
  const rail = `<ol class="rail">
    ${step(1, st.profile, 'Профиль и резюме', 'ФИО, контакты, стек, опыт — вручную или из PDF. Эти данные видны вам, но не влияют на категорию.', '#/c/profile', st.profile ? 'Изменить' : 'Заполнить')}
    ${step(2, st.survey && st.test, 'Опрос и тест на грейд', 'Определяют вашу категорию — именно её видит работодатель. Тест уникален для каждой попытки.', '#/c/test', st.test ? 'Подробнее' : 'Пройти')}
    ${step(3, st.publish, 'Согласие на публикацию', 'Без него работодатели вас не увидят. Что именно показывать, решаете вы.', '#/c/settings', st.publish ? 'Настройки' : 'Разрешить')}
    ${step(4, s.fsp.linked, 'ФСП ID (по желанию)', 'Достижения в соревнованиях ФСП поднимают вас выше в подборке. Без них вы тоже в подборке.', '#/c/settings', s.fsp.linked ? 'Подробнее' : 'Привязать')}
  </ol>`;
  const catPanel = cat.grade ? `
    <div class="panel tint">
      <div class="row" style="justify-content:space-between;align-items:flex-start">
        <div><h2 style="margin-bottom:4px">${esc(cat.label)}</h2>
          <p class="muted" style="margin:0">Присвоена ${dd(cat.assigned_at)}. ${s.visible_to_employers ? 'Работодатели видят вас в банке кандидатов.' : '<b>Вас пока не видят работодатели</b> — включите публикацию в настройках.'}</p></div>
        <div class="score-big">${cat.score_pct}<small>%</small></div>
      </div>
      <p style="margin:14px 0 4px"><b>Подтверждено тестом:</b> ${s.stack_confirmed.length ? chips(s.stack_confirmed, 'ok') : '<span class="muted">пока ничего — выполните задания по нужным темам</span>'}</p>
      ${s.fsp.summary ? `<p style="margin:6px 0 0"><b>ФСП:</b> ${s.fsp.summary.events_count} мероприятий, лучший результат — топ-${s.fsp.summary.best_top_percent}% (${esc(s.fsp.summary.best_event)})</p>`
        : '<p class="muted" style="margin:6px 0 0">История участия в ФСП не найдена — это не мешает попадать в подборки.</p>'}
    </div>` : `<div class="notice">Категория пока не присвоена. Пройдите опрос и тест — это обязательный шаг, после него работодатели смогут вас найти.</div>`;
  return `<div class="page-head"><div><h1>${esc(s.profile.full_name || 'Добро пожаловать')}</h1><p class="muted">Ваш код для работодателей: <span class="code">${esc(s.code)}</span></p></div></div>
    ${catPanel}<div class="panel"><h2>Путь кандидата</h2>${rail}</div>`;
}, 'candidate');

/* ---------- профиль ---------- */
route(/^\/c\/profile$/, async () => {
  const s = await me(), p = s.profile;
  return `<div class="page-head"><div><h1>Профиль и резюме</h1><p class="muted">Эти данные заполняете вы. Категорию и ранжирование определяют результаты теста и данные ФСП, а не этот текст.</p></div>
      <div class="row"><button class="btn ghost" data-act="pdfDownload">Скачать PDF-профиль</button></div></div>
    <div class="panel tint"><h3>Заполнить из PDF</h3>
      <p class="small muted">Загрузите резюме в PDF — мы предзаполним форму. Ничего не сохраняется, пока вы не нажмёте «Сохранить профиль».</p>
      <input type="file" id="cvfile" accept="application/pdf" data-onchange="parseCv"></div>
    <form class="panel" data-form="profile" id="profileForm">
      <div class="grid2"><label class="f">ФИО<input type="text" name="full_name" value="${esc(p.full_name)}" required></label>
        <label class="f">Телефон<input type="text" name="phone" value="${esc(p.phone)}" placeholder="+7 900 000-00-00"></label></div>
      <div class="grid2"><label class="f">Город<input type="text" name="city" value="${esc(p.city)}"></label>
        <label class="f">Стаж, лет<input type="number" name="experience_years" min="0" max="50" step="0.5" value="${p.experience_years}"></label></div>
      <label class="f">Заголовок профиля<input type="text" name="headline" value="${esc(p.headline)}" placeholder="Например: Backend-разработчик, Python"></label>
      <label class="f">О себе<textarea name="about">${esc(p.about)}</textarea></label>
      <label class="f">Роли и места работы<span class="hint">По одной в строке</span><textarea name="roles">${esc((p.roles || []).join('\n'))}</textarea></label>
      <label class="f">Стек (заявленный)<span class="hint">Через запятую. В подборке отдельно отмечается, что из него подтверждено тестом.</span>
        <input type="text" name="stack_declared" value="${esc((p.stack_declared || []).join(', '))}"></label>
      <fieldset style="border:0;padding:0;margin:0 0 14px"><legend style="font-weight:600;font-size:.92rem;margin-bottom:6px">Софт-скиллы</legend>
        ${S.tax.soft_skills.map(k => `<label class="check" style="display:inline-flex;margin-right:16px"><input type="checkbox" name="soft_${esc(k)}" ${(p.soft_skills || []).includes(k) ? 'checked' : ''}><span>${esc(k)}</span></label>`).join('')}</fieldset>
      <button class="btn" type="submit">Сохранить профиль</button>
    </form>`;
}, 'candidate');
forms.profile = async (f, d) => {
  const body = {
    full_name: d.full_name, phone: d.phone, city: d.city, headline: d.headline, about: d.about, experience_years: d.experience_years || 0,
    roles: d.roles.split('\n').map(x => x.trim()).filter(Boolean).slice(0, 8), stack_declared: csv(d.stack_declared),
    soft_skills: S.tax.soft_skills.filter(k => d['soft_' + k]),
  };
  await api('/api/candidate/profile', { method: 'PUT', body });
  toast('Профиль сохранён', 'ok');
};
acts.parseCv = async el => {
  const file = el.files[0]; if (!file) return;
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await api('/api/candidate/resume/parse', { method: 'POST', form: fd });
    const f = $('#profileForm');
    const set = (n, v) => { const i = $(`[name=${n}]`, f); if (i && v) i.value = v; };
    set('full_name', r.full_name); set('phone', r.phone); set('experience_years', r.experience_years || '');
    set('stack_declared', (r.stack_declared || []).join(', ')); set('roles', (r.roles || []).join('\n'));
    $$('input[name^=soft_]', f).forEach(c => { c.checked = (r.soft_skills || []).includes(c.name.slice(5)); });
    toast('Данные распознаны. Проверьте форму и сохраните профиль.', 'ok');
  } catch (e) { fail(e); } finally { el.value = ''; }
};
acts.pdfDownload = async () => {
  const b = await api('/api/candidate/profile.pdf', { blob: true });
  const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'profile.pdf'; a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};

/* ---------- опрос, тест, история ---------- */
const stackBoxes = (spec, picked) => (S.tax.stack[spec] || []).map(t => `<label class="check" style="display:inline-flex;margin-right:16px"><input type="checkbox" name="stack" value="${esc(t)}" ${picked.includes(t) ? 'checked' : ''}><span>${esc(t)}</span></label>`).join('');
route(/^\/c\/test$/, async () => {
  const [s, h] = await Promise.all([me(), api('/api/candidate/tests')]);
  const sv = s.survey || {}, spec0 = sv.spec || 'backend';
  const survey = `<form class="panel" data-form="survey"><h2>Опрос по отрасли и специализации</h2>
      <label class="f">Отрасль, в которой вам интереснее работать<select name="industry">${S.tax.industries.map(i => `<option ${i === sv.industry ? 'selected' : ''}>${esc(i)}</option>`).join('')}</select></label>
      <label class="f">Специализация<select name="spec" data-onchange="surveySpec">${opts(Object.fromEntries(Object.entries(S.tax.specs).map(([k, v]) => [k, v.title])), spec0)}</select></label>
      <div class="f"><b style="font-size:.92rem">Технологии, с которыми вы работаете</b><div id="stackBoxes" style="margin-top:6px">${stackBoxes(spec0, sv.stack || [])}</div></div>
      <div class="f"><b style="font-size:.92rem">Каким грейдом вы себя считаете?</b><div style="margin-top:8px">
        ${Object.entries(S.tax.grades).map(([k, g]) => `<label class="choice"><input type="radio" name="grade" value="${k}" ${(sv.grade || 'junior') === k ? 'checked' : ''}><b>${esc(g.title)}</b> <span class="muted">— ${esc(g.hint)}</span></label>`).join('')}</div></div>
      <label class="f">Предпочтительный формат работы<select name="format">${opts(S.tax.work_formats, sv.format || 'remote')}</select></label>
      <button class="btn" type="submit">${s.steps.survey ? 'Обновить ответы' : 'Сохранить и перейти к тесту'}</button></form>`;
  const gc = s.grade_change;
  const startBlock = !s.steps.survey ? `<div class="notice">Сначала ответьте на вопросы опроса — тест подбирается под вашу специализацию и заявленный грейд.</div>` : `
    <div class="panel"><h2>Тест на грейд</h2>
      ${s.category.grade ? `<div class="notice ${gc.allowed ? '' : 'warn'}">Ваша категория: <b>${esc(s.category.label)}</b>. ${gc.allowed ? 'Вы можете пройти тест на другой грейд.' : `Сменить грейд или специализацию можно не чаще одного раза в ${s.cooldown_days} дней — следующая попытка через ${gc.days_left} дн. (${dd(gc.next_allowed_at)}). Пересдать свой текущий грейд можно в любой момент.`}</div>`
        : '<div class="notice">Тест определит вашу категорию. Если не получится на заявленном уровне — можно сразу пройти тест на уровень ниже: грейд не понижается принудительно.</div>'}
      <p class="muted">12 заданий, ${40} минут. Задания генерируются под вашу попытку: данные и числа уникальны, сложность для вашего грейда одинакова для всех. Зачёт — не менее 65% баллов и половина заданий вашего уровня.</p>
      <form class="row" data-form="startTest" style="align-items:flex-end">
        <label class="f" style="margin:0;min-width:220px">Специализация<select name="spec">${opts(Object.fromEntries(Object.entries(S.tax.specs).map(([k, v]) => [k, v.title])), s.category.spec || sv.spec)}</select></label>
        <label class="f" style="margin:0;min-width:180px">Грейд<select name="grade">${opts(Object.fromEntries(Object.entries(S.tax.grades).map(([k, g]) => [k, g.title])), sv.grade || s.category.grade)}</select></label>
        <button class="btn" type="submit">Начать тест</button></form></div>`;
  const hist = h.items.length ? `<div class="panel"><h2>История попыток</h2><table class="t"><thead><tr><th>Дата</th><th>Категория</th><th>Результат</th><th></th></tr></thead><tbody>
      ${h.items.map(i => `<tr><td>${dt(i.started_at)}</td><td>${esc(catName(i.spec, i.grade))}</td><td>${i.score_pct == null ? stat('assigned') : `${i.score_pct}% <span class="status ${i.passed ? 'passed' : 'failed'}">${i.passed ? 'зачёт' : 'не зачтено'}</span>`}</td>
      <td><a href="#/c/${i.status === 'active' ? 'test' : 'result'}/${i.id}">${i.status === 'active' ? 'Продолжить' : 'Разбор'}</a></td></tr>`).join('')}</tbody></table>
      ${h.grade_history.length ? `<h3 style="margin-top:18px">Смены категории</h3>${h.grade_history.map(g => `<p class="small" style="margin:0 0 4px">${dd(g.at)}: ${g.old_grade ? gradeName(g.old_grade) + ' → ' : 'присвоена '}<b>${esc(catName(g.spec, g.new_grade))}</b></p>`).join('')}` : ''}</div>` : '';
  return `<div class="page-head"><div><h1>Тест и категория</h1><p class="muted">Обязательный путь: опрос, выбор грейда, тест. Результат автоматически определяет категорию, видимую работодателю.</p></div></div>${survey}${startBlock}${hist}`;
}, 'candidate');
acts.surveySpec = el => { $('#stackBoxes').innerHTML = stackBoxes(el.value, []); };
forms.survey = async (f, d) => {
  const stack = $$('input[name=stack]:checked', f).map(i => i.value).slice(0, 8);
  await api('/api/candidate/survey', { method: 'POST', body: { industry: d.industry, spec: d.spec, grade: d.grade, format: d.format, stack } });
  toast('Ответы сохранены', 'ok'); render();
};
forms.startTest = async (f, d) => {
  const a = await api('/api/candidate/tests', { method: 'POST', body: { spec: d.spec, grade: d.grade } });
  location.hash = '#/c/test/' + a.id;
};
acts.startNext = async el => {
  const a = await api('/api/candidate/tests', { method: 'POST', body: { spec: el.dataset.spec, grade: el.dataset.grade } });
  location.hash = '#/c/test/' + a.id;
};

/* ---------- прохождение теста ---------- */
let RUN = null;
route(/^\/c\/test\/(\d+)$/, async m => {
  const a = await api('/api/candidate/tests/' + m[1]);
  if (a.state !== 'active') { location.hash = '#/c/result/' + m[1]; return ''; }
  let saved = null; try { saved = JSON.parse(sessionStorage.getItem('run_' + a.id) || 'null'); } catch (_) { /* пусто */ }
  RUN = { id: a.id, q: a.questions, ans: (saved && saved.ans) || {}, idx: (saved && saved.idx) || 0, blur: (saved && saved.blur) || 0, deadline: new Date(a.deadline_at).getTime(), spec: a.spec, grade: a.grade, sending: false };
  return {
    html: `<div class="page-head"><div><h1>Тест: ${esc(catName(a.spec, a.grade))}</h1><p class="muted">Не закрывайте вкладку: переключения на другие окна фиксируются.</p></div>
      <div class="timer" id="timer" aria-live="off"></div></div>
      <div class="panel"><div class="strip" id="strip"></div></div>
      <div class="panel" id="qpanel"></div>`,
    after: runnerStart,
  };
}, 'candidate');
function runnerSave() { if (RUN) sessionStorage.setItem('run_' + RUN.id, JSON.stringify({ ans: RUN.ans, idx: RUN.idx, blur: RUN.blur })); }
function runnerStart() {
  drawQuestion();
  const tick = () => {
    if (!RUN || !$('#timer')) { clearInterval(RUN && RUN.timer); return; }
    const left = Math.max(0, Math.round((RUN.deadline - Date.now()) / 1000));
    const t = $('#timer'); t.textContent = `${String(Math.floor(left / 60)).padStart(2, '0')}:${String(left % 60).padStart(2, '0')}`;
    t.classList.toggle('low', left < 300);
    if (left <= 0 && !RUN.sending) { toast('Время вышло — ответы отправляются', 'bad'); finishRun(); }
  };
  tick(); RUN.timer = setInterval(tick, 1000);
}
document.addEventListener('visibilitychange', () => { if (RUN && document.hidden && $('#timer')) { RUN.blur++; runnerSave(); } });
function drawQuestion() {
  const q = RUN.q[RUN.idx], last = RUN.idx === RUN.q.length - 1;
  $('#strip').innerHTML = RUN.q.map((x, i) => `<button class="cell ${i === RUN.idx ? 'current' : RUN.ans[x.id] != null && RUN.ans[x.id] !== '' ? 'answered' : ''}" data-act="goQ" data-i="${i}" aria-label="Задание ${i + 1}">${i + 1}</button>`).join('');
  const val = RUN.ans[q.id];
  const input = q.kind === 'choice'
    ? q.options.map((o, i) => `<label class="choice"><input type="radio" name="a" value="${i}" ${val === i ? 'checked' : ''} data-onchange="setAns"> ${esc(o)}</label>`).join('')
    : `<label class="f" style="max-width:280px">Ваш ответ<input type="text" inputmode="decimal" name="a" value="${esc(val ?? '')}" autocomplete="off" data-oninput="1"><span class="hint">${esc(q.hint)}</span></label>`;
  $('#qpanel').innerHTML = `<h3>Задание ${q.n} из ${RUN.q.length}</h3><div class="q-body">${md(q.prompt)}</div><div style="margin-top:14px">${input}</div>
    <div class="row" style="margin-top:18px;justify-content:space-between">
      <button class="btn ghost" data-act="prevQ" ${RUN.idx === 0 ? 'disabled' : ''}>Назад</button>
      ${last ? '<button class="btn ok" data-act="finishRun">Завершить и отправить</button>' : '<button class="btn" data-act="nextQ">Дальше</button>'}</div>`;
  const num = $('#qpanel input[type=text]'); if (num) num.addEventListener('input', () => { RUN.ans[q.id] = num.value; runnerSave(); $('#strip .current').classList.add('answered'); });
}
acts.setAns = el => { const q = RUN.q[RUN.idx]; RUN.ans[q.id] = Number(el.value); runnerSave(); const cur = $('#strip .current'); if (cur) cur.classList.add('answered'); };
acts.goQ = el => { RUN.idx = Number(el.dataset.i); runnerSave(); drawQuestion(); };
acts.nextQ = () => { RUN.idx = Math.min(RUN.q.length - 1, RUN.idx + 1); runnerSave(); drawQuestion(); };
acts.prevQ = () => { RUN.idx = Math.max(0, RUN.idx - 1); runnerSave(); drawQuestion(); };
async function finishRun() {
  if (!RUN || RUN.sending) return;
  const unanswered = RUN.q.filter(q => RUN.ans[q.id] == null || RUN.ans[q.id] === '').length;
  if (unanswered && RUN.deadline - Date.now() > 0 && !confirm(`Без ответа осталось заданий: ${unanswered}. Отправить тест?`)) return;
  RUN.sending = true; clearInterval(RUN.timer);
  try {
    const r = await api(`/api/candidate/tests/${RUN.id}/finish`, { method: 'POST', body: { answers: RUN.ans, blur_count: RUN.blur } });
    sessionStorage.removeItem('run_' + RUN.id); RUN = null;
    location.hash = '#/c/result/' + r.id;
  } catch (e) { RUN.sending = false; fail(e); }
}
acts.finishRun = () => finishRun();

/* ---------- результат ---------- */
route(/^\/c\/result\/(\d+)$/, async m => {
  const r = await api('/api/candidate/tests/' + m[1]);
  if (r.state === 'active') { location.hash = '#/c/test/' + m[1]; return ''; }
  const o = r.outcome || {};
  const nextBtn = (x, label) => `<button class="btn ghost" data-act="startNext" data-spec="${esc(r.spec)}" data-grade="${esc(x.grade)}">${label}: ${esc(x.label)}</button>`;
  const topics = Object.entries(r.topics || {});
  return `<div class="page-head"><div><h1>Результат: ${esc(catName(r.spec, r.grade))}</h1><p class="muted">${dt(r.finished_at)}</p></div><a class="btn ghost" href="#/c">К обзору</a></div>
    <div class="panel ${r.passed ? 'tint' : ''}">
      <div class="row" style="gap:28px;align-items:center"><div class="score-big">${r.score_pct}<small>%</small></div>
        <div><span class="status ${r.passed ? 'passed' : 'failed'}" style="font-size:1rem">${r.passed ? 'Зачтено' : 'Не зачтено'}</span>
          <p style="margin:8px 0 0">${esc(o.message || '')}</p>
          ${o.new_category ? `<p style="margin:4px 0 0"><b>Категория: ${esc(o.new_category.label)}</b></p>` : ''}</div></div>
      <div class="row" style="margin-top:14px">${o.can_try_higher ? nextBtn(o.can_try_higher, 'Уверенный результат — попробовать грейд выше') : ''}${o.suggest_lower ? nextBtn(o.suggest_lower, 'Пройти тест на уровень ниже') : ''}</div>
      ${o.integrity_review ? '<div class="notice warn" style="margin:14px 0 0">Прохождение отмечено для проверки: слишком быстрые ответы или частые переключения вкладок. Результат засчитан, но вес вашего профиля в подборках снижен.</div>' : ''}</div>
    <div class="panel"><h2>Задания</h2><div class="strip" style="margin-bottom:14px">${r.detail.map((d, i) => `<span class="cell ${d.ok ? 'good' : 'miss'}" title="Уровень ${d.level}">${i + 1}</span>`).join('')}</div>
      ${topics.length ? '<h3>По темам</h3>' + topics.map(([t, v]) => `<div class="factor"><span>${esc(TOPIC_RU[t] || t)}</span><div>${bar(100 * v.c / v.n, v.c === v.n ? 'ok' : '')}<span class="small muted">${v.c} из ${v.n}</span></div></div>`).join('') : ''}</div>
    <div class="panel"><h2>Разбор</h2><p class="muted small">Каждая попытка уникальна, поэтому правильные ответы показываем сразу — это помогает учиться и ничего не раскрывает другим.</p>
      ${r.detail.map((d, i) => `<details class="invite"><summary style="grid-template-columns:44px 1fr auto"><span class="cell ${d.ok ? 'good' : 'miss'}">${i + 1}</span><span>${esc((l => l.length > 90 ? l.slice(0, 88).trimEnd() + '…' : l)(d.prompt.split('\n')[0]))}</span><span class="chip">уровень ${d.level}</span></summary>
        <div class="body"><div class="q-body">${md(d.prompt)}</div>
        <p><b>Ваш ответ:</b> ${d.given == null || d.given === '' ? '<span class="muted">нет ответа</span>' : d.options ? esc(d.options[d.given] ?? '') : esc(d.given)}<br>
        <b>Верно:</b> ${d.options ? esc(d.options[d.correct]) : esc(d.correct)}</p></div></details>`).join('')}</div>`;
}, 'candidate');

/* ---------- приглашения ---------- */
route(/^\/c\/invites$/, async () => {
  const r = await api('/api/candidate/invites');
  if (!r.items.length) return `<div class="page-head"><h1>Приглашения</h1></div>` + empty('Приглашений пока нет', 'Работодатели увидят вас в банке кандидатов, когда у вас есть категория и включена публикация профиля. Тем временем можно <a href="#/c/vacancies">откликнуться на вакансии</a>.');
  return `<div class="page-head"><div><h1>Приглашения</h1><p class="muted">Условия видны сразу. Контакты работодатель получит, только если вы примете приглашение.</p></div></div>
    ${r.items.map(i => `<details class="invite" data-id="${i.id}" data-onopen="${i.status === 'sent' ? 1 : 0}">
      <summary><div><b>${esc(i.title)}</b><div class="muted small">${esc(i.company.name)}${i.company.industry ? ', ' + esc(i.company.industry) : ''} · ${dt(i.created_at)}</div></div>
        <span class="salary">${salary(i.salary_from, i.salary_to)}</span>${stat(i.status)}</summary>
      <div class="body"><p>${esc(i.description).replace(/\n/g, '<br>')}</p>
        ${i.company.description ? `<p class="muted small"><b>О компании:</b> ${esc(i.company.description)}</p>` : ''}
        <p class="small"><b>Способ связи:</b> ${esc(i.contact_method)}</p>
        ${['sent', 'viewed'].includes(i.status) ? `<div class="row"><button class="btn ok" data-act="decide" data-id="${i.id}" data-d="accept">Принять и открыть контакты</button><button class="btn danger" data-act="decide" data-id="${i.id}" data-d="decline">Отклонить</button></div>` : ''}</div></details>`).join('')}`;
}, 'candidate');
document.addEventListener('toggle', async e => {
  const d = e.target;
  if (d.matches && d.matches('details.invite[data-onopen="1"]') && d.open) {
    d.dataset.onopen = '0';
    try { await api('/api/candidate/invites/' + d.dataset.id); refreshBadge(); } catch (_) { /* не критично */ }
  }
}, true);
acts.decide = async el => {
  if (el.dataset.d === 'accept' && !confirm('Работодатель увидит ваши ФИО, e-mail и телефон. Принять приглашение?')) return;
  await api(`/api/candidate/invites/${el.dataset.id}/decision`, { method: 'POST', body: { decision: el.dataset.d } });
  toast(el.dataset.d === 'accept' ? 'Приглашение принято, контакты переданы' : 'Приглашение отклонено', 'ok');
  refreshBadge(); render();
};

/* ---------- вакансии и отклики ---------- */
route(/^\/c\/vacancies$/, async () => {
  const [v, a] = await Promise.all([api('/api/candidate/vacancies'), api('/api/candidate/applications')]);
  return `<div class="page-head"><div><h1>Вакансии</h1><p class="muted">Дополнительный путь: можно откликнуться самому, пока нет приглашений. Первыми показаны вакансии вашей категории.</p></div></div>
    ${v.items.length ? v.items.map(i => `<div class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start">
      <div><h3 style="margin-bottom:2px">${esc(i.title)}</h3><div class="muted small">${esc(i.company.name)} · ${esc(i.category_label)} · ${dt(i.created_at)}</div></div>
      <span class="salary">${salary(i.salary_from, i.salary_to)}</span></div>
      <p style="margin-top:10px">${esc(i.description).replace(/\n/g, '<br>')}</p>
      <div>${chips(i.stack)}${i.fit >= 1 ? '<span class="chip ok">ваша категория</span>' : ''}</div>
      <div class="row" style="margin-top:12px">${i.my_application ? stat(i.my_application) : `<button class="btn" data-act="applyOpen" data-id="${i.id}" data-title="${esc(i.title)}">Откликнуться</button>`}</div></div>`).join('')
      : empty('Открытых вакансий пока нет', 'Загляните позже — работодатели публикуют вакансии с обязательной вилкой зарплаты.')}
    ${a.items.length ? `<div class="panel"><h2>Мои отклики</h2><table class="t"><thead><tr><th>Вакансия</th><th>Компания</th><th>Статус</th><th>Обновлён</th></tr></thead><tbody>${a.items.map(x => `<tr><td>${esc(x.title)}</td><td>${esc(x.company)}</td><td>${stat(x.status)}</td><td>${dt(x.updated_at)}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
}, 'candidate');
acts.applyOpen = el => openModal(`<form data-form="apply" data-id="${esc(el.dataset.id)}"><h2>Отклик: ${esc(el.dataset.title)}</h2>
  <div class="notice warn">Отклик раскрывает работодателю ваши ФИО, e-mail и телефон.</div>
  <label class="f">Сообщение (по желанию)<textarea name="message"></textarea></label>
  <div class="row"><button class="btn" type="submit">Отправить отклик</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
forms.apply = async (f, d) => { await api(`/api/candidate/vacancies/${f.dataset.id}/apply`, { method: 'POST', body: { message: d.message } }); closeModal(); toast('Отклик отправлен', 'ok'); render(); };

/* ---------- регулярные задания ---------- */
route(/^\/c\/tasks$/, async () => {
  const r = await api('/api/candidate/microtasks');
  return `<div class="page-head"><div><h1>Задания от работодателей</h1><p class="muted">Короткие задачи: решите их или опишите свой подход. Ответы поддерживают профиль в актуальном состоянии и дают работодателю свежий сигнал.</p></div></div>
    ${r.items.length ? r.items.map(t => `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t.title)}</h3>${stat(t.status)}</div>
      <div class="muted small" style="margin-bottom:8px">${esc(t.company)} · ${t.kind === 'solve' ? 'нужно решение' : 'опишите подход'}</div>
      <p>${esc(t.body).replace(/\n/g, '<br>')}</p>
      ${t.status === 'assigned' ? `<form data-form="answer" data-id="${t.task_id}"><label class="f">Ваш ответ<textarea name="answer" required minlength="3"></textarea></label><button class="btn" type="submit">Отправить ответ</button></form>`
        : `<div class="notice"><b>Ваш ответ:</b><br>${esc(t.answer).replace(/\n/g, '<br>')}${t.rating ? `<br><b>Оценка работодателя: ${t.rating}/5</b>${t.feedback ? ' — ' + esc(t.feedback) : ''}` : ''}</div>`}</div>`).join('')
      : empty('Заданий пока нет', 'Они появятся, когда у вас будет категория и работодатели добавят задачи для вашей специализации. Мы назначаем не больше пары заданий в неделю.')}`;
}, 'candidate');
forms.answer = async (f, d) => { await api(`/api/candidate/microtasks/${f.dataset.id}/answer`, { method: 'POST', body: { answer: d.answer } }); toast('Ответ отправлен', 'ok'); render(); };

/* ---------- настройки ---------- */
route(/^\/c\/settings$/, async () => {
  const s = await me(), pr = s.settings.privacy, f = s.fsp;
  const sw = (n, t, h) => `<label class="check"><input type="checkbox" name="${n}" ${pr[n] ? 'checked' : ''}><span>${t}<br><span class="muted small">${h}</span></span></label>`;
  return `<div class="page-head"><h1>Настройки</h1></div>
    <form class="panel" data-form="settings"><h2>Публикация и приватность</h2>
      <label class="check"><input type="checkbox" name="consent_publish" ${s.settings.consent_publish ? 'checked' : ''}><span><b>Согласен на публикацию профиля в банке кандидатов</b><br><span class="muted small">Работодатели увидят код, категорию, результат теста, подтверждённый стек и достижения ФСП. Имя и контакты скрыты, пока вы не примете приглашение или не откликнетесь сами.</span></span></label>
      <h3 style="margin-top:20px">Что видно работодателю</h3>
      ${sw('visible_in_bank', 'Показывать меня в банке кандидатов', 'Если выключить, вы не будете появляться в поиске, но свои приглашения и отклики сохраните.')}
      ${sw('show_stack', 'Подтверждённый и заявленный стек', '')}${sw('show_fsp', 'Достижения в ФСП', '')}${sw('show_experience', 'Стаж, роли и «О себе»', '')}${sw('show_city', 'Город', '')}
      <button class="btn" type="submit">Сохранить настройки</button></form>
    <div class="panel"><h2>ФСП ID</h2>
      ${f.linked ? `<p>Привязан: <b class="code">${esc(f.fsp_id)}</b> (${esc(f.full_name || '')})</p>
        ${f.summary ? `<p>${f.summary.events_count} мероприятий, лучший результат — топ-${f.summary.best_top_percent}% (${esc(f.summary.best_event)}). Последнее: ${dd(f.summary.last_event_date)}.</p>${f.summary.recent.map(e => `<span class="chip">${esc(e.title)}: ${esc(e.place)}</span>`).join('')}` : '<p class="muted">В реестре ФСП пока нет мероприятий.</p>'}
        <p style="margin-top:12px"><button class="btn danger small" data-act="unlinkFsp">Отвязать</button></p>`
        : `<p class="muted">Привяжите идентификатор участника ФСП — достижения будут подтягиваться автоматически и поднимут вас в подборках. Если истории ФСП нет, вы тоже участвуете в подборках.</p>
        <form class="row" data-form="linkFsp" style="align-items:flex-end"><label class="f" style="margin:0;min-width:240px">ФСП ID<input type="text" name="fsp_id" placeholder="FSP-100001" required></label><button class="btn" type="submit">Привязать</button></form>
        <p class="small muted" style="margin-top:8px">В прототипе e-mail аккаунта должен совпадать с e-mail участника в ФСП. В боевой версии здесь будет вход через ФСП ID.</p>`}</div>
    <div class="panel"><h2>Мои данные</h2><div class="row"><button class="btn ghost" data-act="exportData">Выгрузить мои данные (JSON)</button><button class="btn danger" data-act="deleteAccount">Удалить аккаунт</button></div>
      <p class="small muted" style="margin-top:10px">Вы вправе получить копию данных и потребовать их удаления (152-ФЗ). Удаление необратимо.</p></div>`;
}, 'candidate');
forms.settings = async (f, d) => {
  await api('/api/candidate/settings', { method: 'PUT', body: { consent_publish: d.consent_publish, privacy: { visible_in_bank: d.visible_in_bank, show_stack: d.show_stack, show_fsp: d.show_fsp, show_experience: d.show_experience, show_city: d.show_city } } });
  toast('Настройки сохранены', 'ok');
};
forms.linkFsp = async (f, d) => { await api('/api/candidate/fsp', { method: 'POST', body: { fsp_id: d.fsp_id } }); toast('ФСП ID привязан', 'ok'); render(); };
acts.unlinkFsp = async () => { await api('/api/candidate/fsp', { method: 'DELETE' }); toast('ФСП ID отвязан'); render(); };
acts.exportData = async () => {
  const data = await api('/api/candidate/export');
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })); a.download = 'my-data.json'; a.click();
};
acts.deleteAccount = async () => {
  const pw = prompt('Удаление необратимо. Введите пароль для подтверждения:');
  if (!pw) return;
  await api('/api/auth/account', { method: 'DELETE', body: { password: pw } });
  logout(true); toast('Аккаунт удалён');
};
