/* ERGOPLUS · Asistente de evaluación en 5 pasos */
(function () {
  var $ = function (id) { return document.getElementById(id); };
  var S = { emp: '', puesto: null, puestos: [], trabs: [], trab: null, fotos: [], foto: null, pts: {}, mira: 'Derecha', vision: false, usoIA: false, activo: null, img: null, res: null };
  var PUNTOS = [['oreja', 'Oreja'], ['hombro', 'Hombro'], ['codo', 'Codo'], ['muneca', 'Muñeca'], ['mano', 'Mano'], ['cadera', 'Cadera']];
  var ETQ = {
    tipo_tarea: 'Tipo de tarea', silla_regulable: 'Silla regulable', silla_respaldo_lumbar: 'Respaldo lumbar', apoyabrazos: 'Apoyabrazos', apoyapies: 'Apoyapiés',
    pantalla_posicion: 'Posición de la pantalla', teclado_mouse: 'Teclado y mouse', ventilacion: 'Ventilación', espacio: 'Espacio', pausas_activas: 'Pausas activas',
    frecuencia_manipulacion: 'Frecuencia de manipulación de cargas'
  };
  var NUM = [['pantalla_distancia_cm', 'Distancia a la pantalla (cm)', 0, 300], ['horas_pantalla', 'Horas frente a pantalla al día', 0, 24], ['iluminacion_lux', 'Iluminación (lux)', 0, 100000],
    ['ruido_db', 'Ruido (dB)', 0, 140], ['temperatura_c', 'Temperatura (°C)', -10, 60], ['peso_tipico_kg', 'Peso típico manipulado (kg)', 0, 500]];

  /* ---------- navegación ---------- */
  function go(n) {
    document.querySelectorAll('.wstep').forEach(function (s) { s.classList.toggle('hidden', s.id !== 's' + n); });
    document.querySelectorAll('#wiz button').forEach(function (b) { b.classList.toggle('on', b.dataset.s === String(n)); });
    if (n === 3) gateFotos();
    if (n === 5) calcular(false);
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-go]'); if (b) { if (needs(+b.dataset.go)) return; go(+b.dataset.go); }
    var w = e.target.closest('#wiz button'); if (w) { if (needs(+w.dataset.s)) return; go(+w.dataset.s); }
  });
  function needs(n) {
    if (n > 1 && !S.emp) { toast('Primero selecciona la empresa.', 'warning'); go(1); return true; }
    return false;
  }

  /* ---------- paso 1 ---------- */
  function opts(sel, list, ph, fmt) {
    sel.innerHTML = '<option value="">' + ph + '</option>' + list.map(function (x) { return '<option value="' + x.id + '">' + esc(fmt(x)) + '</option>'; }).join('');
    sel.disabled = false;
  }
  $('empSel').onchange = async function () {
    S.emp = this.value; S.puesto = null; S.trab = null; S.fotos = []; fillTrab(null); renderConsent();
    if (!S.emp) { $('puestoSel').disabled = $('trabSel').disabled = true; return; }
    var r = await fetch('/api/empresa/' + S.emp + '/puestos'); S.puestos = await r.json();
    opts($('puestoSel'), S.puestos, '— Opcional —', function (p) { return p.etiqueta; });
    await loadTrabs();
  };
  async function loadTrabs(keep) {
    var r = await (await fetch('/api/trabajadores?empresa_id=' + S.emp)).json(); S.trabs = r.trabajadores || [];
    opts($('trabSel'), S.trabs, '— Selecciona —', function (t) { return t.nombre + (t.consentimiento ? ' ✓' : ''); });
    if (keep) $('trabSel').value = keep;
  }
  $('puestoSel').onchange = function () {
    S.puesto = S.puestos.find(function (p) { return String(p.id) === $('puestoSel').value; }) || null;
    buildCond(S.puesto ? S.puesto.condiciones : {});
  };
  $('trabSel').onchange = function () {
    S.trab = S.trabs.find(function (t) { return String(t.id) === $('trabSel').value; }) || null;
    fillTrab(S.trab); renderConsent(); loadFotos();
  };
  var tf = $('trabForm');
  function fillTrab(t) {
    tf.reset();
    if (t) ['nombre', 'documento', 'cargo', 'genero', 'fecha_nacimiento', 'antiguedad_meses', 'horas_jornada', 'lateralidad', 'estatura_cm', 'antecedentes'].forEach(function (k) {
      if (tf.elements[k]) tf.elements[k].value = t[k] == null ? '' : t[k];
    });
    $('trabEstado').textContent = t ? (t.edad != null ? t.edad + ' años · ' : '') + 'en la empresa: ' + t.antiguedad : '';
  }
  $('btnNuevoTrab').onclick = function () { S.trab = null; $('trabSel').value = ''; fillTrab(null); renderConsent(); tf.elements.nombre.focus(); };
  tf.onsubmit = async function (e) {
    e.preventDefault();
    if (!S.emp) { toast('Selecciona la empresa.', 'warning'); return; }
    var b = { empresa_id: +S.emp, puesto_id: S.puesto ? S.puesto.id : null };
    Array.prototype.forEach.call(tf.elements, function (el) { if (el.name) b[el.name] = el.value; });
    var r = await api(S.trab ? '/api/trabajador/' + S.trab.id : '/api/trabajador', { method: S.trab ? 'PUT' : 'POST', body: b });
    if (r.ok) { toast(r.data.msg, 'ok'); S.trab = r.data.trabajador; await loadTrabs(S.trab.id); fillTrab(S.trab); renderConsent(); loadFotos(); }
  };
  async function renderConsent() {
    var est = $('consEstado'), form = $('consForm');
    if (!S.trab) { est.className = 'note warn'; est.textContent = 'Selecciona o crea un trabajador para registrar su consentimiento.'; form.classList.add('hidden'); return; }
    if (S.trab.consentimiento) {
      est.className = 'note ok'; est.innerHTML = '✓ Consentimiento informado registrado el ' + esc(S.trab.consentimiento_fecha) + '. <button type="button" class="btn-sec btn-sm" id="btnRevocar">Revocar</button>';
      form.classList.add('hidden');
      $('btnRevocar').onclick = async function () {
        if (!confirm('¿Revocar el consentimiento? No se podrán subir fotos ni guardar evaluaciones de este trabajador hasta registrarlo de nuevo.')) return;
        var r = await api('/api/trabajador/' + S.trab.id + '/consentimiento', { method: 'DELETE' });
        if (r.ok) { S.trab.consentimiento = false; await loadTrabs(S.trab.id); S.trab = S.trabs.find(function (t) { return t.id === S.trab.id; }); renderConsent(); }
      };
    } else {
      est.className = 'note warn'; est.textContent = 'Este trabajador aún no ha dado su consentimiento informado.';
      form.classList.remove('hidden');
      if (!$('consTexto').textContent) { var t = await (await fetch('/api/consentimiento/texto')).json(); $('consTexto').textContent = t.texto; }
      $('consAcepta').checked = false; $('consNombre').value = S.trab.nombre || '';
    }
  }
  $('btnConsent').onclick = async function () {
    var r = await api('/api/trabajador/' + S.trab.id + '/consentimiento', { method: 'POST', body: { acepta: $('consAcepta').checked, nombre: $('consNombre').value } });
    if (r.ok) { toast(r.data.msg, 'ok'); var id = S.trab.id; await loadTrabs(id); S.trab = S.trabs.find(function (t) { return t.id === id; }); renderConsent(); }
  };

  /* ---------- paso 2 ---------- */
  function buildCond(c) {
    c = c || {}; var h = '';
    Object.keys(CAMPOS).forEach(function (k) {
      h += '<div><label>' + ETQ[k] + '</label><select name="' + k + '"><option value="">—</option>' + CAMPOS[k].map(function (o) { return '<option' + (c[k] === o ? ' selected' : '') + '>' + o + '</option>'; }).join('') + '</select></div>';
    });
    NUM.forEach(function (n) { h += '<div><label>' + n[1] + '</label><input type="number" name="' + n[0] + '" min="' + n[2] + '" max="' + n[3] + '" step="any" value="' + (c[n[0]] != null ? c[n[0]] : '') + '"></div>'; });
    h += '<div style="grid-column:1/-1"><label>Notas del puesto o del entorno</label><textarea name="notas" rows="2" maxlength="500">' + esc(c.notas || '') + '</textarea></div>';
    $('condForm').innerHTML = h; attachCounters($('condForm'));
  }
  function readCond() {
    var o = {}; Array.prototype.forEach.call($('condForm').elements, function (el) { if (el.name && el.value !== '') o[el.name] = el.value; }); return o;
  }
  $('btnGuardarCond').onclick = async function () {
    if (!S.puesto) { toast('Selecciona un puesto (paso 1) para guardar sus condiciones. Igual se usarán en esta evaluación.', 'warning'); return; }
    var r = await api('/api/puesto/' + S.puesto.id + '/condiciones', { method: 'PUT', body: readCond() });
    if (r.ok) { S.puesto.condiciones = r.data.condiciones; $('condEstado').textContent = '✓ Guardadas'; toast(r.data.msg, 'ok'); }
  };
  buildCond({});

  /* ---------- paso 3: fotos ---------- */
  function gateFotos() {
    var ok = S.trab && S.trab.consentimiento;
    $('fotoBloqueo').classList.toggle('hidden', !!ok); $('fotoPanel').classList.toggle('hidden', !ok);
    fetch('/api/ia/estado').then(function (r) { return r.json(); }).then(function (d) { S.vision = !!d.vision; $('btnIA').title = S.vision ? 'Detecta los puntos con IA' : 'La IA de fotos no está configurada (ANTHROPIC_API_KEY): marca los puntos a mano.'; $('btnIA').classList.toggle('btn-off', !S.vision); });
  }
  async function loadFotos() {
    S.fotos = []; S.foto = null; $('editor').classList.add('hidden');
    if (S.trab && S.trab.consentimiento) {
      var r = await (await fetch('/api/fotos?empresa_id=' + S.emp + '&trabajador_id=' + S.trab.id)).json();
      S.fotos = (r.fotos || []).filter(function (f) { return !f.evaluacion_id; });
    }
    renderThumbs();
  }
  function renderThumbs() {
    $('thumbs').innerHTML = S.fotos.length ? S.fotos.map(function (f) {
      return '<button type="button" class="thumb' + (S.foto && S.foto.id === f.id ? ' on' : '') + '" data-id="' + f.id + '"><img src="' + f.url + '" alt="Foto ' + f.vista + '"><span>' + f.vista + (Object.keys(f.puntos).length ? ' · ✓' : '') + '</span></button>';
    }).join('') : '<div class="muted">Aún no hay fotos para este trabajador.</div>';
  }
  $('thumbs').onclick = function (e) { var b = e.target.closest('.thumb'); if (b) abrirFoto(+b.dataset.id); };
  $('btnSubir').onclick = async function () {
    var f = $('fArchivo').files[0]; if (!f) { toast('Elige una imagen.', 'warning'); return; }
    var fd = new FormData(); fd.append('foto', f); fd.append('empresa_id', S.emp); fd.append('trabajador_id', S.trab.id); fd.append('vista', $('fVista').value);
    if (S.puesto) fd.append('puesto_id', S.puesto.id);
    var res = await fetch('/api/foto', { method: 'POST', body: fd }); var d = await res.json().catch(function () { return {}; });
    if (!res.ok) { toast(d.msg || 'No se pudo subir la foto.', 'error'); return; }
    $('fArchivo').value = ''; S.fotos.push(d.foto); renderThumbs(); abrirFoto(d.foto.id); toast('Foto subida.', 'ok');
  };

  var cv = $('cv'), ctx = cv.getContext('2d');
  function abrirFoto(id) {
    S.foto = S.fotos.find(function (f) { return f.id === id; }); if (!S.foto) return;
    S.pts = JSON.parse(JSON.stringify(S.foto.puntos || {})); S.mira = S.foto.mira_a || 'Derecha'; $('mira').value = S.mira; S.activo = null;
    var im = new Image(); im.onload = function () { S.img = im; $('editor').classList.remove('hidden'); fit(); chips(); dibujar(); renderThumbs(); }; im.src = S.foto.url;
  }
  function fit() {
    var w = Math.min($('editor').querySelector('.canvas-wrap').clientWidth || 640, 720);
    cv.width = w; cv.height = Math.round(w * S.img.naturalHeight / S.img.naturalWidth);
  }
  window.addEventListener('resize', function () { if (S.img && S.foto) { fit(); dibujar(); } });
  function chips() {
    $('ptChips').innerHTML = PUNTOS.map(function (p) {
      return '<button type="button" class="chip' + (S.pts[p[0]] ? ' done' : '') + (S.activo === p[0] ? ' on' : '') + '" data-p="' + p[0] + '">' + p[1] + '</button>';
    }).join('');
  }
  $('ptChips').onclick = function (e) { var b = e.target.closest('.chip'); if (!b) return; S.activo = (S.activo === b.dataset.p ? null : b.dataset.p); chips(); $('edAyuda').textContent = S.activo ? 'Haz clic en la foto para colocar: ' + b.textContent + '.' : 'Elige un punto y haz clic en la foto para colocarlo. Arrastra los puntos para corregirlos.'; };
  $('mira').onchange = function () { S.mira = this.value; dibujar(); };
  $('btnLimpiar').onclick = function () { S.pts = {}; S.activo = 'oreja'; chips(); dibujar(); };

  function ang() {
    var P = S.pts, d = S.mira === 'Derecha' ? 1 : -1, o = {}, deg = 180 / Math.PI;
    function dn(a, b) { return [(b[0] - a[0]) * d, b[1] - a[1]]; } // vector con "adelante" = +x
    var tronco = null;
    if (P.hombro && P.cadera) { var v = dn(P.cadera, P.hombro); tronco = Math.atan2(v[0], -v[1]) * deg; o.tronco = tronco; }
    if (P.hombro && P.oreja) { var n = dn(P.hombro, P.oreja); var na = Math.atan2(n[0], -n[1]) * deg; o.cuello = na - (tronco || 0); }
    if (P.hombro && P.codo) {
      var a = dn(P.hombro, P.codo), aa = Math.atan2(a[0], a[1]) * deg, td = 0;
      if (P.cadera) { var t = dn(P.hombro, P.cadera); td = Math.atan2(t[0], t[1]) * deg; }
      o.brazo = aa - td;
    }
    if (P.hombro && P.codo && P.muneca) {
      var u = [P.hombro[0] - P.codo[0], P.hombro[1] - P.codo[1]], w = [P.muneca[0] - P.codo[0], P.muneca[1] - P.codo[1]];
      var inter = Math.acos(Math.max(-1, Math.min(1, (u[0] * w[0] + u[1] * w[1]) / (Math.hypot(u[0], u[1]) * Math.hypot(w[0], w[1]))))) * deg;
      o.antebrazo = 180 - inter;
    }
    if (P.codo && P.muneca && P.mano) {
      var f = dn(P.codo, P.muneca), m = dn(P.muneca, P.mano);
      o.muneca = (Math.atan2(m[1], m[0]) - Math.atan2(f[1], f[0])) * deg; if (o.muneca > 180) o.muneca -= 360; if (o.muneca < -180) o.muneca += 360; o.muneca = -o.muneca;
    }
    Object.keys(o).forEach(function (k) { o[k] = Math.round(o[k] * 10) / 10; });
    return o;
  }
  function dibujar() {
    if (!S.img) return;
    ctx.clearRect(0, 0, cv.width, cv.height); ctx.drawImage(S.img, 0, 0, cv.width, cv.height);
    var P = S.pts, W = cv.width, H = cv.height;
    function seg(a, b, col) { if (P[a] && P[b]) { ctx.strokeStyle = col; ctx.lineWidth = 3; ctx.beginPath(); ctx.moveTo(P[a][0] * W, P[a][1] * H); ctx.lineTo(P[b][0] * W, P[b][1] * H); ctx.stroke(); } }
    seg('oreja', 'hombro', '#ffd23f'); seg('hombro', 'cadera', '#ffd23f'); seg('hombro', 'codo', '#3ddc97'); seg('codo', 'muneca', '#3ddc97'); seg('muneca', 'mano', '#3ddc97');
    PUNTOS.forEach(function (p) {
      var q = P[p[0]]; if (!q) return;
      ctx.fillStyle = '#6a4bc0'; ctx.strokeStyle = '#fff'; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(q[0] * W, q[1] * H, 7, 0, 7); ctx.fill(); ctx.stroke();
      ctx.font = '600 12px Inter, sans-serif'; ctx.fillStyle = '#fff'; ctx.strokeStyle = 'rgba(30,20,60,.8)'; ctx.lineWidth = 3; ctx.strokeText(p[1], q[0] * W + 10, q[1] * H - 8); ctx.fillText(p[1], q[0] * W + 10, q[1] * H - 8);
    });
    var A = ang(), n = { tronco: 'Tronco', cuello: 'Cuello', brazo: 'Brazo', antebrazo: 'Antebrazo', muneca: 'Muñeca' };
    $('angBox').innerHTML = '<h4>Ángulos medidos</h4>' + (Object.keys(A).length ? Object.keys(n).filter(function (k) { return A[k] != null; }).map(function (k) { return '<div class="ang"><span>' + n[k] + '</span><b>' + A[k] + '°</b></div>'; }).join('') : '<div class="muted">Coloca los puntos para ver los ángulos.</div>');
    S.ang = A;
  }
  function pos(e) { var r = cv.getBoundingClientRect(); return [(e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height]; }
  var drag = null;
  cv.addEventListener('pointerdown', function (e) {
    var p = pos(e), best = null, bd = 0.03;
    PUNTOS.forEach(function (k) { var q = S.pts[k[0]]; if (q) { var dd = Math.hypot(q[0] - p[0], q[1] - p[1]); if (dd < bd) { bd = dd; best = k[0]; } } });
    if (best) { drag = best; cv.setPointerCapture(e.pointerId); return; }
    if (S.activo) {
      S.pts[S.activo] = [p[0], p[1]];
      var i = PUNTOS.findIndex(function (k) { return k[0] === S.activo; }), sig = null;
      for (var j = i + 1; j < PUNTOS.length; j++) if (!S.pts[PUNTOS[j][0]]) { sig = PUNTOS[j][0]; break; }
      S.activo = sig; chips(); dibujar();
    }
  });
  cv.addEventListener('pointermove', function (e) { if (!drag) return; var p = pos(e); S.pts[drag] = [Math.max(0, Math.min(1, p[0])), Math.max(0, Math.min(1, p[1]))]; dibujar(); });
  cv.addEventListener('pointerup', function () { drag = null; chips(); });

  async function guardarFoto(origen) {
    var r = await api('/api/foto/' + S.foto.id, { method: 'PUT', body: { puntos: S.pts, angulos: S.ang || {}, mira_a: S.mira, vista: S.foto.vista, origen: origen } });
    if (r.ok) { var i = S.fotos.findIndex(function (f) { return f.id === S.foto.id; }); S.fotos[i] = r.data.foto; S.foto = r.data.foto; renderThumbs(); }
    return r.ok;
  }
  $('btnGuardarFoto').onclick = async function () { if (await guardarFoto(S.foto.origen)) toast('Puntos guardados.', 'ok'); };
  $('btnBorrarFoto').onclick = async function () {
    if (!confirm('¿Eliminar esta foto?')) return;
    var r = await api('/api/foto/' + S.foto.id, { method: 'DELETE' });
    if (r.ok) { S.fotos = S.fotos.filter(function (f) { return f.id !== S.foto.id; }); S.foto = null; $('editor').classList.add('hidden'); renderThumbs(); toast(r.data.msg, 'ok'); }
  };
  $('btnIA').onclick = async function () {
    if (!S.vision) { toast('La IA de fotos no está configurada en este servidor (falta ANTHROPIC_API_KEY). Marca los puntos manualmente.', 'warning'); return; }
    this.disabled = true; this.textContent = 'Analizando…';
    var r = await api('/api/ia/foto/' + S.foto.id, { method: 'POST' });
    this.disabled = false; this.textContent = '✨ Sugerir con IA';
    if (r.ok) {
      S.pts = {}; PUNTOS.forEach(function (p) { if (r.data.puntos[p[0]]) S.pts[p[0]] = r.data.puntos[p[0]]; });
      S.mira = r.data.mira_a; $('mira').value = S.mira; S.usoIA = true; chips(); dibujar(); await guardarFoto('ia');
      toast('Puntos sugeridos por la IA. Revísalos y corrígelos si hace falta.', 'ok');
    }
  };
  var CAMPO = { tronco: 'tronco_angulo', cuello: 'cuello_angulo', brazo: 'brazo_angulo', antebrazo: 'antebrazo_angulo', muneca: 'muneca_angulo' };
  $('btnAplicar').onclick = async function () {
    var A = S.ang || {}; if (!Object.keys(A).length) { toast('Aún no hay ángulos que aplicar.', 'warning'); return; }
    Object.keys(CAMPO).forEach(function (k) { if (A[k] != null) setField(CAMPO[k], Math.round(A[k]), 'foto'); });
    await guardarFoto(S.foto.origen); toast('Ángulos copiados a la medición (paso 4). Puedes corregirlos.', 'ok');
  };

  /* ---------- paso 4 ---------- */
  var rf = $('rulaForm');
  function setField(name, v, tag) {
    var el = rf.elements[name]; if (!el) return;
    if (el.type === 'checkbox') el.checked = !!v; else el.value = v;
    el.dispatchEvent(new Event('input', { bubbles: true }));
    var box = el.closest('label') || el.parentElement; box.classList.add(tag === 'foto' ? 'sug-foto' : 'sug');
  }
  rf.addEventListener('change', function (e) { var b = e.target.closest('label') || e.target.parentElement; b.classList.remove('sug', 'sug-foto'); });
  rf.addEventListener('input', function (e) { if (e.isTrusted) { var b = e.target.closest('label') || e.target.parentElement; b.classList.remove('sug', 'sug-foto'); } });
  $('btnSugerir').onclick = async function () {
    var r = await api('/api/ia/sugerir', { method: 'POST', body: { condiciones: readCond(), trabajador_id: S.trab ? S.trab.id : null } });
    if (!r.ok) return;
    var s = r.data.sugerencia; S.usoIA = true;
    Object.keys(s.valores).forEach(function (k) { setField(k, s.valores[k], 'sug'); });
    $('sugOut').classList.remove('hidden');
    $('sugOut').innerHTML = '<div class="split"><div><h4>Por qué estos valores</h4><ul class="tick">' + s.razones.map(function (x) { return '<li>' + esc(x) + '</li>'; }).join('') + '</ul></div>' +
      '<div><h4>Pasos sugeridos para la visita</h4><ul class="check">' + s.pasos.map(function (x) { return '<li><label><input type="checkbox"> ' + esc(x) + '</label></li>'; }).join('') + '</ul></div></div>' +
      '<p class="muted" style="font-size:12px">Los campos con fondo lila fueron sugeridos; los de fondo verde vienen de las fotos. Edítalos si lo que observas es distinto.</p>';
  };
  function medicion() {
    var d = {}; Array.prototype.forEach.call(rf.elements, function (el) { if (el.name) d[el.name] = el.type === 'checkbox' ? el.checked : el.value; }); return d;
  }

  /* ---------- paso 5 ---------- */
  var COLN = { Verde: '#2e9d5b', Amarillo: '#e3a21a', Rojo: '#d64533' };
  async function calcular(regen) {
    var r = await api('/api/ia/recomendar', { method: 'POST', body: { medicion: medicion(), condiciones: readCond(), trabajador_id: S.trab ? S.trab.id : null } });
    if (!r.ok) return; S.res = r.data.resultado; var x = S.res;
    $('resBox').innerHTML = '<div class="res-top"><div class="sem big" role="img" aria-label="Semáforo ' + x.nivel + '">' + ['Rojo', 'Amarillo', 'Verde'].map(function (n) { return '<i class="' + n + (x.nivel === n ? ' on' : '') + '"></i>'; }).join('') + '</div>' +
      '<div><div class="score" style="color:' + COLN[x.nivel] + '">' + x.puntaje_final + '<small> / 7</small></div><div class="lvl" style="color:' + COLN[x.nivel] + '">' + {Verde: 'Aceptable', Amarillo: 'Requiere revisión y mejoras', Rojo: 'Intervención prioritaria'}[x.nivel] + '</div><p>' + esc(x.accion_sugerida) + '</p></div></div>' +
      '<div class="parts">' + [['Brazo', x.brazo], ['Antebrazo', x.antebrazo], ['Muñeca', x.muneca], ['Cuello', x.cuello], ['Tronco', x.tronco], ['Piernas', x.piernas], ['Grupo A', x.puntos_a], ['Grupo B', x.puntos_b], ['Actividad', '+' + x.puntos_actividad], ['Fuerza', '+' + x.puntos_fuerza]].map(function (p) { return '<div><span>' + p[0] + '</span><b>' + p[1] + '</b></div>'; }).join('') + '</div>';
    var c = r.data.compatibilidad;
    $('compBox').classList.toggle('hidden', !c);
    if (c) $('compBody').innerHTML = '<p>Resultado global: <b style="color:' + COLN[c.global] + '">' + c.global + '</b> <span class="muted">· apoyo para priorizar seguimiento, no un concepto de aptitud laboral.</span></p><table><tr><th>Factor</th><th>Estado</th><th>Detalle</th></tr>' +
      c.factores.map(function (f) { return '<tr><td>' + esc(f.factor) + '</td><td><span class="dotc" style="background:' + COLN[f.estado] + '"></span> ' + f.estado + '</td><td class="muted">' + esc(f.detalle) + '</td></tr>'; }).join('') + '</table>';
    if (regen || !$('recs').value.trim()) $('recs').value = r.data.texto;
  }
  $('btnRegen').onclick = function () { if (!$('recs').value.trim() || confirm('Se reemplazará el texto actual de las recomendaciones. ¿Continuar?')) calcular(true); };
  $('btnGuardarEval').onclick = async function () {
    if (!S.emp) { toast('Selecciona la empresa.', 'warning'); go(1); return; }
    if (!S.trab) { if (!confirm('No elegiste un trabajador: la evaluación quedará sin perfil ni compatibilidad. ¿Guardar igual?')) { go(1); return; } }
    var b = medicion(); b.empresa_id = +S.emp; b.puesto_id = S.puesto ? S.puesto.id : null; b.trabajador_id = S.trab ? S.trab.id : null;
    b.condiciones = readCond(); b.recomendaciones = $('recs').value; b.sugerencias = $('obs').value; b.ia_usada = S.usoIA; b.foto_ids = S.fotos.map(function (f) { return f.id; });
    this.disabled = true;
    var r = await api('/api/rula/guardar', { method: 'POST', body: b });
    if (r.ok) { toast(r.data.msg, 'ok'); setTimeout(function () { location.href = r.data.url; }, 500); } else this.disabled = false;
  };
})();
