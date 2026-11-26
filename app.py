import os
from io import BytesIO, StringIO
import json
from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, jsonify, abort
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta, date
from zoneinfo import ZoneInfo
from functools import wraps
import secrets
import string

from config import Config
import catalogos as cat
from rula import calcular_rula
from db import query, execute, get_db

try:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
    HAS_REPORTLAB = True
except ImportError:
    HAS_REPORTLAB = False

app = Flask(__name__)
if os.getenv("BEHIND_PROXY", "0") == "1":      # Render, AWS, Nginx: respeta https y la IP real del cliente
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config.from_object(Config)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Debes iniciar sesión para continuar."
login_manager.login_message_category = "error"

# ===================== USER MODEL + PERMISOS (RBAC) =====================
# Roles estáticos (permisos NO editables): owner, client
# Roles editables (defecto + ajuste true/false por cuenta): admin, evaluador
ROLE_LABEL = {
    "owner": "Owner", "admin": "Administrador",
    "evaluador": "Evaluador", "client": "Cliente",
}
STATIC_ROLES = ("owner", "client")
EDITABLE_ROLES = ("admin", "evaluador")

# clave, etiqueta, grupo, delegable
PERM_DEFS = [
    ("cuentas", "Crear y desactivar cuentas",       "Equipo",     False),
    ("permisos", "Editar permisos de cuentas",      "Equipo",     False),
    ("emp_ver", "Ver clientes (empresas, sedes, salones, puestos)", "Clientes", True),
    ("emp_edit", "Crear y editar clientes",         "Clientes",   True),
    ("emp_del", "Eliminar (ocultar) clientes",      "Clientes",   True),
    ("con", "Contratos con clientes",              "Operación",  True),
    ("srv", "Gestionar servicios y códigos",        "Operación",  True),
    ("cal", "Calendario de visitas",                "Operación",  True),
    ("eval", "Evaluaciones ergonómicas",             "Operación",  True),
    ("inf_ver", "Ver informes",                     "Informes",   True),
    ("inf_dl", "Descargar informes (PDF)",          "Informes",   True),
    ("logs", "Ver y exportar logs",                 "Auditoría",  True),
]
PERM_KEYS = [p[0] for p in PERM_DEFS]
NON_DELEGABLE = {p[0] for p in PERM_DEFS if not p[3]}

ROLE_PERM = {
    "owner": {k: True for k in PERM_KEYS},
    "admin": {k: (k not in ("cuentas", "permisos", "logs")) for k in PERM_KEYS},
    "evaluador": {k: (k in ("emp_ver", "cal", "eval", "inf_ver")) for k in PERM_KEYS},
    "client": {k: (k in ("inf_ver", "inf_dl")) for k in PERM_KEYS},
}

def role_defaults(role):
    return dict(ROLE_PERM.get(role, {k: False for k in PERM_KEYS}))

def effective_perms(role, overrides=None):
    """Permisos efectivos: defecto del rol + ajustes por cuenta (solo roles editables y permisos delegables)."""
    perms = role_defaults(role)
    if role in EDITABLE_ROLES and overrides:
        for k, v in overrides.items():
            if k in perms and k not in NON_DELEGABLE:
                perms[k] = bool(v)
    return perms

def load_overrides(uid):
    rows = query("SELECT permiso, valor FROM usuario_permisos WHERE usuario_id=%s", (uid,))
    return {r["permiso"]: bool(r["valor"]) for r in rows}


class User(UserMixin):
    def __init__(self, data):
        self.id = data["id"]
        self.username = data["username"]
        self.nombre_completo = data["nombre_completo"]
        self.email = data.get("email")
        self.role = data["role"]
        self.activo = data["activo"]
        self.empresa_id = data.get("empresa_id")
        self.debe_cambiar_clave = bool(data.get("debe_cambiar_clave"))
        self.perms = effective_perms(self.role, load_overrides(self.id) if self.role in EDITABLE_ROLES else None)

    @property
    def role_label(self):
        return ROLE_LABEL.get(self.role, self.role)

    @property
    def is_owner(self):
        return self.role == "owner"

    @property
    def is_admin(self):
        # Compatibilidad: roles con vista de gestión
        return self.role in ("owner", "admin")

    @property
    def is_evaluador(self):
        return self.role == "evaluador"

    @property
    def is_client(self):
        return self.role == "client"

    def can(self, key):
        return bool(self.perms.get(key))


@login_manager.user_loader
def load_user(user_id):
    row = query("SELECT * FROM usuarios WHERE id=%s AND activo=1", (user_id,), one=True)
    return User(row) if row else None


@app.context_processor
def inject_rbac():
    def can(key):
        return current_user.is_authenticated and current_user.can(key)
    return {"can": can, "ROLE_LABEL": ROLE_LABEL, "PERM_DEFS": PERM_DEFS, "METODOS": cat.METODOS}


# ===================== DECORADORES =====================
def perm_required(*keys):
    """Exige que la cuenta tenga TODOS los permisos indicados. Roles estáticos incluidos."""
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                if request.path.startswith("/api/"):
                    return jsonify({"ok": False, "msg": "Sesión expirada."}), 401
                return redirect(url_for("login"))
            if not all(current_user.can(k) for k in keys):
                log_event("denegado", "Sesión", detalle=f"Intento sin permiso ({', '.join(keys)}): {request.method} {request.path}", ok=False)
                if request.path.startswith("/api/") or request.path.endswith("/pdf"):
                    return jsonify({"ok": False, "msg": "No tienes permiso para esta acción."}), 403
                flash("No tienes permiso para acceder a esta sección.", "error")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        return wrapped
    return decorator


# ===================== ALCANCE POR EMPRESA =====================
def empresa_scope():
    """None = todas las empresas · lista = solo esas (Evaluador asignado / Cliente con su empresa)."""
    if not current_user.is_authenticated:
        return []
    if current_user.role in ("owner", "admin"):
        return None
    if current_user.role == "evaluador":
        rows = query("SELECT empresa_id FROM usuario_empresas WHERE usuario_id=%s", (current_user.id,))
        return [r["empresa_id"] for r in rows]
    return [current_user.empresa_id] if current_user.empresa_id else []

def in_scope(empresa_id):
    sc = empresa_scope()
    return sc is None or (empresa_id is not None and int(empresa_id) in sc)

def scope_clause(col):
    """Devuelve (sql, params) para añadir a un WHERE:  AND col IN (...)"""
    sc = empresa_scope()
    if sc is None:
        return "", ()
    if not sc:
        return " AND 1=0", ()
    return f" AND {col} IN ({','.join(['%s'] * len(sc))})", tuple(sc)

def empresa_de(tabla, rid):
    """Empresa a la que pertenece una sede, salón o puesto."""
    sqls = {
        "sedes": "SELECT empresa_id e FROM sedes WHERE id=%s",
        "salones": "SELECT s.empresa_id e FROM salones sa JOIN sedes s ON sa.sede_id=s.id WHERE sa.id=%s",
        "puestos": "SELECT s.empresa_id e FROM puestos p JOIN salones sa ON p.salon_id=sa.id JOIN sedes s ON sa.sede_id=s.id WHERE p.id=%s",
    }
    r = query(sqls[tabla], (rid,), one=True)
    return r["e"] if r else None

def deny_scope():
    return jsonify({"ok": False, "msg": "Esa empresa no está asignada a tu cuenta."}), 403


# ===================== AUDITORÍA (LOGS) =====================
def get_client_ip():
    return (request.headers.get("X-Forwarded-For", request.remote_addr) or "")[:45]

_SKIP_FIELDS = {"password_hash", "actualizado_en"}

def snap(tabla, rid):
    """Foto de un registro para guardar antes/después en el log."""
    if tabla not in ("empresas", "sedes", "salones", "puestos", "servicios", "visitas", "usuarios", "contratos", "areas", "operarios") or rid is None:
        return None
    row = query(f"SELECT * FROM {tabla} WHERE id=%s", (rid,), one=True)
    if not row:
        return None
    return {k: (str(v) if v is not None else None) for k, v in row.items() if k not in _SKIP_FIELDS}

def _label(d):
    if not d:
        return None
    for k in ("nombre", "titulo", "username", "codigo_acceso", "numero"):
        if d.get(k):
            return f"{d[k]} (#{d.get('id')})"
    if d.get("fecha"):
        return f"Visita {d['fecha']} (#{d.get('id')})"
    return f"#{d.get('id')}"

def _diff(antes, despues):
    cambios = []
    for k in sorted(set((antes or {}).keys()) | set((despues or {}).keys())):
        a, b = (antes or {}).get(k), (despues or {}).get(k)
        if a != b and k not in ("id", "creado_en"):
            cambios.append(f"{k}: {a or '—'} → {b or '—'}")
    return "; ".join(cambios)

