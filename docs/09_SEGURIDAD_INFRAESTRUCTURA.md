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

## 2. Requisitos pendientes de aprobación por TI / Seguridad de la información

| # | Requisito | Detalle |
|---|---|---|
| S1 | Servidor y sistema operativo | Servidor interno (VM) con soporte, parches y antivirus; o nube aprobada por la empresa |
| S2 | Base de datos de producción | PostgreSQL o SQL Server con respaldo diario, retención definida y prueba de restauración; SQLite solo para demo |
| S3 | HTTPS | Certificado corporativo, proxy inverso, `SESSION_COOKIE_SECURE=1`, HSTS |
| S4 | Gestión de identidades | Decidir: usuarios locales (con política de contraseñas y cambio periódico) o SSO/Active Directory/Entra ID (requiere desarrollo adicional) |
| S5 | Matriz de permisos final | Validación por cada jefatura del detalle propuesto y del alcance de "acceso completo" (Q4) |
| S6 | Correo | Cuenta SMTP de servicio, remitente autorizado, SPF/DKIM; lista de destinatarios aprobada |
| S7 | Datos personales y comerciales | Las exportaciones contienen RUC, nombres, direcciones, precios, conductores y placas: definir clasificación, accesos y retención conforme a la Ley N.° 29733 de Protección de Datos Personales y su reglamento |
| S8 | Evidencias de entrega (fotos, guías firmadas) | Almacenamiento con respaldo, control de acceso y plazo de conservación |
| S9 | Registros de auditoría | Retención mínima, protección contra modificación, revisión periódica |
| S10 | Red | Acceso solo desde red corporativa o VPN; si se requiere acceso móvil de conductores, evaluar exposición controlada |
| S11 | Secretos | `SECRET_KEY` y credenciales SMTP/BD en variables de entorno o bóveda; nunca en el repositorio |
| S12 | Modo demo | `DEMO_MODE=0` en producción (oculta usuarios demo); no cargar `seed_demo` en producción |
| S13 | Continuidad | Procedimiento de contingencia si el sistema no está disponible (formatos actuales) y responsable de soporte |
| S14 | Gestión de cambios | Migraciones de base de datos controladas (incorporar Alembic), ambientes de prueba y producción separados |
| S15 | Pruebas adicionales | Prueba de penetración básica, prueba de carga con usuarios concurrentes, prueba en el motor de BD definitivo |
| S16 | Integración SAP futura | Si se aprueba, usuario técnico de solo lectura y acuerdo con el administrador SAP |

## 3. Dimensionamiento orientativo para la primera etapa

Volumen observado en los archivos: ~1 200 lotes en stock, ~400 productos con BOM, ~250 OV abiertas, ~42 000 líneas de
venta anuales. Un servidor de 2 vCPU, 4 GB RAM y 50 GB de disco (más el crecimiento de evidencias fotográficas) es
suficiente para decenas de usuarios concurrentes; la carga del historial de 42 000 líneas tomó ~16 s en la prueba.
