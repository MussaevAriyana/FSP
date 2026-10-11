/* Общие разделы и новые кабинеты: аватар, кошелёк и услуги, поддержка, тренировка, резюме, награды, вакансии. Файл подключается последним — в конце запуск приложения. */
'use strict';

const EMPLOY = { full: 'Полная занятость', part: 'Частичная', project: 'Проект', internship: 'Стажировка' };
const FORMAT_RU = { office: 'Офис', remote: 'Удалённо', hybrid: 'Гибрид' };
const nl = s => esc(s).replace(/\n/g, '<br>');
const rewardToast = list => (list || []).forEach((t, i) => setTimeout(() => toast('🏅 Новая награда: ' + t, 'ok'), i * 900));
const logo = (src, name) => src ? `<img class="ava big sq" src="${esc(src)}" alt="">` : `<span class="ava big sq" aria-hidden="true">${esc((name || '?').trim()[0].toUpperCase())}</span>`;

/* ---------- фото профиля / логотип ---------- */
acts.avatarPick = () => {
  const inp = document.createElement('input'); inp.type = 'file'; inp.accept = 'image/jpeg,image/png,image/webp';
  inp.onchange = async () => {
    const file = inp.files[0]; if (!file) return;
    try {
      const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = () => no(new Error('Не удалось прочитать изображение')); i.src = URL.createObjectURL(file); });
      const side = Math.min(img.width, img.height), c = document.createElement('canvas'); c.width = c.height = 256;
      c.getContext('2d').drawImage(img, (img.width - side) / 2, (img.height - side) / 2, side, side, 0, 0, 256, 256);
      const r = await api('/api/account/avatar', { method: 'PUT', body: { image: c.toDataURL('image/jpeg', 0.82) } });
      S.user.avatar = r.avatar; toast('Фото обновлено', 'ok'); drawNav(location.hash.slice(1) || '/');
    } catch (e) { fail(e); }
  };
  inp.click();
};
acts.avatarDel = async () => { await api('/api/account/avatar', { method: 'DELETE' }); S.user.avatar = null; drawNav(location.hash.slice(1) || '/'); toast('Фото удалено'); };

/* ---------- кошелёк и услуги ---------- */
route(/^\/wallet$/, async () => {
  const w = await api('/api/wallet'), emp = S.user.role === 'employer';
  const vac = emp ? (await api('/api/employer/vacancies')).items.filter(v => v.status === 'published') : [];
  return `<div class="page-head"><div><h1>Кошелёк и услуги</h1><p class="muted">Платные услуги дают заметность и удобство. Категорию они не меняют: её присваивает только тест.</p></div>
      <div class="balance"><span class="small muted">Баланс</span><b>${money(w.balance)}</b></div></div>
    ${w.demo ? '<div class="notice warn">Демо-режим: пополнение зачисляется сразу, реальные деньги не списываются. Для боевой работы подключается платёжный провайдер (см. документацию, раздел «Монетизация»).</div>' : ''}
    <div class="panel"><h2>Пополнить</h2><form class="row" data-form="topup" style="align-items:flex-end">
      <label class="f" style="margin:0">Сумма, ₽<input type="text" inputmode="numeric" data-money name="amount" value="1 000" required style="width:150px"></label>
      <button class="btn" type="submit">Пополнить</button>
      ${[500, 1000, 3000].map(n => `<button class="btn ghost small" type="button" data-act="topupQuick" data-n="${n}">+${nf.format(n)}</button>`).join('')}</form></div>
    <div class="cards">${w.services.map(s => `<div class="panel svc ${s.active ? 'on' : ''}"><div class="row" style="justify-content:space-between;align-items:flex-start"><h3 style="margin:0">${esc(s.title)}</h3><span class="salary">${money(s.price)}</span></div>
      <p class="muted">${esc(s.description)}</p>
      <p class="small muted">${s.days ? `Срок: ${s.days} дн.` : ''}${s.uses ? `Попыток: ${s.uses}` : ''}</p>
      ${s.active ? `<p class="small"><span class="chip ok">Активно</span> ${s.expires_at ? 'до ' + dd(s.expires_at) : ''}${s.uses_left != null ? ' · осталось: ' + s.uses_left : ''}</p>` : ''}
      <form data-form="buy" data-service="${esc(s.service)}" class="row">${s.needs_vacancy ? (vac.length ? `<select name="vacancy_id" required>${vac.map(v => `<option value="${v.id}">${esc(v.title)}</option>`).join('')}</select>` : '<span class="small muted">Сначала опубликуйте вакансию</span>') : ''}
      <button class="btn small" type="submit" ${s.needs_vacancy && !vac.length ? 'disabled' : ''}>${s.active ? 'Продлить' : 'Купить'}</button></form></div>`).join('')}</div>
    <div class="panel"><h2>История операций</h2>${w.transactions.length ? `<table class="t"><thead><tr><th>Дата</th><th>Операция</th><th>Сумма</th></tr></thead><tbody>${w.transactions.map(t => `<tr><td>${dt(t.at)}</td><td>${esc(t.title)}</td><td>${t.amount > 0 ? '+' : ''}${money(t.amount)}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">Операций пока нет.</p>'}</div>`;
}, 'any');
forms.topup = async (f, d) => { await api('/api/wallet/topup', { method: 'POST', body: { amount: moneyNum(d.amount) } }); toast('Кошелёк пополнен', 'ok'); render(); };
acts.topupQuick = async el => { await api('/api/wallet/topup', { method: 'POST', body: { amount: Number(el.dataset.n) } }); toast('Кошелёк пополнен', 'ok'); render(); };
forms.buy = async (f, d) => {
  try { await api('/api/wallet/buy', { method: 'POST', body: { service: f.dataset.service, vacancy_id: d.vacancy_id ? Number(d.vacancy_id) : null } }); toast('Услуга подключена', 'ok'); render(); }
  catch (e) { if (e.status === 402) toast('Не хватает средств — пополните кошелёк', 'bad'); else throw e; }
};

/* ---------- поддержка ---------- */
route(/^\/support$/, async () => {
  const r = await api('/api/support');
  return `<div class="page-head"><div><h1>Связь с поддержкой</h1><p class="muted">Опишите вопрос — ответ появится здесь же.</p></div></div>
    <form class="panel" data-form="support"><label class="f">Тема<input type="text" name="subject" required minlength="3" maxlength="160"></label>
      <label class="f">Сообщение<textarea name="message" required minlength="10" maxlength="4000" rows="4"></textarea></label><button class="btn" type="submit">Отправить</button></form>
    ${r.items.map(t => `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t.subject)}</h3><span class="chip ${t.status === 'answered' ? 'ok' : ''}">${t.status === 'answered' ? 'есть ответ' : 'на рассмотрении'}</span></div>
      <p class="small muted">${dt(t.created_at)}</p><p>${nl(t.message)}</p>${t.reply ? `<div class="notice"><b>Ответ поддержки:</b><br>${nl(t.reply)}</div>` : ''}</div>`).join('')}`;
}, 'any');
forms.support = async (f, d) => { await api('/api/support', { method: 'POST', body: d }); toast('Обращение отправлено', 'ok'); render(); };
route(/^\/m\/support$/, async () => {
  const r = await api('/api/moderator/support');
  return `<div class="page-head"><div><h1>Обращения в поддержку</h1></div></div>${r.items.length ? r.items.map(t => `<div class="panel"><div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(t.subject)}</h3><span class="chip ${t.status === 'answered' ? 'ok' : 'warn'}">${t.status === 'answered' ? 'отвечено' : 'ждёт ответа'}</span></div>
    <p class="small muted">${esc(t.email)} (${esc(t.role)}) · ${dt(t.created_at)}</p><p>${nl(t.message)}</p>
    ${t.reply ? `<div class="notice"><b>Ответ:</b><br>${nl(t.reply)}</div>` : `<form class="row" data-form="supReply" data-id="${t.id}"><input type="text" name="reply" required minlength="2" placeholder="Ответ" style="flex:1;min-width:240px"><button class="btn small" type="submit">Ответить</button></form>`}</div>`).join('') : empty('Обращений нет', 'Новые сообщения появятся здесь.')}`;
}, 'moderator');
forms.supReply = async (f, d) => { await api(`/api/moderator/support/${f.dataset.id}/reply`, { method: 'POST', body: { reply: d.reply } }); toast('Ответ отправлен', 'ok'); render(); };

