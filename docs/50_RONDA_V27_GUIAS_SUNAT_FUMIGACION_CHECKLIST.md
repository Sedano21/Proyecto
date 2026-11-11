# Ronda V27 (11-nov-2026): guías SUNAT, días no laborables, fumigación solicitada, checklist diario y más

Pruebas con datos ficticios. La guía SUNAT y el checklist de Excel que envió la empresa se usaron solo para conocer el
formato: no se suben al repositorio. Migración nueva: **0039**.

## 1. Lo pedido y dónde quedó

| Pedido | Implementación | Dónde |
|---|---|---|
| Rol Gerente de Administración y Finanzas | Perfil nuevo **Gerente de Administración y Finanzas**. Tiene el poder del Jefe de Administración y Finanzas y de la Coordinación de Finanzas, y además ve compras, costos, margen, nivel de servicio y rendiciones. Si el Jefe de Administración y Finanzas no atiende sus tareas, se le avisa al Gerente. | Usuarios y permisos |
| Cada usuario cambia su nombre | La pantalla **«Mi cuenta (nombre y contraseña)»** permite corregir el nombre propio; queda en la auditoría. El usuario de ingreso y el perfil los sigue cambiando Sistemas. | Menú de usuario |
| Día no laborable de un área y replanificación | **Días no laborables**: el jefe registra la fecha y el motivo de su área. Áreas: Producción, Almacén, Distribución, Mantenimiento y Limpieza. Desde ese momento la programación no usa ese día: Producción no programa, el picking se corre al siguiente día hábil y no se arman rutas. Lo ya programado (producción, picking, rutas, órdenes de trabajo y limpiezas) aparece con casillas y se pasa **todo junto** al siguiente día hábil del área o a la fecha elegida. Si una OV queda después de su fecha comprometida, se avisa a Comercial. | Panel → Días no laborables |
| Regularización de guías emitidas en SUNAT | **Guías SUNAT (regularización)**. Ver el detalle en el punto 1.1. | Distribución → Guías SUNAT |
| OV vs guías: no salían las facturas | Ahora se reconocen las tres formas de SAP: factura basada en la guía, factura basada en la OV y **factura de reserva** con la guía basada en ella. También se muestran las facturas traídas de SAP a Finanzas que están unidas a la OV. | Integración SAP → OV abiertas vs guías |
| Contrastar las OV con órdenes de servicio (maquila) | Botón **«Traer de SAP» de órdenes de servicio/fabricación**: lee las órdenes de SAP cuyo origen es una OV (últimos `sap_servicios_dias` = 90 días). Cada OV muestra su orden con lo completado frente a lo planificado y el estado. Si la orden está completa pero la OV no se despachó, se avisa. | Ídem |
| Fumigación solicitada por Calidad, Producción o Almacén | **Solicitudes de fumigación**. Ver el detalle en el punto 1.2. | Calidad → Solicitudes de fumigación (también Almacén y Producción) |
| Firmas de los certificados: solo la Jefe de Calidad y la Supervisora de Calidad | Cada una carga **su propia firma** (PNG; se guarda solo en el servidor) y se imprime en los certificados **que ella aprobó**, con su nombre y cargo. Otros perfiles no cargan ni usan firma. Los certificados anteriores conservan la firma general. | Calidad → Certificados |
| Pestaña Estado de OV | **Estado de OV**: indicadores por etapa que filtran la lista (borrador, detenida, en preparación, lista, despachada, entregada, cerrada y atrasadas). Una línea por OV con el avance: stock, picking, ruta, guía, entrega y factura. Filtros por fechas, cliente y ejecutivo; el ejecutivo ve solo sus OV. | Comercial → Estado de OV |
| Gestión Humana: rendimiento por persona | **Desempeño por persona**. Por persona: OV preparadas, clientes, unidades, kg, **% de picking a tiempo**, movimientos, minutos por movimiento, tareas completadas y ausencias del periodo (vacaciones, descanso médico, faltas justificadas e injustificadas). Filtros por fechas y área. Lo ven Gestión Humana, las jefaturas y la gerencia. | Panel → Desempeño por persona |
| Checklist vehicular al comienzo y al final del día, con fotos | **Checklist vehicular diario** (formato CP-OPE-004). Ver el detalle en el punto 1.3. | Distribución → Checklist vehicular diario; Mis entregas |
| Validan la carga: conductor, Seguridad, Calidad (día antes o mismo día), auxiliar de despacho y líder operativo | Los vistos buenos de la salida ahora son los cinco. **Calidad** da el suyo **solo el día anterior o el mismo día** del despacho y no espera la carga validada. El conductor y el auxiliar, con la carga validada. Seguridad, al revisar los documentos. El Líder Operativo da el último al autorizar la salida. Calidad tiene acceso a las rutas para dar su visto bueno. | Ruta → 5. Vistos buenos |

### 1.1 Regularización de guías emitidas en SUNAT

1. Coordinación o Asistencia de Distribución, o el Auxiliar de Despacho, sube el **PDF de SUNAT o el XML**. Se pueden
   subir varias guías a la vez.
2. El sistema lee:
   - serie y número;
   - fecha de emisión y de traslado;
   - motivo;
   - destinatario con su RUC;
   - placa;
   - productos con **lote, FP, FV**, cantidad y unidad.
