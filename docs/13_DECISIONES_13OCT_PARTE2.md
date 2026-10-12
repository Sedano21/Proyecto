# Decisiones del 13-oct-2026 (segunda parte), lista de clientes con penalidades y estado frente a producción

## 1. Respuestas aplicadas

| Tema | Su respuesta | Implementación | Prueba |
|---|---|---|---|
| Precio de venta | Se negocia con el cliente y no puede estar por debajo del precio de la lista. El Jefe Comercial es el único que modifica la lista | La OV trae su precio de venta (columna de precio de la exportación o el formulario). Se compara con el mínimo del canal del cliente | `test_q11_*` |
| OV bajo el mínimo (P7) | Se alerta y queda detenida hasta que la confirme el Coordinador Comercial o el Jefe Comercial | `retenida_precio`: la OV no se prepara, no se programa en ruta y no sale. Se libera con "Confirmar precio y liberar" (permiso exclusivo `ov.aprobar_precio`, motivo obligatorio). Si después cambian los precios observados, vuelve a detenerse | `test_q11_ov_sin_precio_o_muestra_comercial_queda_detenida` |
| Muestra comercial (P3) | Se incluye en la alerta | El tipo de venta se importa de SAP ("Tipo de Venta"). Una línea con precio 0 cuenta como bajo el mínimo | ídem |
| Canales (P2) | Por ahora ningún canal para OFICINA, CANASTERIA y MINORISTA. Los clientes se asignan o trasladan de canal en Configuración; lo hace el Jefe Comercial y Sistemas tiene todo el panel | Campo "canal de precios" por cliente en Configuración → Clientes (permiso exclusivo `clientes.canal`: Jefe Comercial y Sistemas). Si está vacío, se deduce del grupo de SAP. Un cliente sin canal genera la alerta PRECIO_FALTANTE | `test_q11_productos_o_clientes_sin_precio_alertan_para_completar` |
| Granel o general (P4) | Depende del canal: granel no pasa por empaque y su precio es menor | Canal **MAYORISTA GRANEL**: sus clientes usan la lista granel; los demás usan la lista por canal (presentaciones) | `test_q11_lista_granel_por_canal_y_compara_kg_y_saco` |
| Granel kg o saco (P5) | Ambos | Se compara el precio por kg **y** por saco (conversión con los kg por saco) | ídem |
| Productos sin precio (P6) | Deben tenerlo; el sistema alerta y se completa en el panel | Alerta PRECIO_FALTANTE al Jefe Comercial y formulario "Agregar un precio mínimo faltante" en la lista de precios. Cuando se completa, la alerta se cierra al reevaluar la OV | ídem |
| Gerencia General y precios (P8) | No modifica precios | Confirmado: GG no tiene `precios.editar`, `ov.aprobar_precio` ni `clientes.canal` | `test_roles_y_configuracion` |
| Vencimiento de la lista (P9) | Se avisa sin bloquear; la fecha se puede modificar; sería ideal contrastar con precios de mercado | Vigencia por lista (desde/hasta), editable por el Jefe Comercial y al cargar el archivo. Alerta LISTA_PRECIOS_VENCIDA (aviso previo configurable); la lista sigue en uso. **El contraste con precios de mercado queda pendiente**: requiere una fuente de esos precios | `test_q11_vigencia_de_lista_avisa_sin_bloquear` |
| Jefe Comercial (P10) | Es el Jefe de Ventas | Rol "Jefe Comercial (Jefe de Ventas)" | — |
| Costo de la empresa | Se subirá más adelante en un Excel | Pendiente de recibir el formato. Hoy el costo no se guarda | — |
| Configuración | La edita Sistemas | `config.editar` es exclusivo de Sistemas; Gerencia General ya no lo tiene | `test_roles_y_configuracion` |
| Compras de mayor volumen | Se configura en el panel; por defecto aprueba Gerencia de Operaciones | Umbral en **KG, UNIDADES o SOLES** (parámetro `umbral_mayor_volumen_unidad`; en soles se evalúa con el precio cotizado). `mayor_volumen_requiere_go` = sí | `test_umbral_mayor_volumen_en_kg_o_soles` |
| Reglas no documentadas | Se configuran en el panel | `margen_por_proveedor` (con el proveedor habitual del artículo), `excepciones_bom` (cantidad fija por orden), `conversiones_calidad_permitidas`, `clasificacion_abc_pct` (columna ABC en reposición), `orden_asignacion_flota` y `vehiculos_por_zona` | 5 pruebas en `test_respuestas_13oct_b.py` |
| Coordinación de Producción | No existe; hay 2 asistentes de producción | Rol eliminado. Las alertas de producción van al Jefe y a los Asistentes de Producción. Usuarios demo `asist.produccion` y `asist.produccion2` | `test_roles_y_configuracion` |
| Merma de SAP | El desmedro de los formatos es la merma; el formato de liquidación son Truer, Cimbria, Envasado R1-R3 y Selección manual | Pantalla **Producción → Partes de producción** con las fórmulas de esos formatos (ver §2). La merma real de la liquidación se toma de sus partes (por número de OF), y se alerta si supera el umbral | `test_partes_de_produccion_con_formulas_de_los_formatos` |
| Instalación | Local, administrada por Sistemas | Guía en `08_INSTALACION_DESPLIEGUE.md` §8 | — |
| Base de datos | PostgreSQL, con las mejores prácticas de respaldo | Controlador PostgreSQL y migraciones Alembic. **Las pruebas pasan en PostgreSQL 16.** Scripts de respaldo cifrado y de restauración de prueba, probados (`08` §10) | `test_migraciones_al_dia` |
| Correo | No; las alertas quedan en el sistema | `correo_habilitado` = no (no se encolan correos) | `test_correo_deshabilitado_alertas_solo_en_sistema` |
| Ingreso | Microsoft 365 | OpenID Connect con la librería oficial MSAL (`08` §9). Probado con un servidor de identidad simulado; falta registrar la aplicación en su tenant | `test_login_microsoft_365` |
| Exportaciones de SAP | Cada área exporta a diario, con 2 cortes al día como mínimo | Alerta CARGA_SAP_DESACTUALIZADA cuando la última carga de un tipo supera las horas configuradas (12 h stock/OV/liquidación, 24 h salidas). Va al área responsable y a Sistemas | `test_alerta_si_las_cargas_de_sap_no_se_actualizan` |
| Datos personales | El tiempo que permita la ley | Parámetro `retencion_datos_personales_dias` (vacío) y comando `app.cli depurar`. El plazo lo debe fijar su asesoría legal | `test_depuracion_de_fotos_segun_retencion` |