/* ---------- тренировка ---------- */
const PR = { spec: null, level: 2, item: null, res: null };
route(/^\/c\/practice$/, async () => {
  const [s, st] = await Promise.all([me(), api('/api/candidate/practice/stats')]);
  if (!PR.spec) PR.spec = s.category.spec || (s.survey && s.survey.spec) || 'backend';
  PR.item = null; PR.res = null;
  return `<div class="page-head"><div><h1>Тренировка</h1><p class="muted">Задания из того же генератора, что и в тесте, но без таймера, камеры и категории. Ответ и разбор показываются сразу. Результат влияет только на награды.</p></div>
      <a class="btn ghost" href="#/c/rewards">Мои награды</a></div>
    <div class="panel"><div class="row" style="align-items:flex-end">
      <label class="f" style="margin:0;min-width:220px">Специализация<select id="prSpec" data-onchange="prSetSpec">${opts(Object.fromEntries(Object.entries(S.tax.specs).map(([k, v]) => [k, v.title])), PR.spec)}</select></label>
      <div class="f" style="margin:0"><span style="font-size:.92rem;font-weight:600">Сложность</span><div class="tabs" style="margin:6px 0 0" id="prLevels">${[1, 2, 3, 4, 5].map(n => `<button class="tab ${n === PR.level ? 'on' : ''}" data-act="prLevel" data-n="${n}">${n}</button>`).join('')}</div></div>
      <button class="btn" data-act="prNext">Получить задание</button></div>
      <p class="small muted" style="margin:10px 0 0">Решено: <b>${st.solved}</b> из ${st.attempts} попыток · сложных (4–5): ${st.hard_solved}</p></div>
    <div id="prBox"></div>`;
}, 'candidate');
acts.prSetSpec = el => { PR.spec = el.value; };
acts.prLevel = el => { PR.level = Number(el.dataset.n); $$('#prLevels .tab').forEach(b => b.classList.toggle('on', Number(b.dataset.n) === PR.level)); };
acts.prNext = async () => {
  const it = await api('/api/candidate/practice/next', { method: 'POST', body: { spec: PR.spec, level: PR.level } });
  PR.item = it; PR.res = null; drawPractice();
};
function drawPractice() {
  const it = PR.item, r = PR.res, box = $('#prBox'); if (!box || !it) return;
  const body = it.kind === 'choice'
    ? it.options.map((o, i) => `<label class="choice"><input type="radio" name="answer" value="${i}" ${r ? 'disabled' : ''} required><span>${esc(o)}</span></label>`).join('')
    : `<label class="f">Ответ<span class="hint">${esc(it.hint || '')}</span><input type="text" name="answer" inputmode="decimal" autocomplete="off" required ${r ? 'disabled' : ''} style="max-width:260px"></label>`;
  box.innerHTML = `<form class="panel" data-form="prAnswer"><div class="row" style="justify-content:space-between"><span class="chip">${esc(TOPIC_RU[it.topic] || it.topic)}</span><span class="chip">сложность ${it.level}</span></div>
    <div class="q-body">${md(it.prompt)}</div>${body}
    ${r ? `<div class="notice ${r.ok ? '' : 'bad'}"><b>${r.ok ? 'Верно!' : 'Неверно.'}</b> Правильный ответ: <b>${esc(String(r.correct))}</b>${r.explanation ? '<div class="q-body" style="margin-top:8px">' + md(r.explanation) + '</div>' : ''}</div>
      <div class="row"><button class="btn" type="button" data-act="prNext">Следующее задание</button></div>`
      : `<div class="row"><button class="btn" type="submit">Проверить</button><button class="btn ghost" type="button" data-act="prSkip">Пропустить</button></div>`}</form>`;
}
forms.prAnswer = async (f, d) => {
  if (PR.res) return;
  let a = d.answer; if (PR.item.kind === 'choice') a = Number(a); else a = String(a).replace(',', '.');
  PR.res = await api(`/api/candidate/practice/${PR.item.id}/answer`, { method: 'POST', body: { answer: a } });
  drawPractice(); rewardToast(PR.res.rewards);
};
acts.prSkip = async () => { await api(`/api/candidate/practice/${PR.item.id}/skip`, { method: 'POST' }); await acts.prNext(); };