def log_event(accion, modulo, antes=None, despues=None, detalle=None, registro=None, ok=True, usuario=None, rol=None):
    """Inserta un evento en `logs`. Nunca rompe la petición si falla."""
    try:
        if usuario is None:
            if current_user.is_authenticated:
                usuario, rol, uid = current_user.username, current_user.role, current_user.id
            else:
                usuario, rol, uid = "(anónimo)", "—", None
        else:
            uid = None
            u = query("SELECT id, role FROM usuarios WHERE username=%s", (usuario,), one=True)
            if u:
                uid, rol = u["id"], rol or u["role"]
            rol = rol or "—"
        registro = registro or _label(despues) or _label(antes)
        if detalle is None:
            if accion == "editar":
                detalle = _diff(antes, despues) or "Sin cambios"
            elif accion == "crear":
                detalle = f"Creó {registro or modulo}"
            elif accion == "eliminar":
                detalle = f"Eliminó {registro or modulo}"
        execute(
            """INSERT INTO logs (usuario_id, usuario, rol, accion, modulo, registro, detalle, antes, despues, ip, ok)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                uid, usuario, rol, accion, modulo,
                (registro or "")[:160] or None,
                (detalle or "")[:400] or None,
                json.dumps(antes, ensure_ascii=False) if antes else None,
                json.dumps(despues, ensure_ascii=False) if despues else None,
                get_client_ip(), 1 if ok else 0,
            ),
        )
    except Exception as e:  # el log nunca debe tumbar la operación
        print("LOG ERROR:", e)


# ===================== LOGIN SECURITY =====================
def record_failed_attempt(username):
    execute(
        "INSERT INTO login_attempts (username, ip_address) VALUES (%s, %s)",
        (username, get_client_ip())
    )

def clear_attempts(username):
    execute("DELETE FROM login_attempts WHERE username=%s", (username,))

def get_lockout_info(username):
    """Returns (is_locked, remaining_seconds, attempts_count)"""
    rows = query(
        "SELECT attempt_time FROM login_attempts WHERE username=%s ORDER BY attempt_time DESC LIMIT 20",
        (username,)
    )
    if not rows:
        return False, 0, 0

    attempts = len(rows)
    if attempts < Config.MAX_LOGIN_ATTEMPTS:
        return False, 0, attempts

    # Calculate progressive lockout
    excess = attempts - Config.MAX_LOGIN_ATTEMPTS + 1
    lockout_secs = min(
        Config.LOCKOUT_BASE_SECONDS * (Config.LOCKOUT_MULTIPLIER ** (excess - 1)),
        Config.LOCKOUT_MAX_SECONDS
    )

    last_attempt = rows[0]["attempt_time"]
    if isinstance(last_attempt, str):
        last_attempt = datetime.strptime(last_attempt, "%Y-%m-%d %H:%M:%S")

    unlock_at = last_attempt + timedelta(seconds=lockout_secs)
    now = datetime.now()
    if now < unlock_at:
        remaining = int((unlock_at - now).total_seconds())
        return True, remaining, attempts
    return False, 0, attempts

# ===================== AUTH ROUTES =====================

# ===================== CONTRASEÑA TEMPORAL =====================
def clave_temporal():
    alfabeto = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alfabeto) for _ in range(10))

@app.before_request
def exigir_cambio_clave():
    """Mientras la contraseña sea temporal, solo se permite cambiarla o salir."""
    if not current_user.is_authenticated or not getattr(current_user, "debe_cambiar_clave", False):
        return None
    ep = request.endpoint or ""
    if ep in ("cambiar_clave", "api_cambiar_clave", "logout", "static"):
        return None
    if request.path.startswith("/api/"):
        return jsonify({"ok": False, "msg": "Debes cambiar tu contraseña temporal primero.", "cambiar_clave": True}), 403
    return redirect(url_for("cambiar_clave"))

@app.route("/cambiar-clave")
@login_required
def cambiar_clave():
    return render_template("cambiar_clave.html")

@app.route("/api/cambiar-clave", methods=["POST"])
@login_required
def api_cambiar_clave():
    d = request.json or {}
    actual, nueva = d.get("actual") or "", d.get("nueva") or ""
    fila = query("SELECT password_hash FROM usuarios WHERE id=%s", (current_user.id,), one=True)
    if not fila or not check_password_hash(fila["password_hash"], actual):
        return jsonify({"ok": False, "msg": "La contraseña actual (temporal) no es correcta."}), 400
    if len(nueva) < 8 or nueva.isdigit() or nueva.isalpha():
        return jsonify({"ok": False, "msg": "La nueva contraseña debe tener 8 o más caracteres e incluir letras y números."}), 400
    if nueva == actual:
        return jsonify({"ok": False, "msg": "La nueva contraseña debe ser distinta de la temporal."}), 400
    execute("UPDATE usuarios SET password_hash=%s, debe_cambiar_clave=0 WHERE id=%s", (generate_password_hash(nueva), current_user.id))
    log_event("editar", "Cuentas", detalle="Cambió su contraseña temporal")
    return jsonify({"ok": True, "redirect": url_for("dashboard"), "msg": "Contraseña actualizada."})

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("cambiar_clave") if current_user.debe_cambiar_clave else url_for("dashboard"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        # Validaciones básicas
        if not username or not password:
            return jsonify({
                "ok": False,
                "msg": "Debes completar usuario y contraseña.",
                "type": "warning"
            })

        locked, remaining, attempts = get_lockout_info(username)
        if locked:
            log_event("login_fallido", "Sesión", usuario=username, detalle="Cuenta bloqueada temporalmente por intentos fallidos", ok=False)
            mins = remaining // 60
            secs = remaining % 60
            tiempo = f"{mins} min {secs} s" if mins else f"{secs} segundos"
            return jsonify({
                "ok": False,
                "msg": f"Demasiados intentos fallidos. Espera {tiempo} antes de volver a intentar.",
                "type": "error",
                "lockout": remaining
            })

        user_row = query(
            "SELECT * FROM usuarios WHERE username=%s AND activo=1",
            (username,), one=True
        )

        if not user_row or not check_password_hash(user_row["password_hash"], password):
            record_failed_attempt(username)
            log_event("login_fallido", "Sesión", usuario=username, detalle="Usuario o contraseña incorrectos", ok=False)
            locked2, remaining2, attempts2 = get_lockout_info(username)
            msg = "Usuario o contraseña incorrectos."
            if locked2:
                mins = remaining2 // 60
                secs = remaining2 % 60
                tiempo = f"{mins} min {secs} s" if mins else f"{secs} segundos"
                msg = f"Usuario o contraseña incorrectos. Cuenta bloqueada temporalmente. Espera {tiempo}."
            elif attempts2 >= Config.MAX_LOGIN_ATTEMPTS - 2:
                msg = f"Usuario o contraseña incorrectos. Te quedan {Config.MAX_LOGIN_ATTEMPTS - attempts2} intentos."
            return jsonify({"ok": False, "msg": msg, "type": "error"})

        # Login exitoso
        clear_attempts(username)
        user = User(user_row)
        login_user(user, remember=True)
        log_event("login", "Sesión", usuario=user.username, rol=user.role, detalle="Inicio de sesión")
        destino = url_for("cambiar_clave") if user.debe_cambiar_clave else url_for("dashboard")
        return jsonify({"ok": True, "redirect": destino, "temporal": user.debe_cambiar_clave})

    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    log_event("logout", "Sesión", detalle="Cierre de sesión")
    logout_user()
    flash("Sesión cerrada correctamente.", "ok")
    return redirect(url_for("login"))

# ===================== DASHBOARD =====================
@app.route("/")
@login_required
def dashboard():
    sc_e, p_e = scope_clause("e.id")
    stats = {}
    stats["empresas"] = query("SELECT COUNT(*) c FROM empresas e WHERE e.activo=1" + sc_e, p_e, one=True)["c"]
    stats["sedes"] = query("SELECT COUNT(*) c FROM sedes se JOIN empresas e ON se.empresa_id=e.id WHERE se.activo=1" + sc_e, p_e, one=True)["c"]
    stats["puestos"] = query("""
        SELECT COUNT(*) c FROM puestos p JOIN salones s ON p.salon_id=s.id
        JOIN sedes se ON s.sede_id=se.id JOIN empresas e ON se.empresa_id=e.id
        WHERE p.activo=1""" + sc_e, p_e, one=True)["c"]
    stats["operarios"] = query("SELECT COUNT(*) c FROM operarios o JOIN empresas e ON o.empresa_id=e.id WHERE o.activo=1" + sc_e, p_e, one=True)["c"]
    stats["servicios_activos"] = query(
        "SELECT COUNT(*) c FROM servicios sv JOIN empresas e ON sv.empresa_id=e.id "
        "WHERE sv.estado='activo' AND sv.fecha_fin >= CURDATE()" + sc_e, p_e, one=True
    )["c"]
    # RULA: Rojo = grave, Amarillo = medio
    niveles = query("SELECT er.nivel, COUNT(*) c FROM evaluacion_rula er JOIN empresas e ON er.empresa_id=e.id WHERE 1=1" + sc_e + " GROUP BY er.nivel", p_e)
    cnt = {r["nivel"]: r["c"] for r in niveles}
    stats["graves"] = cnt.get("Rojo", 0)
    stats["medios"] = cnt.get("Amarillo", 0)
    stats["bajos"] = cnt.get("Verde", 0)

    ultimas = query("""
        SELECT er.fecha_evaluacion fecha, er.nivel resultado, er.puntaje_final,
               COALESCE(p.nombre, '—') puesto, e.nombre empresa
        FROM evaluacion_rula er
        JOIN empresas e ON er.empresa_id = e.id
        LEFT JOIN puestos p ON er.puesto_id = p.id
        WHERE 1=1""" + sc_e + """
        ORDER BY er.id DESC LIMIT 6
    """, p_e)
    for u in ultimas:
        u["fecha"] = str(u["fecha"])[:10] if u["fecha"] else ""

    ultimos_logs = []
    if current_user.can("logs"):
        ultimos_logs = [_log_json(r) for r in query("SELECT * FROM logs ORDER BY id DESC LIMIT 5")]

    tot = max(1, stats["graves"] + stats["medios"] + stats["bajos"])
    sem = {"r": round(100 * stats["graves"] / tot), "y": round(100 * stats["medios"] / tot)}
    sem["g"] = 100 - sem["r"] - sem["y"] if (stats["graves"] + stats["medios"] + stats["bajos"]) else 0
    proximas = []
    sin_contrato = []
    try:
        proximas = query("""
            SELECT v.fecha, v.hora_entrada, v.categoria, v.responsable, e.nombre empresa
            FROM visitas v JOIN empresas e ON v.empresa_id=e.id
            WHERE v.fecha >= CURDATE()""" + sc_e + " ORDER BY v.fecha, v.hora_entrada LIMIT 5", p_e)
        for v in proximas:
            v["fecha"] = str(v["fecha"])[:10]
            v["hora_entrada"] = str(v["hora_entrada"] or "")[:5]
        if current_user.can("con"):
            sin_contrato = query("""
                SELECT e.nombre FROM empresas e WHERE e.activo=1 AND NOT EXISTS
                (SELECT 1 FROM contratos c WHERE c.empresa_id=e.id AND c.estado='Vigente')""" + sc_e + " LIMIT 5", p_e)
    except Exception:
        pass
    return render_template("dashboard.html", stats=stats, ultimas=ultimas, ultimos_logs=ultimos_logs,
                           sem=sem, proximas=proximas, sin_contrato=sin_contrato)

# ===================== CLIENTES (jerárquico) =====================
@app.route("/clientes")
@login_required
@perm_required("emp_ver")
def clientes():
    sc_sql, sc_p = scope_clause("e.id")
    rows = query("""
        SELECT e.id, e.nombre, e.tipo_persona, e.tipo_documento, e.nit, e.direccion, e.departamento, e.ciudad,
               e.tamano, e.num_trabajadores, e.arl, e.telefono, e.email, e.contacto, e.cargo_contacto, e.sector,
               (SELECT COUNT(*) FROM sedes s WHERE s.empresa_id=e.id AND s.activo=1) AS num_sedes
        FROM empresas e
        WHERE e.activo=1""" + sc_sql + """
        ORDER BY e.nombre
    """, sc_p)
    # Convertir a dicts simples (sin datetime) para tojson
    empresas = []
    for r in rows:
        d = {k: ("" if v is None else v) for k, v in r.items()}
        d["num_sedes"] = int(r["num_sedes"] or 0)
        empresas.append(d)
    return render_template("clientes.html", empresas=empresas, CAT=cat.catalogos_js())

@app.route("/api/empresa/<int:eid>/puestos")
@login_required
def api_puestos_empresa(eid):
    if not in_scope(eid):
        return deny_scope()
    rows = query("""SELECT p.id, p.numero_puesto, p.nombre, p.condiciones, sa.nombre salon, s.nombre sede
                    FROM puestos p JOIN salones sa ON p.salon_id=sa.id JOIN sedes s ON sa.sede_id=s.id
                    WHERE s.empresa_id=%s AND p.activo=1 ORDER BY s.nombre, sa.nombre, p.numero_puesto, p.nombre""", (eid,))
    out = []
    for r in rows:
        try:
            c = _json.loads(r["condiciones"]) if r["condiciones"] else {}
        except ValueError:
            c = {}
        out.append({"id": r["id"], "etiqueta": f"{(r['numero_puesto'] + ' · ') if r['numero_puesto'] else ''}{r['nombre']} — {r['sede']} / {r['salon']}",
                    "sede_id": None, "condiciones": c})
    return jsonify(out)

@app.route("/api/empresa/<int:eid>/sedes")
@login_required
@perm_required("emp_ver")
def api_sedes(eid):
    if not in_scope(eid):
        return deny_scope()
    rows = query(
        "SELECT s.*, (SELECT COUNT(*) FROM salones sa WHERE sa.sede_id=s.id AND sa.activo=1) num_salones "
        "FROM sedes s WHERE s.empresa_id=%s AND s.activo=1 ORDER BY s.nombre",
        (eid,)
    )
    return jsonify(rows)

@app.route("/api/sede/<int:sid>/salones")
@login_required
@perm_required("emp_ver")
def api_salones(sid):
    if not in_scope(empresa_de("sedes", sid)):
        return deny_scope()
    rows = query(
        "SELECT sa.*, (SELECT COUNT(*) FROM puestos p WHERE p.salon_id=sa.id AND p.activo=1) num_puestos "
        "FROM salones sa WHERE sa.sede_id=%s AND sa.activo=1 ORDER BY sa.nombre",
        (sid,)
    )
    return jsonify(rows)

@app.route("/api/salon/<int:said>/puestos")
@login_required
@perm_required("emp_ver")
def api_puestos(said):
    if not in_scope(empresa_de("salones", said)):
        return deny_scope()
    rows = query(
        "SELECT * FROM puestos WHERE salon_id=%s AND activo=1 ORDER BY numero_puesto, nombre",
        (said,)
    )
    return jsonify(rows)

# ---- CRUD Empresa ----
@app.route("/api/empresa", methods=["POST"])
@login_required
@perm_required("emp_edit")
def api_crear_empresa():
    d, err = cat.validar_empresa(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cols = list(d.keys())
    eid = execute(
        f"INSERT INTO empresas ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})",
        tuple(d[c] for c in cols),
    )
    log_event("crear", "Empresas", despues=snap("empresas", eid))
    return jsonify({"ok": True, "id": eid, "msg": "Empresa creada."})

@app.route("/api/empresa/<int:eid>", methods=["PUT"])
@login_required
@perm_required("emp_edit")
def api_editar_empresa(eid):
    if not in_scope(eid):
        return deny_scope()
    antes = snap("empresas", eid)
    d, err = cat.validar_empresa(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cols = list(d.keys())
    execute(
        f"UPDATE empresas SET {', '.join(c + '=%s' for c in cols)} WHERE id=%s",
        tuple(d[c] for c in cols) + (eid,),
    )
    log_event("editar", "Empresas", antes=antes, despues=snap("empresas", eid))
    return jsonify({"ok": True, "msg": "Empresa actualizada."})

@app.route("/api/empresa/<int:eid>", methods=["DELETE"])
@login_required
@perm_required("emp_del")
def api_borrar_empresa(eid):
    if not in_scope(eid):
        return deny_scope()
    antes = snap("empresas", eid)
    # Soft delete
    execute("UPDATE empresas SET activo=0 WHERE id=%s", (eid,))
    log_event("eliminar", "Empresas", antes=antes)
    return jsonify({"ok": True, "msg": "Empresa ocultada."})

# ---- CRUD Sede ----
@app.route("/api/sede", methods=["POST"])
@login_required
@perm_required("emp_edit")
def api_crear_sede():
    data = request.json or {}
    err = cat.revisar_largos(data, ['nombre', 'direccion', 'ciudad', 'telefono'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    if not data.get("nombre") or not data.get("empresa_id"):
        return jsonify({"ok": False, "msg": "Nombre y empresa son obligatorios."}), 400
    if not in_scope(data["empresa_id"]):
        return deny_scope()
    sid = execute(
        "INSERT INTO sedes (empresa_id, nombre, direccion, ciudad, telefono) VALUES (%s,%s,%s,%s,%s)",
        (data["empresa_id"], data["nombre"], data.get("direccion"), data.get("ciudad"), data.get("telefono"))
    )
    log_event("crear", "Sedes", despues=snap("sedes", sid))
    return jsonify({"ok": True, "id": sid, "msg": "Sede creada."})

@app.route("/api/sede/<int:sid>", methods=["PUT"])
@login_required
@perm_required("emp_edit")
def api_editar_sede(sid):
    if not in_scope(empresa_de("sedes", sid)):
        return deny_scope()
    antes = snap("sedes", sid)
    data = request.json or {}
    err = cat.revisar_largos(data, ['nombre', 'direccion', 'ciudad', 'telefono'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    execute(
        "UPDATE sedes SET nombre=%s, direccion=%s, ciudad=%s, telefono=%s WHERE id=%s",
        (data.get("nombre"), data.get("direccion"), data.get("ciudad"), data.get("telefono"), sid)
    )
    log_event("editar", "Sedes", antes=antes, despues=snap("sedes", sid))
    return jsonify({"ok": True, "msg": "Sede actualizada."})

@app.route("/api/sede/<int:sid>", methods=["DELETE"])
@login_required
@perm_required("emp_del")
def api_borrar_sede(sid):
    if not in_scope(empresa_de("sedes", sid)):
        return deny_scope()
    antes = snap("sedes", sid)
    execute("UPDATE sedes SET activo=0 WHERE id=%s", (sid,))
    log_event("eliminar", "Sedes", antes=antes)
    return jsonify({"ok": True, "msg": "Sede eliminada."})

# ---- CRUD Salon ----
@app.route("/api/salon", methods=["POST"])
@login_required
@perm_required("emp_edit")
def api_crear_salon():
    data = request.json or {}
    err = cat.revisar_largos(data, ['nombre', 'descripcion'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    if not data.get("nombre") or not data.get("sede_id"):
        return jsonify({"ok": False, "msg": "Nombre y sede son obligatorios."}), 400
    if not in_scope(empresa_de("sedes", data["sede_id"])):
        return deny_scope()
    said = execute(
        "INSERT INTO salones (sede_id, nombre, descripcion) VALUES (%s,%s,%s)",
        (data["sede_id"], data["nombre"], data.get("descripcion"))
    )
    log_event("crear", "Salones", despues=snap("salones", said))
    return jsonify({"ok": True, "id": said, "msg": "Salón creado."})

@app.route("/api/salon/<int:said>", methods=["PUT"])
@login_required
@perm_required("emp_edit")
def api_editar_salon(said):
    if not in_scope(empresa_de("salones", said)):
        return deny_scope()
    antes = snap("salones", said)
    data = request.json or {}
    err = cat.revisar_largos(data, ['nombre', 'descripcion'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    execute(
        "UPDATE salones SET nombre=%s, descripcion=%s WHERE id=%s",
        (data.get("nombre"), data.get("descripcion"), said)
    )
    log_event("editar", "Salones", antes=antes, despues=snap("salones", said))
    return jsonify({"ok": True, "msg": "Salón actualizado."})

@app.route("/api/salon/<int:said>", methods=["DELETE"])
@login_required
@perm_required("emp_del")
def api_borrar_salon(said):
    if not in_scope(empresa_de("salones", said)):
        return deny_scope()
    antes = snap("salones", said)
    execute("UPDATE salones SET activo=0 WHERE id=%s", (said,))
    log_event("eliminar", "Salones", antes=antes)
    return jsonify({"ok": True, "msg": "Salón eliminado."})

# ---- CRUD Puesto ----
@app.route("/api/puesto", methods=["POST"])
@login_required
@perm_required("emp_edit")
def api_crear_puesto():
    data = request.json or {}
    err = cat.revisar_largos(data, ['nombre', 'numero_puesto', 'area', 'ubicacion', 'descripcion'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    if not data.get("nombre") or not data.get("salon_id"):
        return jsonify({"ok": False, "msg": "Nombre y salón son obligatorios."}), 400
    if not in_scope(empresa_de("salones", data["salon_id"])):
        return deny_scope()
    pid = execute(
        """INSERT INTO puestos (salon_id, numero_puesto, nombre, area, ubicacion, descripcion)
           VALUES (%s,%s,%s,%s,%s,%s)""",
        (
            data["salon_id"], data.get("numero_puesto"), data["nombre"],
            data.get("area"), data.get("ubicacion"), data.get("descripcion")
        )
    )
    log_event("crear", "Puestos", despues=snap("puestos", pid))
    return jsonify({"ok": True, "id": pid, "msg": "Puesto creado."})

@app.route("/api/puesto/<int:pid>", methods=["PUT"])
@login_required
@perm_required("emp_edit")
def api_editar_puesto(pid):
    if not in_scope(empresa_de("puestos", pid)):
        return deny_scope()
    antes = snap("puestos", pid)
    data = request.json or {}
    err = cat.revisar_largos(data, ['nombre', 'numero_puesto', 'area', 'ubicacion', 'descripcion'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    execute(
        """UPDATE puestos SET numero_puesto=%s, nombre=%s, area=%s, ubicacion=%s, descripcion=%s
           WHERE id=%s""",
        (
            data.get("numero_puesto"), data.get("nombre"), data.get("area"),
            data.get("ubicacion"), data.get("descripcion"), pid
        )
    )
    log_event("editar", "Puestos", antes=antes, despues=snap("puestos", pid))
    return jsonify({"ok": True, "msg": "Puesto actualizado."})

@app.route("/api/puesto/<int:pid>", methods=["DELETE"])
@login_required
@perm_required("emp_del")
def api_borrar_puesto(pid):
    if not in_scope(empresa_de("puestos", pid)):
        return deny_scope()
    antes = snap("puestos", pid)
    execute("UPDATE puestos SET activo=0 WHERE id=%s", (pid,))
    log_event("eliminar", "Puestos", antes=antes)
    return jsonify({"ok": True, "msg": "Puesto eliminado."})

# ===================== SERVICIOS =====================
@app.route("/servicios")
@login_required
def servicios():
    if current_user.is_client:
        return render_template("servicios_cliente.html")
    if not current_user.can("srv"):
        flash("No tienes permiso para acceder a esta sección.", "error")
        return redirect(url_for("dashboard"))
    sc_sql, sc_p = scope_clause("s.empresa_id")
    lista = query("""
        SELECT s.*, e.nombre empresa
        FROM servicios s
        JOIN empresas e ON s.empresa_id = e.id
        WHERE 1=1""" + sc_sql + """
        ORDER BY s.fecha_fin DESC
    """, sc_p)
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    sc3, p3 = scope_clause("empresa_id")
    contr = query("SELECT id, numero, empresa_id, objeto FROM contratos WHERE estado IN ('Vigente','Borrador')" + sc3 + " ORDER BY id DESC", p3)
    return render_template("servicios.html", servicios=lista, empresas=empresas, contratos=contr)

@app.route("/api/servicio", methods=["POST"])
@login_required
@perm_required("srv")
def api_crear_servicio():
    data = request.json or {}
    err = cat.revisar_largos(data, ['titulo', 'observaciones'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    empresa_id = data.get("empresa_id")
    fecha_inicio = data.get("fecha_inicio")
    fecha_fin = data.get("fecha_fin")
    if not all([empresa_id, fecha_inicio, fecha_fin]):
        return jsonify({"ok": False, "msg": "Faltan datos obligatorios."}), 400
    if not in_scope(empresa_id):
        return deny_scope()
    contrato_id = data.get("contrato_id") or None
    if contrato_id:
        c = query("SELECT empresa_id FROM contratos WHERE id=%s", (contrato_id,), one=True)
        if not c or int(c["empresa_id"]) != int(empresa_id):
            return jsonify({"ok": False, "msg": "El contrato no pertenece a esa empresa."}), 400

    # Generar código único
    codigo = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))
    while query("SELECT id FROM servicios WHERE codigo_acceso=%s", (codigo,), one=True):
        codigo = "".join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

    sid = execute(
        """INSERT INTO servicios (empresa_id, contrato_id, codigo_acceso, titulo, fecha_inicio, fecha_fin, observaciones, creado_por)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            empresa_id, contrato_id, codigo,
            data.get("titulo") or "Servicio de evaluación ergonómica",
            fecha_inicio, fecha_fin,
            data.get("observaciones"),
            current_user.id
        )
    )
    log_event("crear", "Servicios", despues=snap("servicios", sid))
    return jsonify({"ok": True, "id": sid, "codigo": codigo, "msg": "Servicio creado."})

