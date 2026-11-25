"""Catálogos (listas de selección), límites de caracteres y validaciones estándar."""
import re

TIPOS_PERSONA = ["Jurídica", "Natural"]
TIPOS_DOCUMENTO = ["NIT", "CC", "CE", "PASAPORTE"]
DOC_AYUDA = {
    "NIT": "NIT sin puntos: 6 a 10 dígitos, con dígito de verificación opcional (ej. 900123456-7).",
    "CC": "Cédula de ciudadanía: 6 a 10 dígitos, sin puntos.",
    "CE": "Cédula de extranjería: 4 a 10 caracteres alfanuméricos.",
    "PASAPORTE": "Pasaporte: 5 a 12 caracteres alfanuméricos.",
}
DEPARTAMENTOS = [
    "Amazonas", "Antioquia", "Arauca", "Atlántico", "Bogotá D.C.", "Bolívar", "Boyacá", "Caldas", "Caquetá",
    "Casanare", "Cauca", "Cesar", "Chocó", "Córdoba", "Cundinamarca", "Guainía", "Guaviare", "Huila",
    "La Guajira", "Magdalena", "Meta", "Nariño", "Norte de Santander", "Putumayo", "Quindío", "Risaralda",
    "San Andrés y Providencia", "Santander", "Sucre", "Tolima", "Valle del Cauca", "Vaupés", "Vichada",
]
SECTORES = [
    "Manufactura", "Textil y confección", "Alimentos y bebidas", "Metalmecánica", "Construcción", "Comercio",
    "Servicios administrativos", "Salud", "Educación", "Tecnología y software", "Transporte y logística",
    "Agroindustria", "Minería y energía", "Financiero y seguros", "Call center / BPO", "Otro",
]
TAMANOS = ["Micro", "Pequeña", "Mediana", "Grande"]
ARLS = ["Positiva", "ARL Sura", "Colmena Seguros", "Seguros Bolívar", "La Equidad Seguros", "AXA Colpatria", "Otra"]

TIPOS_AREA = ["Administrativa", "Operativa", "Apoyo"]
AREAS_SUGERIDAS = [
    "Gerencia", "Recursos humanos", "Contabilidad", "Finanzas y tesorería", "Compras", "Ventas y comercial",
    "Servicio al cliente", "Sistemas / TI", "Seguridad y salud en el trabajo", "Calidad", "Logística", "Producción",
]

TIPOS_CONTRATO = ["Evaluación ergonómica", "Estudio de métodos", "Capacitación", "Asesoría", "Otro"]
FORMAS_PAGO = ["Contado", "50% anticipo / 50% entrega", "30 días", "60 días", "Por cuotas"]
ESTADOS_CONTRATO = ["Borrador", "Vigente", "Finalizado", "Cancelado"]
MONEDAS = ["COP", "USD"]

# Límite máximo de caracteres por campo (el formulario y el servidor usan los mismos)
LIMITES = {
    "nombre": 120, "direccion": 120, "ciudad": 60, "departamento": 60, "telefono": 20, "email": 100,
    "contacto": 100, "cargo_contacto": 60, "sector": 60, "arl": 60, "nit": 20,
    "descripcion": 250, "numero_puesto": 20, "area": 60, "ubicacion": 80,
    "responsable": 100, "cargo_responsable": 60,
    "objeto": 250, "alcance": 1000, "resumen": 1500, "notas": 500, "titulo": 150, "observaciones": 500,
}

def catalogos_js():
    return {
        "tipos_persona": TIPOS_PERSONA, "tipos_documento": TIPOS_DOCUMENTO, "doc_ayuda": DOC_AYUDA,
        "departamentos": DEPARTAMENTOS, "sectores": SECTORES, "tamanos": TAMANOS, "arls": ARLS,
        "tipos_area": TIPOS_AREA, "areas_sugeridas": AREAS_SUGERIDAS, "limites": LIMITES,
    }

# ---------- Validaciones ----------
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_TEL = re.compile(r"^[\d\s()+\-]{7,20}$")

def digito_verificacion_nit(num):
    """Dígito de verificación DIAN (Colombia)."""
    pesos = [3, 7, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71]
    s = sum(int(d) * pesos[i] for i, d in enumerate(reversed(num)))
    r = s % 11
    return r if r < 2 else 11 - r

