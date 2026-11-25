-- =====================================================
-- PMV Estudio de Métodos y Ergonomía - Base de datos v2
-- Python + Flask + MySQL
-- Universidad Alexander von Humboldt
-- =====================================================

CREATE DATABASE IF NOT EXISTS pmv_ergonomia CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE pmv_ergonomia;

SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS evaluaciones_ergo;
DROP TABLE IF EXISTS observaciones_tiempo;
DROP TABLE IF EXISTS visitas;
DROP TABLE IF EXISTS puestos;
DROP TABLE IF EXISTS salones;
DROP TABLE IF EXISTS sedes;
DROP TABLE IF EXISTS servicios;
DROP TABLE IF EXISTS operarios;
DROP TABLE IF EXISTS empresas;
DROP TABLE IF EXISTS login_attempts;
DROP TABLE IF EXISTS encuestas;
DROP TABLE IF EXISTS puesto_fotos;
DROP TABLE IF EXISTS logs;
DROP TABLE IF EXISTS areas;
DROP TABLE IF EXISTS contratos;
DROP TABLE IF EXISTS usuario_empresas;
DROP TABLE IF EXISTS usuario_permisos;
DROP TABLE IF EXISTS usuarios;

SET FOREIGN_KEY_CHECKS = 1;

-- ===================== USUARIOS =====================
CREATE TABLE usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nombre_completo VARCHAR(120) NOT NULL,
    email VARCHAR(120),
    role ENUM('owner','admin','evaluador','client') NOT NULL DEFAULT 'client',
    empresa_id INT NULL,
    debe_cambiar_clave TINYINT(1) NOT NULL DEFAULT 0,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- ===================== EMPRESAS (soft delete) =====================
CREATE TABLE empresas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    tipo_persona ENUM('Jurídica','Natural') NOT NULL DEFAULT 'Jurídica',
    tipo_documento ENUM('NIT','CC','CE','PASAPORTE') NOT NULL DEFAULT 'NIT',
    nit VARCHAR(20),                                -- número del documento
    direccion VARCHAR(120),
    departamento VARCHAR(60),
    ciudad VARCHAR(60),
    tamano ENUM('Micro','Pequeña','Mediana','Grande') NULL,
    num_trabajadores INT NULL,
    arl VARCHAR(60),
    telefono VARCHAR(30),
    email VARCHAR(100),
    contacto VARCHAR(100),
    cargo_contacto VARCHAR(60),
    sector VARCHAR(80),
    activo TINYINT(1) NOT NULL DEFAULT 1,          -- soft delete
    fecha_registro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ===================== SEDES =====================
CREATE TABLE sedes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    direccion VARCHAR(200),
    ciudad VARCHAR(80),
    telefono VARCHAR(30),
    puesto_id INT NULL,
    genero ENUM('Femenino','Masculino','Otro') NULL,
    fecha_nacimiento DATE NULL,
    antiguedad_meses INT NULL,
    horas_jornada DECIMAL(4,1) NULL,
    lateralidad ENUM('Diestro','Zurdo','Ambidiestro') NULL,
    estatura_cm INT NULL,
    antecedentes VARCHAR(300) NULL,
    consentimiento_fecha DATETIME NULL,
    consentimiento_nombre VARCHAR(120) NULL,
    consentimiento_version VARCHAR(20) NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

-- ===================== SALONES =====================
CREATE TABLE salones (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sede_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    descripcion VARCHAR(255),
    activo TINYINT(1) NOT NULL DEFAULT 1,
    FOREIGN KEY (sede_id) REFERENCES sedes(id) ON DELETE CASCADE
);

-- ===================== PUESTOS =====================
CREATE TABLE puestos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    area_id INT NULL,
    condiciones TEXT NULL,
    salon_id INT NOT NULL,
    numero_puesto VARCHAR(30),
    nombre VARCHAR(100) NOT NULL,
    area VARCHAR(80),
    ubicacion VARCHAR(120),
    descripcion TEXT,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    FOREIGN KEY (salon_id) REFERENCES salones(id) ON DELETE CASCADE
);