La nueva lista granel que enviaron es **idéntica** a la anterior. GR-041 sigue con un precio por kg (2,98) menor que
su costo (4,57).

Además, PostgreSQL detectó **4 columnas demasiado cortas** que SQLite no controlaba (fuente de permisos, corte,
estados largos de traslados, importaciones y decisiones). Se corrigieron y se agregó una prueba que valida que las
migraciones coincidan con el modelo.

## 2. Partes de producción: fórmulas tomadas de sus formatos

| Formato | Datos | Cálculo | Ejemplo de su formato | Resultado del sistema |
|---|---|---|---|---|
| Selección: LÍNEA TRUER, LÍNEA CIMBRIA, SELECCIÓN MANUAL | Peso de entrada, granel, MP recuperada, CAL3, desmedro, horas | % rendimiento = granel / peso; **% desmedro (merma) = desmedro / peso**; diferencia = peso − (granel + MP + CAL3 + desmedro); kg/h = granel / horas | Cimbria 01-10: 10 795,68 kg, granel 10 400, desmedro 300 → 96,33 % / 2,78 % | 96,33 % / 2,78 % |
| ENVASADOS R1 R2 Y R3 | Kg de MP, presentación (kg), unidades, CAL3, sobrante | Unidades teóricas = kg MP / presentación; % rendimiento = unidades / teóricas; desmedro = kg MP no convertidos en unidades | R3 PT-105: 2 950 kg, 5 kg, 587 unid. → 99,49 % | 99,49 % |

## 3. Lista de clientes con penalidades y lotes

**Qué se hace con cada columna:**

