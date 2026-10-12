# Requisitos de seguridad e infraestructura a aprobar antes del uso en la organización

## 1. Controles ya incluidos en el prototipo

- Autenticación con usuario y contraseña; contraseñas con hash (Werkzeug/scrypt); bloqueo de 5 minutos tras 5 intentos fallidos.
- Autorización por permisos en cada pantalla y en cada servicio de negocio (doble control); matriz rol-permiso auditada.
- Protección CSRF en todos los formularios; cookies de sesión HttpOnly y SameSite=Lax (Secure configurable).
- Auditoría de ingresos, intentos fallidos, cambios, aprobaciones, cargas, exportaciones y configuración.
- Validación de archivos (solo .xlsx/.xlsm para cargas; imágenes/PDF para evidencias; tamaño máximo configurable;
  nombres de archivo generados por el servidor).
- Sin conexiones a SAP ni a sistemas productivos; correo solo si se configura SMTP.
- Plantillas con escape automático de HTML (Jinja2).
- Redirección tras el ingreso solo a rutas internas (corregido en esta entrega: se rechazaba `//sitio-externo`).
- Permisos exclusivos: precios mínimos y venta bajo el mínimo (Jefe/Coord. Comercial), configuración (Sistemas).

## 2. Requisitos pendientes de aprobación por TI / Seguridad de la información

| # | Requisito | Detalle |
|---|---|---|
| S1 | Servidor y sistema operativo | **Definido: instalación local administrada por Sistemas.** Parches, antivirus y acceso físico restringido |
| S2 | Base de datos de producción | **Definido: PostgreSQL.** Respaldo diario cifrado, prueba de restauración mensual, WAL para recuperación puntual (`08` §10). Probado con PostgreSQL 16 |
| S3 | HTTPS | Certificado corporativo, proxy inverso, `SESSION_COOKIE_SECURE=1`, HSTS |
| S4 | Gestión de identidades | **Definido: Microsoft 365 (Entra ID).** Implementado con MSAL; falta registrar la aplicación en el tenant (`08` §9). Mantener una cuenta local de emergencia de Sistemas |
| S5 | Matriz de permisos final | Validación por cada jefatura del detalle propuesto y del alcance de "acceso completo" (Q4) |
| S6 | Correo | **Definido: por ahora sin correo; alertas solo en el sistema** (`correo_habilitado` = no). Si más adelante se habilita: cuenta de servicio, SPF/DKIM |
| S7 | Datos personales y comerciales | Conservar "el tiempo que permita la ley" (Ley N.° 29733 y su reglamento): el plazo concreto debe fijarlo la asesoría legal; luego se configura `retencion_datos_personales_dias` y se usa `app.cli depurar`. Los documentos tributarios (guías, facturas) pueden tener plazos de conservación propios |
| S8 | Evidencias de entrega (fotos, guías firmadas) | Almacenamiento con respaldo, control de acceso y plazo de conservación |
| S9 | Registros de auditoría | Retención mínima, protección contra modificación, revisión periódica |
| S10 | Red | Acceso solo desde red corporativa o VPN; si se requiere acceso móvil de conductores, evaluar exposición controlada |
| S11 | Secretos | `SECRET_KEY` y credenciales SMTP/BD en variables de entorno o bóveda; nunca en el repositorio |
| S12 | Modo demo | `DEMO_MODE=0` en producción (oculta usuarios demo); no cargar `seed_demo` en producción |
| S13 | Continuidad | Procedimiento de contingencia si el sistema no está disponible (formatos actuales) y responsable de soporte |
| S14 | Gestión de cambios | **Alembic incorporado** (`migrations/`). Ambiente de prueba separado del productivo; respaldo antes de cada `alembic upgrade` |
| S15 | Pruebas adicionales | Prueba de penetración básica, prueba de carga con usuarios concurrentes, prueba en el motor de BD definitivo |
| S16 | Integración SAP futura | Si se aprueba, usuario técnico de solo lectura y acuerdo con el administrador SAP |

## 3. Dimensionamiento orientativo para la primera etapa

Volumen observado en los archivos: ~1 200 lotes en stock, ~400 productos con BOM, ~250 OV abiertas, ~42 000 líneas de
venta anuales. Un servidor de 2 vCPU, 4 GB RAM y 50 GB de disco (más el crecimiento de evidencias fotográficas) es
suficiente para decenas de usuarios concurrentes; la carga del historial de 42 000 líneas tomó ~16 s en la prueba.