3. Se une sola a la OV si hay una única OV abierta del cliente con esos productos. Si no, se elige la OV o se escribe el
   número de la OV en SAP.
4. El **Jefe de Operaciones** decide el inventario:
   - «ya se descontó»: no se toca el stock;
   - «descontarlo ahora»: se descuenta del lote en el módulo. Mayúsculas, puntos y comas del lote dan igual. Si la OV
     tenía ese lote reservado, la reserva se consume para no descontarlo dos veces.
5. **«Enviar a SAP»** crea la entrega (guía) basada en la OV de SAP, con la serie y el número de SUNAT y los lotes. Solo
   lo hace en las bases autorizadas (`sap_escritura_empresas`).

### 1.2 Solicitudes de fumigación

1. Calidad, Producción o Almacén solicita: elige **uno o varios lotes** y la cantidad de cada uno. Puede ser el lote
   completo o una parte. Indica el motivo.
2. **Calidad aprueba** o rechaza. Elige el **lugar** (Contenedor 1, Contenedor 2 o Patio; parámetro
   `fumigacion_lugares`) y las fechas de inicio y de **liberación**.
3. **Almacén** recibe el **checklist** de lo que ingresa y confirma lote por lote la cantidad que ingresó.
   - Esa cantidad pasa a «En fumigación».
   - Si es solo una parte, el lote se separa y las reservas que ya no caben se liberan.
4. Sigue el flujo de siempre: aviso de liberación y liberación por Calidad. Luego, el seguimiento de producto fumigado
   almacenado (máximo 20 días).

### 1.3 Checklist vehicular diario

- Lo hace el conductor, por **cada vehículo** que maneje en el día. Puede manejar dos o más vehículos el mismo día.
- Hay un checklist de **inicio del día** y otro de **fin del día**, cada uno con:
  - los ítems B/M/NA;
  - los puntos NN;
  - el kilometraje inicial o final;
  - la **foto de adelante y la de atrás**;
  - las observaciones de choques o raspaduras;
  - la imagen interactiva para marcar daños.
- Reglas:
  - el fin del día exige el inicio del mismo vehículo;
  - el kilometraje final no puede ser menor al inicial.
- Seguridad valida y registra el kilometraje.
- Los puntos NN en mal estado alertan para no movilizar el vehículo.
- Este checklist convive con el de salida y retorno de cada ruta.

## 2. Parámetros nuevos

| Parámetro | Valor | Estado |
|---|---|---|
| `dias_no_laborables_areas_por_rol` | áreas que registra cada jefe | PROPUESTO |
| `sap_servicios_dias` | 90 | PROPUESTO |
| `fumigacion_lugares` | Contenedor 1, Contenedor 2, Patio | DEFINIDO |
| `firma_certificado_roles` | Jefe de Calidad, Supervisora de Calidad | DEFINIDO |
| `certificado_cargos` | cargo impreso por perfil | PROPUESTO |
| `vistos_buenos_salida` | Seguridad, Conductor, Calidad, Auxiliar de Despacho, Líder Operativo | DEFINIDO (cambio V27) |

**Permisos nuevos:**
- `dias.no_laborables`;
- `guias.sunat_cargar`;
- `guias.regularizar_inventario` (Jefe de Operaciones);
- `fumigacion.solicitar`, `fumigacion.aprobar` y `fumigacion.ingreso`;
- `desempeno.personas`;
- `distribucion.visto_bueno_calidad`.

**Alertas nuevas:**
- `DIA_NO_LABORABLE`;
- `GUIA_SUNAT_INVENTARIO`;
- `FUMIGACION_SOLICITADA`;
- `FUMIGACION_INGRESO`.

## 3. Puntos a confirmar con la empresa

1. **Órdenes de servicio (maquila).** Se interpretó que son órdenes de fabricación de SAP cuyo origen es la OV. Si en
   SAP la maquila se registra de otra forma (otro documento u otro campo), se ajusta la lectura.
2. **Envío a SAP de la guía SUNAT.** La entrega se crea con la serie y el número de SUNAT
   (FolioPrefixString/FolioNumber). Hay que probarlo primero en la base de pruebas con el partner: algunos add-ons de
   facturación electrónica controlan esos campos.
3. **Nombre real en el repositorio.** El nombre de la Jefa de Calidad estaba escrito en el catálogo de parámetros desde
   una ronda anterior. Se quitó del código y de la documentación, pero **queda en el historial de Git** del repositorio
   público. El valor que ya está configurado en el servidor no cambia.

## 4. Verificación

- `tests/test_v27.py` (11 pruebas):
  - perfil y nombre propio;
  - días no laborables y replanificación;
  - lectura de la guía en texto, XML y PDF;
  - unión a la OV, descuento de inventario y envío a SAP con un SAP simulado;
  - facturas y órdenes de servicio en la conciliación;
  - fumigación parcial;
  - firmas;
  - estado de OV y desempeño;
  - checklist diario con dos vehículos;
  - visto bueno de Calidad.
- Suite completa: **592 pruebas, todas pasan** (las pruebas anteriores de salida siguen con los 3 vistos buenos; el flujo de 5 se prueba aparte).
- Revisión en navegador:
  - solicitudes de fumigación;
  - días no laborables;
  - guías SUNAT;
  - estado de OV;
  - checklist diario.
