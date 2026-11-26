/* Guía visual RULA: figuras SVG que se mueven con el ángulo escrito */
(function () {
  var COL = { 1: '#4caf7a', 2: '#b7c74a', 3: '#f0a93a', 4: '#e0554b', 0: '#9a94b3' };
  var W = 230, H = 190;
  // base: 'down' (0° = hacia abajo), 'up' (0° = hacia arriba), 'right' (0° = hacia la derecha). Positivo = flexión hacia adelante.
  var KINDS = {
    brazo: { t: 'Paso 2.1 · Brazo', sub: 'Ángulo de flexión respecto al tronco', pv: [78, 98], base: 'down', len: 78, R: 84,
      ctx: function (p) { return line(p[0], p[1] - 62, p[0], p[1] + 8, 6) + '<circle cx="' + p[0] + '" cy="' + (p[1] - 76) + '" r="13" fill="#cfc7e8"/>'; },
      wedges: [[-60, -20, 2], [-20, 20, 1], [20, 45, 2], [45, 90, 3], [90, 150, 4]], def: 20, unit: '°',
      note: 'Extensión >20°, flexión 20–45° (+2), 45–90° (+3), >90° (+4).' },
    antebrazo: { t: 'Paso 2.2 · Antebrazo', sub: 'Flexión del codo (0° = brazo extendido)', pv: [80, 72], base: 'down', len: 78, R: 82,
      ctx: function (p) { return line(p[0], p[1] - 40, p[0], p[1], 6) + '<circle cx="' + p[0] + '" cy="' + (p[1] - 54) + '" r="11" fill="#cfc7e8"/>'; },
      wedges: [[0, 60, 2], [60, 100, 1], [100, 160, 2]], def: 90, unit: '°',
      note: 'Entre 60° y 100° es lo adecuado (1). Fuera de ese rango, +2.' },
    muneca: { t: 'Paso 2.3 · Muñeca', sub: 'Flexión/extensión respecto al antebrazo', pv: [88, 95], base: 'right', len: 74, R: 80,
      ctx: function (p) { return line(p[0] - 70, p[1], p[0], p[1], 6) + '<circle cx="' + (p[0] - 74) + '" cy="' + p[1] + '" r="10" fill="#cfc7e8"/>'; },
      wedges: [[-60, -15, 3], [-15, -5, 2], [-5, 5, 1], [5, 15, 2], [15, 60, 3]], def: 0, unit: '°',
      note: 'Neutra (1), hasta 15° (+2), más de 15° (+3).' },
    cuello: { t: 'Paso 3.1 · Cuello', sub: 'Inclinación de la cabeza (negativo = extensión)', pv: [100, 128], base: 'up', len: 70, R: 76,
      ctx: function (p) { return line(p[0], p[1], p[0], p[1] + 56, 6); },
      wedges: [[-45, 0, 4], [0, 10, 1], [10, 20, 2], [20, 70, 3]], def: 0, unit: '°', head: true,
      note: '0–10° (1), 10–20° (+2), >20° (+3). Extensión (+4).' },
    tronco: { t: 'Paso 3.2 · Tronco', sub: 'Inclinación del tronco (0° = erguido y apoyado)', pv: [100, 150], base: 'up', len: 96, R: 92,
      ctx: function (p) { return line(p[0], p[1], p[0] - 36, p[1] + 2, 6); },
      wedges: [[-6, 6, 1], [6, 20, 2], [20, 60, 3], [60, 105, 4]], def: 0, unit: '°', head: true,
      note: '0° bien apoyado (1), 0–20° (+2), 20–60° (+3), >60° (+4).' },
    carga: { t: 'Paso 4 · Carga o fuerza', sub: 'Peso manipulado (kg)', bar: true, def: 0, unit: ' kg',
      wedges: [[0, 2, 0], [2, 10, 1], [10, 20, 2], [20, 40, 3]],
      note: '<2 kg intermitente (0), 2–10 kg (+1), 10 kg estático/repetido (+2), >10 kg o golpes (+3).' },
    piernas: { t: 'Paso 3.3 · Piernas y pies', sub: 'Apoyo y reparto del peso', legs: true,
      note: 'Pies apoyados y peso repartido = +1. Sin apoyo estable = +2.' }
  };
  function line(x1, y1, x2, y2, w) { return '<line x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke="#cfc7e8" stroke-width="' + w + '" stroke-linecap="round"/>'; }
  function vec(base, a) {
    var r = a * Math.PI / 180;
    if (base === 'down') return [Math.sin(r), Math.cos(r)];
    if (base === 'up') return [Math.sin(r), -Math.cos(r)];
    return [Math.cos(r), Math.sin(r)];
  }
  function score(k, v) { var s = null; k.wedges.forEach(function (w) { if (v >= w[0] && v <= w[1]) s = w[2]; }); return s; }
  function draw(k, v) {
    if (k.legs) {
      return '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Piernas y pies">' +
        '<g stroke="#cfc7e8" stroke-width="7" stroke-linecap="round"><line x1="70" y1="40" x2="70" y2="110"/><line x1="70" y1="110" x2="52" y2="150"/><line x1="70" y1="110" x2="92" y2="150"/></g>' +
        '<g stroke="' + COL[1] + '" stroke-width="5" stroke-linecap="round"><line x1="40" y1="152" x2="64" y2="152"/><line x1="82" y1="152" x2="106" y2="152"/></g><text x="70" y="172" text-anchor="middle" font-size="10" fill="' + COL[1] + '">apoyado (+1)</text>' +
        '<g stroke="#cfc7e8" stroke-width="7" stroke-linecap="round"><line x1="170" y1="40" x2="170" y2="100"/><line x1="170" y1="100" x2="152" y2="135"/><line x1="170" y1="100" x2="196" y2="120"/></g>' +
        '<g stroke="' + COL[4] + '" stroke-width="5" stroke-linecap="round"><line x1="140" y1="140" x2="160" y2="138"/></g><text x="170" y="172" text-anchor="middle" font-size="10" fill="' + COL[4] + '">sin apoyo (+2)</text></svg>';
    }
    if (k.bar) {
      var max = 40, x0 = 18, wbar = W - 36, s = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="Escala de carga">';
      k.wedges.forEach(function (w) {
        s += '<rect x="' + (x0 + w[0] / max * wbar) + '" y="70" width="' + ((w[1] - w[0]) / max * wbar) + '" height="26" fill="' + COL[w[2] === 0 ? 1 : w[2] + 0] + '" opacity=".85"/>' +
          '<text x="' + (x0 + (w[0] + w[1]) / 2 / max * wbar) + '" y="88" text-anchor="middle" font-size="11" fill="#fff" font-weight="700">+' + w[2] + '</text>';
      });
      var px = x0 + Math.min(v, max) / max * wbar;
      s += '<polygon points="' + px + ',66 ' + (px - 6) + ',54 ' + (px + 6) + ',54" fill="var(--acento)"/><text x="' + px + '" y="46" text-anchor="middle" font-size="12" font-weight="700" fill="var(--acento)">' + v + ' kg</text>';
      [0, 2, 10, 20, 40].forEach(function (m) { s += '<text x="' + (x0 + m / max * wbar) + '" y="116" text-anchor="middle" font-size="10" fill="#8a84a6">' + m + '</text>'; });
      s += '<rect x="82" y="138" width="64" height="30" rx="3" fill="#cfc7e8"/><text x="114" y="158" text-anchor="middle" font-size="11" fill="#4b3f7a">carga</text></svg>';
      return s;
    }
    var p = k.pv, s2 = '<svg viewBox="0 0 ' + W + ' ' + H + '" role="img" aria-label="' + k.t + '">' + k.ctx(p);
    k.wedges.forEach(function (w) {
      var a = vec(k.base, w[0]), b = vec(k.base, w[1]);
      var sweep = k.base === 'down' ? 0 : 1;
      s2 += '<path d="M' + p[0] + ' ' + p[1] + ' L' + (p[0] + a[0] * k.R) + ' ' + (p[1] + a[1] * k.R) + ' A' + k.R + ' ' + k.R + ' 0 0 ' + sweep + ' ' + (p[0] + b[0] * k.R) + ' ' + (p[1] + b[1] * k.R) + ' Z" fill="' + COL[w[2]] + '" opacity=".38"/>';
      var m = vec(k.base, (w[0] + w[1]) / 2);
      s2 += '<text x="' + (p[0] + m[0] * k.R * .72) + '" y="' + (p[1] + m[1] * k.R * .72 + 4) + '" text-anchor="middle" font-size="11" font-weight="700" fill="#3d2a85">' + w[2] + '</text>';
    });
    var d0 = vec(k.base, 0);
    s2 += '<line x1="' + p[0] + '" y1="' + p[1] + '" x2="' + (p[0] + d0[0] * (k.R + 8)) + '" y2="' + (p[1] + d0[1] * (k.R + 8)) + '" stroke="#8a84a6" stroke-width="1.2" stroke-dasharray="4 3"/>';
    var vv = Math.max(-60, Math.min(160, v)), d = vec(k.base, vv);
    var ex = p[0] + d[0] * k.len, ey = p[1] + d[1] * k.len;
    s2 += '<line x1="' + p[0] + '" y1="' + p[1] + '" x2="' + ex + '" y2="' + ey + '" stroke="var(--acento)" stroke-width="7" stroke-linecap="round"/>';
    if (k.head) s2 += '<circle cx="' + (p[0] + d[0] * (k.len + 12)) + '" cy="' + (p[1] + d[1] * (k.len + 12)) + '" r="' + (k.len > 80 ? 0 : 13) + '" fill="var(--acento)" opacity=".85"/>';
    s2 += '<circle cx="' + p[0] + '" cy="' + p[1] + '" r="5" fill="#fff" stroke="var(--acento)" stroke-width="3"/></svg>';
    return s2;
  }
  document.querySelectorAll('.fig').forEach(function (el) {
    var k = KINDS[el.dataset.kind], input = el.dataset.input ? document.querySelector('[name="' + el.dataset.input + '"]') : null;
    el.innerHTML = '<div class="fig-t">' + k.t + '</div><div class="fig-s">' + k.sub + '</div><div class="fig-svg"></div><div class="fig-n">' + k.note + '</div><div class="fig-badge"></div>';
    function upd() {
      var v = input ? parseFloat(input.value) : 0; if (isNaN(v)) v = 0;
      el.querySelector('.fig-svg').innerHTML = draw(k, v);
      var sc = k.wedges ? score(k, v) : null, b = el.querySelector('.fig-badge');
      if (input && k.wedges) { b.innerHTML = 'Con ' + v + (k.unit || '') + ' → <b style="color:' + (sc == null ? '#9a94b3' : COL[sc === 0 ? 1 : sc]) + '">' + (sc == null ? 'fuera de rango' : 'puntaje base ' + (sc === 0 ? 0 : sc)) + '</b>'; } else { b.textContent = ''; }
    }
    if (input) input.addEventListener('input', upd);
    upd();
  });
})();
