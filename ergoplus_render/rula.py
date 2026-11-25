"""
Motor de cálculo RULA (Rapid Upper Limb Assessment)
Basado en McAtamney & Corlett (1993) y tablas de Ergonautas (UPV).
https://www.ergonautas.upv.es/metodos/rula/rula-ayuda.php
"""

# ---------------------------------------------------------------------------
# Tabla A: Grupo A (brazo, antebrazo, muñeca, giro muñeca) -> puntos_a (1-9)
# Índices: brazo 1-6, antebrazo 1-3, muneca 1-4, giro 1-2
# ---------------------------------------------------------------------------
TABLA_A = {
    # (brazo, antebrazo, muneca, giro): puntos_a
}
def _build_tabla_a():
    # Datos de Ergonautas (Tabla 13)
    data = [
        # brazo1
        [1,1,1,2, 2,2,2,3, 2,3,3,3, 3,3,3,3],  # ant1: mun1g1,g2 mun2g1,g2 ... simplified by nested
    ]
    # Explicit full matrix from Ergonautas
    # Format: for brazo in 1..6, antebrazo in 1..3, muneca in 1..4, giro in 1..2
    matrix = {
        (1,1,1,1):1,(1,1,1,2):2,(1,1,2,1):2,(1,1,2,2):2,(1,1,3,1):2,(1,1,3,2):3,(1,1,4,1):3,(1,1,4,2):3,
        (1,2,1,1):2,(1,2,1,2):2,(1,2,2,1):2,(1,2,2,2):2,(1,2,3,1):3,(1,2,3,2):3,(1,2,4,1):3,(1,2,4,2):3,
        (1,3,1,1):2,(1,3,1,2):3,(1,3,2,1):3,(1,3,2,2):3,(1,3,3,1):3,(1,3,3,2):3,(1,3,4,1):4,(1,3,4,2):4,
        (2,1,1,1):2,(2,1,1,2):3,(2,1,2,1):3,(2,1,2,2):3,(2,1,3,1):3,(2,1,3,2):4,(2,1,4,1):4,(2,1,4,2):4,
        (2,2,1,1):3,(2,2,1,2):3,(2,2,2,1):3,(2,2,2,2):3,(2,2,3,1):3,(2,2,3,2):4,(2,2,4,1):4,(2,2,4,2):4,
        (2,3,1,1):3,(2,3,1,2):4,(2,3,2,1):4,(2,3,2,2):4,(2,3,3,1):4,(2,3,3,2):4,(2,3,4,1):5,(2,3,4,2):5,
        (3,1,1,1):3,(3,1,1,2):3,(3,1,2,1):4,(3,1,2,2):4,(3,1,3,1):4,(3,1,3,2):4,(3,1,4,1):5,(3,1,4,2):5,
        (3,2,1,1):3,(3,2,1,2):4,(3,2,2,1):4,(3,2,2,2):4,(3,2,3,1):4,(3,2,3,2):4,(3,2,4,1):5,(3,2,4,2):5,
        (3,3,1,1):4,(3,3,1,2):4,(3,3,2,1):4,(3,3,2,2):4,(3,3,3,1):4,(3,3,3,2):5,(3,3,4,1):5,(3,3,4,2):5,
        (4,1,1,1):4,(4,1,1,2):4,(4,1,2,1):4,(4,1,2,2):4,(4,1,3,1):4,(4,1,3,2):5,(4,1,4,1):5,(4,1,4,2):5,
        (4,2,1,1):4,(4,2,1,2):4,(4,2,2,1):4,(4,2,2,2):4,(4,2,3,1):4,(4,2,3,2):5,(4,2,4,1):5,(4,2,4,2):5,
        (4,3,1,1):4,(4,3,1,2):4,(4,3,2,1):4,(4,3,2,2):5,(4,3,3,1):5,(4,3,3,2):5,(4,3,4,1):6,(4,3,4,2):6,
        (5,1,1,1):5,(5,1,1,2):5,(5,1,2,1):5,(5,1,2,2):5,(5,1,3,1):5,(5,1,3,2):6,(5,1,4,1):6,(5,1,4,2):7,
        (5,2,1,1):5,(5,2,1,2):6,(5,2,2,1):6,(5,2,2,2):6,(5,2,3,1):6,(5,2,3,2):7,(5,2,4,1):7,(5,2,4,2):7,
        (5,3,1,1):6,(5,3,1,2):6,(5,3,2,1):6,(5,3,2,2):7,(5,3,3,1):7,(5,3,3,2):7,(5,3,4,1):7,(5,3,4,2):8,
        (6,1,1,1):7,(6,1,1,2):7,(6,1,2,1):7,(6,1,2,2):7,(6,1,3,1):7,(6,1,3,2):8,(6,1,4,1):8,(6,1,4,2):9,
        (6,2,1,1):8,(6,2,1,2):8,(6,2,2,1):8,(6,2,2,2):8,(6,2,3,1):8,(6,2,3,2):9,(6,2,4,1):9,(6,2,4,2):9,
        (6,3,1,1):9,(6,3,1,2):9,(6,3,2,1):9,(6,3,2,2):9,(6,3,3,1):9,(6,3,3,2):9,(6,3,4,1):9,(6,3,4,2):9,
    }
    return matrix