| Columna | Uso en el sistema |
|---|---|
| LOTE ("1 LOTE POR SKU", "2 LOTES POR SKU") | **Regla de reserva.** Por cada producto se usan como máximo esos lotes. Entre opciones equivalentes se prefiere el lote que vence antes (FEFO) y el que cubre con menos lotes. Si no alcanza sin superar el máximo, queda un faltante en lugar de mezclar lotes. Cambiar el lote en el plan de picking también respeta el máximo |
| PENALIDAD | Se clasifica por tipo: ventana horaria, fecha de entrega (PAE), fill rate (con su umbral, p. ej. < 95 %), bloqueo o retiro de proveedor, paletizado, documentos, peso, falta de entrega, ruptura de stock no informada y no conformidades. **Prioridad:** a igual fecha comprometida, se atiende primero al cliente con penalidades más severas (pesos propuestos en `peso_penalidad`). Se muestra en la OV, la preparación y la ruta. Si la cobertura queda bajo el fill rate del cliente, la alerta de despacho parcial lo advierte |
| VIDA UTIL ("12 MESES", "6 MESES", "12 MESES / 6 MESES HARINAS") | Se registra y se muestra. **No se aplica a la reserva** hasta que confirme su significado (pregunta R1) |
| EJECUTIVO, CANAL, SOLICITUD | Se registran como referencia. **El canal de esta lista no cambia el canal de precios**, que asigna el Jefe Comercial |

**Validación con su archivo** (base temporal descartada):
- 103 clientes leídos sin errores. En la regla de lotes, 93 aceptan 1 lote por SKU y 10 aceptan 2.
- Tipos de penalidad reconocidos: ventana horaria 91, fecha de entrega 11, fill rate 7 y otros 8.
- **El archivo no trae RUC**, así que el vínculo con cada cliente es por nombre. De los 77 clientes de su archivo de OV, 28 coinciden; esos 28 concentran **137 de las 194 OV**. Los otros 75 de la lista quedan pendientes y se vinculan solos cuando el cliente llegue en una OV con el mismo nombre.
- La carga la hace el Jefe Comercial (o Sistemas) en Cargas de archivos → "Clientes: penalidades, lotes y vida útil".

## 4. Preguntas abiertas

| # | Pregunta | Qué hace hoy el sistema |
|---|---|---|
| R1 | "Vida útil 12 meses" (o 6 meses para harinas): ¿es la **vida útil restante mínima** que debe tener el producto al despacharlo? Si es así, se activa `aplicar_vida_util_cliente`. Advertencia: con 12 meses restantes, gran parte del stock actual no calificaría | Solo se registra |
| R2 | ¿Pueden agregar el **RUC** a la lista de clientes con penalidades? El vínculo por nombre falla con diferencias de escritura (75 de 103 no coincidieron) | Vínculo por nombre normalizado |
| R3 | Pesos de prioridad por tipo de penalidad (propuestos: retiro de proveedor 5, fecha de entrega 4, fill rate 4, entrega parcial 3, ruptura de stock 3, ventana horaria 2, peso 2, paletizado 2, documentos 1, no conformidades 1). ¿Los validan? ¿La penalidad va antes o después de la completitud del pedido? | Fecha → penalidad → completitud → urgencia |
| R4 | Formato del Excel de **costo de la empresa** y qué cálculos esperan (¿margen real por OV?, ¿recalcular la lista mínima con costo / (1 − margen)?) | Pendiente de recibir |
| R5 | **Precios de mercado** para el contraste: ¿qué fuente y con qué frecuencia? | Pendiente |
| R6 | La nueva exportación de OV que enviarán, ¿traerá la columna de precio unitario de venta y el "Tipo de Venta"? | Se leen si vienen con esos encabezados |

## 5. Qué sigue faltando para pasar a producción

**Lo que depende de ustedes:**
1. Responder R1 a R6.
2. Revisar los destinatarios de las alertas (21 propuestos) y la matriz de permisos (272 asignaciones propuestas). Sus respuestas no las confirmaron todavía; se pueden ajustar en la pantalla sin programar.
3. Cargar los valores reales de configuración, las fases de importación, los maestros (artículos, clientes con canal, flota, capacidad de líneas), la base inicial de stock, las listas de precios, la lista de clientes con penalidades y los usuarios con su correo corporativo.
4. Registrar la aplicación en Entra ID (Microsoft 365) y entregar los datos a Sistemas.
5. Que su asesoría legal fije el plazo de conservación de datos personales y fotos.
6. Instalar PostgreSQL en el servidor local según `08` §8 y programar el respaldo diario y la prueba mensual de restauración.

**Lo que se hace antes y durante la puesta en marcha:**
7. Pruebas de aceptación con usuarios clave, usando la nueva exportación de OV completa en el entorno de prueba.
8. Prueba de carga con varios usuarios a la vez.
9. Capacitación por rol.
10. Arranque en paralelo con el Excel.

Hasta completar estos puntos, el sistema **no está listo para producción**.
