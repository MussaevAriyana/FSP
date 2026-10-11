/* Кабинет модератора: очередь попыток, отмеченных прокторингом, журнал, снимки, решение. */
'use strict';

const MOD_STATE = { flagged: 'Ждут решения', decided: 'Разобранные', all: 'Все с риском' };
const RV = { clean: 'без замечаний', flagged: 'на проверке', cleared: 'отметка снята', annulled: 'аннулирована' };

route(/^\/m(?:\?.*)?$/, async () => {
  const st = (location.hash.split('?')[1] || '').replace('state=', '') || 'flagged';
  const q = await api('/api/moderator/queue?state=' + (MOD_STATE[st] ? st : 'flagged'));
  const tabs = Object.entries(MOD_STATE).map(([k, t]) => `<a class="tab ${k === st ? 'on' : ''}" href="#/m?state=${k}">${t}</a>`).join('');
  return `<div class="page-head"><div><h1>Проверка тестов</h1><p class="muted">Порог проверки — риск ${q.flag_at}, порог автоматического прекращения — ${q.terminate_at}.</p></div></div>
    <div class="tabs">${tabs}</div>
    ${q.items.length ? `<div class="panel"><table class="t"><thead><tr><th>Попытка</th><th>Кандидат</th><th>Категория</th><th>Результат</th><th>Риск</th><th>Статус</th><th></th></tr></thead><tbody>
      ${q.items.map(i => `<tr><td>#${i.id}<div class="small muted">${dt(i.started_at)}</div></td><td><b style="font-family:var(--mono)">${esc(i.pseudo_code)}</b></td><td>${esc(catName(i.spec, i.target_grade))}</td>
        <td>${i.status === 'terminated' ? '<span class="status failed">прекращён</span>' : i.ratio == null ? '—' : Math.round(i.ratio * 100) + '% ' + (i.passed ? '<span class="status passed">зачёт</span>' : '<span class="status failed">не зачтено</span>')}</td>
        <td><span class="risk ${i.risk >= 36 ? 'bad' : 'warn'}">${i.risk}</span></td><td>${esc(RV[i.review_state] || i.review_state)}<div class="small muted">событий: ${i.evs}, снимков: ${i.snaps}</div></td>
        <td><a class="btn small" href="#/m/${i.id}">Открыть</a></td></tr>`).join('')}</tbody></table></div>`
      : empty('Очередь пуста', 'Нет попыток, требующих решения.')}`;
}, 'moderator');

route(/^\/m\/(\d+)$/, async m => {
  const d = await api('/api/moderator/attempts/' + m[1]);
  const byKind = {};
  d.events.forEach(e => { if (e.weight > 0) { byKind[e.label] = (byKind[e.label] || 0) + 1; } });
  const done = d.state === 'cleared' || d.state === 'annulled';
  return {
    html: `<div class="page-head"><div><h1>Попытка #${d.id} · ${esc(d.code)}</h1><p class="muted">${esc(catName(d.spec, d.grade))} · ${dt(d.started_at)} · риск <b>${d.risk}</b> · ${esc(RV[d.state] || d.state)}</p></div><a class="btn ghost" href="#/m">К очереди</a></div>
      <div class="panel"><h2>Сводка</h2>
        <p>Результат: ${d.ratio == null ? '—' : Math.round(d.ratio * 100) + '%'} ${d.status === 'terminated' ? '(попытка прекращена автоматически)' : d.passed ? '(зачёт)' : '(не зачтено)'}</p>
        ${Object.keys(byKind).length ? '<div class="row">' + Object.entries(byKind).map(([k, n]) => `<span class="chip">${esc(k)} × ${n}</span>`).join('') + '</div>' : '<p class="muted">Нарушений не зафиксировано.</p>'}</div>
      <div class="panel"><h2>Снимки с камеры (${d.snapshots.length})</h2>
        ${d.snapshots.length ? `<div class="snaps" id="snaps" data-ids="${d.snapshots.map(s => s.id).join(',')}"></div>` : '<p class="muted">Снимков нет: истёк срок хранения или камера не работала.</p>'}</div>
      <div class="panel"><h2>Журнал событий</h2>
        ${d.events.length ? `<table class="t"><thead><tr><th>Время</th><th>Событие</th><th>Вес</th><th>Детали</th></tr></thead><tbody>${d.events.map(e => `<tr><td>${new Date(e.at).toLocaleTimeString('ru-RU')}</td><td>${esc(e.label)}</td><td>${e.weight}</td><td class="small muted">${esc(Object.entries(e.meta).map(([k, v]) => k + '=' + v).join(', '))}</td></tr>`).join('')}</tbody></table>` : '<p class="muted">Журнал пуст.</p>'}</div>
      <div class="panel"><h2>Решение</h2>
        ${d.decisions.length ? d.decisions.map(x => `<p class="small">${dt(x.at)} — <b>${x.decision === 'clear' ? 'отметка снята' : 'аннулирована'}</b>${x.comment ? ': ' + esc(x.comment) : ''}</p>`).join('') : ''}
        ${d.status === 'active' ? '<p class="muted">Попытка ещё идёт.</p>' : `<form data-form="modDecide" data-id="${d.id}">
          <label class="f">Комментарий<textarea name="comment" rows="3" maxlength="1000" placeholder="Что вы увидели в журнале и на снимках"></textarea></label>
          <div class="row"><button class="btn ok" type="submit" name="decision" value="clear">Снять отметку — результат честный</button>
          <button class="btn danger" type="submit" name="decision" value="annul">Аннулировать попытку</button></div></form>`}</div>`,
    after: async () => {
      const box = $('#snaps'); if (!box) return;
      for (const id of box.dataset.ids.split(',')) {
        try {
          const b = await api('/api/moderator/snapshots/' + id, { blob: true });
          const img = document.createElement('img'); img.src = URL.createObjectURL(b); img.alt = 'Снимок ' + id; box.appendChild(img);
        } catch (_) { /* снимок удалён */ }
      }
    },
  };
}, 'moderator');
let modPicked = 'clear';
document.addEventListener('click', e => { const b = e.target.closest('button[name=decision]'); if (b) modPicked = b.value; }, true);
forms.modDecide = async (f, d) => {
  if (modPicked === 'annul' && !(await confirmBox('Аннулировать попытку?', 'Если категория присвоена этой попыткой, она будет снята.', 'Аннулировать', true))) return;
  await api(`/api/moderator/attempts/${f.dataset.id}/decision`, { method: 'POST', body: { decision: modPicked, comment: d.comment || '' } });
  toast(modPicked === 'annul' ? 'Попытка аннулирована' : 'Отметка снята', 'ok'); render();
};