TABLA_A = _build_tabla_a()

# Tabla B: cuello 1-6, tronco 1-6, piernas 1-2 -> puntos_b
def _build_tabla_b():
    m = {}
    # Ergonautas Tabla 14
    rows = [
        # cuello1
        [1,3, 2,3, 3,4, 5,5, 6,6, 7,7],
        # cuello2
        [2,3, 2,3, 4,5, 5,5, 6,7, 7,7],
        # cuello3
        [3,3, 3,4, 4,5, 5,6, 6,7, 7,7],
        # cuello4
        [5,5, 5,6, 6,7, 7,7, 7,7, 8,8],
        # cuello5
        [7,7, 7,7, 7,8, 8,8, 8,8, 8,8],
        # cuello6
        [8,8, 8,8, 8,8, 8,9, 9,9, 9,9],
    ]
    for c, row in enumerate(rows, 1):
        idx = 0
        for t in range(1, 7):
            for p in (1, 2):
                m[(c, t, p)] = row[idx]
                idx += 1
    return m

TABLA_B = _build_tabla_b()

# Tabla C: puntos_c (1-8) x puntos_d (1-7) -> final 1-7
def _build_tabla_c():
    # rows C=1..8, cols D=1..7
    data = [
        [1,2,3,3,4,5,5],  # C1
        [2,2,3,4,4,5,5],  # C2
        [3,3,3,4,4,5,6],  # C3
        [3,3,3,4,5,6,6],  # C4
        [4,4,4,5,6,7,7],  # C5
        [4,4,5,6,6,7,7],  # C6
        [5,5,6,6,7,7,7],  # C7
        [5,5,6,7,7,7,7],  # C8
    ]
    m = {}
    for c, row in enumerate(data, 1):
        for d, val in enumerate(row, 1):
            m[(c, d)] = val
    return m

TABLA_C = _build_tabla_c()

NIVELES = {
    (1, 2): ("Verde", "Aceptable. No se requieren cambios.", "No necesita cambios"),
    (3, 4): ("Amarillo", "Pueden requerirse cambios; conviene profundizar el estudio.", "Hacer una revisión"),
    (5, 6): ("Rojo", "Se requiere el rediseño de la tarea.", "Intervención necesaria"),
    (7, 7): ("Rojo", "Se requieren cambios urgentes en la tarea.", "Intervención inmediata"),
}


def nivel_actuacion(puntaje_final: int):
    p = max(1, min(7, int(puntaje_final)))
    if p <= 2:
        return NIVELES[(1, 2)]
    if p <= 4:
        return NIVELES[(3, 4)]
    if p <= 6:
        return NIVELES[(5, 6)]
    return NIVELES[(7, 7)]


def score_brazo(angulo_flexion, extension=False, hombro_elevado=False, abducido=False, rotado=False, apoyo=False):
    """
    angulo_flexion: grados de flexión (positivo). Si extension=True, se trata como extensión.
    Retorna (puntos_base, puntos_extra, puntos_parte)
    """
    a = abs(float(angulo_flexion or 0))
    if extension:
        base = 2 if a > 20 else 1
    else:
        if a <= 20:
            base = 1
        elif a <= 45:
            base = 2
        elif a <= 90:
            base = 3
        else:
            base = 4
    extra = 0
    if hombro_elevado or rotado:
        extra += 1
    if abducido:
        extra += 1
    if apoyo:
        extra -= 1
    total = max(1, min(6, base + extra))
    return base, extra, total


def score_antebrazo(angulo_flexion, cruza_linea_media=False, a_un_lado=False):
    a = abs(float(angulo_flexion or 0))
    base = 1 if 60 <= a <= 100 else 2
    extra = 1 if (cruza_linea_media or a_un_lado) else 0
    total = min(3, base + extra)
    return base, extra, total


def score_muneca(angulo, desviacion=False):
    a = abs(float(angulo or 0))
    if a == 0:
        base = 1
    elif a <= 15:
        base = 2
    else:
        base = 3
    extra = 1 if desviacion else 0
    total = min(4, base + extra)
    return base, extra, total


def score_giro_muneca(extremo=False):
    base = 2 if extremo else 1
    return base, 0, base


def score_cuello(angulo_flexion, extension=False, rotada=False, inclinada=False):
    a = abs(float(angulo_flexion or 0))
    if extension:
        base = 4
    else:
        if a <= 10:
            base = 1
        elif a <= 20:
            base = 2
        else:
            base = 3
    extra = 0
    if rotada:
        extra += 1
    if inclinada:
        extra += 1
    total = min(6, base + extra)
    return base, extra, total


