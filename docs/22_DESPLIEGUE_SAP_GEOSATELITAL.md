# Despliegue para las pruebas con usuarios, SAP Service Layer y GEOSATELITAL (26-oct-2026)

## 1. Qué se necesita de la empresa para desplegar

| # | Qué | Para qué | Quién |
|---|---|---|---|
| 1 | Servidor (VM Linux o Windows Server) con 2 vCPU, 4 GB RAM, 40 GB de disco, en la red de la empresa o en la nube | Ejecutar el sistema (Python 3.11+ con waitress/gunicorn) | Sistemas |
| 2 | Base de datos PostgreSQL 14+ (o SQL Server) con un usuario propio | Datos del sistema; respaldo diario | Sistemas |
| 3 | Nombre de dominio interno o público y certificado HTTPS | Acceso de los usuarios desde PC y celular (choferes, almacén) | Sistemas |
| 4 | Visibilidad de red del servidor hacia el SAP Service Layer (puerto 50000/50001) | Integración con SAP | Sistemas / partner SAP |
| 5 | Correo saliente (SMTP de Microsoft 365) con una cuenta de envío | Correos de alertas | Sistemas |
| 6 | Opcional: registro de aplicación en Microsoft 365 (Entra ID) | Ingreso con la cuenta corporativa | Sistemas |
| 7 | Lista de usuarios reales: nombre, cargo/perfil, correo, almacén y líneas (asistentes) | Crear las cuentas (Sistemas también las crea en Usuarios y permisos) | RR. HH. / jefaturas |
| 8 | Datos maestros reales en Excel (si no se traen de SAP): artículos, stock por lote, lista de materiales, precios, clientes, flota (placas, SOAT), colaboradores de Producción | Carga inicial | Cada área |
| 9 | Parámetros PENDIENTE de la pantalla Configuración (velocidades, tolerancias, días de aviso, vigencia de fumigación, etc.) | Reglas del negocio | Jefaturas |
| 10 | Respaldos: carpeta o bucket para la copia diaria de la base y de `UPLOAD_DIR` | Recuperación ante fallas | Sistemas |

Pasos: `docs/08_INSTALACION_DESPLIEGUE.md` §5 (sin datos de demostración, `DEMO_MODE=0`, `alembic upgrade head`,
`python -m app.cli init`, crear el usuario de Sistemas). Para las pruebas con usuarios se recomienda un ambiente aparte
(base de pruebas) del de la marcha blanca.

## 2. SAP Business One – Service Layer (solo lectura)

El conector (`app/services/sap_sl.py`) **solo lee** SAP: inicia sesión (`POST /Login`), consulta con `GET` y cierra
sesión. No crea ni modifica documentos en SAP. Lo que trae pasa por el flujo de cargas (validación, revisión y
autorización, o autorización automática configurable) y por la conciliación de la marcha blanca.

| Dato | Origen en SAP | Estado |
|---|---|---|
| Órdenes de venta abiertas | `Orders` (DocumentStatus abierto) + `BusinessPartners` (RUC) + `SalesPersons` | Implementado; probado con respuestas simuladas, no contra SAP |
| Clientes | `BusinessPartners` (clientes) | Implementado; aún sin probar (ni simulado ni contra SAP) |
| Artículos | `Items` | Implementado; aún sin probar (ni simulado ni contra SAP) |
| Entregas (guías) | `DeliveryNotes` → OV de origen | Implementado; aún sin probar (ni simulado ni contra SAP) |
| Stock por lote | Consulta SQL guardada (no hay entidad estándar con el saldo por lote y almacén) | Requiere la consulta en SAP |
| Liquidaciones de producción | Consulta SQL guardada | Requiere la consulta en SAP |
| Facturas | `Invoices` | Pendiente (hoy por Excel/PDF en Finanzas) |

Necesito de SAP / del partner:
1. URL del Service Layer (`https://servidor:50000/b1s/v1`) y versión de SAP B1 (9.3, 10.0; HANA o SQL Server).
2. Nombre de la base de la empresa (CompanyDB).
3. Un **usuario de SAP de solo consulta** para la integración (licencia que permita Service Layer/DI API) y su contraseña.
4. El certificado de la CA del Service Layer, si usa uno propio.
5. Dos consultas SQL guardadas en el Service Layer (`SQLQueries`), con estas columnas:
   - Stock por lote: `Número de artículo`, `Descripción del artículo`, `Lote`, `Almacén`, `Cantidad`, `Fecha de vencimiento`,
     `Fecha de fabricación`, `Fecha de admisión` (tablas OBTN/OBTQ u OIBT según la versión).
   - Liquidaciones: `Número de documento`, `Código de producto`, `Cantidad Planificada`, `Cantidad Completada`, `Lote`,
     `Almacén`, `Fecha de creación`, `Fecha de vencimiento`.
   Sus códigos se registran en el parámetro `sap_consultas`.
6. Confirmar los campos de usuario (UDF) que usan para canal, tipo de venta, cita y lugar de entrega, si existen, para
   agregarlos al mapeo.

Configuración: variables `SAP_SL_*` en el servidor; prueba: `python -m app.cli sap-probar` o Almacén → Cargas de archivos →
«Traer directamente de SAP». Sincronización automática: `SAP_SYNC_MIN`, `SAP_SYNC_USER` y el parámetro `sap_sync_tipos`.

## 3. GEOSATELITAL

La cuenta recibida no se guardó en el repositorio. GEOSATELITAL no publica una API: hay que pedir a su soporte el servicio
para integradores (dirección, formato y forma de autenticación). Con eso se configuran `GEOSAT_API_URL` y la credencial
(`GEOSAT_TOKEN`, o `GEOSAT_USER` y `GEOSAT_PASSWORD`) en el servidor. Si solo dan acceso al portal web, se puede mostrar
su panel dentro del sistema con `geosatelital_url_panel` (si el proveedor lo permite). Se recomienda cambiar la contraseña
compartida por chat y crear un usuario exclusivo para la integración.
