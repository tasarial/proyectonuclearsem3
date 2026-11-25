"""Asistente de evaluación: sugerencias, recomendaciones, compatibilidad puesto-persona y visión por IA (opcional).

- Todo lo "automático" (presets, recomendaciones, compatibilidad) es determinista y se ejecuta en el servidor, sin internet.
- El análisis de fotos por IA solo funciona si defines ANTHROPIC_API_KEY. El ingeniero SIEMPRE puede corregir lo sugerido.
"""
import base64
import io
import json
import re
import urllib.request
import urllib.error
from datetime import date

from config import Config

# ---------------------------------------------------------------- condiciones del puesto
TIPOS_TAREA = ["Sedente de oficina", "De pie", "Manipulación de cargas", "Mixta"]
SI_NO = ["Sí", "No"]
CONDICIONES_CAMPOS = {
    "tipo_tarea": TIPOS_TAREA,
    "silla_regulable": SI_NO, "silla_respaldo_lumbar": SI_NO, "apoyabrazos": SI_NO, "apoyapies": SI_NO,
    "pantalla_posicion": ["A la altura de los ojos", "Por debajo", "Por encima", "No usa pantalla"],
    "teclado_mouse": ["Adecuado", "Inadecuado", "No aplica"],
    "ventilacion": ["Adecuada", "Insuficiente"],
    "espacio": ["Suficiente", "Reducido"],
    "pausas_activas": SI_NO,
    "frecuencia_manipulacion": ["Nunca", "Ocasional", "Frecuente"],
}
CONDICIONES_NUM = {  # clave: (mínimo, máximo)
    "pantalla_distancia_cm": (0, 300), "horas_pantalla": (0, 24), "iluminacion_lux": (0, 100000),
    "ruido_db": (0, 140), "temperatura_c": (-10, 60), "peso_tipico_kg": (0, 500),
}

def limpiar_condiciones(d):
    """Valida y devuelve solo claves conocidas (o error)."""
    out = {}
    for k, lista in CONDICIONES_CAMPOS.items():
        v = (d or {}).get(k)
        if v in (None, ""):
            continue
        if v not in lista:
            return None, f"Valor no válido en «{k.replace('_', ' ')}»."
        out[k] = v
    for k, (mn, mx) in CONDICIONES_NUM.items():
        v = (d or {}).get(k)
        if v in (None, ""):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None, f"«{k.replace('_', ' ')}» debe ser un número."
        if not mn <= f <= mx:
            return None, f"«{k.replace('_', ' ')}» debe estar entre {mn} y {mx}."
        out[k] = f
    nota = ((d or {}).get("notas") or "").strip()
    if len(nota) > 500:
        return None, "Las notas admiten máximo 500 caracteres."
    if nota:
        out["notas"] = nota
    return out, None

# ---------------------------------------------------------------- perfil del trabajador
def edad(fecha_nac):
    if not fecha_nac:
        return None
    if isinstance(fecha_nac, str):
        try:
            y, m, d = [int(x) for x in fecha_nac[:10].split("-")]
            fecha_nac = date(y, m, d)
        except ValueError:
            return None
    hoy = date.today()
    return hoy.year - fecha_nac.year - ((hoy.month, hoy.day) < (fecha_nac.month, fecha_nac.day))

def texto_antiguedad(meses):
    if meses in (None, ""):
        return "—"
    meses = int(meses)
    a, m = divmod(meses, 12)
    return (f"{a} año(s) " if a else "") + (f"{m} mes(es)" if m or not a else "")

# Referencia colombiana para levantamiento manual (Res. 2400 de 1979): verificar vigencia con tu asesor SST.
LIMITE_CARGA_KG = {"Masculino": 25.0, "Femenino": 12.5}