def score_tronco(angulo_flexion, rotado=False, inclinado=False, sentado_bien=False):
    a = abs(float(angulo_flexion or 0))
    if a == 0 or (sentado_bien and a <= 0):
        base = 1
    elif a <= 20:
        base = 2
    elif a <= 60:
        base = 3
    else:
        base = 4
    extra = 0
    if rotado:
        extra += 1
    if inclinado:
        extra += 1
    total = min(6, base + extra)
    return base, extra, total


def score_piernas(pies_apoyados=True, peso_repartido=True):
    base = 1 if (pies_apoyados and peso_repartido) else 2
    return base, 0, base


def score_actividad(estatica=False, repetitiva=False):
    """0 o 1: estática (>1 min) o repetitiva (>4/min)"""
    return 1 if (estatica or repetitiva) else 0


def score_fuerza(carga_kg=0, estatica_o_rep=False, golpes=False):
    """0-3 según Ergonautas"""
    if golpes:
        return 3
    c = float(carga_kg or 0)
    if c < 2:
        return 0
    if c <= 10:
        return 2 if estatica_o_rep else 1
    return 3 if estatica_o_rep else 2


def calcular_rula(datos: dict) -> dict:
    """
    datos: diccionario con ángulos y flags.
    Retorna puntuaciones parciales, final y nivel.
    """
    # Grupo A
    _, _, p_brazo = score_brazo(
        datos.get("brazo_angulo", 0),
        extension=bool(datos.get("brazo_extension")),
        hombro_elevado=bool(datos.get("hombro_elevado")),
        abducido=bool(datos.get("brazo_abducido")),
        rotado=bool(datos.get("brazo_rotado")),
        apoyo=bool(datos.get("brazo_apoyo")),
    )
    _, _, p_ant = score_antebrazo(
        datos.get("antebrazo_angulo", 90),
        cruza_linea_media=bool(datos.get("antebrazo_cruza")),
        a_un_lado=bool(datos.get("antebrazo_lado")),
    )
    _, _, p_mun = score_muneca(
        datos.get("muneca_angulo", 0),
        desviacion=bool(datos.get("muneca_desviacion")),
    )
    _, _, p_giro = score_giro_muneca(extremo=bool(datos.get("giro_extremo")))

    p_brazo = max(1, min(6, p_brazo))
    p_ant = max(1, min(3, p_ant))
    p_mun = max(1, min(4, p_mun))
    p_giro = max(1, min(2, p_giro))

    puntos_a = TABLA_A.get((p_brazo, p_ant, p_mun, p_giro), 5)

    # Grupo B
    _, _, p_cue = score_cuello(
        datos.get("cuello_angulo", 0),
        extension=bool(datos.get("cuello_extension")),
        rotada=bool(datos.get("cuello_rotado")),
        inclinada=bool(datos.get("cuello_inclinado")),
    )
    _, _, p_tron = score_tronco(
        datos.get("tronco_angulo", 0),
        rotado=bool(datos.get("tronco_rotado")),
        inclinado=bool(datos.get("tronco_inclinado")),
        sentado_bien=bool(datos.get("sentado_bien")),
    )
    _, _, p_pier = score_piernas(
        pies_apoyados=bool(datos.get("pies_apoyados", True)),
        peso_repartido=bool(datos.get("peso_repartido", True)),
    )
    p_cue = max(1, min(6, p_cue))
    p_tron = max(1, min(6, p_tron))
    p_pier = max(1, min(2, p_pier))
    puntos_b = TABLA_B.get((p_cue, p_tron, p_pier), 5)

    act = score_actividad(
        estatica=bool(datos.get("actividad_estatica")),
        repetitiva=bool(datos.get("actividad_repetitiva")),
    )
    fuerza = score_fuerza(
        carga_kg=datos.get("carga_kg", 0),
        estatica_o_rep=bool(datos.get("carga_estatica_rep") or datos.get("actividad_estatica") or datos.get("actividad_repetitiva")),
        golpes=bool(datos.get("golpes")),
    )

    puntos_c = min(8, puntos_a + act + fuerza)
    puntos_d = min(7, puntos_b + act + fuerza)
    # Si C>8 usar 8; D>7 usar 7 (ya capped)
    final = TABLA_C.get((max(1, puntos_c), max(1, puntos_d)), 5)
    nombre, desc, accion = nivel_actuacion(final)

    return {
        "brazo": p_brazo,
        "antebrazo": p_ant,
        "muneca": p_mun,
        "giro_muneca": p_giro,
        "cuello": p_cue,
        "tronco": p_tron,
        "piernas": p_pier,
        "puntos_a": puntos_a,
        "puntos_b": puntos_b,
        "puntos_actividad": act,
        "puntos_fuerza": fuerza,
        "puntos_c": puntos_c,
        "puntos_d": puntos_d,
        "puntaje_final": final,
        "nivel": nombre,
        "nivel_descripcion": desc,
        "accion_sugerida": accion,
    }
