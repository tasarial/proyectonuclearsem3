"""Informe descriptivo PDF de una evaluación ergonómica (evaluador, trabajador, condiciones, resultado, fotos con ángulos, recomendaciones)."""
import io
import json
import os
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable, Image as RLImage, KeepTogether)
from reportlab.graphics.shapes import Drawing, Circle, Rect, String

import ia as asistente

VIOLETA = colors.HexColor("#4b3a9e")
LILA = colors.HexColor("#ece7fb")
SEMAFORO = {"Verde": "#2e9d5b", "Amarillo": "#e3a21a", "Rojo": "#d64533"}
ETIQ = {"Verde": "Verde · Aceptable", "Amarillo": "Amarillo · Requiere revisión y mejoras", "Rojo": "Rojo · Intervención prioritaria"}
PUNTOS_ES = {"oreja": "oreja", "hombro": "hombro", "codo": "codo", "muneca": "muñeca", "mano": "mano", "cadera": "cadera", "rodilla": "rodilla", "tobillo": "tobillo"}

def _e(x):
    return escape(str(x)) if x not in (None, "") else "—"

def _fecha(x):
    return str(x)[:16] if x else "—"

def semaforo(nivel, puntaje):
    d = Drawing(112, 52)
    d.add(Rect(0, 0, 112, 52, rx=10, ry=10, fillColor=colors.HexColor("#2b2540"), strokeColor=None))
    for i, n in enumerate(("Verde", "Amarillo", "Rojo")):
        on = n == nivel
        d.add(Circle(20 + i * 36, 26, 14, fillColor=colors.HexColor(SEMAFORO[n]) if on else colors.HexColor("#4a4366"),
                     strokeColor=colors.white if on else None, strokeWidth=1.6))
    return d