def compatibilidad(trab, cond, carga_kg=None, nivel_rula=None):
    """Ajuste puesto–persona: lista de factores con semáforo y un resultado global.
    Es un apoyo para priorizar seguimiento, NO un criterio de aptitud ni de exclusión laboral."""
    f = []
    def add(nombre, estado, detalle):
        f.append({"factor": nombre, "estado": estado, "detalle": detalle})  # estado: Verde/Amarillo/Rojo
    cond = cond or {}
    trab = trab or {}
    h = trab.get("horas_jornada")
    if h not in (None, ""):
        h = float(h)
        add("Horas de jornada", "Rojo" if h > 10 else "Amarillo" if h > 8 else "Verde",
            f"{h:g} h/día. " + ("Exposición prolongada: reforzar pausas y rotación." if h > 8 else "Dentro de lo esperado."))
    hp = cond.get("horas_pantalla")
    if hp not in (None, ""):
        hp = float(hp)
        add("Horas frente a pantalla", "Rojo" if hp > 8 else "Amarillo" if hp > 6 else "Verde",
            f"{hp:g} h/día. " + ("Alta exposición visual y postural." if hp > 6 else "Aceptable."))
    m = trab.get("antiguedad_meses")
    if m not in (None, ""):
        m = int(m)
        if m < 6:
            add("Tiempo en la empresa", "Amarillo", "Menos de 6 meses: etapa de adaptación, conviene capacitación en postura y seguimiento.")
        elif m > 120:
            add("Tiempo en la empresa", "Amarillo", "Más de 10 años: exposición acumulada, conviene vigilancia periódica.")
        else:
            add("Tiempo en la empresa", "Verde", texto_antiguedad(m) + ".")
    e = edad(trab.get("fecha_nacimiento"))
    if e is not None:
        add("Edad", "Amarillo" if e >= 50 else "Verde",
            f"{e} años. " + ("No es una limitación; se sugiere vigilancia y pausas más frecuentes." if e >= 50 else "Sin consideraciones especiales."))
    if (trab.get("antecedentes") or "").strip():
        add("Antecedentes / molestias", "Amarillo", "Hay antecedentes registrados: remitir a SST/medicina laboral para seguimiento.")
    g = trab.get("genero")
    if carga_kg not in (None, "") and float(carga_kg) > 0:
        lim = LIMITE_CARGA_KG.get(g, 12.5)
        c = float(carga_kg)
        add("Carga manipulada", "Rojo" if c > lim else "Amarillo" if c > lim * 0.7 else "Verde",
            f"{c:g} kg frente a un límite de referencia de {lim:g} kg (Res. 2400/1979)." +
            (" Supera el límite: usar ayudas mecánicas o dividir la carga." if c > lim else ""))
    est = trab.get("estatura_cm")
    if est not in (None, "") and (cond.get("silla_regulable") == "No"):
        est = int(est)
        if est < 155 or est > 185:
            add("Estatura y mobiliario", "Amarillo", f"{est} cm con silla no regulable: el mobiliario puede no ajustarse a sus medidas.")
    if nivel_rula:
        add("Postura (RULA)", nivel_rula, "Resultado de la evaluación postural.")
    estados = [x["estado"] for x in f]
    if "Rojo" in estados:
        glob = "Rojo"
    elif estados.count("Amarillo") >= 2 or ("Amarillo" in estados and nivel_rula == "Amarillo"):
        glob = "Amarillo"
    elif "Amarillo" in estados:
        glob = "Amarillo"
    else:
        glob = "Verde"
    return {"global": glob, "factores": f}

# ---------------------------------------------------------------- sugerencias (posturas tipo + pasos)
PRESETS = {
    "Sedente de oficina": dict(brazo_angulo=20, antebrazo_angulo=90, muneca_angulo=10, cuello_angulo=15, tronco_angulo=10,
                               sentado_bien=1, actividad_repetitiva=1),
    "De pie": dict(brazo_angulo=30, antebrazo_angulo=80, muneca_angulo=5, cuello_angulo=15, tronco_angulo=15,
                   actividad_estatica=1),
    "Manipulación de cargas": dict(brazo_angulo=60, antebrazo_angulo=100, muneca_angulo=10, cuello_angulo=20, tronco_angulo=30),
    "Mixta": dict(brazo_angulo=30, antebrazo_angulo=90, muneca_angulo=10, cuello_angulo=15, tronco_angulo=15),
}