/* ---------- конструктор резюме ---------- */
let RS = null, RS_PRIV = null, RS_CONSENT = true, RS_ADVICE = [];
const RS_EMPTY = { experience: { company: '', position: '', start: '', end: '', description: '' }, projects: { name: '', role: '', link: '', description: '', stack: [] },
  education: { institution: '', level: '', degree: '', specialty: '', year_from: '', year_to: '' }, certificates: { kind: 'certificate', name: '', issuer: '', year: '', link: '' },
  languages: { name: '', level: 'B1' } };
const LEVEL_RU = { '': 'Не указан', secondary: 'Среднее общее', college: 'Среднее профессиональное', bachelor: 'Бакалавриат', specialist: 'Специалитет', master: 'Магистратура', phd: 'Аспирантура', courses: 'Курсы, переподготовка' };
const inp = (sec, i, k, label, v, extra = '') => `<label class="f">${label}<input type="${extra.includes('month') ? 'month' : 'text'}" data-rs="${sec}.${i}.${k}" value="${esc(v)}" ${extra.replace('month', '')}></label>`;
const txt = (sec, i, k, label, v, hint = '') => `<label class="f">${label}${hint ? `<span class="hint">${hint}</span>` : ''}<textarea data-rs="${sec}.${i}.${k}" rows="3" maxlength="2000">${esc(v)}</textarea></label>`;
const oinp = (path, label, v, extra = '') => `<label class="f">${label}<input type="text" data-rs="${path}" value="${esc(v ?? '')}" ${extra}></label>`;
const osel = (path, label, o, v) => `<label class="f">${label}<select data-rs="${path}">${opts(o, v ?? '')}</select></label>`;
const checks = (key, o, arr) => o && Object.entries(o).map(([k, t]) => `<label class="check" style="display:inline-flex;margin-right:16px"><input type="checkbox" data-rsarr="${key}:${k}" ${(arr || []).includes(k) ? 'checked' : ''}><span>${t}</span></label>`).join('');
function rsSection(sec, title, hint, row) {
  return `<div class="panel" id="rs_${sec}"><div class="row" style="justify-content:space-between"><div><h2 style="margin:0">${title}</h2><p class="small muted" style="margin:2px 0 0">${hint}</p></div>
    <button class="btn ghost small" type="button" data-act="rsAdd" data-sec="${sec}">Добавить</button></div>
    ${RS[sec].map((x, i) => `<div class="item"><div class="row" style="justify-content:flex-end"><button class="btn ghost small" type="button" data-act="rsDel" data-sec="${sec}" data-i="${i}">Удалить</button></div>${row(x, i)}</div>`).join('') || '<p class="muted">Пока пусто.</p>'}</div>`;
}
const rsPct = () => Math.round(100 * [RS.summary, RS.desired_position, RS.experience.length, RS.projects.length, RS.education.length, RS.certificates.length].filter(Boolean).length / 6);
function rsDraw() {
  const box = $('#rsBox'); if (!box) return;
  const pct = rsPct(), pr = RS.personal;
  box.innerHTML = `<div class="panel tint"><div class="row" style="justify-content:space-between"><b>Заполнено на ${pct}%</b><span class="small muted">Полное резюме приносит награду «Резюме 100%»</span></div>${bar(pct, pct === 100 ? 'ok' : '')}</div>
    ${RS_ADVICE.length ? `<details class="panel" ${RS_ADVICE.some(a => a.severity === 'warn') ? 'open' : ''}><summary><b>Проверка резюме: ${RS_ADVICE.length} ${RS_ADVICE.length === 1 ? 'подсказка' : 'подсказок'}</b></summary><ul class="advice">${RS_ADVICE.map(a => `<li class="${a.severity}">${esc(a.text)}</li>`).join('')}</ul></details>` : '<div class="notice ok">Резюме оформлено по всем рекомендациям.</div>'}
    <div class="panel"><h2>Позиция и пожелания</h2><div class="grid2">${oinp('desired_position', 'Желаемая должность', RS.desired_position, 'maxlength="120" placeholder="Например: Backend-разработчик (Python)"')}
      <label class="f">Желаемая зарплата, ₽<input type="text" inputmode="numeric" data-money data-rs="salary_expectation" value="${RS.salary_expectation ? nf.format(RS.salary_expectation) : ''}"></label></div>
      <label class="f">О себе и целях<span class="hint">2–4 предложения: кто вы, главный опыт, что ищете</span><textarea data-rs="summary" rows="4" maxlength="2000">${esc(RS.summary)}</textarea></label>
      <div class="f"><b style="font-size:.92rem">Занятость</b><div>${checks('employment_types', EMPLOY, RS.employment_types)}</div></div>
      <div class="f"><b style="font-size:.92rem">Формат работы</b><div>${checks('schedules', { ...FORMAT_RU, shift: 'Сменный график' }, RS.schedules)}</div></div>
      <div class="grid2">${osel('relocation', 'Готовность к переезду', { '': 'Не указано', no: 'Нет', yes: 'Да', maybe: 'Рассмотрю варианты' }, RS.relocation)}${osel('business_trips', 'Командировки', { '': 'Не указано', no: 'Нет', rarely: 'Редко', yes: 'Да' }, RS.business_trips)}</div></div>
    ${rsSection('experience', 'Опыт работы', 'От новых мест к старым. Укажите даты и результаты в цифрах', (x, i) => `<div class="grid2">${inp('experience', i, 'company', 'Компания', x.company)}${inp('experience', i, 'position', 'Должность', x.position)}</div>
      <div class="grid2">${inp('experience', i, 'start', 'Начало', x.start, 'month')}${inp('experience', i, 'end', 'Окончание (пусто — по сей день)', x.end, 'month')}</div>${txt('experience', i, 'description', 'Обязанности и достижения', x.description, 'Например: «сократил время ответа API с 800 до 200 мс»')}`)}
    ${rsSection('projects', 'Проекты', 'Личные, учебные, коммерческие, open-source', (x, i) => `<div class="grid2">${inp('projects', i, 'name', 'Название', x.name)}${inp('projects', i, 'role', 'Ваша роль', x.role)}</div>
      ${inp('projects', i, 'link', 'Ссылка (репозиторий, демо)', x.link)}<label class="f">Технологии через запятую<input type="text" data-rs="projects.${i}.stack" value="${esc((x.stack || []).join(', '))}"></label>${txt('projects', i, 'description', 'Описание', x.description)}`)}
    ${rsSection('education', 'Образование', 'Вуз, колледж, курсы, переподготовка', (x, i) => `${inp('education', i, 'institution', 'Учебное заведение', x.institution)}<div class="grid3"><label class="f">Уровень<select data-rs="education.${i}.level">${opts(LEVEL_RU, x.level)}</select></label>${inp('education', i, 'specialty', 'Специальность', x.specialty)}${inp('education', i, 'degree', 'Квалификация / степень', x.degree)}</div>
      <div class="grid2">${inp('education', i, 'year_from', 'Год начала', x.year_from, 'maxlength="4" inputmode="numeric"')}${inp('education', i, 'year_to', 'Год окончания (или ожидаемый)', x.year_to, 'maxlength="4" inputmode="numeric"')}</div>`)}
    ${rsSection('certificates', 'Дипломы и сертификаты', 'Подтверждающие документы и награды', (x, i) => `<div class="grid3"><label class="f">Тип<select data-rs="certificates.${i}.kind">${opts({ certificate: 'Сертификат', diploma: 'Диплом', award: 'Награда' }, x.kind)}</select></label>${inp('certificates', i, 'name', 'Название', x.name)}${inp('certificates', i, 'issuer', 'Кто выдал', x.issuer)}</div>
      <div class="grid2">${inp('certificates', i, 'year', 'Год', x.year, 'maxlength="4" inputmode="numeric"')}${inp('certificates', i, 'link', 'Ссылка на документ', x.link)}</div>`)}
    ${rsSection('languages', 'Языки', 'Уровень по шкале CEFR: A1–C2', (x, i) => `<div class="grid2">${inp('languages', i, 'name', 'Язык', x.name)}<label class="f">Уровень<select data-rs="languages.${i}.level">${opts({ native: 'Родной', A1: 'A1', A2: 'A2', B1: 'B1 — средний', B2: 'B2 — выше среднего', C1: 'C1 — продвинутый', C2: 'C2 — свободный' }, x.level)}</select></label></div>`)}
    <div class="panel"><h2>Ссылки</h2><p class="small muted">Работодатель увидит их только после принятия приглашения.</p><div class="grid2">${oinp('links.github', 'GitHub', RS.links.github, 'placeholder="https://github.com/…"')}${oinp('links.telegram', 'Telegram', RS.links.telegram, 'placeholder="@username"')}${oinp('links.linkedin', 'LinkedIn', RS.links.linkedin)}${oinp('links.site', 'Сайт или портфолио', RS.links.site)}</div></div>
    <div class="panel"><h2>Личные сведения <span class="chip">по желанию</span></h2>
      <p class="small muted">Все поля необязательны. Работодатель не вправе требовать семейное положение или сведения о детях при приёме на работу (ст. 64 ТК РФ) — заполняйте, только если хотите.</p>
      <label class="check" style="margin-bottom:12px"><input type="checkbox" data-rspriv="show_personal" ${RS_PRIV.show_personal ? 'checked' : ''}><span><b>Показывать личные сведения работодателям</b> (возраст вместо года рождения, гражданство, семейное положение и т. д.). По умолчанию скрыты.</span></label>
      <div class="grid3">${oinp('personal.birth_year', 'Год рождения', pr.birth_year, 'maxlength="4" inputmode="numeric"')}${oinp('personal.citizenship', 'Гражданство', pr.citizenship)}${oinp('personal.driving', 'Водительские права', pr.driving, 'placeholder="B"')}</div>
      <div class="grid3">${osel('personal.marital_status', 'Семейное положение', { '': 'Не указано', single: 'Не женат / не замужем', married: 'Женат / замужем', divorced: 'Разведён / разведена', widowed: 'Вдовец / вдова' }, pr.marital_status)}
        ${osel('personal.children', 'Дети', { '': 'Не указано', none: 'Нет', one: 'Один ребёнок', two: 'Двое', three_plus: 'Трое и более' }, pr.children)}
        ${osel('personal.military', 'Воинская обязанность', { '': 'Не указано', served: 'Служил(а)', reserve: 'В запасе', exempt: 'Освобождён(а)', not_liable: 'Не военнообязан(а)', student: 'Отсрочка (учёба)' }, pr.military)}</div></div>
    <div class="row"><button class="btn" data-act="rsSave">Сохранить резюме</button><button class="btn ghost" data-act="rsPdf">Скачать PDF</button><label class="btn ghost" style="cursor:pointer">Заполнить из PDF<input type="file" accept="application/pdf" data-onchange="rsFromPdf" hidden></label></div>`;
}
async function rsLoad() {
  const [r, s] = await Promise.all([api('/api/candidate/resume'), me()]);
  RS_ADVICE = r.advice || []; RS_PRIV = s.settings.privacy; RS_CONSENT = s.settings.consent_publish;
  delete r.progress; delete r.advice;
  RS = { ...r, links: { github: '', telegram: '', linkedin: '', site: '', ...(r.links || {}) }, personal: { ...(r.personal || {}) } };
}
route(/^\/c\/resume$/, async () => {
  await rsLoad();
  return { html: `<div class="page-head"><div><h1>Резюме</h1><p class="muted">Конструктор резюме по принятой в ИТ структуре. Работодатель видит его по вашим настройкам приватности, а названия компаний, вузов и ссылки — после принятия приглашения.</p></div><a class="btn ghost" href="#/c/profile">Профиль</a></div><div id="rsBox"></div>`, after: rsDraw };
}, 'candidate');
document.addEventListener('input', e => {
  const k = e.target.dataset && e.target.dataset.rs; if (!k || !RS) return;
  const p = k.split('.'); let v = e.target.value;
  if ('money' in e.target.dataset) v = moneyNum(v) || null;
  if (p.length === 1) { RS[p[0]] = v; return; }
  if (p.length === 2) { RS[p[0]][p[1]] = p[1] === 'birth_year' ? (v ? Number(v) : null) : v; return; }
  if (p[2] === 'stack') v = v.split(',').map(x => x.trim()).filter(Boolean);
  RS[p[0]][Number(p[1])][p[2]] = v;
});
document.addEventListener('change', e => {
  const t = e.target; if (!RS || !t.dataset) return;
  if (t.dataset.rsarr) { const [key, val] = t.dataset.rsarr.split(':'); const a = new Set(RS[key] || []); t.checked ? a.add(val) : a.delete(val); RS[key] = [...a]; }
  if (t.dataset.rspriv) RS_PRIV[t.dataset.rspriv] = t.checked;
  if (t.dataset.rs && t.tagName === 'SELECT') { const p = t.dataset.rs.split('.'); if (p.length === 1) RS[p[0]] = t.value; else if (p.length === 2) RS[p[0]][p[1]] = t.value; else RS[p[0]][Number(p[1])][p[2]] = t.value; }
});
acts.rsAdd = el => { RS[el.dataset.sec].push({ ...RS_EMPTY[el.dataset.sec] }); rsDraw(); };
acts.rsDel = el => { RS[el.dataset.sec].splice(Number(el.dataset.i), 1); rsDraw(); };
acts.rsSave = async () => {
  const body = { ...RS, salary_expectation: RS.salary_expectation || null, personal: { ...RS.personal, birth_year: RS.personal.birth_year || null } };
  const r = await api('/api/candidate/resume', { method: 'PUT', body });
  await api('/api/candidate/settings', { method: 'PUT', body: { consent_publish: RS_CONSENT, privacy: RS_PRIV } });
  RS_ADVICE = r.advice || [];
  const { progress, rewards, advice, ...data } = r; RS = { ...data, links: { github: '', telegram: '', linkedin: '', site: '', ...(data.links || {}) } };
  rsDraw(); toast('Резюме сохранено', 'ok'); rewardToast(rewards);
};
acts.rsPdf = async () => {
  const b = await api('/api/candidate/profile.pdf' + (RS_PRIV.show_personal ? '?personal=1' : ''), { blob: true });
  const a = document.createElement('a'); a.href = URL.createObjectURL(b); a.download = 'resume.pdf'; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};
