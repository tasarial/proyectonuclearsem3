-- OPCIONAL: hace la tabla logs realmente "solo-inserción" a nivel de base de datos.
-- Ejecutar con el cliente mysql (usa DELIMITER):  mysql -u root -p pmv_ergonomia < sql/logs_append_only.sql
DELIMITER $$
CREATE TRIGGER logs_no_update BEFORE UPDATE ON logs FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'logs es de solo lectura'; END$$
CREATE TRIGGER logs_no_delete BEFORE DELETE ON logs FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'logs es de solo lectura'; END$$
DELIMITER ;