def sugerir(cond, trab=None):
    """Valores iniciales para la medición + pasos recomendados. Todo editable por el evaluador."""
    cond = cond or {}
    tarea = cond.get("tipo_tarea") or "Sedente de oficina"
    v = dict(PRESETS.get(tarea, PRESETS["Mixta"]))
    razones = [f"Postura tipo para «{tarea}» (valores de partida, no medidos)."]
    pos = cond.get("pantalla_posicion")
    if pos == "Por debajo":
        v["cuello_angulo"] = 25; razones.append("Pantalla por debajo de los ojos → cuello más flexionado (25°).")
    elif pos == "Por encima":
        v["cuello_extension"] = 1; v["cuello_angulo"] = 15; razones.append("Pantalla por encima de los ojos → extensión de cuello.")
    if cond.get("silla_respaldo_lumbar") == "No":
        v["sentado_bien"] = 0; razones.append("Sin respaldo lumbar → tronco sin buen apoyo.")
    if cond.get("apoyapies") == "No" and tarea == "Sedente de oficina":
        razones.append("Sin apoyapiés: verifica si los pies llegan al suelo.")
    if cond.get("teclado_mouse") == "Inadecuado":
        v["muneca_angulo"] = 20; v["muneca_desviacion"] = 1; razones.append("Teclado/mouse inadecuado → muñeca desviada.")
    if cond.get("apoyabrazos") == "Sí":
        v["brazo_apoyo"] = 1; razones.append("Hay apoyabrazos → brazo con apoyo (-1).")
    peso = cond.get("peso_typico_kg") or cond.get("peso_tipico_kg")
    if peso:
        v["carga_kg"] = float(peso); razones.append(f"Carga típica registrada: {float(peso):g} kg.")
    if cond.get("frecuencia_manipulacion") == "Frecuente":
        v["carga_estatica_rep"] = 1
    if (cond.get("horas_pantalla") or 0) and float(cond["horas_pantalla"]) > 4:
        v["actividad_repetitiva"] = 1
    pasos = [
        "Confirmar el consentimiento informado del trabajador.",
        "Registrar condiciones del puesto (silla, pantalla, iluminación, ruido, temperatura).",
        "Tomar fotos: vista lateral con el trabajador en su postura habitual (idealmente 2 o 3 momentos de la jornada).",
        "Marcar los puntos en la foto (o usar la sugerencia por IA) y revisar los ángulos.",
    ]
    if tarea in ("Sedente de oficina", "Mixta") or pos not in (None, "No usa pantalla"):
        pasos.append("Medir distancia y altura de la pantalla; observar muñeca y mouse.")
    if tarea in ("Manipulación de cargas", "Mixta") or cond.get("frecuencia_manipulacion") in ("Ocasional", "Frecuente"):
        pasos.append("Registrar peso, frecuencia y distancia de la carga manipulada.")
    pasos += ["Aplicar la encuesta de molestias (Nórdico) al trabajador.", "Revisar el resultado, ajustar las recomendaciones y generar el informe."]
    return {"valores": v, "razones": razones, "pasos": pasos, "fuente": "asistente"}

# ---------------------------------------------------------------- recomendaciones
def recomendaciones(res, cond=None, compat=None):
    """Lista de {prioridad, texto} a partir de puntajes parciales y condiciones."""
    cond = cond or {}
    r = []
    def add(p, t):
        r.append({"prioridad": p, "texto": t})
    if res.get("brazo", 1) >= 3:
        add("Alta", "Reducir la elevación del brazo: acercar los elementos de trabajo al cuerpo y ajustar la altura de la superficie.")
    elif res.get("brazo", 1) == 2:
        add("Media", "Mantener los codos cerca del cuerpo y apoyar el antebrazo cuando sea posible.")
    if res.get("antebrazo", 1) >= 2:
        add("Media", "Ajustar la altura de silla/superficie para que el codo quede entre 60° y 100° y evitar cruzar la línea media.")
    if res.get("muneca", 1) >= 3:
        add("Alta", "Corregir la posición de la muñeca: teclado plano, apoyamuñecas y mouse acorde a la mano; evitar desviaciones.")
    elif res.get("muneca", 1) == 2:
        add("Media", "Mantener la muñeca neutra al teclear y usar el mouse.")
    if res.get("cuello", 1) >= 3:
        add("Alta", "Subir la pantalla/documentos hasta que el borde superior quede a la altura de los ojos y evitar torsiones de cuello.")
    elif res.get("cuello", 1) == 2:
        add("Media", "Revisar la altura de la pantalla para mantener el cuello casi vertical.")
    if res.get("tronco", 1) >= 3:
        add("Alta", "Mejorar el apoyo del tronco: respaldo con soporte lumbar y acercar el trabajo para evitar inclinarse.")
    elif res.get("tronco", 1) == 2:
        add("Media", "Sentarse con la espalda apoyada en el respaldo.")
    if res.get("piernas", 1) >= 2:
        add("Media", "Garantizar apoyo estable de ambos pies (apoyapiés si la altura de la silla lo exige).")
    if res.get("puntos_actividad", 0) >= 1:
        add("Media", "Establecer pausas activas y alternancia de tareas (p. ej. 5 min cada hora) para reducir carga estática y repetitiva.")
    if res.get("puntos_fuerza", 0) >= 2:
        add("Alta", "Reducir el peso manipulado, dividir la carga o usar ayudas mecánicas.")
    # condiciones
    if cond.get("silla_regulable") == "No":
        add("Media", "Sustituir o ajustar la silla por una regulable en altura.")
    if cond.get("silla_respaldo_lumbar") == "No":
        add("Media", "Dotar la silla de soporte lumbar o cojín lumbar.")
    lux = cond.get("iluminacion_lux")
    if lux not in (None, "") and float(lux) < 300:
        add("Media", f"Iluminación baja ({float(lux):g} lux): para oficina se suelen recomendar 300–500 lux; mejorar luminarias y evitar reflejos.")
    db = cond.get("ruido_db")
    if db not in (None, "") and float(db) > 65:
        add("Media", f"Ruido elevado ({float(db):g} dB) para trabajo de oficina: evaluar aislamiento o reubicación del puesto.")
    t = cond.get("temperatura_c")
    if t not in (None, "") and not 20 <= float(t) <= 26:
        add("Baja", f"Temperatura de {float(t):g} °C fuera del rango de confort habitual (20–26 °C).")
    if cond.get("ventilacion") == "Insuficiente":
        add("Baja", "Mejorar la ventilación del área.")
    if cond.get("pausas_activas") == "No":
        add("Media", "Implementar un programa de pausas activas en la jornada.")
    for fac in (compat or {}).get("factores", []):
        if fac["estado"] == "Rojo" and fac["factor"] != "Postura (RULA)":
            add("Alta", f"{fac['factor']}: {fac['detalle']}")
    nivel = res.get("nivel")
    plazo = {"Verde": "Mantener las condiciones actuales y reevaluar en 12 meses.",
             "Amarillo": "Implementar las mejoras sugeridas en un plazo aproximado de 3 meses y reevaluar después.",
             "Rojo": "Intervenir con prioridad (idealmente dentro del primer mes) y reevaluar a los 3 meses."}.get(nivel)
    if plazo:
        add("Alta" if nivel == "Rojo" else "Media" if nivel == "Amarillo" else "Baja", plazo + " (plazos sugeridos; ajústalos al criterio profesional).")
    orden = {"Alta": 0, "Media": 1, "Baja": 2}
    r.sort(key=lambda x: orden[x["prioridad"]])
    return r

