/* PMV · Utilidades globales */

function toast(msg, type = "ok", duration = 4500) {
  const cont = document.getElementById("toasts");
  if (!cont) return;
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.innerHTML = `<span class="flex-1">${msg}</span><span class="close" title="Cerrar">×</span>`;
  el.querySelector(".close").onclick = () => removeToast(el);
  cont.appendChild(el);
  setTimeout(() => removeToast(el), duration);
}

function removeToast(el) {
  if (!el || el.classList.contains("leaving")) return;
  el.classList.add("leaving");
  setTimeout(() => el.remove(), 260);
}

async function api(url, options = {}) {
  const opts = {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options
  };
  if (opts.body && typeof opts.body === "object") {
    opts.body = JSON.stringify(opts.body);
  }
  const res = await fetch(url, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok && data.msg) {
    toast(data.msg, "error");
  }
  return { ok: res.ok, status: res.status, data };
}

// Confirmación simple
function confirmar(msg) {
  return window.confirm(msg);
}

/* ===== ERGOPLUS · utilidades de interfaz ===== */
window.esc = window.esc || function (t) {
  return String(t == null ? '' : t).replace(/[&<>"']/g, function (c) {
    return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
  });
};

// Menús emergentes (notificaciones, usuario)
document.addEventListener('click', function (e) {
  var btn = e.target.closest('[data-pop]');
  document.querySelectorAll('.pop.open').forEach(function (p) {
    if (!btn || p.id !== btn.getAttribute('data-pop')) p.classList.remove('open');
  });
  if (btn) {
    var pop = document.getElementById(btn.getAttribute('data-pop'));
    if (pop) pop.classList.toggle('open');
  }
});
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') document.querySelectorAll('.pop.open').forEach(function (p) { p.classList.remove('open'); });
});

// Notificaciones
(function () {
  var list = document.getElementById('notifList');
  if (!list) return;
  fetch('/api/notificaciones').then(function (r) { return r.json(); }).then(function (d) {
    var items = (d && d.items) || [];
    list.innerHTML = items.length
      ? items.map(function (i) { return '<div class="notif">' + esc(i.t) + '<small>' + esc(i.s) + '</small></div>'; }).join('')
      : '<div class="notif">Sin avisos por ahora.</div>';
    var dot = document.getElementById('notifDot');
    if (dot && items.length) dot.classList.remove('hidden');
  }).catch(function () { list.innerHTML = '<div class="notif">No se pudieron cargar.</div>'; });
})();

// Ver/ocultar contraseña
document.addEventListener('click', function (e) {
  var b = e.target.closest('.pwd-eye');
  if (!b) return;
  var inp = document.getElementById(b.getAttribute('data-target'));
  if (inp) inp.type = inp.type === 'password' ? 'text' : 'password';
});

// Tema y acento (se guardan en este navegador)
function setTheme(t) {
  try { localStorage.setItem('ergo_theme', t); } catch (e) {}
  if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t);
  else document.documentElement.removeAttribute('data-theme');
}
function setAccent(a) {
  try { localStorage.setItem('ergo_accent', a); } catch (e) {}
  document.documentElement.setAttribute('data-accent', a);
}

/* Combobox con búsqueda por texto y selección múltiple.
   makeCombo(el, {options:[...], placeholder, onChange(selectedArray)}) -> {get(), set(arr), clear()} */
function makeCombo(el, cfg) {
  var sel = [], opts = cfg.options || [], hl = -1;
  el.classList.add('combo');
  el.innerHTML = '<input type="text" autocomplete="off" placeholder="' + esc(cfg.placeholder || 'Escribe para buscar…') + '"><div class="combo-list"></div>';
  var inp = el.querySelector('input'), list = el.querySelector('.combo-list');
  function render() {
    var q = inp.value.trim().toLowerCase();
    var f = opts.filter(function (o) { return !q || String(o).toLowerCase().indexOf(q) >= 0; });
    list.innerHTML = f.length ? f.map(function (o, i) {
      return '<div class="combo-opt' + (sel.indexOf(o) >= 0 ? ' sel' : '') + (i === hl ? ' hl' : '') + '" data-v="' + esc(o) + '">' +
        (sel.indexOf(o) >= 0 ? '✓ ' : '') + esc(o) + '</div>';
    }).join('') : '<div class="combo-empty">Sin coincidencias</div>';
  }
  function toggle(v) {
    var i = sel.indexOf(v);
    if (i >= 0) sel.splice(i, 1); else sel.push(v);
    inp.value = ''; render();
    if (cfg.onChange) cfg.onChange(sel.slice());
  }
  inp.addEventListener('focus', function () { el.classList.add('open'); hl = -1; render(); });
  inp.addEventListener('input', function () { el.classList.add('open'); hl = 0; render(); });
  inp.addEventListener('keydown', function (e) {
    var items = list.querySelectorAll('.combo-opt');
    if (e.key === 'ArrowDown') { hl = Math.min(hl + 1, items.length - 1); render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp') { hl = Math.max(hl - 1, 0); render(); e.preventDefault(); }
    else if (e.key === 'Enter' && items[Math.max(hl, 0)]) { toggle(items[Math.max(hl, 0)].getAttribute('data-v')); e.preventDefault(); }
    else if (e.key === 'Escape') { el.classList.remove('open'); inp.blur(); }
  });
  list.addEventListener('mousedown', function (e) {
    var o = e.target.closest('.combo-opt');
    if (o) { e.preventDefault(); toggle(o.getAttribute('data-v')); }
  });
  document.addEventListener('click', function (e) { if (!el.contains(e.target)) el.classList.remove('open'); });
  return {
    get: function () { return sel.slice(); },
    set: function (a) { sel = (a || []).slice(); render(); },
    clear: function () { sel = []; inp.value = ''; render(); if (cfg.onChange) cfg.onChange([]); }
  };
}

/* Contador de caracteres para campos con maxlength (textarea y los inputs de texto largos) */
function attachCounters(root) {
  (root || document).querySelectorAll('input[maxlength], textarea[maxlength]').forEach(function (el) {
    var max = parseInt(el.getAttribute('maxlength'), 10);
    if (!max || (el.tagName !== 'TEXTAREA' && max < 200) || el.dataset.counter) return;
    el.dataset.counter = '1';
    var c = document.createElement('div');
    c.className = 'muted'; c.style.cssText = 'text-align:right;font-size:11px;margin-top:2px';
    function upd() { c.textContent = el.value.length + ' / ' + max; c.style.color = el.value.length >= max ? 'var(--grave)' : ''; }
    el.addEventListener('input', upd); upd();
    el.insertAdjacentElement('afterend', c);
  });
}
document.addEventListener('DOMContentLoaded', function () { attachCounters(document); });