acts.rsFromPdf = async el => {
  const file = el.files[0]; if (!file) return;
  const fd = new FormData(); fd.append('file', file);
  try {
    const r = await api('/api/candidate/resume/parse', { method: 'POST', form: fd });
    if (!RS.desired_position && r.roles && r.roles[0]) RS.desired_position = r.roles[0];
    (r.roles || []).slice(0, 4).forEach(x => { if (!RS.experience.some(e => e.position === x)) RS.experience.push({ ...RS_EMPTY.experience, position: x }); });
    rsDraw(); toast('Данные из PDF добавлены. Проверьте и дополните разделы, затем сохраните.', 'ok');
  } catch (e) { fail(e); } finally { el.value = ''; }
};

/* ---------- награды ---------- */
const GROUPS = { profile: 'Профиль', resume: 'Резюме', tests: 'Тесты', practice: 'Тренировка', career: 'Карьера' };
route(/^\/c\/rewards$/, async () => {
  const r = await api('/api/candidate/achievements');
  return { html: `<div class="page-head"><div><h1>Мои награды</h1><p class="muted">Значки выдаются за заполненный профиль и резюме, пройденные тесты и решённые задачи. Они видны только вам.</p></div></div>
    <div class="panel tint"><div class="row" style="justify-content:space-between;align-items:center"><div><div class="small muted">Уровень ${r.level.index}</div><h2 style="margin:0">${esc(r.level.title)}</h2></div><div class="score-big">${r.points}<small> очк.</small></div></div>
      ${r.next ? bar(100 * r.points / r.next.at) + `<p class="small muted" style="margin:6px 0 0">До уровня «${esc(r.next.title)}» осталось ${r.next.left} очк. Наград: ${r.earned} из ${r.total}.</p>` : '<p class="small muted">Максимальный уровень достигнут.</p>'}</div>
    ${Object.entries(GROUPS).map(([g, t]) => `<div class="panel"><h2>${t}</h2><div class="badges">${r.badges.filter(b => b.group === g).map(b => `<div class="badge ${b.earned ? 'on' : ''}" title="${esc(b.description)}"><span class="medal" aria-hidden="true">${b.earned ? '★' : '☆'}</span><b>${esc(b.title)}</b><span class="small">${esc(b.description)}</span><span class="small muted">${b.earned ? 'получено ' + dd(b.at) : '+' + b.points + ' очк.'}</span></div>`).join('')}</div></div>`).join('')}`, after: () => rewardToast(r.new) };
}, 'candidate');