-- ===================== OPERARIOS =====================
CREATE TABLE operarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    documento VARCHAR(30),
    cargo VARCHAR(80),
    area VARCHAR(80),
    turno VARCHAR(40),
    telefono VARCHAR(30),
    activo TINYINT(1) NOT NULL DEFAULT 1,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
);

-- ===================== SERVICIOS / CONTRATOS =====================
CREATE TABLE servicios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    contrato_id INT NULL,
    codigo_acceso VARCHAR(20) NOT NULL UNIQUE,
    titulo VARCHAR(150) NOT NULL DEFAULT 'Servicio de evaluación ergonómica',
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    estado ENUM('activo', 'vencido', 'cancelado') NOT NULL DEFAULT 'activo',
    observaciones TEXT,
    creado_por INT,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL
);

-- ===================== VISITAS =====================
CREATE TABLE visitas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    sede_id INT NULL,
    fecha DATE NOT NULL,
    hora_entrada TIME,
    hora_salida TIME,
    categoria VARCHAR(80),
    salon VARCHAR(80),
    cantidad_puestos INT DEFAULT 0,
    responsable VARCHAR(100),
    observaciones TEXT,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    FOREIGN KEY (sede_id) REFERENCES sedes(id) ON DELETE SET NULL
);

-- ===================== OBSERVACIONES DE TIEMPO =====================
CREATE TABLE observaciones_tiempo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    puesto_id INT NOT NULL,
    operario_id INT NOT NULL,
    tarea VARCHAR(150) NOT NULL,
    tiempo_ciclo DECIMAL(10,2) NOT NULL,
    num_ciclos INT DEFAULT 1,
    fecha DATE NOT NULL,
    observaciones TEXT,
    FOREIGN KEY (puesto_id) REFERENCES puestos(id) ON DELETE CASCADE,
    FOREIGN KEY (operario_id) REFERENCES operarios(id) ON DELETE CASCADE
);

-- ===================== EVALUACIONES ERGONÓMICAS =====================
CREATE TABLE evaluaciones_ergo (
    id INT AUTO_INCREMENT PRIMARY KEY,
    puesto_id INT NOT NULL,
    operario_id INT NULL,
    fecha DATE NOT NULL,
    lado ENUM('Izquierdo','Derecho','Ambos') DEFAULT 'Ambos',
    altura_adecuada ENUM('Si','No') DEFAULT 'Si',
    postura_espalda ENUM('Si','No') DEFAULT 'Si',
    iluminacion ENUM('Si','No') DEFAULT 'Si',
    movimiento_repetitivo ENUM('Si','No') DEFAULT 'No',
    carga_pesada ENUM('Si','No') DEFAULT 'No',
    apoyo_pies ENUM('Si','No') DEFAULT 'Si',
    alcance_brazos ENUM('Si','No') DEFAULT 'Si',
    resultado ENUM('Bajo','Medio','Grave') NOT NULL,
    puntuacion INT DEFAULT 0,
    observaciones TEXT,
    recomendaciones TEXT,
    FOREIGN KEY (puesto_id) REFERENCES puestos(id) ON DELETE CASCADE,
    FOREIGN KEY (operario_id) REFERENCES operarios(id) ON DELETE SET NULL
);

-- ===================== INTENTOS DE LOGIN (rate limit) =====================
CREATE TABLE login_attempts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL,
    ip_address VARCHAR(45),
    attempt_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_username_time (username, attempt_time)
);

-- ===================== DATOS INICIALES =====================


-- ===================== CONTRATOS =====================
CREATE TABLE contratos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    numero VARCHAR(30) NOT NULL UNIQUE,
    tipo ENUM('Evaluación ergonómica','Estudio de métodos','Capacitación','Asesoría','Otro') NOT NULL DEFAULT 'Evaluación ergonómica',
    objeto VARCHAR(250) NOT NULL,
    alcance TEXT,
    resumen VARCHAR(1500),
    fecha_firma DATE NULL,
    fecha_inicio DATE NOT NULL,
    fecha_fin DATE NOT NULL,
    valor DECIMAL(14,2) NULL,
    moneda ENUM('COP','USD') NOT NULL DEFAULT 'COP',
    forma_pago ENUM('Contado','50% anticipo / 50% entrega','30 días','60 días','Por cuotas') NULL,
    estado ENUM('Borrador','Vigente','Finalizado','Cancelado') NOT NULL DEFAULT 'Vigente',
    responsable VARCHAR(100),
    notas VARCHAR(500),
    creado_por INT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL,
    INDEX idx_contratos_empresa (empresa_id)
) ENGINE=InnoDB;

