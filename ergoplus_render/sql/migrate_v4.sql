-- =====================================================================
-- ERGOPLUS · Migración v4  (ejecutar DESPUÉS de migrate_v3.sql, una sola vez)
--   · Se elimina el rol Manager (sus cuentas pasan a Administrador)
--   · Datos estándar del cliente (tipo de persona, documento, ubicación…)
--   · Contratos y Áreas (administrativas / operativas / apoyo)
--   · Se borran las cuentas demo y los datos de ejemplo
-- =====================================================================

-- 1) Manager -> Administrador y se quita del ENUM
UPDATE usuarios SET role='admin' WHERE role='manager';
ALTER TABLE usuarios MODIFY role ENUM('owner','admin','evaluador','client') NOT NULL DEFAULT 'client';

-- 2) Datos estándar de la empresa
ALTER TABLE empresas
  ADD COLUMN tipo_persona ENUM('Jurídica','Natural') NOT NULL DEFAULT 'Jurídica' AFTER nombre,
  ADD COLUMN tipo_documento ENUM('NIT','CC','CE','PASAPORTE') NOT NULL DEFAULT 'NIT' AFTER tipo_persona,
  ADD COLUMN departamento VARCHAR(60) NULL AFTER direccion,
  ADD COLUMN tamano ENUM('Micro','Pequeña','Mediana','Grande') NULL AFTER ciudad,
  ADD COLUMN num_trabajadores INT NULL AFTER tamano,
  ADD COLUMN arl VARCHAR(60) NULL AFTER num_trabajadores,
  ADD COLUMN cargo_contacto VARCHAR(60) NULL AFTER contacto;
ALTER TABLE empresas MODIFY nit VARCHAR(20) NULL, MODIFY direccion VARCHAR(120) NULL, MODIFY ciudad VARCHAR(60) NULL;

-- 3) Contratos
CREATE TABLE IF NOT EXISTS contratos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    empresa_id INT NOT NULL,
    numero VARCHAR(30) NOT NULL UNIQUE,
    tipo ENUM('Evaluación ergonómica','Estudio de métodos','Capacitación','Asesoría','Otro') NOT NULL DEFAULT 'Evaluación ergonómica',
    objeto VARCHAR(250) NOT NULL,
    alcance TEXT,
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
ALTER TABLE servicios ADD COLUMN contrato_id INT NULL AFTER empresa_id;

-- 4) Áreas
CREATE TABLE IF NOT EXISTS areas (
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
ALTER TABLE puestos ADD COLUMN area_id INT NULL AFTER id;

-- 5) Fuera lo demo
DELETE FROM usuarios WHERE username IN ('manager','admin','evaluador','cliente') AND password_hash IN ('PENDIENTE')
   OR (username IN ('admin','evaluador','cliente') AND email LIKE '%@ergoplus.co');
-- Si habías cargado los datos de ejemplo del schema original y quieres empezar limpio, descomenta:
-- SET FOREIGN_KEY_CHECKS=0; TRUNCATE evaluacion_rula; TRUNCATE visitas; TRUNCATE servicios; TRUNCATE operarios;
-- TRUNCATE puestos; TRUNCATE salones; TRUNCATE sedes; TRUNCATE empresas; SET FOREIGN_KEY_CHECKS=1;