@app.route("/api/servicio/consultar", methods=["POST"])
@login_required
def api_consultar_codigo():
    """Clientes consultan con código + confirmación de identidad"""
    data = request.json or {}
    codigo = (data.get("codigo") or "").strip().upper()
    contacto = (data.get("contacto") or "").strip()

    if not codigo:
        return jsonify({"ok": False, "msg": "Ingresa el código de acceso."}), 400

    servicio = query("""
        SELECT s.*, e.nombre empresa, e.nit, e.ciudad, e.contacto AS contacto_empresa
        FROM servicios s
        JOIN empresas e ON s.empresa_id = e.id
        WHERE s.codigo_acceso = %s
    """, (codigo,), one=True)

    if not servicio:
        log_event("consultar", "Servicios", detalle=f"Código no válido: {codigo}", ok=False)
        return jsonify({"ok": False, "msg": "Código no válido."}), 404

    if servicio["estado"] != "activo":
        return jsonify({"ok": False, "msg": "Este servicio no está activo."}), 403

    if servicio["fecha_fin"] < datetime.now().date():
        return jsonify({"ok": False, "msg": "El servicio ha vencido."}), 403

    # Confirmación de identidad simple (contacto de la empresa)
    if contacto and servicio["contacto_empresa"]:
        if contacto.lower() not in servicio["contacto_empresa"].lower():
            log_event("consultar", "Servicios", registro=codigo, detalle="La identidad no coincide con el contacto del contrato", ok=False)
            return jsonify({
                "ok": False,
                "msg": "La identidad no coincide con la persona de contacto del contrato."
            }), 403

    # Datos completos de la empresa
    empresa_id = servicio["empresa_id"]
    sedes = query("SELECT * FROM sedes WHERE empresa_id=%s AND activo=1", (empresa_id,))
    for sede in sedes:
        sede["salones"] = query("SELECT * FROM salones WHERE sede_id=%s AND activo=1", (sede["id"],))
        for salon in sede["salones"]:
            salon["puestos"] = query("SELECT * FROM puestos WHERE salon_id=%s AND activo=1", (salon["id"],))
            for p in salon["puestos"]:
                # Mejor evaluación (más alta puntuación / más grave)
                ev = query("""
                    SELECT * FROM evaluaciones_ergo
                    WHERE puesto_id=%s
                    ORDER BY FIELD(resultado,'Grave','Medio','Bajo'), puntuacion DESC
                    LIMIT 1
                """, (p["id"],), one=True)
                p["evaluacion"] = ev

    log_event("consultar", "Servicios", registro=f"{servicio['empresa']} ({codigo})", detalle=f"Consultó el servicio con código {codigo}")
    return jsonify({
        "ok": True,
        "servicio": servicio,
        "sedes": sedes
    })

# ===================== CONTRATOS =====================
CONTRATO_CAMPOS = ["empresa_id", "tipo", "objeto", "alcance", "fecha_firma", "fecha_inicio", "fecha_fin",
                   "valor", "moneda", "forma_pago", "estado", "responsable", "resumen", "notas"]

def _validar_contrato(d):
    err = cat.revisar_largos(d, ["objeto", "alcance", "responsable", "resumen", "notas"])
    if err:
        return None, err
    if not d.get("empresa_id"):
        return None, "Selecciona la empresa."
    if not in_scope(d["empresa_id"]):
        return None, "Esa empresa no está asignada a tu cuenta."
    if not (d.get("objeto") or "").strip():
        return None, "El objeto del contrato es obligatorio."
    for k, l, n in (("tipo", cat.TIPOS_CONTRATO, "el tipo"), ("moneda", cat.MONEDAS, "la moneda"),
                    ("forma_pago", cat.FORMAS_PAGO, "la forma de pago"), ("estado", cat.ESTADOS_CONTRATO, "el estado")):
        e = cat.en_lista(d.get(k), l, n)
        if e:
            return None, e
    if not d.get("fecha_inicio") or not d.get("fecha_fin"):
        return None, "Indica fecha de inicio y de fin."
    if d["fecha_fin"] < d["fecha_inicio"]:
        return None, "La fecha de fin no puede ser anterior al inicio."
    valor = d.get("valor")
    if valor in (None, ""):
        valor = None
    else:
        try:
            valor = round(float(valor), 2)
        except (TypeError, ValueError):
            return None, "El valor debe ser un número."
        if not 0 <= valor <= 99999999999.99:
            return None, "El valor está fuera de rango."
    limpio = {
        "empresa_id": int(d["empresa_id"]), "tipo": d.get("tipo") or "Evaluación ergonómica",
        "objeto": d["objeto"].strip(), "alcance": (d.get("alcance") or "").strip() or None,
        "fecha_firma": d.get("fecha_firma") or None, "fecha_inicio": d["fecha_inicio"], "fecha_fin": d["fecha_fin"],
        "valor": valor, "moneda": d.get("moneda") or "COP", "forma_pago": d.get("forma_pago") or None,
        "estado": d.get("estado") or "Vigente", "responsable": (d.get("responsable") or "").strip() or None,
        "resumen": (d.get("resumen") or "").strip() or None,
        "notas": (d.get("notas") or "").strip() or None,
    }
    return limpio, None

@app.route("/contratos")
@login_required
@perm_required("con")
def contratos():
    sc, p = scope_clause("c.empresa_id")
    rows = query("""SELECT c.*, e.nombre empresa FROM contratos c JOIN empresas e ON c.empresa_id=e.id
                    WHERE 1=1""" + sc + " ORDER BY c.fecha_fin DESC, c.id DESC", p)
    lista = []
    for r in rows:
        d = {k: ("" if v is None else str(v)) for k, v in r.items()}
        d["id"] = r["id"]; d["empresa_id"] = r["empresa_id"]
        lista.append(d)
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    # Empresas sin contrato vigente: sin contrato, terminado/cancelado o vencido
    hoy = ahora_local().date()
    por_emp = {}
    for r in rows:
        por_emp.setdefault(r["empresa_id"], []).append(r)
    sin = []
    for e in empresas:
        cs = por_emp.get(e["id"], [])
        vig = [c for c in cs if c["estado"] == "Vigente" and c["fecha_fin"] >= hoy]
        if vig:
            continue
        if not cs:
            estado, detalle = "Sin contrato", "Nunca ha tenido un contrato registrado."
        else:
            ult = max(cs, key=lambda c: c["fecha_fin"])
            if ult["estado"] == "Vigente":
                estado, detalle = "Vencido", f"Venció el {ult['fecha_fin']} ({ult['numero']})."
            else:
                estado, detalle = "Terminado", f"{ult['numero']} — {ult['estado']}, fin {ult['fecha_fin']}."
        sin.append({"id": e["id"], "nombre": e["nombre"], "estado": estado, "detalle": detalle})
    return render_template("contratos.html", contratos=lista, empresas=empresas, sin_contrato=sin, hoy=str(hoy),
                           TIPOS=cat.TIPOS_CONTRATO, PAGOS=cat.FORMAS_PAGO, ESTADOS=cat.ESTADOS_CONTRATO,
                           MONEDAS=cat.MONEDAS, LIM=cat.LIMITES)