def foto_anotada(ruta, puntos, angulos, mira_a):
    """Dibuja sobre la foto los puntos y segmentos marcados y devuelve (bytes jpeg, ancho, alto)."""
    from PIL import Image, ImageDraw, ImageFont
    im = Image.open(ruta).convert("RGB")
    im.thumbnail((900, 900))
    w, h = im.size
    dr = ImageDraw.Draw(im)
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", max(14, w // 40))
    except OSError:
        font = ImageFont.load_default()
    px = {k: (v[0] * w, v[1] * h) for k, v in (puntos or {}).items()}
    # nombres antiguos (un solo brazo) se tratan como derecho
    for k in ("hombro", "codo", "muneca", "mano"):
        if k in px and k + "_d" not in px:
            px[k + "_d"] = px.pop(k)
    L = "i" if (angulos or {}).get("lado_i") else "d"
    O = "d" if L == "i" else "i"
    r = max(5, w // 110)
    ancho = max(3, w // 200)
    def cadena(keys, col, ancho_=None):
        pts = [px[k] for k in keys if k in px]
        if len(pts) > 1:
            dr.line(pts, fill=col, width=ancho_ or ancho)
    cadena(("oreja", "hombro_" + L, "cadera"), "#ffd23f")
    cadena(("hombro_d", "codo_d", "muneca_d", "mano_d"), "#3ddc97")
    cadena(("hombro_i", "codo_i", "muneca_i", "mano_i"), "#ff9f43")
    cadena(("cadera", "pie_" + L), "#cccccc", max(2, ancho - 1))
    cadena(("pie_d", "pie_i"), "#999999", 2)
    for k, (x, y) in px.items():
        col = "#3ddc97" if k.endswith("_d") else "#ff9f43" if k.endswith("_i") else "#6a4bc0"
        dr.ellipse([x - r, y - r, x + r, y + r], fill=col, outline="white", width=2)
    lugar = {"brazo": "hombro_" + L, "antebrazo": "codo_" + L, "muneca": "muneca_" + L, "cuello": "oreja", "tronco": "cadera"}
    for k, v in (angulos or {}).items():
        base = px.get(lugar.get(k))
        if base is None or v is None:
            continue
        txt = f"{k[:3].upper()} {float(v):.0f}°"
        x, y = base[0] + r * 2, base[1] - r * 3
        bb = dr.textbbox((x, y), txt, font=font)
        dr.rectangle([bb[0] - 3, bb[1] - 2, bb[2] + 3, bb[3] + 2], fill="#2b2540")
        dr.text((x, y), txt, fill="white", font=font)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=82)
    out.seek(0)
    return out, w, h

def generar(r, upload_dir, consent_version):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.6 * cm, bottomMargin=1.6 * cm,
                            title=f"Informe de evaluación ergonómica #{r['id']}", author="ERGOPLUS")
    ss = getSampleStyleSheet()
    ss.add(ParagraphStyle("T", fontName="Helvetica-Bold", fontSize=18, leading=24, textColor=VIOLETA, alignment=TA_CENTER, spaceAfter=4))
    ss.add(ParagraphStyle("S", fontSize=10, alignment=TA_CENTER, textColor=colors.HexColor("#6b6486"), spaceAfter=8))
    ss.add(ParagraphStyle("H", fontName="Helvetica-Bold", fontSize=12, textColor=VIOLETA, spaceBefore=12, spaceAfter=5, keepWithNext=1))
    ss.add(ParagraphStyle("B", fontSize=9.6, leading=13, alignment=TA_JUSTIFY, spaceAfter=3))
    ss.add(ParagraphStyle("Sm", fontSize=8.2, leading=11, textColor=colors.HexColor("#6b6486")))
    ss.add(ParagraphStyle("C", fontSize=9, leading=12))
    st = []
    st.append(Paragraph("INFORME DE EVALUACIÓN ERGONÓMICA", ss["T"]))
    st.append(Paragraph("Método aplicado: RULA · ERGOPLUS, ergonomía y métodos", ss["S"]))
    st.append(HRFlowable(width="100%", thickness=1.4, color=VIOLETA, spaceAfter=6))
    st.append(Paragraph(f"Informe N.º <b>{r['id']}</b> · Emitido el {_fecha(r.get('fecha_evaluacion'))}", ss["Sm"]))

    def tabla(filas, ancho=(4.2 * cm, 12.8 * cm)):
        t = Table([[Paragraph(f"<b>{k}</b>", ss["C"]), Paragraph(_e(v), ss["C"])] for k, v in filas], colWidths=ancho)
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), LILA), ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#d8d0f0")),
                               ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))
        return t

    # 1 empresa
    st.append(Paragraph("1. Empresa y contrato", ss["H"]))
    ct = r.get("contrato")
    filas = [("Empresa", r["empresa"]), ("NIT / documento", r.get("nit")), ("Tipo de persona", r.get("tipo_persona")),
             ("Puesto evaluado", ((r.get("numero_puesto") or "") + " " + (r.get("puesto") or "")).strip() or None)]
    if ct:
        filas.append(("Contrato vigente", f"{ct['numero']} · {ct['tipo']} ({ct['fecha_inicio']} a {ct['fecha_fin']})"))
    st.append(tabla(filas))

    # 2 evaluador
    st.append(Paragraph("2. Evaluador", ss["H"]))
    st.append(tabla([("Nombre", r.get("visitante")), ("Cuenta en ERGOPLUS", r.get("ev_nombre")), ("Correo", r.get("ev_email")),
                     ("Fecha de la evaluación", _fecha(r.get("fecha_evaluacion"))),
                     ("Apoyo de IA", "Sí: se usaron sugerencias automáticas, revisadas y corregidas por el evaluador" if r.get("ia_usada") else "No")]))

    # 3 trabajador
    t = r.get("trab")
    st.append(Paragraph("3. Trabajador evaluado", ss["H"]))
    if t:
        ed = asistente.edad(t.get("fecha_nacimiento"))
        st.append(tabla([("Nombre", t["nombre"]), ("Documento", t.get("documento")), ("Cargo", t.get("cargo")), ("Género", t.get("genero")),
                         ("Edad", f"{ed} años" if ed is not None else None), ("Tiempo en la empresa", asistente.texto_antiguedad(t.get("antiguedad_meses"))),
                         ("Jornada laboral", f"{float(t['horas_jornada']):g} h/día" if t.get("horas_jornada") is not None else None),
                         ("Lateralidad / estatura", f"{t.get('lateralidad') or '—'} · {str(t.get('estatura_cm')) + ' cm' if t.get('estatura_cm') else '—'}"),
                         ("Antecedentes / molestias", t.get("antecedentes")),
                         ("Consentimiento informado", f"Firmado por «{t.get('consentimiento_nombre')}» el {_fecha(t.get('consentimiento_fecha'))} (texto {t.get('consentimiento_version') or consent_version})")]))
    else:
        st.append(Paragraph("Evaluación realizada sin vincular a un trabajador específico.", ss["B"]))

    # 4 condiciones
    c = r.get("cond") or {}
    st.append(Paragraph("4. Condiciones del puesto y del entorno", ss["H"]))
    if c:
        et = {"tipo_tarea": "Tipo de tarea", "silla_regulable": "Silla regulable", "silla_respaldo_lumbar": "Respaldo lumbar", "apoyabrazos": "Apoyabrazos",
              "apoyapies": "Apoyapiés", "pantalla_posicion": "Posición de la pantalla", "pantalla_distancia_cm": "Distancia a la pantalla (cm)",
              "horas_pantalla": "Horas frente a pantalla", "teclado_mouse": "Teclado y mouse", "iluminacion_lux": "Iluminación (lux)", "ruido_db": "Ruido (dB)",
              "temperatura_c": "Temperatura (°C)", "ventilacion": "Ventilación", "espacio": "Espacio", "pausas_activas": "Pausas activas",
              "peso_tipico_kg": "Peso típico manipulado (kg)", "frecuencia_manipulacion": "Frecuencia de manipulación", "notas": "Notas"}
        filas = []
        for k, lab in et.items():
            if k in c:
                v = c[k]
                filas.append((lab, f"{v:g}" if isinstance(v, float) else v))
        st.append(tabla(filas))
    else:
        st.append(Paragraph("No se registraron condiciones del puesto.", ss["B"]))

    # 5 resultado
    st.append(Paragraph("5. Resultado de la evaluación", ss["H"]))
    nivel = r["nivel"]
    cab = Table([[semaforo(nivel, r["puntaje_final"]),
                  Paragraph(f"<font size='16'><b>Puntaje final: {r['puntaje_final']} de 7</b></font><br/><font color='{SEMAFORO[nivel]}'><b>{ETIQ.get(nivel, nivel)}</b></font><br/>{_e(r.get('accion_sugerida'))}", ss["B"])]],
                colWidths=[4.6 * cm, 12.4 * cm])
    cab.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    st.append(cab)
    st.append(Spacer(1, 4))
    md = [["Segmento", "Medición", "Puntaje"],
          ["Brazo", f"{r.get('brazo_angulo')}°", r.get("puntos_brazo")], ["Antebrazo", f"{r.get('antebrazo_angulo')}°", r.get("puntos_antebrazo")],
          ["Muñeca", f"{r.get('muneca_angulo')}°", r.get("puntos_muneca")], ["Cuello", f"{r.get('cuello_angulo')}°", r.get("puntos_cuello")],
          ["Tronco", f"{r.get('tronco_angulo')}°", r.get("puntos_tronco")], ["Piernas", "", r.get("puntos_piernas")],
          ["Grupo A / Grupo B", f"{r.get('puntos_a')} / {r.get('puntos_b')}", ""], ["Actividad / fuerza", f"+{r.get('puntos_actividad')} / +{r.get('puntos_fuerza')}", ""]]
    tm = Table([[str(x) if x is not None else "" for x in row] for row in md], colWidths=[6 * cm, 6 * cm, 5 * cm])
    tm.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), VIOLETA), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
                            ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#d8d0f0")), ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold")]))
    st.append(tm)

    # 6 compatibilidad
    cp = r.get("compat")
    if cp:
        st.append(Paragraph("6. Compatibilidad puesto–trabajador", ss["H"]))
        st.append(Paragraph(f"Resultado global: <font color='{SEMAFORO[cp['global']]}'><b>{cp['global']}</b></font>. "
                            "Es un apoyo para priorizar seguimiento; no constituye un concepto de aptitud ni de exclusión laboral.", ss["B"]))
        fl = [["Factor", "Estado", "Detalle"]] + [[f["factor"], f["estado"], Paragraph(escape(f["detalle"]), ss["C"])] for f in cp["factores"]]
        tc = Table(fl, colWidths=[4.2 * cm, 2.2 * cm, 10.6 * cm])
        sty = [("BACKGROUND", (0, 0), (-1, 0), VIOLETA), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 9),
               ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#d8d0f0")), ("VALIGN", (0, 0), (-1, -1), "TOP")]
        for i, f in enumerate(cp["factores"], 1):
            sty.append(("TEXTCOLOR", (1, i), (1, i), colors.HexColor(SEMAFORO[f["estado"]])))
            sty.append(("FONTNAME", (1, i), (1, i), "Helvetica-Bold"))
        tc.setStyle(TableStyle(sty))
        st.append(tc)

    # 7 fotos
    fotos = r.get("fotos") or []
    if fotos:
        st.append(Paragraph("7. Registro fotográfico y ángulos", ss["H"]))
        for f in fotos:
            ruta = os.path.join(upload_dir, os.path.basename(f["archivo"]))
            if not os.path.exists(ruta):
                continue
            try:
                pts = json.loads(f["puntos"]) if f["puntos"] else {}
                ang = json.loads(f["angulos"]) if f["angulos"] else {}
                img, w, h = foto_anotada(ruta, pts, ang, f["mira_a"])
            except Exception:
                continue
            ancho = 8.5 * cm
            alto = ancho * h / w
            if alto > 9 * cm:
                alto = 9 * cm; ancho = alto * w / h
            texto = "<br/>".join([f"<b>Vista {escape(f['vista'].lower())}</b> · mira a la {escape((f['mira_a'] or '').lower())}"] +
                                 [f"{k.capitalize()}: {float(v):.0f}°" for k, v in ang.items() if k != "lado_i"] + [f"Brazo medido: {'izquierdo' if ang.get('lado_i') else 'derecho'}"] +
                                 ([f"Origen de los puntos: {'sugeridos por IA y revisados' if f['origen'] == 'ia' else 'marcados manualmente'}"]) +
                                 ([escape(f["notas"])] if f.get("notas") else []))
            row = Table([[RLImage(img, width=ancho, height=alto), Paragraph(texto, ss["C"])]], colWidths=[ancho + .4 * cm, 17 * cm - ancho - .4 * cm])
            row.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
            st.append(KeepTogether([row, Spacer(1, 6)]))

    # 8 recomendaciones
    st.append(Paragraph("8. Recomendaciones", ss["H"]))
    recs = (r.get("recomendaciones") or "").strip()
    if recs:
        for linea in recs.splitlines():
            if linea.strip():
                st.append(Paragraph("• " + escape(linea.strip()), ss["B"]))
    else:
        st.append(Paragraph("Sin recomendaciones registradas.", ss["B"]))
    if r.get("sugerencias"):
        st.append(Paragraph("<b>Observaciones del evaluador:</b> " + escape(r["sugerencias"]), ss["B"]))

    st.append(Spacer(1, 14))
    st.append(HRFlowable(width="100%", thickness=.6, color=colors.HexColor("#cfc7e8")))
    st.append(Paragraph("Este informe se basa en el método RULA (McAtamney y Corlett, 1993) y en la información registrada al momento de la visita. "
                        "Las sugerencias automáticas son un apoyo y fueron revisadas por el evaluador. Contiene datos personales sujetos a la Ley 1581 de 2012: "
                        "úselo solo para los fines autorizados por el trabajador.", ss["Sm"]))
    st.append(Spacer(1, 22))
    firma = Table([["_______________________________", "_______________________________"],
                   [Paragraph(f"{_e(r.get('visitante'))}<br/>Evaluador", ss["C"]), Paragraph("Trabajador / representante de la empresa", ss["C"])]],
                  colWidths=[8.5 * cm, 8.5 * cm])
    st.append(firma)

    def pie(canvas, d):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#6b6486"))
        canvas.drawString(2 * cm, 1 * cm, f"ERGOPLUS · Informe #{r['id']} · {r['empresa']}")
        canvas.drawRightString(letter[0] - 2 * cm, 1 * cm, f"Página {d.page}")
        canvas.restoreState()
    doc.build(st, onFirstPage=pie, onLaterPages=pie)
    return buf.getvalue()
