-- =====================================================================
-- ERGOPLUS · Migración v3  (roles Manager/Evaluador, permisos por cuenta, Logs)
-- Ejecutar UNA vez sobre la base existente:   mysql -u root -p pmv_ergonomia < sql/migrate_v3.sql
-- (si ya habías usado migrate_rula.sql, también está bien)
-- =====================================================================

-- 1) Nuevos roles. 'owner', 'manager' y 'client' son ESTÁTICOS (sus permisos no se editan);
--    'admin' y 'evaluador' usan permisos por defecto + ajustes por cuenta.
ALTER TABLE usuarios
  MODIFY role ENUM('owner','manager','admin','evaluador','client') NOT NULL DEFAULT 'client';

-- 2) Empresa asociada a una cuenta Cliente (opcional)
ALTER TABLE usuarios ADD COLUMN empresa_id INT NULL AFTER email;
ALTER TABLE usuarios ADD CONSTRAINT fk_usuarios_empresa
  FOREIGN KEY (empresa_id) REFERENCES empresas(id) ON DELETE SET NULL;

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