def validar_documento(tipo, numero):
    """Devuelve (numero_normalizado, error|None)."""
    n = (numero or "").strip().replace(".", "").replace(" ", "")
    if not n:
        return "", None
    if tipo == "NIT":
        if not re.fullmatch(r"\d{6,10}(-\d)?", n):
            return n, "NIT inválido: usa 6 a 10 dígitos, con dígito de verificación opcional (ej. 900123456-7)."
        if "-" in n:
            base, dv = n.split("-")
            if digito_verificacion_nit(base) != int(dv):
                return n, f"El dígito de verificación no coincide (debería ser {digito_verificacion_nit(base)})."
    elif tipo == "CC":
        if not re.fullmatch(r"\d{6,10}", n):
            return n, "La cédula debe tener entre 6 y 10 dígitos."
    elif tipo == "CE":
        if not re.fullmatch(r"[A-Za-z0-9]{4,10}", n):
            return n, "La cédula de extranjería debe tener entre 4 y 10 caracteres."
    elif tipo == "PASAPORTE":
        if not re.fullmatch(r"[A-Za-z0-9]{5,12}", n):
            return n, "El pasaporte debe tener entre 5 y 12 caracteres."
    else:
        return n, "Tipo de documento no válido."
    return n.upper(), None

def revisar_largos(data, campos):
    """Error si algún campo supera su límite. `campos` = lista de nombres."""
    for c in campos:
        v = data.get(c)
        if isinstance(v, str) and len(v.strip()) > LIMITES.get(c, 255):
            return f"«{c.replace('_', ' ')}» admite máximo {LIMITES.get(c, 255)} caracteres."
    return None

def en_lista(v, lista, etiqueta, obligatorio=False):
    if v in (None, ""):
        return f"Selecciona {etiqueta}." if obligatorio else None
    return None if v in lista else f"Valor no válido para {etiqueta}."

def validar_empresa(d):
    """Devuelve (datos_limpios, error|None)."""
    e = revisar_largos(d, ["nombre", "direccion", "ciudad", "telefono", "email", "contacto", "cargo_contacto", "sector", "arl", "nit"])
    if e: return None, e
    nombre = (d.get("nombre") or "").strip()
    if not nombre:
        return None, "El nombre es obligatorio."
    tp = d.get("tipo_persona") or "Jurídica"
    td = d.get("tipo_documento") or "NIT"
    for v, l, n in ((tp, TIPOS_PERSONA, "el tipo de persona"), (td, TIPOS_DOCUMENTO, "el tipo de documento")):
        e = en_lista(v, l, n, True)
        if e: return None, e
    if tp == "Jurídica" and td != "NIT":
        return None, "Una persona jurídica se identifica con NIT."
    num, e = validar_documento(td, d.get("nit"))
    if e: return None, e
    for k, l, n in (("departamento", DEPARTAMENTOS, "el departamento"), ("sector", SECTORES, "el sector"),
                    ("tamano", TAMANOS, "el tamaño"), ("arl", ARLS, "la ARL")):
        e = en_lista(d.get(k), l, n)
        if e: return None, e
    tel = (d.get("telefono") or "").strip()
    if tel and not _TEL.fullmatch(tel):
        return None, "Teléfono inválido: 7 a 20 caracteres (números, espacios, +, -, paréntesis)."
    em = (d.get("email") or "").strip()
    if em and not _EMAIL.fullmatch(em):
        return None, "El correo no es válido."
    nt = d.get("num_trabajadores")
    if nt in (None, ""):
        nt = None
    else:
        try:
            nt = int(nt)
        except (TypeError, ValueError):
            return None, "El número de trabajadores debe ser un entero."
        if not 1 <= nt <= 200000:
            return None, "El número de trabajadores debe estar entre 1 y 200 000."
    limpio = {
        "nombre": nombre, "tipo_persona": tp, "tipo_documento": td, "nit": num or None,
        "direccion": (d.get("direccion") or "").strip() or None,
        "departamento": d.get("departamento") or None,
        "ciudad": (d.get("ciudad") or "").strip() or None,
        "tamano": d.get("tamano") or None, "num_trabajadores": nt, "arl": d.get("arl") or None,
        "telefono": tel or None, "email": em or None,
        "contacto": (d.get("contacto") or "").strip() or None,
        "cargo_contacto": (d.get("cargo_contacto") or "").strip() or None,
        "sector": d.get("sector") or None,
    }
    return limpio, None