/* ---------- вакансии кандидата: список и карточка ---------- */
route(/^\/c\/vacancies$/, async () => {
  const [v, a] = await Promise.all([api('/api/candidate/vacancies'), api('/api/candidate/applications')]);
  return `<div class="page-head"><div><h1>Вакансии</h1><p class="muted">Откройте вакансию, чтобы увидеть всё: описание, требования, условия и компанию. Первыми — вакансии вашей категории.</p></div></div>
    ${v.items.length ? v.items.map(i => `<a class="panel vac" href="#/c/vacancies/${i.id}"><div class="row" style="gap:14px;align-items:flex-start;flex-wrap:nowrap">${logo(i.company.logo, i.company.name)}
      <div style="flex:1;min-width:0"><div class="row" style="justify-content:space-between;align-items:flex-start"><h3 style="margin:0">${esc(i.title)}${i.boosted ? ' <span class="chip fsp">Топ</span>' : ''}</h3><span class="salary">${salary(i.salary_from, i.salary_to)}</span></div>
      <div class="muted small">${esc(i.company.name)} · ${esc(i.category_label)}${i.city ? ' · ' + esc(i.city) : ''}${i.work_format ? ' · ' + FORMAT_RU[i.work_format] : ''}</div>
      <p style="margin:8px 0">${esc(i.description)}${i.description.length >= 240 ? '…' : ''}</p>
      <div>${chips(i.stack)}${i.fit >= 1 ? '<span class="chip ok">ваша категория</span>' : ''}${i.my_application && i.my_application !== 'withdrawn' ? stat(i.my_application) : ''}</div></div></div></a>`).join('')
      : empty('Открытых вакансий пока нет', 'Загляните позже — работодатели публикуют вакансии с обязательной вилкой зарплаты.')}
    ${a.items.length ? `<div class="panel"><h2>Мои отклики</h2><table class="t"><thead><tr><th>Вакансия</th><th>Компания</th><th>Статус</th><th>Обновлён</th><th></th></tr></thead><tbody>${a.items.map(x => `<tr><td><a href="#/c/vacancies/${x.vacancy_id}">${esc(x.title)}</a></td><td>${esc(x.company)}</td><td>${stat(x.status)}</td><td>${dt(x.updated_at)}</td>
      <td class="row" style="gap:6px">${['sent', 'viewed'].includes(x.status) ? `<button class="btn ghost small" data-act="appEdit" data-id="${x.id}" data-msg="${esc(x.message)}">Изменить</button>` : ''}${x.status !== 'withdrawn' && x.status !== 'rejected' ? `<button class="btn danger small" data-act="appWithdraw" data-id="${x.id}" data-title="${esc(x.title)}">Отозвать</button>` : ''}</td></tr>`).join('')}</tbody></table></div>` : ''}`;
}, 'candidate');
route(/^\/c\/vacancies\/(\d+)$/, async m => {
  const v = await api('/api/candidate/vacancies/' + m[1]), c = v.company;
  const sec = (t, x) => x ? `<h3>${t}</h3><p>${nl(x)}</p>` : '';
  return `<div class="page-head"><div class="row" style="gap:14px;flex-wrap:nowrap">${logo(c.logo, c.name)}<div><h1 style="margin:0">${esc(v.title)}</h1><p class="muted" style="margin:0">${esc(c.name)}${c.industry ? ' · ' + esc(c.industry) : ''}</p></div></div><a class="btn ghost" href="#/c/vacancies">Все вакансии</a></div>
    <div class="panel tint"><div class="row" style="justify-content:space-between;align-items:center"><span class="salary big">${salary(v.salary_from, v.salary_to)}</span>
      <div>${v.my_application && v.my_application !== 'withdrawn' ? `<div class="row">${stat(v.my_application)}${['sent', 'viewed'].includes(v.my_application) ? `<button class="btn ghost" data-act="appEdit" data-id="${v.my_application_id}" data-msg="${esc(v.my_message)}">Изменить отклик</button>` : ''}<button class="btn danger" data-act="appWithdraw" data-id="${v.my_application_id}" data-title="${esc(v.title)}">Отозвать</button></div>` : v.status === 'published' ? `<button class="btn big" data-act="applyOpen" data-id="${v.id}" data-title="${esc(v.title)}">Откликнуться</button>` : '<span class="chip">Вакансия закрыта</span>'}</div></div>
      <p style="margin:12px 0 0"><span class="chip">${esc(v.category_label)}</span>${v.work_format ? `<span class="chip">${FORMAT_RU[v.work_format]}</span>` : ''}${v.employment ? `<span class="chip">${EMPLOY[v.employment]}</span>` : ''}${v.city ? `<span class="chip">${esc(v.city)}</span>` : ''}${v.fit >= 1 ? '<span class="chip ok">ваша категория</span>' : ''}</p>
      ${v.fit_text ? `<p class="small muted" style="margin:6px 0 0">${esc(v.fit_text)}</p>` : ''}</div>
    <div class="panel">${sec('Описание', v.description)}${sec('Требования', v.requirements)}${sec('Условия', v.conditions)}${v.stack.length ? `<h3>Технологии</h3><div>${chips(v.stack)}</div>` : ''}
      <p class="small muted">Опубликовано ${dd(v.created_at)}</p></div>
    <div class="panel"><h2>О компании</h2><p><b>${esc(c.name)}</b>${c.industry ? ' · ' + esc(c.industry) : ''}</p>${c.description ? `<p>${nl(c.description)}</p>` : ''}${c.website ? `<p><a href="${esc(c.website)}" target="_blank" rel="noopener noreferrer">${esc(c.website)}</a></p>` : ''}</div>`;
}, 'candidate');
acts.appEdit = el => openModal(`<form data-form="appEdit" data-id="${esc(el.dataset.id)}"><h2>Изменить отклик</h2>
  <label class="f">Сообщение работодателю<textarea name="message" rows="5" maxlength="1500">${esc(el.dataset.msg || '')}</textarea></label>
  <div class="row"><button class="btn" type="submit">Сохранить</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
forms.appEdit = async (f, d) => { await api('/api/candidate/applications/' + f.dataset.id, { method: 'PATCH', body: { message: d.message || '' } }); closeModal(); toast('Отклик обновлён', 'ok'); render(); };
acts.appWithdraw = async el => {
  if (!(await confirmBox('Отозвать отклик?', `Вы отзовёте отклик на «${el.dataset.title}». Работодатель потеряет доступ к вашим контактам. Позже можно откликнуться снова.`, 'Отозвать', true))) return;
  await api('/api/candidate/applications/' + el.dataset.id, { method: 'DELETE' }); toast('Отклик отозван'); render();
};
acts.applyOpen = el => openModal(`<form data-form="apply" data-id="${esc(el.dataset.id)}"><h2>Отклик: ${esc(el.dataset.title)}</h2>
  <div class="notice warn">Отклик раскрывает работодателю ваши ФИО, e-mail и телефон.</div>
  <label class="f">Сообщение (по желанию)<textarea name="message"></textarea></label>
  <div class="row"><button class="btn" type="submit">Отправить отклик</button><button class="btn ghost" type="button" data-act="closeModal">Отмена</button></div></form>`);
forms.apply = async (f, d) => { const r = await api(`/api/candidate/vacancies/${f.dataset.id}/apply`, { method: 'POST', body: { message: d.message } }); closeModal(); toast('Отклик отправлен', 'ok'); render(); rewardToast(r.rewards); };

/* ---------- вакансии работодателя: управление ---------- */
route(/^\/e\/vacancies$/, async () => {
  const r = await api('/api/employer/vacancies');
  return `<div class="page-head"><div><h1>Мои вакансии</h1><p class="muted">Создавайте и редактируйте вакансии, смотрите отклики, поднимайте важные в списке кандидатов.</p></div><a class="btn" href="#/e/vacancies/new">Новая вакансия</a></div>
    ${r.items.length ? r.items.map(v => `<div class="panel"><div class="row" style="justify-content:space-between;align-items:flex-start"><div><h3 style="margin:0">${esc(v.title)} ${stat(v.status)}${v.boosted ? ' <span class="chip fsp">Поднята</span>' : ''}</h3>
      <div class="muted small">${esc(v.category_label)}${v.city ? ' · ' + esc(v.city) : ''}${v.work_format ? ' · ' + FORMAT_RU[v.work_format] : ''} · ${dt(v.created_at)}</div></div><span class="salary">${salary(v.salary_from, v.salary_to)}</span></div>
      <div style="margin:8px 0">${chips(v.stack)}</div>
      <div class="row"><a class="btn small" href="#/e/vacancies/${v.id}/edit">Редактировать</a>
        <button class="btn ghost small" data-act="vacToggle" data-id="${v.id}" data-s="${v.status === 'published' ? 'closed' : 'published'}">${v.status === 'published' ? 'Закрыть' : 'Опубликовать'}</button>
        <button class="btn ghost small" data-act="loadApps" data-id="${v.id}">Отклики${v.applications ? ' (' + v.applications + (v.applications_new ? ', новых ' + v.applications_new : '') + ')' : ''}</button>
        ${v.status === 'published' ? '<a class="btn ghost small" href="#/wallet">Поднять в списке</a>' : ''}
        <button class="btn ghost small" data-act="vacDel" data-id="${v.id}" data-title="${esc(v.title)}">Удалить</button></div>
      <div id="apps${v.id}" style="margin-top:10px"></div></div>`).join('')
      : empty('Вакансий пока нет', 'Опубликуйте первую: зарплатная вилка обязательна — так кандидаты видят условия сразу.', '<a class="btn" href="#/e/vacancies/new">Создать вакансию</a>')}`;
}, 'employer');
acts.vacToggle = async el => { await api(`/api/employer/vacancies/${el.dataset.id}/status`, { method: 'PATCH', body: { status: el.dataset.s } }); toast(el.dataset.s === 'closed' ? 'Вакансия закрыта' : 'Вакансия опубликована', 'ok'); render(); };
acts.vacDel = async el => { if (!(await confirmBox('Удалить вакансию?', `«${el.dataset.title}» будет удалена вместе с откликами. Это действие нельзя отменить.`, 'Удалить', true))) return; await api('/api/employer/vacancies/' + el.dataset.id, { method: 'DELETE' }); toast('Вакансия удалена'); render(); };
async function vacEditor(v) {
  const isNew = !v;
  v = v || { title: '', description: '', requirements: '', conditions: '', spec: 'backend', grade: 'middle', stack: [], work_format: 'remote', city: '', employment: 'full', salary_from: '', salary_to: '' };
  return `<div class="page-head"><div><h1>${isNew ? 'Новая вакансия' : 'Редактирование вакансии'}</h1><p class="muted">Зарплатная вилка обязательна. Подробности увидят кандидаты на странице вакансии.</p></div><a class="btn ghost" href="#/e/vacancies">К списку</a></div>
    <form class="panel" data-form="vacancy" data-id="${isNew ? '' : v.id}">
      <label class="f">Название<input type="text" name="title" value="${esc(v.title)}" required minlength="3" maxlength="160"></label>
      <div class="grid3"><label class="f">Специализация<select name="spec">${opts(specTitles(), v.spec)}</select></label><label class="f">Грейд<select name="grade">${opts(gradeTitles(), v.grade)}</select></label>
        <label class="f">Занятость<select name="employment">${opts(EMPLOY, v.employment, 'Не указана')}</select></label></div>
      <div class="grid3"><label class="f">Формат работы<select name="work_format">${opts(FORMAT_RU, v.work_format, 'Не указан')}</select></label><label class="f">Город<input type="text" name="city" value="${esc(v.city)}" maxlength="80"></label><span></span></div>
      <div class="grid2">${moneyField('salary_from', 'Зарплата от, ₽', v.salary_from, 'required')}${moneyField('salary_to', 'Зарплата до, ₽', v.salary_to, 'required')}</div>
      <label class="f">Описание<textarea name="description" rows="5" maxlength="5000">${esc(v.description)}</textarea></label>
      <label class="f">Требования<textarea name="requirements" rows="4" maxlength="4000">${esc(v.requirements)}</textarea></label>
      <label class="f">Условия<textarea name="conditions" rows="4" maxlength="4000" placeholder="ДМС, оборудование, график, обучение">${esc(v.conditions)}</textarea></label>
      <div class="f"><b style="font-size:.92rem">Технологии</b><div style="margin-top:8px">${techPicker('stack', (v.stack || []).filter(t => S.techMap[t]), v.spec, 12)}</div></div>
      <button class="btn" type="submit">${isNew ? 'Опубликовать' : 'Сохранить'}</button></form>`;
}
route(/^\/e\/vacancies\/new$/, () => vacEditor(null), 'employer');
route(/^\/e\/vacancies\/(\d+)\/edit$/, async m => vacEditor(await api('/api/employer/vacancies/' + m[1])), 'employer');
forms.vacancy = async (f, d) => {
  const body = { title: d.title, description: d.description || '', requirements: d.requirements || '', conditions: d.conditions || '', spec: d.spec, grade: d.grade, employment: d.employment || '',
    work_format: d.work_format || '', city: d.city || '', salary_from: moneyNum(d.salary_from), salary_to: moneyNum(d.salary_to), stack: pickedTech(f) };
  if (f.dataset.id) await api('/api/employer/vacancies/' + f.dataset.id, { method: 'PUT', body });
  else await api('/api/employer/vacancies', { method: 'POST', body });
  toast(f.dataset.id ? 'Вакансия сохранена' : 'Вакансия опубликована', 'ok'); location.hash = '#/e/vacancies';
};

boot();
