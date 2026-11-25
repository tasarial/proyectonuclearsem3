-- =====================================================================
-- ERGOPLUS · Migración v5 (después de v3 y v4, una sola vez)
--   Contraseña temporal · resumen de contrato · perfil del trabajador y consentimiento
--   Condiciones del puesto · fotos con ángulos · encuestas · recomendaciones
-- =====================================================================
ALTER TABLE usuarios ADD COLUMN debe_cambiar_clave TINYINT(1) NOT NULL DEFAULT 0;

ALTER TABLE contratos ADD COLUMN resumen VARCHAR(1500) NULL AFTER alcance;

ALTER TABLE operarios
  ADD COLUMN puesto_id INT NULL,
  ADD COLUMN genero ENUM('Femenino','Masculino','Otro') NULL,
  ADD COLUMN fecha_nacimiento DATE NULL,
  ADD COLUMN antiguedad_meses INT NULL,
  ADD COLUMN horas_jornada DECIMAL(4,1) NULL,
  ADD COLUMN lateralidad ENUM('Diestro','Zurdo','Ambidiestro') NULL,
  ADD COLUMN estatura_cm INT NULL,
  ADD COLUMN antecedentes VARCHAR(300) NULL,
  ADD COLUMN consentimiento_fecha DATETIME NULL,
  ADD COLUMN consentimiento_nombre VARCHAR(120) NULL,
  ADD COLUMN consentimiento_version VARCHAR(20) NULL;

ALTER TABLE puestos ADD COLUMN condiciones TEXT NULL;

ALTER TABLE evaluacion_rula
  ADD COLUMN trabajador_id INT NULL,
  ADD COLUMN condiciones TEXT NULL,
  ADD COLUMN recomendaciones TEXT NULL,
  ADD COLUMN ia_usada TINYINT(1) NOT NULL DEFAULT 0;

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
