/* Прокторинг на стороне браузера: события, камера, полноэкранный режим. Всё взвешивает и решает сервер (services/proctor.py). */
'use strict';

const Proctor = (() => {
  const P = { stream: null, video: null, attempt: null, queue: [], timers: [], armed: false, cid: null, info: { risk: 0 }, lastDev: 0, lastFace: 0 };
  const rid = () => Array.from(crypto.getRandomValues(new Uint8Array(8)), b => b.toString(16).padStart(2, '0')).join('');
  P.cid = sessionStorage.getItem('proc_cid') || rid(); sessionStorage.setItem('proc_cid', P.cid);   // у каждой вкладки свой идентификатор

  /* ---------- камера ---------- */
  P.cameraOn = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) throw new Error('Браузер не поддерживает доступ к камере (нужен HTTPS или localhost)');
    try { P.stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false }); }
    catch (e) { throw new Error('Не удалось включить камеру: разрешите доступ в браузере и проверьте, что камеру не занимает другое приложение'); }
    P.video = document.createElement('video'); P.video.muted = true; P.video.playsInline = true; P.video.srcObject = P.stream;
    await P.video.play().catch(() => {});
    return P.stream;
  };
  P.cameraAlive = () => !!(P.stream && P.stream.getVideoTracks().some(t => t.readyState === 'live' && t.enabled));
  P.cameraOff = () => { if (P.stream) P.stream.getTracks().forEach(t => t.stop()); P.stream = null; P.video = null; };

  /* ---------- события ---------- */
  const push = (kind, meta) => { if (P.armed) P.queue.push({ kind, meta: meta || {} }); };
  const onVis = () => { if (document.hidden) push('tab_hidden'); };
  let blurT = 0;
  const onBlur = () => { blurT = setTimeout(() => { if (!document.hidden) push('window_blur'); }, 400); };
  const onFocus = () => clearTimeout(blurT);
  const onFs = () => { if (!document.fullscreenElement && P.armed) { push('fullscreen_exit'); P.onGate && P.onGate(); } };
  const stop = e => { e.preventDefault(); };
  const onCopy = e => { push(e.type); stop(e); };
  const onCtx = e => { push('contextmenu'); stop(e); };
  const onKey = e => {
    const k = e.key || '', c = e.ctrlKey || e.metaKey;
    if (k === 'F12' || (c && e.shiftKey && /^[ijc]$/i.test(k))) { push('devtools', { key: k }); stop(e); }
    else if (c && /^[uspa]$/i.test(k) && !/^a$/i.test(k)) { push(/^p$/i.test(k) ? 'print' : 'shortcut', { key: k }); stop(e); }
    else if (k === 'PrintScreen') { push('shortcut', { key: k }); }
    else if (e.altKey && k === 'Tab') push('shortcut', { key: 'Alt+Tab' });
  };
  const onPrint = () => push('print');
  const devtoolsProbe = () => {
    const wide = window.outerWidth - window.innerWidth > 240, tall = window.outerHeight - window.innerHeight > 260;
    if ((wide || tall) && !document.fullscreenElement && Date.now() - P.lastDev > 30000) { P.lastDev = Date.now(); push('devtools', { probe: 'size' }); }
  };

  /* ---------- снимки ---------- */
  const lum = ctx => {
    const d = ctx.getImageData(0, 0, ctx.canvas.width, ctx.canvas.height).data; let s = 0, n = 0;
    for (let i = 0; i < d.length; i += 64) { s += 0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]; n++; }
    return s / Math.max(n, 1);
  };
  const snap = async () => {
    if (!P.cameraAlive() || !P.video || !P.video.videoWidth) return null;
    const cv = document.createElement('canvas'); cv.width = 320; cv.height = 240;
    const ctx = cv.getContext('2d', { willReadFrequently: true }); ctx.drawImage(P.video, 0, 0, 320, 240);
    if (lum(ctx) < 14) push('camera_covered');
    if ('FaceDetector' in window && Date.now() - P.lastFace > 20000) {
      P.lastFace = Date.now();
      try { const faces = await new FaceDetector({ fastMode: true, maxDetectedFaces: 3 }).detect(cv); if (faces.length === 0) push('no_face'); else if (faces.length > 1) push('multi_face', { n: faces.length }); } catch (_) { /* детектор недоступен */ }
    }
    return cv.toDataURL('image/jpeg', 0.55);
  };

  /* ---------- распознавание предметов в кадре (телефон, второй человек) ---------- */
  // Модель COCO-SSD (TensorFlow.js) грузится в браузере с CDN при включении камеры; нужен доступ к cdn.jsdelivr.net и storage.googleapis.com.
  // Если загрузка не удалась, тест идёт как раньше (снимки + модератор), а в журнал попадает служебная отметка.
  P.det = { model: null, loading: false, failed: false, streak: {}, busy: false };
  const CDN = ['https://cdn.jsdelivr.net/npm/@tensorflow/tfjs@4.22.0/dist/tf.min.js', 'https://cdn.jsdelivr.net/npm/@tensorflow-models/coco-ssd@2.2.3/dist/coco-ssd.min.js'];
  const loadScript = src => new Promise((ok, no) => { const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = () => no(new Error('load ' + src)); document.head.appendChild(s); });
  P.loadDetector = async () => {
    if (P.det.model || P.det.loading || P.det.failed) return;
    P.det.loading = true;
    try { await loadScript(CDN[0]); await loadScript(CDN[1]); P.det.model = await window.cocoSsd.load({ base: 'lite_mobilenet_v2' }); }
    catch (_) { P.det.failed = true; } finally { P.det.loading = false; }
  };
  P.detectorState = () => P.det.model ? 'coco-ssd' : P.det.failed ? 'unavailable' : 'loading';
  // событие фиксируется после двух подряд срабатываний (меньше ложных), затем пауза
  const hit = (kind, cond, meta) => {
    const s = P.det.streak; s[kind] = cond ? (s[kind] || 0) + 1 : Math.min(0, s[kind] || 0) + (s[kind] < 0 ? 1 : 0);
    if (s[kind] >= 2) { s[kind] = -6; push(kind, meta); flush(true); }
  };
  const detect = async () => {
    if (!P.armed || !P.det.model || P.det.busy || !P.video || !P.video.videoWidth || document.hidden) return;
    P.det.busy = true;
    try {
      const preds = await P.det.model.detect(P.video, 10, 0.45);
      const phones = preds.filter(p => p.class === 'cell phone' && p.score >= 0.55), persons = preds.filter(p => p.class === 'person' && p.score >= 0.6);
      hit('phone_detected', phones.length > 0, { score: phones[0] ? Math.round(phones[0].score * 100) : 0 });
      hit('multi_person', persons.length > 1, { n: persons.length });
      if (!('FaceDetector' in window)) hit('no_face', persons.length === 0, { by: 'coco' });
    } catch (_) { /* кадр не прочитан — пропускаем цикл */ } finally { P.det.busy = false; }
  };

  /* ---------- отправка ---------- */
  let busy = false;
  const flush = async (withSnap) => {
    if (!P.attempt || busy) return;
    busy = true;
    try {
      const events = P.queue.splice(0, 60);
      const snapshot = withSnap ? await snap() : null;
      const r = await api(`/api/candidate/tests/${P.attempt}/proctor`, { method: 'POST', body: { cid: P.cid, events, snapshot, camera: P.cameraAlive() } });
      P.info = r; P.onState && P.onState(r);
      if (r.terminated) P.onTerminated && P.onTerminated(r);
    } catch (e) { if (e.status === 401) return; /* сеть мигнула — события уйдут со следующим пакетом */ } finally { busy = false; }
  };

  P.begin = (attemptId, hooks = {}) => {
    P.end();
    P.attempt = attemptId; P.onState = hooks.onState; P.onGate = hooks.onGate; P.onTerminated = hooks.onTerminated;
    document.addEventListener('visibilitychange', onVis); window.addEventListener('blur', onBlur); window.addEventListener('focus', onFocus);
    document.addEventListener('fullscreenchange', onFs); document.addEventListener('copy', onCopy); document.addEventListener('cut', onCopy);
    document.addEventListener('paste', onCopy); document.addEventListener('contextmenu', onCtx); document.addEventListener('keydown', onKey, true);
    window.addEventListener('beforeprint', onPrint);
    P.loadDetector();
    P.timers = [setInterval(() => flush(false), 8000), setInterval(() => flush(true), 30000), setInterval(devtoolsProbe, 4000), setInterval(detect, 5000)];
  };
  P.arm = () => { P.armed = true; P.queue.push({ kind: 'info', meta: { detector: P.detectorState() } }); flush(true); };       // с этого момента нарушения учитываются
  P.disarm = () => { P.armed = false; };
  P.end = async () => {
    P.timers.forEach(clearInterval); P.timers = []; P.armed = false;
    document.removeEventListener('visibilitychange', onVis); window.removeEventListener('blur', onBlur); window.removeEventListener('focus', onFocus);
    document.removeEventListener('fullscreenchange', onFs); document.removeEventListener('copy', onCopy); document.removeEventListener('cut', onCopy);
    document.removeEventListener('paste', onCopy); document.removeEventListener('contextmenu', onCtx); document.removeEventListener('keydown', onKey, true);
    window.removeEventListener('beforeprint', onPrint);
    if (document.fullscreenElement) { try { await document.exitFullscreen(); } catch (_) { /* уже вышли */ } }
    P.attempt = null;
  };
  P.flushNow = () => flush(true);
  P.fullscreen = async () => { try { await document.documentElement.requestFullscreen(); } catch (_) { /* iOS и др.: полноэкранный режим недоступен */ } };
  P.preview = el => { if (el && P.stream) { el.srcObject = P.stream; el.play().catch(() => {}); } };
  return P;
})();