@app.route("/api/contrato", methods=["POST"])
@login_required
@perm_required("con")
def api_crear_contrato():
    d, err = _validar_contrato(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    anio = datetime.now().year
    n = query("SELECT COUNT(*) c FROM contratos WHERE numero LIKE %s", (f"CT-{anio}-%",), one=True)["c"] + 1
    numero = f"CT-{anio}-{n:04d}"
    while query("SELECT id FROM contratos WHERE numero=%s", (numero,), one=True):
        n += 1
        numero = f"CT-{anio}-{n:04d}"
    cols = ["numero"] + list(d.keys()) + ["creado_por"]
    vals = (numero,) + tuple(d.values()) + (current_user.id,)
    cid = execute(f"INSERT INTO contratos ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", vals)
    log_event("crear", "Contratos", despues=snap("contratos", cid))
    return jsonify({"ok": True, "id": cid, "numero": numero, "msg": f"Contrato {numero} creado."})

@app.route("/api/contrato/<int:cid>", methods=["PUT"])
@login_required
@perm_required("con")
def api_editar_contrato(cid):
    antes = snap("contratos", cid)
    if not antes:
        return jsonify({"ok": False, "msg": "Contrato no encontrado."}), 404
    if not in_scope(int(antes["empresa_id"])):
        return deny_scope()
    d, err = _validar_contrato(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cols = list(d.keys())
    execute(f"UPDATE contratos SET {', '.join(c + '=%s' for c in cols)} WHERE id=%s", tuple(d.values()) + (cid,))
    log_event("editar", "Contratos", antes=antes, despues=snap("contratos", cid))
    return jsonify({"ok": True, "msg": "Contrato actualizado."})

@app.route("/api/contrato/<int:cid>", methods=["DELETE"])
@login_required
@perm_required("con", "emp_del")
def api_borrar_contrato(cid):
    antes = snap("contratos", cid)
    if not antes:
        return jsonify({"ok": False, "msg": "Contrato no encontrado."}), 404
    if not in_scope(int(antes["empresa_id"])):
        return deny_scope()
    execute("UPDATE servicios SET contrato_id=NULL WHERE contrato_id=%s", (cid,))
    execute("DELETE FROM contratos WHERE id=%s", (cid,))
    log_event("eliminar", "Contratos", antes=antes)
    return jsonify({"ok": True, "msg": "Contrato eliminado."})


# ===================== ÁREAS (administrativas / operativas / apoyo) =====================
def _validar_area(d):
    err = cat.revisar_largos(d, ["nombre", "responsable", "cargo_responsable", "descripcion"])
    if err:
        return None, err
    if not d.get("empresa_id"):
        return None, "Selecciona la empresa."
    if not in_scope(d["empresa_id"]):
        return None, "Esa empresa no está asignada a tu cuenta."
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        return None, "El nombre del área es obligatorio."
    tipo = d.get("tipo") or "Administrativa"
    if tipo not in cat.TIPOS_AREA:
        return None, "Tipo de área no válido."
    n = d.get("num_personas")
    if n in (None, ""):
        n = None
    else:
        try:
            n = int(n)
        except (TypeError, ValueError):
            return None, "El número de personas debe ser un entero."
        if not 0 <= n <= 100000:
            return None, "El número de personas está fuera de rango."
    return {
        "empresa_id": int(d["empresa_id"]), "nombre": nombre, "tipo": tipo,
        "responsable": (d.get("responsable") or "").strip() or None,
        "cargo_responsable": (d.get("cargo_responsable") or "").strip() or None,
        "num_personas": n, "descripcion": (d.get("descripcion") or "").strip() or None,
    }, None

@app.route("/areas")
@login_required
@perm_required("emp_ver")
def areas_page():
    sc, p = scope_clause("a.empresa_id")
    rows = query("""SELECT a.*, e.nombre empresa FROM areas a JOIN empresas e ON a.empresa_id=e.id
                    WHERE a.activo=1""" + sc + " ORDER BY e.nombre, FIELD(a.tipo,'Administrativa','Operativa','Apoyo'), a.nombre", p)
    lista = [{k: ("" if v is None else v) for k, v in r.items() if k != "activo"} for r in rows]
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    return render_template("areas.html", areas=lista, empresas=empresas, CAT=cat.catalogos_js())

@app.route("/api/area", methods=["POST"])
@login_required
@perm_required("emp_edit")
def api_crear_area():
    d, err = _validar_area(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cols = list(d.keys())
    aid = execute(f"INSERT INTO areas ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", tuple(d.values()))
    log_event("crear", "Áreas", despues=snap("areas", aid))
    return jsonify({"ok": True, "id": aid, "msg": "Área creada."})

@app.route("/api/area/<int:aid>", methods=["PUT"])
@login_required
@perm_required("emp_edit")
def api_editar_area(aid):
    antes = snap("areas", aid)
    if not antes:
        return jsonify({"ok": False, "msg": "Área no encontrada."}), 404
    if not in_scope(int(antes["empresa_id"])):
        return deny_scope()
    d, err = _validar_area(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cols = list(d.keys())
    execute(f"UPDATE areas SET {', '.join(c + '=%s' for c in cols)} WHERE id=%s", tuple(d.values()) + (aid,))
    log_event("editar", "Áreas", antes=antes, despues=snap("areas", aid))
    return jsonify({"ok": True, "msg": "Área actualizada."})

@app.route("/api/area/<int:aid>", methods=["DELETE"])
@login_required
@perm_required("emp_del")
def api_borrar_area(aid):
    antes = snap("areas", aid)
    if not antes:
        return jsonify({"ok": False, "msg": "Área no encontrada."}), 404
    if not in_scope(int(antes["empresa_id"])):
        return deny_scope()
    execute("UPDATE areas SET activo=0 WHERE id=%s", (aid,))
    log_event("eliminar", "Áreas", antes=antes)
    return jsonify({"ok": True, "msg": "Área eliminada."})

# ===================== BUSCAR =====================
@app.route("/buscar")
@login_required
@perm_required("emp_ver")
def buscar():
    sc_sql, sc_p = scope_clause("id")
    empresas = query("SELECT id, nombre, ciudad, sector, nit FROM empresas WHERE activo=1" + sc_sql + " ORDER BY nombre", sc_p)
    lista = [{"id": e["id"], "nombre": e["nombre"] or "", "ciudad": e["ciudad"] or "", "sector": e["sector"] or "", "nit": e["nit"] or ""} for e in empresas]
    return render_template("buscar.html", empresas=lista)

@app.route("/api/buscar")
@login_required
@perm_required("emp_ver")
def api_buscar():
    q = (request.args.get("q") or "").strip()
    tipo = request.args.get("tipo") or "todo"
    if not q:
        return jsonify([])

    like = f"%{q}%"
    resultados = []
    sc_e, p_e = scope_clause("id")
    sc_o, p_o = scope_clause("e.id")
    sc_op, p_op = scope_clause("o.empresa_id")

    if tipo in ("todo", "empresas"):
        rows = query(
            "SELECT id, nombre, ciudad, sector, nit, 'empresa' AS tipo FROM empresas "
            "WHERE activo=1 AND (nombre LIKE %s OR nit LIKE %s OR ciudad LIKE %s OR sector LIKE %s OR contacto LIKE %s)" + sc_e,
            (like, like, like, like, like) + p_e
        )
        resultados.extend(rows)

    if tipo in ("todo", "puestos"):
        rows = query("""
            SELECT p.id, p.nombre, p.numero_puesto, e.nombre empresa, 'puesto' AS tipo
            FROM puestos p
            JOIN salones s ON p.salon_id = s.id
            JOIN sedes se ON s.sede_id = se.id
            JOIN empresas e ON se.empresa_id = e.id
            WHERE p.activo=1 AND (p.nombre LIKE %s OR p.numero_puesto LIKE %s OR e.nombre LIKE %s)""" + sc_o + """
        """, (like, like, like) + p_o)
        resultados.extend(rows)

    if tipo in ("todo", "operarios"):
        rows = query("""
            SELECT o.id, o.nombre, o.cargo, e.nombre empresa, 'operario' AS tipo
            FROM operarios o
            JOIN empresas e ON o.empresa_id = e.id
            WHERE o.activo=1 AND (o.nombre LIKE %s OR o.documento LIKE %s OR o.cargo LIKE %s)""" + sc_op + """
        """, (like, like, like) + p_op)
        resultados.extend(rows)

    return jsonify(resultados)

# ===================== AJUSTES (usuarios) =====================
@app.route("/ajustes")
@login_required
def ajustes():
    perfil = query("SELECT id, username, nombre_completo, email, role FROM usuarios WHERE id=%s", (current_user.id,), one=True)
    return render_template("ajustes.html", perfil=perfil)

# ===================== INIT =====================

# ===================== CALENDARIO =====================
@app.route("/calendario")
@login_required
@perm_required("cal")
def calendario():
    sc_sql, sc_p = scope_clause("v.empresa_id")
    visitas = query("""
        SELECT v.id, v.fecha, v.hora_entrada, v.hora_salida, v.categoria, v.salon,
               v.cantidad_puestos, v.responsable, v.observaciones,
               e.nombre AS empresa, e.id AS empresa_id
        FROM visitas v
        JOIN empresas e ON v.empresa_id = e.id
        WHERE 1=1""" + sc_sql + """
        ORDER BY v.fecha, v.hora_entrada
    """, sc_p)
    lista = []
    for v in visitas:
        lista.append({
            "id": v["id"],
            "fecha": str(v["fecha"]) if v["fecha"] else "",
            "hora_entrada": str(v["hora_entrada"])[:5] if v["hora_entrada"] else "",
            "hora_salida": str(v["hora_salida"])[:5] if v["hora_salida"] else "",
            "categoria": v["categoria"] or "",
            "salon": v["salon"] or "",
            "cantidad_puestos": v["cantidad_puestos"] or 0,
            "responsable": v["responsable"] or "",
            "observaciones": v["observaciones"] or "",
            "empresa": v["empresa"] or "",
            "empresa_id": v["empresa_id"],
        })
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    emps = [{"id": e["id"], "nombre": e["nombre"]} for e in empresas]
    return render_template("calendario.html", hoy_min=str(ahora_local().date()), anticipacion=f"{Config.MIN_ANTICIPACION_HORAS:g}", visitas=lista, empresas=emps)

def ahora_local():
    return datetime.now(ZoneInfo(Config.TIMEZONE)).replace(tzinfo=None)

def _validar_anticipacion(fecha, hora):
    try:
        inicio = datetime.strptime(f"{fecha} {hora[:5]}", "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        return "Fecha u hora no válidas."
    minimo = ahora_local() + timedelta(hours=Config.MIN_ANTICIPACION_HORAS)
    if inicio < minimo:
        h = Config.MIN_ANTICIPACION_HORAS
        return f"Las visitas deben reservarse con al menos {h:g} hora(s) de anticipación (hora de Bogotá). Primer horario disponible: {minimo.strftime('%d/%m/%Y %H:%M')}."
    return None

@app.route("/api/visita", methods=["POST"])
@login_required
@perm_required("cal")
def api_crear_visita():
    """Owner y Administrador pueden agendar visitas."""
    data = request.json or {}
    err = cat.revisar_largos(data, ['responsable', 'observaciones'])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    empresa_id = data.get("empresa_id")
    fecha = data.get("fecha")
    responsable = (data.get("responsable") or "").strip()
    if not empresa_id or not fecha:
        return jsonify({"ok": False, "msg": "Empresa y fecha son obligatorias."}), 400
    if not in_scope(empresa_id):
        return deny_scope()
    if not responsable:
        responsable = current_user.nombre_completo
    hora_e = data.get("hora_entrada") or None
    hora_s = data.get("hora_salida") or None
    if not hora_e:
        return jsonify({"ok": False, "msg": "Indica la hora de entrada."}), 400
    err_t = _validar_anticipacion(fecha, hora_e)
    if err_t:
        return jsonify({"ok": False, "msg": err_t}), 400
    if hora_s and hora_s <= hora_e:
        return jsonify({"ok": False, "msg": "La hora de salida debe ser posterior a la de entrada."}), 400
    sede_id = data.get("sede_id") or None
    if sede_id == "":
        sede_id = None
    vid = execute(
        """INSERT INTO visitas (empresa_id, sede_id, fecha, hora_entrada, hora_salida, categoria, salon,
           cantidad_puestos, responsable, observaciones)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
        (
            int(empresa_id),
            int(sede_id) if sede_id else None,
            fecha, hora_e, hora_s,
            data.get("categoria") or None,
            data.get("salon") or None,
            int(data.get("cantidad_puestos") or 0),
            responsable,
            data.get("observaciones") or None,
        )
    )
    log_event("crear", "Calendario", despues=snap("visitas", vid))
    return jsonify({"ok": True, "id": vid, "msg": "Visita agendada."})

@app.route("/api/visita/<int:vid>", methods=["DELETE"])
@login_required
@perm_required("cal")
def api_borrar_visita(vid):
    antes = snap("visitas", vid)
    if antes and not in_scope(antes.get("empresa_id")):
        return deny_scope()
    execute("DELETE FROM visitas WHERE id=%s", (vid,))
    log_event("eliminar", "Calendario", antes=antes)
    return jsonify({"ok": True, "msg": "Visita eliminada."})


# ===================== CUENTAS (solo Owner) =====================
def _puede_gestionar(actor, target_role):
    """Solo el Owner crea y gestiona cuentas (Administrador, Evaluador, Cliente)."""
    return actor.role == "owner" and target_role in ("admin", "evaluador", "client")

def _cuenta_json(u, overrides, empresas):
    perms = effective_perms(u["role"], overrides)
    return {
        "id": u["id"], "username": u["username"], "nombre_completo": u["nombre_completo"],
        "email": u["email"] or "", "role": u["role"], "activo": int(u["activo"]),
        "empresa_id": u.get("empresa_id"),
        "creado_en": str(u["creado_en"])[:10] if u.get("creado_en") else "",
        "perms": perms,
        "overrides": overrides,
        "editable": u["role"] in EDITABLE_ROLES,
        "empresas": empresas,
    }

@app.route("/usuarios")
@login_required
@perm_required("cuentas")
def usuarios():
    rows = query("SELECT * FROM usuarios ORDER BY FIELD(role,'owner','admin','evaluador','client'), username")
    ov = {}
    for r in query("SELECT usuario_id, permiso, valor FROM usuario_permisos"):
        ov.setdefault(r["usuario_id"], {})[r["permiso"]] = bool(r["valor"])
    asg = {}
    for r in query("SELECT usuario_id, empresa_id FROM usuario_empresas"):
        asg.setdefault(r["usuario_id"], []).append(r["empresa_id"])
    lista = []
    for u in rows:
        emps = asg.get(u["id"], [])
        if u["role"] == "client" and u.get("empresa_id"):
            emps = [u["empresa_id"]]
        lista.append(_cuenta_json(u, ov.get(u["id"], {}), emps))
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1 ORDER BY nombre")
    creables = [r for r in ("admin", "evaluador", "client") if _puede_gestionar(current_user, r)]
    return render_template(
        "usuarios.html", usuarios=lista, empresas=empresas, creables=creables,
        puede_permisos=current_user.can("permisos"),
        role_defaults={r: role_defaults(r) for r in ROLE_PERM},
    )

@app.route("/api/usuario", methods=["POST"])
@login_required
@perm_required("cuentas")
def api_crear_usuario():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    role = data.get("role") or "client"
    nombre = (data.get("nombre_completo") or "").strip()
    if not username or not password or not nombre:
        return jsonify({"ok": False, "msg": "Usuario, contraseña y nombre son obligatorios."}), 400
    if len(password) < 6:
        return jsonify({"ok": False, "msg": "La contraseña debe tener al menos 6 caracteres."}), 400
    if not _puede_gestionar(current_user, role):
        log_event("crear", "Cuentas", detalle=f"Intento de crear cuenta {role} sin autorización", ok=False)
        return jsonify({"ok": False, "msg": "Tu rol no puede crear cuentas de ese tipo."}), 403
    if query("SELECT id FROM usuarios WHERE username=%s", (username,), one=True):
        return jsonify({"ok": False, "msg": "Ese nombre de usuario ya existe."}), 400
    empresa_id = int(data["empresa_id"]) if role == "client" and data.get("empresa_id") else None
    uid = execute(
        "INSERT INTO usuarios (username, password_hash, nombre_completo, email, role, empresa_id, debe_cambiar_clave) VALUES (%s,%s,%s,%s,%s,%s,1)",
        (username, generate_password_hash(password), nombre, data.get("email") or None, role, empresa_id),
    )
    if role == "evaluador":
        for eid in (data.get("empresas") or []):
            execute("INSERT IGNORE INTO usuario_empresas (usuario_id, empresa_id) VALUES (%s,%s)", (uid, int(eid)))
    log_event("crear", "Cuentas", despues=snap("usuarios", uid), detalle=f"Creó cuenta {username} con rol {ROLE_LABEL[role]}")
    return jsonify({"ok": True, "id": uid, "msg": f"Cuenta {ROLE_LABEL[role]} creada. La contraseña es temporal: deberá cambiarla al ingresar."})

def _target(uid):
    row = query("SELECT * FROM usuarios WHERE id=%s", (uid,), one=True)
    return row

@app.route("/api/usuario/<int:uid>", methods=["PUT"])
@login_required
@perm_required("cuentas")
def api_editar_usuario(uid):
    t = _target(uid)
    if not t:
        return jsonify({"ok": False, "msg": "Cuenta no encontrada."}), 404
    if uid != current_user.id and not _puede_gestionar(current_user, t["role"]):
        return jsonify({"ok": False, "msg": "No puedes editar esa cuenta."}), 403
    data = request.json or {}
    nombre = (data.get("nombre_completo") or t["nombre_completo"]).strip()
    email = (data.get("email") if "email" in data else t["email"]) or None
    antes = snap("usuarios", uid)
    password = data.get("password") or ""
    if password:
        if len(password) < 6:
            return jsonify({"ok": False, "msg": "La contraseña debe tener al menos 6 caracteres."}), 400
        execute("UPDATE usuarios SET nombre_completo=%s, email=%s, password_hash=%s, debe_cambiar_clave=1 WHERE id=%s",
                (nombre, email, generate_password_hash(password), uid))
    else:
        execute("UPDATE usuarios SET nombre_completo=%s, email=%s WHERE id=%s", (nombre, email, uid))
    if t["role"] == "client" and "empresa_id" in data:
        execute("UPDATE usuarios SET empresa_id=%s WHERE id=%s", (int(data["empresa_id"]) if data["empresa_id"] else None, uid))
    d = _diff(antes, snap("usuarios", uid))
    if password:
        d = (d + "; " if d else "") + "contraseña restablecida"
    log_event("editar", "Cuentas", antes=antes, despues=snap("usuarios", uid), detalle=d or "Sin cambios")
    return jsonify({"ok": True, "msg": "Cuenta actualizada."})

@app.route("/api/usuario/<int:uid>/toggle", methods=["POST"])
@login_required
@perm_required("cuentas")
def api_toggle_usuario(uid):
    t = _target(uid)
    if not t:
        return jsonify({"ok": False, "msg": "Cuenta no encontrada."}), 404
    if t["role"] == "owner":
        return jsonify({"ok": False, "msg": "La cuenta Owner no se puede desactivar."}), 400
    if uid == current_user.id:
        return jsonify({"ok": False, "msg": "No puedes desactivarte a ti mismo."}), 400
    if not _puede_gestionar(current_user, t["role"]):
        log_event("desactivar", "Cuentas", detalle=f"Intento sobre {t['username']} sin autorización", ok=False)
        return jsonify({"ok": False, "msg": "No puedes cambiar el estado de esa cuenta."}), 403
    nuevo = 0 if t["activo"] else 1
    execute("UPDATE usuarios SET activo=%s WHERE id=%s", (nuevo, uid))
    log_event("activar" if nuevo else "desactivar", "Cuentas", registro=f"{t['username']} (#{uid})",
              detalle=("Activó" if nuevo else "Desactivó") + f" la cuenta {t['username']}")
    return jsonify({"ok": True, "activo": nuevo, "msg": "Estado actualizado."})

@app.route("/api/usuario/<int:uid>/permisos", methods=["PUT"])
@login_required
@perm_required("permisos")
def api_permisos_usuario(uid):
    """Guarda true/false por cuenta. Solo roles editables (admin, evaluador) y permisos delegables."""
    t = _target(uid)
    if not t:
        return jsonify({"ok": False, "msg": "Cuenta no encontrada."}), 404
    if t["role"] in STATIC_ROLES:
        return jsonify({"ok": False, "msg": f"El rol {ROLE_LABEL[t['role']]} es estático: sus permisos no se editan."}), 400
    if not _puede_gestionar(current_user, t["role"]):
        return jsonify({"ok": False, "msg": "No puedes editar los permisos de esa cuenta."}), 403
    pedidos = (request.json or {}).get("perms") or {}
    base = role_defaults(t["role"])
    antes = load_overrides(uid)
    nuevos = {}
    for k, v in pedidos.items():
        if k not in base or k in NON_DELEGABLE:
            continue
        if bool(v) != base[k]:
            nuevos[k] = bool(v)
    execute("DELETE FROM usuario_permisos WHERE usuario_id=%s", (uid,))
    for k, v in nuevos.items():
        execute("INSERT INTO usuario_permisos (usuario_id, permiso, valor) VALUES (%s,%s,%s)", (uid, k, 1 if v else 0))
    etiquetas = {p[0]: p[1] for p in PERM_DEFS}
    cambios = []
    for k in PERM_KEYS:
        a = antes.get(k, base[k]); b = nuevos.get(k, base[k])
        if a != b:
            cambios.append(f"{etiquetas[k]}: {'sí' if a else 'no'} → {'sí' if b else 'no'}")
    log_event("permisos", "Cuentas", registro=f"{t['username']} (#{uid})",
              antes=antes or None, despues=nuevos or None,
              detalle="; ".join(cambios) or "Sin cambios en permisos")
    return jsonify({"ok": True, "overrides": nuevos, "perms": effective_perms(t["role"], nuevos), "msg": "Permisos guardados."})

@app.route("/api/usuario/<int:uid>/permisos", methods=["DELETE"])
@login_required
@perm_required("permisos")
def api_permisos_reset(uid):
    t = _target(uid)
    if not t or t["role"] in STATIC_ROLES:
        return jsonify({"ok": False, "msg": "Esa cuenta no tiene permisos editables."}), 400
    if not _puede_gestionar(current_user, t["role"]):
        return jsonify({"ok": False, "msg": "No puedes editar los permisos de esa cuenta."}), 403
    antes = load_overrides(uid)
    execute("DELETE FROM usuario_permisos WHERE usuario_id=%s", (uid,))
    log_event("permisos", "Cuentas", registro=f"{t['username']} (#{uid})", antes=antes or None,
              detalle=f"Restableció permisos de {t['username']} a los del rol {ROLE_LABEL[t['role']]}")
    return jsonify({"ok": True, "perms": role_defaults(t["role"]), "msg": "Permisos restablecidos al rol."})

@app.route("/api/usuario/<int:uid>/empresas", methods=["PUT"])
@login_required
@perm_required("cuentas")
def api_empresas_usuario(uid):
    """Evaluador: varias empresas asignadas. Cliente: una sola (su empresa)."""
    t = _target(uid)
    if not t or t["role"] not in ("evaluador", "client"):
        return jsonify({"ok": False, "msg": "Solo Evaluador o Cliente tienen empresas asignadas."}), 400
    if not _puede_gestionar(current_user, t["role"]):
        return jsonify({"ok": False, "msg": "No puedes editar esa cuenta."}), 403
    ids = [int(x) for x in ((request.json or {}).get("empresas") or [])]
    if t["role"] == "client":
        eid = ids[0] if ids else None
        execute("UPDATE usuarios SET empresa_id=%s WHERE id=%s", (eid, uid))
    else:
        execute("DELETE FROM usuario_empresas WHERE usuario_id=%s", (uid,))
        for eid in ids:
            execute("INSERT IGNORE INTO usuario_empresas (usuario_id, empresa_id) VALUES (%s,%s)", (uid, eid))
    nombres = [r["nombre"] for r in query("SELECT nombre FROM empresas WHERE id IN (%s)" % ",".join(["%s"] * len(ids)), tuple(ids))] if ids else []
    log_event("editar", "Cuentas", registro=f"{t['username']} (#{uid})",
              detalle="Empresas asignadas: " + (", ".join(nombres) or "ninguna"))
    return jsonify({"ok": True, "msg": "Asignación guardada."})


# ===================== LOGS =====================
def _logs_filtrados(args, limit=500, offset=0):
    where, params = ["1=1"], []
    q = (args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        where.append("(usuario LIKE %s OR accion LIKE %s OR modulo LIKE %s OR registro LIKE %s OR detalle LIKE %s)")
        params += [like] * 5
    for campo in ("usuario", "accion", "modulo"):
        vals = [v for v in args.getlist(campo) if v]
        if vals:
            where.append(f"{campo} IN ({','.join(['%s'] * len(vals))})")
            params += vals
    periodo = args.get("periodo") or "todo"
    dias = {"hoy": 0, "7d": 7, "30d": 30}.get(periodo)
    if periodo == "hoy":
        where.append("fecha >= CURDATE()")
    elif dias:
        where.append("fecha >= DATE_SUB(NOW(), INTERVAL %s DAY)")
        params.append(dias)
    if args.get("resultado") == "fallidos":
        where.append("ok=0")
    elif args.get("resultado") == "exitosos":
        where.append("ok=1")
    sql = "SELECT * FROM logs WHERE " + " AND ".join(where) + " ORDER BY id DESC LIMIT %s OFFSET %s"
    return query(sql, tuple(params) + (limit, offset)), where, params

def _log_json(r):
    return {
        "id": r["id"], "fecha": str(r["fecha"])[:19], "usuario": r["usuario"], "rol": r["rol"],
        "accion": r["accion"], "modulo": r["modulo"], "registro": r["registro"] or "",
        "detalle": r["detalle"] or "", "antes": r["antes"], "despues": r["despues"],
        "ip": r["ip"] or "", "ok": int(r["ok"]),
    }

@app.route("/logs")
@login_required
@perm_required("logs")
def logs_page():
    usuarios_ = [r["usuario"] for r in query("SELECT DISTINCT usuario FROM logs ORDER BY usuario")]
    acciones = [r["accion"] for r in query("SELECT DISTINCT accion FROM logs ORDER BY accion")]
    modulos = [r["modulo"] for r in query("SELECT DISTINCT modulo FROM logs ORDER BY modulo")]
    return render_template("logs.html", f_usuarios=usuarios_, f_acciones=acciones, f_modulos=modulos)

@app.route("/api/logs")
@login_required
@perm_required("logs")
def api_logs():
    page = max(int(request.args.get("page", 1) or 1), 1)
    size = 100
    rows, where, params = _logs_filtrados(request.args, limit=size, offset=(page - 1) * size)
    total = query("SELECT COUNT(*) c FROM logs WHERE " + " AND ".join(where), tuple(params), one=True)["c"]
    return jsonify({"ok": True, "total": total, "page": page, "size": size, "rows": [_log_json(r) for r in rows]})

@app.route("/api/logs/export.csv")
@login_required
@perm_required("logs")
def api_logs_csv():
    import csv
    from flask import Response
    rows, _, _ = _logs_filtrados(request.args, limit=5000, offset=0)
    out = StringIO()
    w = csv.writer(out)
    w.writerow(["fecha", "usuario", "rol", "accion", "modulo", "registro", "detalle", "ip", "resultado"])
    for r in rows:
        w.writerow([str(r["fecha"])[:19], r["usuario"], r["rol"], r["accion"], r["modulo"],
                    r["registro"] or "", r["detalle"] or "", r["ip"] or "", "ok" if r["ok"] else "fallido"])
    log_event("exportar", "Logs", detalle=f"Exportó {len(rows)} eventos a CSV")
    return Response("﻿" + out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=ergoplus_logs.csv"})



# ===================== NOTIFICACIONES =====================
@app.route("/api/notificaciones")
@login_required
def api_notificaciones():
    """Avisos según lo que la cuenta puede ver (y solo de sus empresas)."""
    items = []
    if current_user.can("cal"):
        sc, p = scope_clause("v.empresa_id")
        for v in query("""SELECT v.fecha, e.nombre empresa FROM visitas v JOIN empresas e ON v.empresa_id=e.id
                          WHERE v.fecha BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)""" + sc + " ORDER BY v.fecha LIMIT 5", p):
            items.append({"t": f"Visita a {v['empresa']}", "s": str(v["fecha"])})
    if current_user.can("srv"):
        sc, p = scope_clause("s.empresa_id")
        for v in query("""SELECT s.fecha_fin, e.nombre empresa FROM servicios s JOIN empresas e ON s.empresa_id=e.id
                          WHERE s.estado='activo' AND s.fecha_fin BETWEEN CURDATE() AND DATE_ADD(CURDATE(), INTERVAL 7 DAY)""" + sc + " LIMIT 5", p):
            items.append({"t": f"Servicio de {v['empresa']} vence pronto", "s": str(v["fecha_fin"])})
    if current_user.can("eval") or current_user.can("inf_ver"):
        sc, p = scope_clause("er.empresa_id")
        for v in query("""SELECT er.puntaje_final, er.fecha_evaluacion, e.nombre empresa FROM evaluacion_rula er JOIN empresas e ON er.empresa_id=e.id
                          WHERE er.nivel='Rojo' AND er.fecha_evaluacion >= DATE_SUB(NOW(), INTERVAL 7 DAY)""" + sc + " ORDER BY er.id DESC LIMIT 5", p):
            items.append({"t": f"Riesgo alto ({v['puntaje_final']}) en {v['empresa']}", "s": str(v["fecha_evaluacion"])[:10]})
    if current_user.can("logs"):
        n = query("SELECT COUNT(*) c FROM logs WHERE ok=0 AND fecha >= DATE_SUB(NOW(), INTERVAL 1 DAY)", one=True)["c"]
        if n:
            items.append({"t": f"{n} evento(s) fallido(s) en las últimas 24 h", "s": "Revisa Logs"})
    return jsonify({"ok": True, "items": items})

# ===================== PERFIL (ajustes cuenta) =====================
@app.route("/api/perfil", methods=["PUT"])
@login_required
def api_perfil():
    data = request.json or {}
    nombre = (data.get("nombre_completo") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""
    if not nombre:
        return jsonify({"ok": False, "msg": "El nombre es obligatorio."}), 400
    antes = snap("usuarios", current_user.id)
    if password:
        if len(password) < 6:
            return jsonify({"ok": False, "msg": "La contraseña debe tener al menos 6 caracteres."}), 400
        pwd_hash = generate_password_hash(password)
        execute(
            "UPDATE usuarios SET nombre_completo=%s, email=%s, password_hash=%s, debe_cambiar_clave=0 WHERE id=%s",
            (nombre, email or None, pwd_hash, current_user.id)
        )
    else:
        execute(
            "UPDATE usuarios SET nombre_completo=%s, email=%s WHERE id=%s",
            (nombre, email or None, current_user.id)
        )
    d = _diff(antes, snap("usuarios", current_user.id))
    if password:
        d = (d + "; " if d else "") + "contraseña cambiada"
    log_event("editar", "Cuentas", antes=antes, despues=snap("usuarios", current_user.id), detalle="Perfil propio: " + (d or "sin cambios"))
    return jsonify({"ok": True, "msg": "Perfil actualizado."})



# ===================== EVALUACIONES RULA =====================
@app.route("/evaluaciones")
@login_required
@perm_required("eval")
def evaluaciones():
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    sc_sql, sc_p = scope_clause("er.empresa_id")
    lista = query("""
        SELECT er.id, er.puntaje_final, er.nivel, er.lado, er.postura, er.visitante,
               er.fecha_evaluacion, e.nombre AS empresa, p.nombre AS puesto, p.numero_puesto, o.nombre AS trabajador
        FROM evaluacion_rula er
        JOIN empresas e ON er.empresa_id = e.id
        LEFT JOIN puestos p ON er.puesto_id = p.id
        LEFT JOIN operarios o ON er.trabajador_id = o.id
        WHERE 1=1""" + sc_sql + """
        ORDER BY er.fecha_evaluacion DESC
        LIMIT 100
    """, sc_p)
    rows = []
    for r in lista:
        rows.append({
            "id": r["id"],
            "empresa": r["empresa"],
            "puesto": ((r["numero_puesto"] or "") + " " + (r["puesto"] or "")).strip() or "—",
            "lado": r["lado"],
            "postura": r["postura"] or "—",
            "visitante": r["visitante"], "trabajador": r["trabajador"] or "—",
            "puntaje_final": r["puntaje_final"],
            "nivel": r["nivel"],
            "fecha": str(r["fecha_evaluacion"])[:16] if r["fecha_evaluacion"] else "",
        })
    return render_template("evaluaciones.html", empresas=empresas, evaluaciones=rows)



@app.route("/evaluacion/nueva")
@login_required
@perm_required("eval")
def evaluacion_nueva():
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    return render_template("eval_nueva.html", empresas=empresas, CAMPOS=asistente.CONDICIONES_CAMPOS,
                           GENEROS=GENEROS, LATERALIDAD=LATERALIDAD, LIM=cat.LIMITES, now_date=str(ahora_local().date()))

def _cargar_eval(eid):
    r = query("""SELECT er.*, e.nombre empresa, e.nit, e.tipo_persona, p.nombre puesto, p.numero_puesto,
                        u.nombre_completo ev_nombre, u.email ev_email, u.role ev_rol
                 FROM evaluacion_rula er JOIN empresas e ON er.empresa_id=e.id LEFT JOIN puestos p ON er.puesto_id=p.id
                 LEFT JOIN usuarios u ON er.creado_por=u.id WHERE er.id=%s""", (eid,), one=True)
    if not r or not in_scope(r["empresa_id"]):
        return None
    try:
        r["cond"] = _json.loads(r["condiciones"]) if r.get("condiciones") else {}
    except ValueError:
        r["cond"] = {}
    r["trab"] = query("SELECT * FROM operarios WHERE id=%s", (r["trabajador_id"],), one=True) if r.get("trabajador_id") else None
    r["fotos"] = query("SELECT * FROM puesto_fotos WHERE evaluacion_id=%s ORDER BY id", (eid,))
    r["contrato"] = query("""SELECT numero, tipo, fecha_inicio, fecha_fin FROM contratos WHERE empresa_id=%s AND estado='Vigente'
                             ORDER BY fecha_fin DESC LIMIT 1""", (r["empresa_id"],), one=True)
    r["compat"] = asistente.compatibilidad(r["trab"], r["cond"], r.get("carga_kg"), r["nivel"]) if r["trab"] else None
    return r

@app.route("/evaluacion/<int:eid>")
@login_required
@perm_required("eval")
def evaluacion_detalle(eid):
    r = _cargar_eval(eid)
    if not r:
        flash("Evaluación no encontrada.", "error")
        return redirect(url_for("evaluaciones"))
    trab = _trab_row(r["trab"]) if r["trab"] else None
    fotos = [_foto_json(f) for f in r["fotos"]]
    base = {k: (str(v) if v is not None else "") for k, v in r.items() if k in
            ("id", "empresa", "nit", "puesto", "numero_puesto", "nivel", "puntaje_final", "accion_sugerida", "visitante", "postura", "lado",
             "recomendaciones", "sugerencias", "observaciones", "fecha_evaluacion", "ev_nombre", "ev_email", "ev_rol", "puntos_a", "puntos_b", "puntos_c", "puntos_d",
             "puntos_actividad", "puntos_fuerza", "brazo_angulo", "antebrazo_angulo", "muneca_angulo", "cuello_angulo", "tronco_angulo", "carga_kg", "ia_usada",
             "brazo", "antebrazo", "muneca", "cuello", "tronco", "piernas")}
    for k, col in (("brazo", "puntos_brazo"), ("antebrazo", "puntos_antebrazo"), ("muneca", "puntos_muneca"), ("cuello", "puntos_cuello"),
                   ("tronco", "puntos_tronco"), ("piernas", "puntos_piernas")):
        base[k] = str(r.get(col) or "")
    return render_template("eval_detalle.html", ev=base, trab=trab, cond=r["cond"], fotos=fotos, compat=r["compat"], contrato=r["contrato"],
                           puede_dl=current_user.can("inf_dl"), CAMPOS=asistente.CONDICIONES_CAMPOS)

@app.route("/api/evaluacion/<int:eid>/recomendaciones", methods=["PUT"])
@login_required
@perm_required("eval")
def api_eval_recs(eid):
    r = query("SELECT empresa_id FROM evaluacion_rula WHERE id=%s", (eid,), one=True)
    if not r:
        return jsonify({"ok": False, "msg": "Evaluación no encontrada."}), 404
    if not in_scope(r["empresa_id"]):
        return deny_scope()
    t = ((request.json or {}).get("recomendaciones") or "").strip()
    if len(t) > 4000:
        return jsonify({"ok": False, "msg": "Las recomendaciones admiten máximo 4000 caracteres."}), 400
    execute("UPDATE evaluacion_rula SET recomendaciones=%s WHERE id=%s", (t or None, eid))
    log_event("editar", "Evaluaciones", registro=f"Evaluación #{eid}", detalle="Editó las recomendaciones")
    return jsonify({"ok": True, "msg": "Recomendaciones guardadas."})

@app.route("/evaluacion/<int:eid>/informe.pdf")
@login_required
@perm_required("inf_dl")
def evaluacion_pdf(eid):
    if not HAS_REPORTLAB:
        return jsonify({"ok": False, "msg": "Falta instalar reportlab."}), 500
    r = _cargar_eval(eid)
    if not r:
        abort(404)
    import informe_eval
    pdf = informe_eval.generar(r, Config.UPLOAD_DIR, CONSENT_VERSION)
    log_event("descargar", "Informes", registro=f"Evaluación #{eid}", detalle="Descargó el informe descriptivo de la evaluación")
    from flask import Response
    return Response(pdf, mimetype="application/pdf", headers={"Content-Disposition": f'attachment; filename="informe_evaluacion_{eid}.pdf"'})

@app.route("/api/rula/calcular", methods=["POST"])
@login_required
@perm_required("eval")
def api_rula_calcular():
    data = request.json or {}
    result = calcular_rula(data)
    return jsonify({"ok": True, "resultado": result})


@app.route("/api/rula/guardar", methods=["POST"])
@login_required
@perm_required("eval")
def api_rula_guardar():
    data = request.json or {}
    empresa_id = data.get("empresa_id")
    visitante = (data.get("visitante") or "").strip() or current_user.nombre_completo
    if not empresa_id:
        return jsonify({"ok": False, "msg": "Seleccione la empresa."}), 400
    if not in_scope(empresa_id):
        return deny_scope()
    trab = None
    if data.get("trabajador_id"):
        trab = query("SELECT * FROM operarios WHERE id=%s AND empresa_id=%s", (int(data["trabajador_id"]), int(empresa_id)), one=True)
        if not trab:
            return jsonify({"ok": False, "msg": "El trabajador no pertenece a esa empresa."}), 400
        if not trab.get("consentimiento_fecha"):
            return jsonify({"ok": False, "msg": "El trabajador no tiene consentimiento informado registrado."}), 400
    if data.get("puesto_id") and empresa_de("puestos", int(data["puesto_id"])) != int(empresa_id):
        return jsonify({"ok": False, "msg": "El puesto no pertenece a esa empresa."}), 400
    if data.get("puesto_id") and not data.get("salon_id"):
        _p = query("SELECT sa.id salon_id, sa.sede_id FROM puestos p JOIN salones sa ON p.salon_id=sa.id WHERE p.id=%s", (int(data["puesto_id"]),), one=True)
        if _p:
            data["salon_id"], data["sede_id"] = _p["salon_id"], _p["sede_id"]
    err = cat.revisar_largos(data, ["postura", "sugerencias", "observaciones"])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cond, err = asistente.limpiar_condiciones(data.get("condiciones") or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    result = calcular_rula(data)
    eid = execute(
        """INSERT INTO evaluacion_rula (
            visita_id, empresa_id, sede_id, salon_id, puesto_id, lado, postura, criterio, tiempo_minutos, visitante,
            brazo_angulo, brazo_extension, hombro_elevado, brazo_abducido, brazo_rotado, brazo_apoyo,
            antebrazo_angulo, antebrazo_cruza, antebrazo_lado,
            muneca_angulo, muneca_desviacion, giro_extremo,
            cuello_angulo, cuello_extension, cuello_rotado, cuello_inclinado,
            tronco_angulo, tronco_rotado, tronco_inclinado, sentado_bien,
            pies_apoyados, peso_repartido,
            actividad_estatica, actividad_repetitiva, carga_kg, carga_estatica_rep, golpes,
            puntos_brazo, puntos_antebrazo, puntos_muneca, puntos_giro,
            puntos_cuello, puntos_tronco, puntos_piernas,
            puntos_a, puntos_b, puntos_actividad, puntos_fuerza, puntos_c, puntos_d,
            puntaje_final, nivel, accion_sugerida, sugerencias, observaciones, creado_por
        ) VALUES (
            %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,
            %s,%s,%s,%s,%s,
            %s,%s,%s,%s,
            %s,%s,%s,
            %s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s,%s,%s
        )""",
        (
            data.get("visita_id") or None,
            int(empresa_id),
            int(data["sede_id"]) if data.get("sede_id") else None,
            int(data["salon_id"]) if data.get("salon_id") else None,
            int(data["puesto_id"]) if data.get("puesto_id") else None,
            data.get("lado") or "Derecho",
            data.get("postura") or None,
            data.get("criterio") or None,
            int(data["tiempo_minutos"]) if data.get("tiempo_minutos") else None,
            visitante,
            float(data.get("brazo_angulo") or 0),
            1 if data.get("brazo_extension") else 0,
            1 if data.get("hombro_elevado") else 0,
            1 if data.get("brazo_abducido") else 0,
            1 if data.get("brazo_rotado") else 0,
            1 if data.get("brazo_apoyo") else 0,
            float(data.get("antebrazo_angulo") or 90),
            1 if data.get("antebrazo_cruza") else 0,
            1 if data.get("antebrazo_lado") else 0,
            float(data.get("muneca_angulo") or 0),
            1 if data.get("muneca_desviacion") else 0,
            1 if data.get("giro_extremo") else 0,
            float(data.get("cuello_angulo") or 0),
            1 if data.get("cuello_extension") else 0,
            1 if data.get("cuello_rotado") else 0,
            1 if data.get("cuello_inclinado") else 0,
            float(data.get("tronco_angulo") or 0),
            1 if data.get("tronco_rotado") else 0,
            1 if data.get("tronco_inclinado") else 0,
            1 if data.get("sentado_bien") else 0,
            1 if data.get("pies_apoyados", True) else 0,
            1 if data.get("peso_repartido", True) else 0,
            1 if data.get("actividad_estatica") else 0,
            1 if data.get("actividad_repetitiva") else 0,
            float(data.get("carga_kg") or 0),
            1 if data.get("carga_estatica_rep") else 0,
            1 if data.get("golpes") else 0,
            result["brazo"], result["antebrazo"], result["muneca"], result["giro_muneca"],
            result["cuello"], result["tronco"], result["piernas"],
            result["puntos_a"], result["puntos_b"], result["puntos_actividad"], result["puntos_fuerza"],
            result["puntos_c"], result["puntos_d"],
            result["puntaje_final"], result["nivel"], result["accion_sugerida"],
            data.get("sugerencias") or None,
            data.get("observaciones") or None,
            current_user.id,
        )
    )
    comp = asistente.compatibilidad(trab, cond, data.get("carga_kg"), result["nivel"]) if trab else None
    recs = (data.get("recomendaciones") or "").strip()
    if not recs:
        recs = asistente.recomendaciones_texto(asistente.recomendaciones(result, cond, comp))
    execute("UPDATE evaluacion_rula SET trabajador_id=%s, condiciones=%s, recomendaciones=%s, ia_usada=%s WHERE id=%s",
            (trab["id"] if trab else None, _json.dumps(cond, ensure_ascii=False), recs[:4000], 1 if data.get("ia_usada") else 0, eid))
    ids = [int(x) for x in (data.get("foto_ids") or []) if str(x).isdigit()][:12]
    if ids:
        execute(f"UPDATE puesto_fotos SET evaluacion_id=%s WHERE empresa_id=%s AND id IN ({','.join(['%s'] * len(ids))})",
                (eid, int(empresa_id)) + tuple(ids))
    emp_n = query("SELECT nombre FROM empresas WHERE id=%s", (int(empresa_id),), one=True)
    log_event("crear", "Evaluaciones", registro=f"Evaluación #{eid} · {(emp_n or {}).get('nombre', '')}",
              detalle=f"Evaluación guardada (método RULA): puntaje {result['puntaje_final']} · nivel {result['nivel']}")
    return jsonify({"ok": True, "id": eid, "resultado": result, "url": url_for("evaluacion_detalle", eid=eid), "msg": "Evaluación guardada."})


# ===================== TRABAJADORES (perfil + consentimiento) =====================
import os, json as _json
import ia as asistente

CONSENT_VERSION = "v1-2026"
CONSENT_TEXTO = (
    "Autorizo de manera libre, previa, expresa e informada a ERGOPLUS y a la empresa contratante para tratar mis datos personales "
    "(identificación, género, edad, antigüedad, jornada, antecedentes de molestias, fotografías de mi puesto de trabajo y respuestas a encuestas) "
    "con la única finalidad de realizar la evaluación ergonómica de mi puesto, generar el informe y proponer mejoras. "
    "Entiendo que las fotografías podrían mostrar mi imagen, que puedo pedir que se omita mi rostro, que los datos sobre mi salud son sensibles y que "
    "no estoy obligado a suministrarlos. Conozco mis derechos de acceso, actualización, rectificación y supresión, y que puedo revocar esta autorización "
    "en cualquier momento (Ley 1581 de 2012 y Decreto 1377 de 2013)."
)
GENEROS = ["Femenino", "Masculino", "Otro"]
LATERALIDAD = ["Diestro", "Zurdo", "Ambidiestro"]

def _trab_row(r):
    return {
        "id": r["id"], "empresa_id": r["empresa_id"], "puesto_id": r.get("puesto_id"), "nombre": r["nombre"],
        "documento": r.get("documento") or "", "cargo": r.get("cargo") or "", "genero": r.get("genero") or "",
        "fecha_nacimiento": str(r["fecha_nacimiento"]) if r.get("fecha_nacimiento") else "",
        "edad": asistente.edad(r.get("fecha_nacimiento")), "antiguedad_meses": r.get("antiguedad_meses"),
        "antiguedad": asistente.texto_antiguedad(r.get("antiguedad_meses")),
        "horas_jornada": float(r["horas_jornada"]) if r.get("horas_jornada") is not None else None,
        "lateralidad": r.get("lateralidad") or "", "estatura_cm": r.get("estatura_cm"),
        "antecedentes": r.get("antecedentes") or "",
        "consentimiento": bool(r.get("consentimiento_fecha")),
        "consentimiento_fecha": str(r["consentimiento_fecha"])[:16] if r.get("consentimiento_fecha") else "",
    }

def _validar_trab(d):
    err = cat.revisar_largos(d, ["nombre", "documento", "cargo", "antecedentes"])
    if err:
        return None, err
    nombre = (d.get("nombre") or "").strip()
    if len(nombre) < 3:
        return None, "El nombre del trabajador es obligatorio."
    if not d.get("empresa_id") or not in_scope(d.get("empresa_id")):
        return None, "Selecciona una empresa asignada a tu cuenta."
    out = {"empresa_id": int(d["empresa_id"]), "nombre": nombre,
           "documento": (d.get("documento") or "").strip() or None, "cargo": (d.get("cargo") or "").strip() or None,
           "antecedentes": (d.get("antecedentes") or "").strip() or None}
    pid = d.get("puesto_id")
    if pid:
        if empresa_de("puestos", int(pid)) != out["empresa_id"]:
            return None, "El puesto no pertenece a esa empresa."
        out["puesto_id"] = int(pid)
    else:
        out["puesto_id"] = None
    g = d.get("genero") or None
    if g and g not in GENEROS:
        return None, "Género no válido."
    out["genero"] = g
    l = d.get("lateralidad") or None
    if l and l not in LATERALIDAD:
        return None, "Lateralidad no válida."
    out["lateralidad"] = l
    fn = d.get("fecha_nacimiento") or None
    if fn:
        e = asistente.edad(fn)
        if e is None or not 14 <= e <= 90:
            return None, "La fecha de nacimiento no es válida (edad entre 14 y 90 años)."
    out["fecha_nacimiento"] = fn
    for k, mn, mx, n in (("antiguedad_meses", 0, 720, "El tiempo en la empresa (meses)"), ("estatura_cm", 100, 230, "La estatura (cm)")):
        v = d.get(k)
        if v in (None, ""):
            out[k] = None
            continue
        try:
            v = int(float(v))
        except (TypeError, ValueError):
            return None, f"{n} debe ser un número."
        if not mn <= v <= mx:
            return None, f"{n} debe estar entre {mn} y {mx}."
        out[k] = v
    h = d.get("horas_jornada")
    if h in (None, ""):
        out["horas_jornada"] = None
    else:
        try:
            h = round(float(h), 1)
        except (TypeError, ValueError):
            return None, "Las horas de jornada deben ser un número."
        if not 1 <= h <= 16:
            return None, "Las horas de jornada deben estar entre 1 y 16."
        out["horas_jornada"] = h
    return out, None

def _trabajador_ok(tid):
    """Devuelve (fila, None) o (None, respuesta de error)."""
    r = query("SELECT * FROM operarios WHERE id=%s", (tid,), one=True)
    if not r:
        return None, (jsonify({"ok": False, "msg": "Trabajador no encontrado."}), 404)
    if not in_scope(r["empresa_id"]):
        return None, deny_scope()
    return r, None

@app.route("/api/consentimiento/texto")
@login_required
@perm_required("eval")
def api_consent_texto():
    return jsonify({"ok": True, "texto": CONSENT_TEXTO, "version": CONSENT_VERSION})

@app.route("/api/trabajadores")
@login_required
@perm_required("eval")
def api_trabajadores():
    eid = request.args.get("empresa_id", type=int)
    if not eid or not in_scope(eid):
        return jsonify({"ok": True, "trabajadores": []})
    pid = request.args.get("puesto_id", type=int)
    sql = "SELECT * FROM operarios WHERE empresa_id=%s AND activo=1"
    p = [eid]
    if pid:
        sql += " AND (puesto_id=%s OR puesto_id IS NULL)"
        p.append(pid)
    rows = query(sql + " ORDER BY nombre", tuple(p))
    return jsonify({"ok": True, "trabajadores": [_trab_row(r) for r in rows]})

@app.route("/api/trabajador", methods=["POST"])
@login_required
@perm_required("eval")
def api_crear_trabajador():
    d, err = _validar_trab(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    cols = list(d.keys())
    tid = execute(f"INSERT INTO operarios ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))})", tuple(d.values()))
    log_event("crear", "Trabajadores", despues=snap("operarios", tid))
    return jsonify({"ok": True, "id": tid, "trabajador": _trab_row(query("SELECT * FROM operarios WHERE id=%s", (tid,), one=True)), "msg": "Trabajador registrado."})

@app.route("/api/trabajador/<int:tid>", methods=["PUT"])
@login_required
@perm_required("eval")
def api_editar_trabajador(tid):
    r, e = _trabajador_ok(tid)
    if e:
        return e
    body = request.json or {}
    body["empresa_id"] = r["empresa_id"]
    d, err = _validar_trab(body)
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    antes = snap("operarios", tid)
    execute(f"UPDATE operarios SET {', '.join(c + '=%s' for c in d)} WHERE id=%s", tuple(d.values()) + (tid,))
    log_event("editar", "Trabajadores", antes=antes, despues=snap("operarios", tid))
    return jsonify({"ok": True, "trabajador": _trab_row(query("SELECT * FROM operarios WHERE id=%s", (tid,), one=True)), "msg": "Trabajador actualizado."})

@app.route("/api/trabajador/<int:tid>/consentimiento", methods=["POST"])
@login_required
@perm_required("eval")
def api_consentimiento(tid):
    r, e = _trabajador_ok(tid)
    if e:
        return e
    d = request.json or {}
    nombre = (d.get("nombre") or "").strip()
    if not d.get("acepta"):
        return jsonify({"ok": False, "msg": "Debes marcar que el trabajador acepta el consentimiento."}), 400
    if len(nombre) < 3 or len(nombre) > 100:
        return jsonify({"ok": False, "msg": "Escribe el nombre completo de quien firma (3 a 100 caracteres)."}), 400
    execute("UPDATE operarios SET consentimiento_fecha=%s, consentimiento_nombre=%s, consentimiento_version=%s WHERE id=%s",
            (ahora_local(), nombre, CONSENT_VERSION, tid))
    log_event("crear", "Consentimiento", registro=f"{r['nombre']} (#{tid})", detalle=f"Consentimiento informado {CONSENT_VERSION} firmado por «{nombre}»")
    return jsonify({"ok": True, "msg": "Consentimiento registrado."})

@app.route("/api/trabajador/<int:tid>/consentimiento", methods=["DELETE"])
@login_required
@perm_required("eval")
def api_revocar_consentimiento(tid):
    r, e = _trabajador_ok(tid)
    if e:
        return e
    execute("UPDATE operarios SET consentimiento_fecha=NULL, consentimiento_nombre=NULL, consentimiento_version=NULL WHERE id=%s", (tid,))
    log_event("eliminar", "Consentimiento", registro=f"{r['nombre']} (#{tid})", detalle="Consentimiento revocado")
    return jsonify({"ok": True, "msg": "Consentimiento revocado."})

# ===================== CONDICIONES DEL PUESTO =====================
def _puesto_ok(pid):
    eid = empresa_de("puestos", pid)
    if eid is None:
        return None, (jsonify({"ok": False, "msg": "Puesto no encontrado."}), 404)
    if not in_scope(eid):
        return None, deny_scope()
    return eid, None

@app.route("/api/puesto/<int:pid>/condiciones", methods=["GET"])
@login_required
@perm_required("eval")
def api_condiciones_get(pid):
    eid, e = _puesto_ok(pid)
    if e:
        return e
    r = query("SELECT condiciones FROM puestos WHERE id=%s", (pid,), one=True)
    try:
        c = _json.loads(r["condiciones"]) if r and r["condiciones"] else {}
    except ValueError:
        c = {}
    return jsonify({"ok": True, "condiciones": c})

@app.route("/api/puesto/<int:pid>/condiciones", methods=["PUT"])
@login_required
@perm_required("eval")
def api_condiciones_put(pid):
    eid, e = _puesto_ok(pid)
    if e:
        return e
    c, err = asistente.limpiar_condiciones(request.json or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    execute("UPDATE puestos SET condiciones=%s WHERE id=%s", (_json.dumps(c, ensure_ascii=False), pid))
    log_event("editar", "Puestos", registro=f"Puesto #{pid}", detalle="Actualizó las condiciones del puesto")
    return jsonify({"ok": True, "condiciones": c, "msg": "Condiciones guardadas."})

# ===================== FOTOS DEL PUESTO =====================
EXT_MAGIC = [(b"\xff\xd8\xff", "jpg", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "png", "image/png")]

def _tipo_imagen(b):
    for magic, ext, mime in EXT_MAGIC:
        if b.startswith(magic):
            return ext, mime
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None, None

def _foto_ok(fid):
    f = query("SELECT * FROM puesto_fotos WHERE id=%s", (fid,), one=True)
    if not f:
        return None, (jsonify({"ok": False, "msg": "Foto no encontrada."}), 404)
    if not in_scope(f["empresa_id"]):
        return None, deny_scope()
    return f, None

def _foto_json(f):
    def j(x):
        try:
            return _json.loads(x) if x else None
        except ValueError:
            return None
    return {"id": f["id"], "url": url_for("ver_foto", fid=f["id"]), "vista": f["vista"], "mira_a": f["mira_a"],
            "puntos": j(f["puntos"]) or {}, "angulos": j(f["angulos"]) or {}, "origen": f["origen"], "notas": f["notas"] or "",
            "evaluacion_id": f["evaluacion_id"]}

@app.route("/api/foto", methods=["POST"])
@login_required
@perm_required("eval")
def api_subir_foto():
    eid = request.form.get("empresa_id", type=int)
    pid = request.form.get("puesto_id", type=int)
    tid = request.form.get("trabajador_id", type=int)
    if not eid or not in_scope(eid):
        return deny_scope()
    if not tid:
        return jsonify({"ok": False, "msg": "Selecciona al trabajador antes de subir fotos."}), 400
    t = query("SELECT * FROM operarios WHERE id=%s AND empresa_id=%s", (tid, eid), one=True)
    if not t:
        return jsonify({"ok": False, "msg": "Trabajador no válido para esa empresa."}), 400
    if not t.get("consentimiento_fecha"):
        return jsonify({"ok": False, "msg": "No se pueden subir fotos sin el consentimiento informado del trabajador."}), 400
    if pid and empresa_de("puestos", pid) != eid:
        return jsonify({"ok": False, "msg": "El puesto no pertenece a esa empresa."}), 400
    f = request.files.get("foto")
    if not f:
        return jsonify({"ok": False, "msg": "Adjunta una imagen."}), 400
    data = f.read(Config.MAX_FOTO_BYTES + 1)
    if len(data) > Config.MAX_FOTO_BYTES:
        return jsonify({"ok": False, "msg": "La foto supera 6 MB."}), 400
    ext, mime = _tipo_imagen(data)
    if not ext:
        return jsonify({"ok": False, "msg": "Formato no permitido. Usa JPG, PNG o WEBP."}), 400
    vista = request.form.get("vista") if request.form.get("vista") in ("Lateral", "Frontal", "Posterior") else "Lateral"
    os.makedirs(Config.UPLOAD_DIR, exist_ok=True)
    nombre = secrets.token_hex(16) + "." + ext
    with open(os.path.join(Config.UPLOAD_DIR, nombre), "wb") as fh:
        fh.write(data)
    fid = execute("""INSERT INTO puesto_fotos (empresa_id, puesto_id, trabajador_id, archivo, mime, vista, mira_a, origen, creado_por)
                     VALUES (%s,%s,%s,%s,%s,%s,'Derecha','manual',%s)""", (eid, pid or None, tid, nombre, mime, vista, current_user.id))
    log_event("crear", "Fotos", registro=f"Foto #{fid}", detalle=f"Subió foto {vista.lower()} del puesto (trabajador #{tid})")
    return jsonify({"ok": True, "foto": _foto_json(query("SELECT * FROM puesto_fotos WHERE id=%s", (fid,), one=True))})

@app.route("/foto/<int:fid>")
@login_required
@perm_required("inf_ver")
def ver_foto(fid):
    f = query("SELECT * FROM puesto_fotos WHERE id=%s", (fid,), one=True)
    if not f or not in_scope(f["empresa_id"]):
        abort(404)
    from flask import send_from_directory
    resp = send_from_directory(Config.UPLOAD_DIR, os.path.basename(f["archivo"]), mimetype=f["mime"])
    resp.headers["Cache-Control"] = "private, max-age=600"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    return resp

@app.route("/api/fotos")
@login_required
@perm_required("eval")
def api_fotos():
    eid = request.args.get("empresa_id", type=int)
    if not eid or not in_scope(eid):
        return jsonify({"ok": True, "fotos": []})
    sql, p = "SELECT * FROM puesto_fotos WHERE empresa_id=%s", [eid]
    for col, k in (("puesto_id", "puesto_id"), ("trabajador_id", "trabajador_id"), ("evaluacion_id", "evaluacion_id")):
        v = request.args.get(k, type=int)
        if v:
            sql += f" AND {col}=%s"; p.append(v)
    return jsonify({"ok": True, "fotos": [_foto_json(f) for f in query(sql + " ORDER BY id", tuple(p))]})

@app.route("/api/foto/<int:fid>", methods=["PUT"])
@login_required
@perm_required("eval")
def api_foto_guardar(fid):
    f, e = _foto_ok(fid)
    if e:
        return e
    d = request.json or {}
    puntos = {}
    for k, v in (d.get("puntos") or {}).items():
        if k in asistente.PUNTOS_VALIDOS and isinstance(v, (list, tuple)) and len(v) == 2:
            try:
                x, y = float(v[0]), float(v[1])
            except (TypeError, ValueError):
                continue
            if 0 <= x <= 1 and 0 <= y <= 1:
                puntos[k] = [round(x, 4), round(y, 4)]
    angulos = {}
    for k, v in (d.get("angulos") or {}).items():
        if k in ("brazo", "antebrazo", "muneca", "cuello", "tronco", "lado_i") and v is not None:
            try:
                angulos[k] = round(float(v), 1)
            except (TypeError, ValueError):
                pass
    mira = d.get("mira_a") if d.get("mira_a") in ("Derecha", "Izquierda") else "Derecha"
    vista = d.get("vista") if d.get("vista") in ("Lateral", "Frontal", "Posterior") else f["vista"]
    execute("UPDATE puesto_fotos SET puntos=%s, angulos=%s, mira_a=%s, vista=%s, notas=%s, origen=%s WHERE id=%s",
            (_json.dumps(puntos), _json.dumps(angulos), mira, vista, (d.get("notas") or "")[:250] or None,
             "ia" if d.get("origen") == "ia" else f["origen"], fid))
    return jsonify({"ok": True, "foto": _foto_json(query("SELECT * FROM puesto_fotos WHERE id=%s", (fid,), one=True))})

@app.route("/api/foto/<int:fid>", methods=["DELETE"])
@login_required
@perm_required("eval")
def api_foto_borrar(fid):
    f, e = _foto_ok(fid)
    if e:
        return e
    if f["evaluacion_id"]:
        return jsonify({"ok": False, "msg": "Esta foto ya forma parte de una evaluación guardada."}), 400
    try:
        os.remove(os.path.join(Config.UPLOAD_DIR, os.path.basename(f["archivo"])))
    except OSError:
        pass
    execute("DELETE FROM puesto_fotos WHERE id=%s", (fid,))
    log_event("eliminar", "Fotos", registro=f"Foto #{fid}")
    return jsonify({"ok": True, "msg": "Foto eliminada."})

# ===================== ASISTENTE / IA =====================
@app.route("/api/ia/estado")
@login_required
@perm_required("eval")
def api_ia_estado():
    return jsonify({"ok": True, "vision": asistente.ia_disponible(), "modelo": Config.AI_MODEL if asistente.ia_disponible() else None})

@app.route("/api/ia/sugerir", methods=["POST"])
@login_required
@perm_required("eval")
def api_ia_sugerir():
    d = request.json or {}
    cond, err = asistente.limpiar_condiciones(d.get("condiciones") or {})
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    trab = None
    if d.get("trabajador_id"):
        trab, e = _trabajador_ok(int(d["trabajador_id"]))
        if e:
            return e
    s = asistente.sugerir(cond, trab)
    comp = asistente.compatibilidad(trab, cond, cond.get("peso_tipico_kg")) if trab else None
    return jsonify({"ok": True, "sugerencia": s, "compatibilidad": comp})

@app.route("/api/ia/foto/<int:fid>", methods=["POST"])
@login_required
@perm_required("eval")
def api_ia_foto(fid):
    f, e = _foto_ok(fid)
    if e:
        return e
    if not asistente.ia_disponible():
        return jsonify({"ok": False, "msg": "La IA de fotos no está configurada (falta ANTHROPIC_API_KEY). Marca los puntos manualmente."}), 400
    t = query("SELECT consentimiento_fecha FROM operarios WHERE id=%s", (f["trabajador_id"],), one=True)
    if not t or not t["consentimiento_fecha"]:
        return jsonify({"ok": False, "msg": "Sin consentimiento informado no se puede analizar la foto."}), 400
    try:
        with open(os.path.join(Config.UPLOAD_DIR, os.path.basename(f["archivo"])), "rb") as fh:
            r = asistente.analizar_foto(fh.read())
    except RuntimeError as ex:
        return jsonify({"ok": False, "msg": str(ex)}), 502
    except OSError:
        return jsonify({"ok": False, "msg": "No se encontró el archivo de la foto."}), 404
    log_event("consultar", "Fotos", registro=f"Foto #{fid}", detalle="Análisis de foto con IA (sugerencia, editable)")
    return jsonify({"ok": True, **r})

@app.route("/api/ia/recomendar", methods=["POST"])
@login_required
@perm_required("eval")
def api_ia_recomendar():
    d = request.json or {}
    res = calcular_rula(d.get("medicion") or {})
    cond, _ = asistente.limpiar_condiciones(d.get("condiciones") or {})
    trab = None
    if d.get("trabajador_id"):
        trab, e = _trabajador_ok(int(d["trabajador_id"]))
        if e:
            return e
    comp = asistente.compatibilidad(trab, cond, (d.get("medicion") or {}).get("carga_kg"), res["nivel"]) if trab else None
    lista = asistente.recomendaciones(res, cond, comp)
    return jsonify({"ok": True, "resultado": res, "compatibilidad": comp, "recomendaciones": lista,
                    "texto": asistente.recomendaciones_texto(lista)})

# ===================== ENCUESTAS =====================
ZONAS_NORDICO = ["Cuello", "Hombros", "Codo / antebrazo", "Muñeca / mano", "Espalda alta", "Espalda baja", "Caderas / muslos", "Rodillas", "Tobillos / pies"]
ITEMS_PERCEPCION = ["Silla", "Mesa / superficie de trabajo", "Iluminación", "Ruido", "Temperatura", "Espacio disponible", "Pausas y descansos", "Carga de trabajo", "Equipos y herramientas"]

@app.route("/encuestas")
@login_required
@perm_required("eval")
def encuestas():
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    return render_template("encuestas.html", empresas=empresas, ZONAS=ZONAS_NORDICO, ITEMS=ITEMS_PERCEPCION)

@app.route("/api/encuesta", methods=["POST"])
@login_required
@perm_required("eval")
def api_encuesta():
    d = request.json or {}
    tipo = d.get("tipo")
    eid = d.get("empresa_id")
    if tipo not in ("nordico", "percepcion"):
        return jsonify({"ok": False, "msg": "Tipo de encuesta no válido."}), 400
    if not eid or not in_scope(eid):
        return deny_scope()
    err = cat.revisar_largos(d, ["comentario"])
    if err:
        return jsonify({"ok": False, "msg": err}), 400
    pid = d.get("puesto_id") or None
    if pid and empresa_de("puestos", int(pid)) != int(eid):
        return jsonify({"ok": False, "msg": "El puesto no pertenece a esa empresa."}), 400
    tid = d.get("trabajador_id") or None
    if tid:
        t = query("SELECT consentimiento_fecha FROM operarios WHERE id=%s AND empresa_id=%s", (int(tid), int(eid)), one=True)
        if not t:
            return jsonify({"ok": False, "msg": "Trabajador no válido."}), 400
        if tipo == "nordico" and not t["consentimiento_fecha"]:
            return jsonify({"ok": False, "msg": "La encuesta de molestias es un dato de salud: requiere el consentimiento informado."}), 400
    resp = d.get("respuestas") or {}
    limpio = {}
    if tipo == "nordico":
        for z in ZONAS_NORDICO:
            v = resp.get(z) or {}
            try:
                inten = max(0, min(5, int(v.get("intensidad") or 0)))
            except (TypeError, ValueError):
                inten = 0
            limpio[z] = {"molestia": bool(v.get("molestia")), "intensidad": inten if v.get("molestia") else 0}
    else:
        for it in ITEMS_PERCEPCION:
            try:
                n = int(resp.get(it))
            except (TypeError, ValueError):
                return jsonify({"ok": False, "msg": f"Califica «{it}» de 1 a 5."}), 400
            if not 1 <= n <= 5:
                return jsonify({"ok": False, "msg": f"Califica «{it}» de 1 a 5."}), 400
            limpio[it] = n
    sid = execute("INSERT INTO encuestas (empresa_id, puesto_id, trabajador_id, tipo, respuestas, comentario, creado_por) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                  (int(eid), int(pid) if pid else None, int(tid) if tid else None, tipo, _json.dumps(limpio, ensure_ascii=False),
                   (d.get("comentario") or "").strip() or None, current_user.id))
    log_event("crear", "Encuestas", registro=f"Encuesta #{sid}", detalle=f"Encuesta {'Nórdica' if tipo == 'nordico' else 'de percepción'} registrada")
    return jsonify({"ok": True, "id": sid, "msg": "Encuesta guardada."})

@app.route("/api/encuestas")
@login_required
@perm_required("eval")
def api_encuestas():
    eid = request.args.get("empresa_id", type=int)
    if not eid or not in_scope(eid):
        return jsonify({"ok": True, "encuestas": [], "resumen": {}})
    pid = request.args.get("puesto_id", type=int)
    sql, p = """SELECT s.*, o.nombre trabajador, pu.nombre puesto FROM encuestas s LEFT JOIN operarios o ON s.trabajador_id=o.id
                LEFT JOIN puestos pu ON s.puesto_id=pu.id WHERE s.empresa_id=%s""", [eid]
    if pid:
        sql += " AND s.puesto_id=%s"; p.append(pid)
    rows = query(sql + " ORDER BY s.id DESC LIMIT 200", tuple(p))
    lista, nord, perc = [], {}, {}
    nn = npp = 0
    for r in rows:
        try:
            resp = _json.loads(r["respuestas"])
        except ValueError:
            resp = {}
        lista.append({"id": r["id"], "tipo": r["tipo"], "puesto": r["puesto"] or "—", "trabajador": r["trabajador"] or "Anónimo",
                      "fecha": str(r["creado_en"])[:16], "comentario": r["comentario"] or ""})
        if r["tipo"] == "nordico":
            nn += 1
            for z, v in resp.items():
                a = nord.setdefault(z, [0, 0]); a[0] += 1 if v.get("molestia") else 0; a[1] += v.get("intensidad", 0)
        else:
            npp += 1
            for k, v in resp.items():
                a = perc.setdefault(k, [0, 0]); a[0] += v; a[1] += 1
    return jsonify({"ok": True, "encuestas": lista,
                    "resumen": {"nordico": {"n": nn, "zonas": {z: {"con_molestia": a[0], "intensidad_media": round(a[1] / a[0], 1) if a[0] else 0} for z, a in nord.items()}},
                                "percepcion": {"n": npp, "items": {k: round(a[0] / a[1], 1) for k, a in perc.items()}}}})


# ===================== INFORMES =====================
@app.route("/informes")
@login_required
@perm_required("inf_ver")
def informes():
    sc2, p2 = scope_clause("id")
    empresas = query("SELECT id, nombre FROM empresas WHERE activo=1" + sc2 + " ORDER BY nombre", p2)
    return render_template("informes.html", empresas=empresas)


@app.route("/api/informe/<int:empresa_id>")
@login_required
@perm_required("inf_ver")
def api_informe(empresa_id):
    if not in_scope(empresa_id):
        return deny_scope()
    emp = query("SELECT * FROM empresas WHERE id=%s", (empresa_id,), one=True)
    if not emp:
        return jsonify({"ok": False, "msg": "Empresa no encontrada"}), 404
    sedes = query("SELECT COUNT(*) AS n FROM sedes WHERE empresa_id=%s AND activo=1", (empresa_id,), one=True)
    salones = query("""
        SELECT COUNT(*) AS n FROM salones sa
        JOIN sedes s ON sa.sede_id=s.id WHERE s.empresa_id=%s AND sa.activo=1
    """, (empresa_id,), one=True)
    puestos = query("""
        SELECT COUNT(*) AS n FROM puestos p
        JOIN salones sa ON p.salon_id=sa.id
        JOIN sedes s ON sa.sede_id=s.id WHERE s.empresa_id=%s AND p.activo=1
    """, (empresa_id,), one=True)
    evals = query("""
        SELECT er.*, p.nombre AS puesto_nombre, p.numero_puesto, s.nombre AS sede_nombre, sa.nombre AS salon_nombre
        FROM evaluacion_rula er
        LEFT JOIN puestos p ON er.puesto_id=p.id
        LEFT JOIN sedes s ON er.sede_id=s.id
        LEFT JOIN salones sa ON er.salon_id=sa.id
        WHERE er.empresa_id=%s
        ORDER BY er.fecha_evaluacion DESC
    """, (empresa_id,))
    verde = amarillo = rojo = 0
    suma = 0
    lista = []
    for e in evals:
        if e["nivel"] == "Verde":
            verde += 1
        elif e["nivel"] == "Amarillo":
            amarillo += 1
        else:
            rojo += 1
        suma += e["puntaje_final"] or 0
        lista.append({
            "id": e["id"],
            "puesto": ((e["numero_puesto"] or "") + " " + (e["puesto_nombre"] or "")).strip() or "—",
            "sede": e["sede_nombre"] or "—",
            "salon": e["salon_nombre"] or "—",
            "lado": e["lado"],
            "postura": e["postura"] or "—",
            "visitante": e["visitante"],
            "puntaje_final": e["puntaje_final"],
            "nivel": e["nivel"],
            "accion": e["accion_sugerida"] or "",
            "sugerencias": e["sugerencias"] or "",
            "fecha": str(e["fecha_evaluacion"])[:16] if e["fecha_evaluacion"] else "",
        })
    n = len(lista)
    return jsonify({
        "ok": True,
        "empresa": {
            "id": emp["id"],
            "nombre": emp["nombre"],
            "nit": emp.get("nit") or "",
            "ciudad": emp.get("ciudad") or "",
            "sector": emp.get("sector") or "",
        },
        "totales": {
            "sedes": sedes["n"] if sedes else 0,
            "salones": salones["n"] if salones else 0,
            "puestos": puestos["n"] if puestos else 0,
            "evaluaciones": n,
            "verde": verde,
            "amarillo": amarillo,
            "rojo": rojo,
            "promedio": round(suma / n, 2) if n else 0,
        },
        "evaluaciones": lista,
    })


@app.route("/informe/<int:empresa_id>/pdf")
@login_required
@perm_required("inf_dl")
def informe_pdf(empresa_id):
    if not in_scope(empresa_id):
        return deny_scope()
    if not HAS_REPORTLAB:
        return "Instale reportlab: pip install reportlab", 500
    emp = query("SELECT * FROM empresas WHERE id=%s", (empresa_id,), one=True)
    if not emp:
        return "Empresa no encontrada", 404
    evals = query("""
        SELECT er.*, p.nombre AS puesto_nombre, p.numero_puesto, s.nombre AS sede_nombre, sa.nombre AS salon_nombre
        FROM evaluacion_rula er
        LEFT JOIN puestos p ON er.puesto_id=p.id
        LEFT JOIN sedes s ON er.sede_id=s.id
        LEFT JOIN salones sa ON er.salon_id=sa.id
        WHERE er.empresa_id=%s
        ORDER BY er.fecha_evaluacion DESC
    """, (empresa_id,))
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2*cm, rightMargin=2*cm, topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="Titulo", fontSize=16, alignment=TA_CENTER, spaceAfter=8, textColor=colors.HexColor("#3d2a85"), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Sub", fontSize=11, alignment=TA_CENTER, spaceAfter=12, textColor=colors.HexColor("#4b5563")))
    styles.add(ParagraphStyle(name="Sec", fontSize=12, spaceBefore=12, spaceAfter=6, textColor=colors.HexColor("#3d2a85"), fontName="Helvetica-Bold"))
    styles.add(ParagraphStyle(name="Body", fontSize=10, alignment=TA_JUSTIFY, spaceAfter=4, leading=13))
    styles.add(ParagraphStyle(name="Small", fontSize=9, textColor=colors.HexColor("#6b7280")))
    story = []
    story.append(Paragraph("INFORME DE EVALUACIÓN ERGONÓMICA", styles["Titulo"]))
    story.append(Paragraph("Método aplicado: RULA (Rapid Upper Limb Assessment)", styles["Sub"]))
    story.append(Paragraph("ERGOPLUS · Ergonomía y métodos", styles["Sub"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#6a4bc0"), spaceAfter=12))
    story.append(Paragraph("1. Datos de la empresa", styles["Sec"]))
    story.append(Paragraph(f"<b>Empresa:</b> {emp['nombre']}", styles["Body"]))
    story.append(Paragraph(f"<b>NIT:</b> {emp.get('nit') or '—'} &nbsp;&nbsp; <b>Ciudad:</b> {emp.get('ciudad') or '—'}", styles["Body"]))
    story.append(Paragraph(f"<b>Sector:</b> {emp.get('sector') or '—'} &nbsp;&nbsp; <b>Contacto:</b> {emp.get('contacto') or '—'}", styles["Body"]))
    verde = sum(1 for e in evals if e["nivel"] == "Verde")
    amarillo = sum(1 for e in evals if e["nivel"] == "Amarillo")
    rojo = sum(1 for e in evals if e["nivel"] == "Rojo")
    n = len(evals)
    prom = round(sum(e["puntaje_final"] or 0 for e in evals) / n, 2) if n else 0
    story.append(Paragraph("2. Resumen de resultados", styles["Sec"]))
    story.append(Paragraph(
        f"Total de evaluaciones: <b>{n}</b>. Puntaje promedio: <b>{prom}</b>. "
        f"Verde (aceptable): <b>{verde}</b> · Amarillo (revisar): <b>{amarillo}</b> · Rojo (intervenir): <b>{rojo}</b>.",
        styles["Body"]
    ))
    story.append(Paragraph(
        "El método RULA, aplicado en esta empresa, evalúa la carga postural de miembros superiores, cuello, tronco y piernas. "
        "Puntaje final de 1 a 7 según tablas A, B y C (McAtamney y Corlett, 1993; Ergonautas UPV).",
        styles["Body"]
    ))
    story.append(Paragraph("3. Detalle por puesto evaluado", styles["Sec"]))
    if not evals:
        story.append(Paragraph("No hay evaluaciones registradas para esta empresa.", styles["Body"]))
    else:
        header = ["#", "Puesto", "Lado", "Final", "Nivel", "Visitante", "Fecha"]
        data = [header]
        for i, e in enumerate(evals, 1):
            puesto = ((e["numero_puesto"] or "") + " " + (e["puesto_nombre"] or "")).strip() or "—"
            data.append([
                str(i),
                puesto[:28],
                e["lado"][:3],
                str(e["puntaje_final"]),
                e["nivel"],
                (e["visitante"] or "—")[:18],
                str(e["fecha_evaluacion"])[:10] if e["fecha_evaluacion"] else "—",
            ])
        table = Table(data, colWidths=[1*cm, 4.2*cm, 1.5*cm, 1.3*cm, 2*cm, 3.2*cm, 2.2*cm])
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6a4bc0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (1, 1), (1, -1), "LEFT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d1d5db")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f0fc")]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(table)
        story.append(Spacer(1, 10))
        for e in evals:
            if e.get("sugerencias") or e.get("accion_sugerida"):
                puesto = ((e["numero_puesto"] or "") + " " + (e["puesto_nombre"] or "")).strip() or "puesto"
                story.append(Paragraph(
                    f"<b>{puesto}</b> (puntaje {e['puntaje_final']} · {e['nivel']}): "
                    f"{e.get('accion_sugerida') or ''} {e.get('sugerencias') or ''}",
                    styles["Body"]
                ))
    story.append(Paragraph("4. Criterios de actuación", styles["Sec"]))
    story.append(Paragraph("• <b>Verde (1–2):</b> postura aceptable; no requiere cambios.", styles["Body"]))
    story.append(Paragraph("• <b>Amarillo (3–4):</b> conviene profundizar el estudio; pueden requerirse cambios.", styles["Body"]))
    story.append(Paragraph("• <b>Rojo (5–7):</b> rediseño de la tarea o intervención; 7 implica urgencia.", styles["Body"]))
    story.append(Spacer(1, 16))
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey, spaceAfter=8))
    story.append(Paragraph(
        f"Documento generado por ERGOPLUS. Evaluador: {current_user.nombre_completo}. "
        f"Este informe no sustituye un diagnóstico médico. Fuente metodológica: Ergonautas (UPV).",
        styles["Small"]
    ))
    doc.build(story)
    buf.seek(0)
    from flask import send_file
    log_event("descargar", "Informes", registro=emp["nombre"], detalle=f"Descargó el informe PDF de {emp['nombre']} ({n} evaluaciones)")
    fname = f"Informe_ergonomico_{emp['nombre'][:40].replace(' ', '_')}.pdf"
    return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name=fname)


def ensure_owner():
    """Crea la cuenta Owner si no existe. No guarda ninguna contraseña fija en el código."""
    if query("SELECT id FROM usuarios WHERE role='owner' LIMIT 1", one=True):
        return
    pwd = Config.OWNER_PASSWORD
    generada = False
    if not pwd:
        pwd = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(14))
        generada = True
    execute(
        "INSERT INTO usuarios (username, password_hash, nombre_completo, email, role, debe_cambiar_clave) VALUES (%s,%s,%s,%s,%s,1)",
        (Config.OWNER_USERNAME, generate_password_hash(pwd), "Owner", Config.OWNER_EMAIL or None, "owner"),
    )
    print("=" * 60)
    print(f">>> Cuenta Owner creada. Usuario: {Config.OWNER_USERNAME}")
    if generada:
        print(f">>> Contraseña inicial (anótala, no se vuelve a mostrar): {pwd}")
    else:
        print(">>> Contraseña: la definida en OWNER_PASSWORD (.env). Bórrala del .env después.")
    print("=" * 60)


def boot():
    """Primer arranque: crea la cuenta Owner si no existe (contraseña de OWNER_PASSWORD o una aleatoria que se imprime una vez)."""
    import os
    if os.getenv("SKIP_BOOT"):
        return
    try:
        ensure_owner()
    except Exception as e:
        print("ADVERTENCIA: no se pudo conectar a MySQL o crear el Owner. Revisa .env e importa sql/schema.sql.")
        print(e)
    if Config.SECRET_KEY.startswith("pmv-ergonomia-dev-key"):
        print("ADVERTENCIA: define SECRET_KEY en .env antes de publicar la aplicación.")

boot()

if __name__ == "__main__":
    import os
    app.run(debug=os.getenv("FLASK_DEBUG") == "1", host=os.getenv("HOST", "127.0.0.1"), port=int(os.getenv("PORT", "5000")))