-- ===================== ÁREAS (administrativas, operativas, de apoyo) =====================
CREATE TABLE areas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    nombre VARCHAR(80) NOT NULL,
    tipo ENUM('Administrativa','Operativa','Apoyo') NOT NULL DEFAULT 'Administrativa',
    responsable VARCHAR(100),
    cargo_responsable VARCHAR(60),
    num_personas INT NULL,
    descripcion VARCHAR(250),
    activo TINYINT(1) NOT NULL DEFAULT 1,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    INDEX idx_areas_empresa (empresa_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS puesto_fotos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    puesto_id INT NULL,
    evaluacion_id INT NULL,
    trabajador_id INT NULL,
    archivo VARCHAR(80) NOT NULL,
    mime VARCHAR(30) NOT NULL,
    vista ENUM('Lateral','Frontal','Posterior') NOT NULL DEFAULT 'Lateral',
    mira_a ENUM('Derecha','Izquierda') NOT NULL DEFAULT 'Derecha',
    puntos TEXT NULL,
    angulos TEXT NULL,
    origen ENUM('manual','ia') NOT NULL DEFAULT 'manual',
    notas VARCHAR(250) NULL,
    creado_por INT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    INDEX idx_fotos_eval (evaluacion_id), INDEX idx_fotos_puesto (puesto_id)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS encuestas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    puesto_id INT NULL,
    trabajador_id INT NULL,
    tipo ENUM('nordico','percepcion') NOT NULL,
    respuestas TEXT NOT NULL,
    comentario VARCHAR(500) NULL,
    creado_por INT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    INDEX idx_enc_puesto (puesto_id)
) ENGINE=InnoDB;

-- ===================== PERMISOS / ASIGNACIONES / LOGS (v3) =====================
-- 3) Permisos true/false por cuenta (solo guarda lo que DIFIERE del rol)
CREATE TABLE IF NOT EXISTS usuario_permisos (
    usuario_id INT NOT NULL,
    permiso VARCHAR(30) NOT NULL,
    valor TINYINT(1) NOT NULL,
    PRIMARY KEY (usuario_id, permiso),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 4) Empresas asignadas a un Evaluador (solo ve/edita esas)
CREATE TABLE IF NOT EXISTS usuario_empresas (
    usuario_id INT NOT NULL,
    empresa_id INT NOT NULL,
    PRIMARY KEY (usuario_id, empresa_id),
    FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- 5) Auditoría (solo se inserta; la app nunca edita ni borra)
CREATE TABLE IF NOT EXISTS logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    fecha TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    usuario_id INT NULL,
    usuario VARCHAR(60) NOT NULL,
    rol VARCHAR(20) NOT NULL,
    accion VARCHAR(30) NOT NULL,      -- crear, editar, eliminar, login, login_fallido, logout, permisos, descargar, exportar...
    modulo VARCHAR(30) NOT NULL,      -- Cuentas, Empresas, Sedes, Salones, Puestos, Servicios, Calendario, Evaluaciones, Informes, Sesión, Logs
    registro VARCHAR(160) NULL,
    detalle VARCHAR(400) NULL,
    antes TEXT NULL,
    despues TEXT NULL,
    ip VARCHAR(45) NULL,
    ok TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_logs_fecha (fecha),
    INDEX idx_logs_usuario (usuario),
    INDEX idx_logs_modulo (modulo),
    INDEX idx_logs_accion (accion)
) ENGINE=InnoDB;


-- (Sin datos de ejemplo: la cuenta Owner se crea al primer arranque de la app.)