def recomendaciones_texto(lista):
    return "\n".join(f"[{x['prioridad']}] {x['texto']}" for x in lista)

# ---------------------------------------------------------------- IA de visión (opcional)
def ia_disponible():
    return bool(Config.ANTHROPIC_API_KEY)

def _llamar_api(content, max_tokens=900):
    body = json.dumps({"model": Config.AI_MODEL, "max_tokens": max_tokens,
                       "messages": [{"role": "user", "content": content}]}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body, method="POST", headers={
        "content-type": "application/json", "x-api-key": Config.ANTHROPIC_API_KEY, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            data = json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"La IA respondió con error {e.code}.")
    except Exception as e:
        raise RuntimeError("No se pudo contactar el servicio de IA.")
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")

PUNTOS = ["oreja", "hombro", "codo", "muneca", "mano", "cadera", "rodilla", "tobillo"]

def analizar_foto(img_bytes):
    """Pide a un modelo de visión los puntos corporales de una foto lateral. Devuelve dict con puntos normalizados (0–1)."""
    from PIL import Image
    im = Image.open(io.BytesIO(img_bytes)).convert("RGB")
    im.thumbnail((1280, 1280))
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "Eres un asistente de ergonomía. En esta foto hay una persona en su puesto de trabajo, vista de lado. "
        "Ubica con la mayor precisión posible estos puntos del lado del cuerpo que se ve mejor: "
        + ", ".join(PUNTOS) + ". Usa coordenadas normalizadas [x, y] entre 0 y 1 con origen arriba-izquierda. "
        "Indica también hacia qué lado mira la persona (Derecha o Izquierda de la imagen) y tu confianza (0 a 1). "
        "Si un punto no es visible, usa null. Responde SOLO con JSON: "
        '{"mira_a":"Derecha","confianza":0.0,"puntos":{"oreja":[0,0],"hombro":[0,0],"codo":[0,0],"muneca":[0,0],"mano":[0,0],"cadera":[0,0],"rodilla":null,"tobillo":null},"notas":""}'
    )
    txt = _llamar_api([{"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                       {"type": "text", "text": prompt}])
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise RuntimeError("La IA no devolvió un resultado interpretable.")
    try:
        d = json.loads(m.group(0))
    except ValueError:
        raise RuntimeError("La IA no devolvió un resultado interpretable.")
    pts = {}
    for k in PUNTOS:
        p = (d.get("puntos") or {}).get(k)
        if isinstance(p, (list, tuple)) and len(p) == 2:
            try:
                x, y = float(p[0]), float(p[1])
            except (TypeError, ValueError):
                continue
            if 0 <= x <= 1 and 0 <= y <= 1:
                pts[k] = [round(x, 4), round(y, 4)]
    mira = d.get("mira_a") if d.get("mira_a") in ("Derecha", "Izquierda") else "Derecha"
    return {"puntos": pts, "mira_a": mira, "confianza": d.get("confianza"), "notas": str(d.get("notas") or "")[:250]}

def redactar(contexto):
    """Borrador del análisis descriptivo (sin datos personales). Devuelve texto."""
    prompt = ("Redacta en español, tono profesional y claro, un análisis descriptivo breve (máx. 180 palabras) de esta evaluación "
              "ergonómica RULA para un informe. No inventes datos; usa solo lo que se da. Datos: " + json.dumps(contexto, ensure_ascii=False))
    return _llamar_api([{"type": "text", "text": prompt}], max_tokens=500).strip()
