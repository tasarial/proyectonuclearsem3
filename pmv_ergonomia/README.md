# ERGOPLUS (Flask + MySQL)

Aplicación web de evaluación ergonómica (RULA) y estudio de métodos: clientes, áreas, contratos, servicios con código de acceso, calendario, evaluaciones con guía visual, informes PDF, permisos por cuenta y registro de actividad (logs).

## 1. Puesta en marcha (en tu computador)

```bash
python -m venv venv && source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # y edítalo (ver abajo)
```

1. Crea la base: `mysql -u root -p < sql/schema.sql`  (o impórtalo en phpMyAdmin).
   *Si ya tenías datos de una versión anterior:* ejecuta `sql/migrate_v3.sql` y luego `sql/migrate_v4.sql` (una vez cada uno).
2. En `.env` define `SECRET_KEY` (texto largo aleatorio), los datos de MySQL y, si quieres, `OWNER_PASSWORD`.
3. `python app.py` → http://127.0.0.1:5000
4. En el primer arranque se crea la cuenta **Owner**. Si no definiste `OWNER_PASSWORD`, la contraseña inicial sale **una sola vez en la consola**: anótala. Entra y cámbiala en *Ajustes*.
5. Como Owner, ve a **Cuentas y permisos** y crea las cuentas del equipo (Administrador, Evaluador) y de cada cliente.

## 2. Publicarla como web

1. Un servidor (VPS, Render, Railway, PythonAnywhere…) con Python 3.10+ y MySQL (o MySQL administrado).
2. Sube el proyecto, instala dependencias, importa `sql/schema.sql` y crea el `.env` en el servidor con `HTTPS=1`, una `SECRET_KEY` nueva y los datos de MySQL.
3. Ejecuta con un servidor de producción, no con `python app.py`:
   `pip install gunicorn && gunicorn -w 3 -b 0.0.0.0:8000 app:app`
4. Pon delante Nginx/Caddy con certificado HTTPS (Let's Encrypt) apuntando al puerto 8000.
5. Al arrancar se crea el Owner (ver paso 4 de arriba). Haz copias de seguridad de MySQL periódicas.

## 3. Cómo se usa

| Quién | Qué hace |
|---|---|
| **Owner** | Crea cuentas, ajusta permisos, ve logs, y puede todo lo demás. |
| **Administrador** | Registra clientes, áreas, contratos, servicios, visitas y evaluaciones. |
| **Evaluador** | Ve solo las empresas asignadas: calendario, evaluaciones RULA e informes. |
| **Cliente** | Ve y descarga los informes de su empresa, o consulta con su código de servicio. |

Flujo típico: **Clientes** (empresa → sedes → salones → puestos) → **Áreas** (administrativas, operativas, apoyo) → **Contratos** (se firma y se registra) → **Servicios** (se genera el código y se vincula al contrato) → **Calendario** (visita) → **Evaluaciones RULA** (siguiendo los 5 pasos con las figuras guía) → **Informes** (PDF) → el cliente entra o usa su código.

### Datos estándar y validaciones
- Cliente: tipo de persona (Jurídica/Natural), tipo de documento (NIT, CC, CE, Pasaporte), departamento, sector, tamaño, ARL… se eligen de listas.
- El NIT se valida con su dígito de verificación (ej. `900123456-8`); la persona jurídica solo usa NIT.
- Todos los textos tienen límite de caracteres (en el formulario y en el servidor); los largos muestran contador. Los límites están en `catalogos.py` (`LIMITES`) y las listas también.

## 4. Permisos

Claves: `cuentas`, `permisos`, `emp_ver`, `emp_edit`, `emp_del`, `con` (contratos), `srv`, `cal`, `eval`, `inf_ver`, `inf_dl`, `logs`.
Owner y Cliente son roles estáticos. Administrador y Evaluador tienen valores por defecto que el Owner puede cambiar true/false por cuenta (`cuentas` y `permisos` no se delegan). Todo se valida en el servidor.

## 5. Logs

Sección **Logs**: búsqueda, filtros (usuario, acción, módulo, periodo, resultado), detalle antes/después y exportación CSV. Registro de solo lectura; opcionalmente `sql/logs_append_only.sql` lo protege también en la base.

## 6. Seguridad básica
- Sin cuentas ni datos de ejemplo; contraseñas con hash; bloqueo progresivo por intentos fallidos.
- Cookies `HttpOnly` y `SameSite=Lax` (`Secure` con `HTTPS=1`).
- Cambia `SECRET_KEY` y la contraseña inicial del Owner antes de publicar.


## 7. Novedades de la versión 5
- **Base de datos:** si ya tenías datos, ejecuta en orden `sql/migrate_v3.sql`, `sql/migrate_v4.sql` y `sql/migrate_v5.sql`. En instalaciones nuevas basta `sql/schema.sql`.
- **Contraseña temporal:** toda cuenta nueva (o con clave restablecida) debe cambiarla al primer ingreso. En *Cuentas* hay un botón «Generar contraseña temporal».
- **Contratos:** resumen del contrato, duración calculada y pestaña «Sin contrato vigente» (sin contrato, terminado o vencido).
- **Citas:** no se pueden reservar con menos de `MIN_ANTICIPACION_HORAS` (por defecto 2 h, hora de Bogotá).
- **Evaluaciones:** asistente de 5 pasos (puesto y trabajador → condiciones → fotos y ángulos → mediciones RULA → resultado). Incluye perfil del trabajador, consentimiento informado, semáforo, recomendaciones editables e informe PDF descargable.
- **Fotos:** se guardan en `UPLOAD_DIR` (fuera de `static`) y solo se sirven con sesión y permisos. Hay que hacer copia de seguridad de esa carpeta.
- **IA:** las sugerencias de pasos, valores, recomendaciones y compatibilidad funcionan sin internet. Para que la IA detecte puntos en las fotos define `ANTHROPIC_API_KEY` en `.env`; sin clave los puntos se marcan a mano. Todo es corregible por el ingeniero.
- **Encuestas:** Nórdico simplificado (molestias) y percepción del puesto, con resumen por empresa o puesto.
- **Identidad visual:** violeta profundo (marca), verde salud (positivo), ámbar y coral para el semáforo; Space Grotesk para títulos e Inter para texto.
- **Datos personales:** el texto de consentimiento se basa en la Ley 1581 de 2012; pide a un abogado que lo revise antes de usarlo con clientes. Los límites de carga (Res. 2400/1979) son una referencia: verifica su vigencia con tu asesor en SST. La compatibilidad puesto–persona no es un concepto de aptitud laboral.