-- ===================== EVALUACIÓN RULA (reemplaza/amplía evaluaciones_ergo) =====================
DROP TABLE IF EXISTS evaluacion_rula;
CREATE TABLE evaluacion_rula (
    id INT AUTO_INCREMENT PRIMARY KEY,
    visita_id INT NULL,
    empresa_id INT NOT NULL,
    sede_id INT NULL,
    salon_id INT NULL,
    puesto_id INT NULL,
    lado ENUM('Derecho','Izquierdo') NOT NULL DEFAULT 'Derecho',
    postura VARCHAR(150),
    criterio VARCHAR(80),
    tiempo_minutos INT,
    visitante VARCHAR(120) NOT NULL COMMENT 'Nombre de quien realizó la visita/evaluación',
    -- Ángulos y flags (entrada)
    brazo_angulo DECIMAL(6,1) DEFAULT 0,
    brazo_extension TINYINT(1) DEFAULT 0,
    hombro_elevado TINYINT(1) DEFAULT 0,
    brazo_abducido TINYINT(1) DEFAULT 0,
    brazo_rotado TINYINT(1) DEFAULT 0,
    brazo_apoyo TINYINT(1) DEFAULT 0,
    antebrazo_angulo DECIMAL(6,1) DEFAULT 90,
    antebrazo_cruza TINYINT(1) DEFAULT 0,
    antebrazo_lado TINYINT(1) DEFAULT 0,
    muneca_angulo DECIMAL(6,1) DEFAULT 0,
    muneca_desviacion TINYINT(1) DEFAULT 0,
    giro_extremo TINYINT(1) DEFAULT 0,
    cuello_angulo DECIMAL(6,1) DEFAULT 0,
    cuello_extension TINYINT(1) DEFAULT 0,
    cuello_rotado TINYINT(1) DEFAULT 0,
    cuello_inclinado TINYINT(1) DEFAULT 0,
    tronco_angulo DECIMAL(6,1) DEFAULT 0,
    tronco_rotado TINYINT(1) DEFAULT 0,
    tronco_inclinado TINYINT(1) DEFAULT 0,
    sentado_bien TINYINT(1) DEFAULT 0,
    pies_apoyados TINYINT(1) DEFAULT 1,
    peso_repartido TINYINT(1) DEFAULT 1,
    actividad_estatica TINYINT(1) DEFAULT 0,
    actividad_repetitiva TINYINT(1) DEFAULT 0,
    carga_kg DECIMAL(6,2) DEFAULT 0,
    carga_estatica_rep TINYINT(1) DEFAULT 0,
    golpes TINYINT(1) DEFAULT 0,
    -- Resultados calculados
    puntos_brazo TINYINT,
    puntos_antebrazo TINYINT,
    puntos_muneca TINYINT,
    puntos_giro TINYINT,
    puntos_cuello TINYINT,
    puntos_tronco TINYINT,
    puntos_piernas TINYINT,
    puntos_a TINYINT,
    puntos_b TINYINT,
    puntos_actividad TINYINT,
    puntos_fuerza TINYINT,
    puntos_c TINYINT,
    puntos_d TINYINT,
    puntaje_final TINYINT NOT NULL,
    nivel ENUM('Verde','Amarillo','Rojo') NOT NULL,
    accion_sugerida VARCHAR(255),
    sugerencias TEXT,
    observaciones TEXT,
    trabajador_id INT NULL,
    condiciones TEXT NULL,
    recomendaciones TEXT NULL,
    ia_usada TINYINT(1) NOT NULL DEFAULT 0,
    creado_por INT,
    fecha_evaluacion DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (visita_id) REFERENCES visitas(id) ON DELETE SET NULL,
    FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE CASCADE,
    FOREIGN KEY (sede_id) REFERENCES sedes(id) ON DELETE SET NULL,
    FOREIGN KEY (salon_id) REFERENCES salones(id) ON DELETE SET NULL,
    FOREIGN KEY (puesto_id) REFERENCES puestos(id) ON DELETE SET NULL,
    FOREIGN KEY (creado_por) REFERENCES usuarios(id) ON DELETE SET NULL
);
