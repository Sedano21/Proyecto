# Ronda V21 (05-nov-2026): lotes con puntos, autorización de cargas, SAP (liquidaciones, entregas y OV de prueba), VPN e inventario

Todos los ejemplos usan datos ficticios. No se conectó a ninguna base de SAP desde este entorno, ni de prueba ni productiva.
Lo que se describe aquí está probado con un Service Layer simulado (pruebas automáticas `tests/test_v21.py`).

## 1. Lotes con puntos («000863FA», «000863FA.», «000863FA..»)

### El problema

Producción le añade un punto al lote cada vez que vuelve a producir el mismo lote con otra fecha de producción o de
vencimiento. SAP no admite dos lotes con el mismo número y fechas distintas, por eso existe la regla. Como los puntos se
escriben a mano, en el archivo de stock que compartieron aparecieron estos casos:

- comas en lugar de puntos (26 filas, p. ej. `201025IN,`);
- variantes con las mismas fechas (61 filas): dos lotes que en realidad son el mismo;
- formatos raros (31 filas).

### Cómo lo resuelve el sistema

**1. Producción escribe solo el número del lote.** En el parte de producción, el campo «Lote PT (solo el número)» recibe
el lote sin puntos. Si alguien escribe puntos o comas, el sistema los quita y toma el número base.

**2. El sistema pone los puntos** (`app/services/lotes.py`, función `asignar`). Para eso revisa las variantes que ya
existen de ese lote y producto, tanto en el stock traído de SAP como en los partes que aún no llegan a SAP:

| Situación | Lote que se usa |
|---|---|
| Primera vez que se produce ese lote | `000863FA` |
| Ya existe una variante con la misma fecha de producción (y de vencimiento) | esa misma variante, sin punto nuevo |
| Es otra fecha | la siguiente variante libre: `000863FA.`, luego `000863FA..` |

Al iniciar el parte se muestra el código para SAP y el motivo, p. ej.: «Lote para SAP: 000863FA.. 3.ª producción del lote
000863FA: en SAP se registra como «000863FA..»». Producción copia ese código tal cual al registrar en SAP.

**3. En SAP no cambia nada.** El lote se sigue guardando con puntos, como hoy: SAP no tiene otro campo para la variante y
cambiar la numeración rompería la trazabilidad del stock que ya existe. La diferencia es que los puntos los calcula el
sistema y no una persona, así que ya no deberían salir comas, puntos de más ni duplicados.

**4. En pantalla, el lote se muestra legible.** El stock muestra «000863FA · 3.ª prod.» (filtro `|lote`, desde V20) y la
búsqueda por el número base trae todas sus variantes.

### Revisión de lotes para el inventario

La pantalla nueva **Almacén → Lotes y variantes** (`/almacen/lotes`, permiso `stock.ver`) tiene dos partes:

- **Variantes de un lote:** se busca el número base y se ven todas sus variantes con sus fechas y cantidades.
- **Lotes a corregir:** se pueden filtrar por tipo y descargar en Excel (`lotes_a_corregir_AAAAMMDD.xlsx`). Los tipos son:

| Tipo | Qué significa | Qué hacer en SAP |
|---|---|---|
| Coma en lugar de punto | `201025IN,` | Reclasificar al lote correcto (`201025IN.`) |
| Variantes con las mismas fechas | `333001AB` y `333001AB.` con la misma FP y FV | Unificar en un solo lote |
| Variante sin fechas | No se distingue de las otras variantes | Completar la fecha de producción y de vencimiento |
| Caracteres no válidos | Espacios, `#`, etc. | Corregir el número del lote |

## 2. «Su rol no puede autorizar esta carga»

El mensaje es correcto. Desde la decisión Q4, **Sistemas no aprueba ni autoriza**: puede subir o traer el stock de SAP, pero
otro perfil revisa la carga antes de que cambie el stock del módulo (control de doble revisión).

Pueden autorizar el stock por lote los perfiles con el permiso `stock.autorizar_carga`:

- Gerencia General;
- Gerente General Adjunto;
- Coordinación de Almacén 1560;
- Coordinación de Almacén MP;
- Coordinación de Logística.

Cambios de esta ronda:

- Al subir una carga que su perfil no puede autorizar, el sistema envía la alerta **CARGA_POR_AUTORIZAR** a los perfiles
  que sí pueden.
- El mensaje ahora dice quién la autoriza y que ya se les avisó.

Si el negocio quiere que Sistemas también autorice, es una decisión de negocio que cambia la Q4. Se cambiaría en
«Permisos por rol» (no hace falta tocar código), pero no se hizo sin esa decisión.

## 3. Traer de SAP: entregas y liquidaciones

- **Despachos (entregas/guías):** antes se pedían solo las entregas de hoy; por eso salía «SAP no devolvió datos de
  entregas». Ahora se traen las de los últimos **30 días** (parámetro `sap_despachos_dias`).
- **Liquidaciones:** ya no hace falta configurar una consulta SQL en `sap_consultas`. Se leen con objetos estándar del
  Service Layer:
  - las entradas de mercancía por producción (`InventoryGenEntries` con líneas de una orden de fabricación,
    `BaseType` 202) de los últimos **30 días** (parámetro `sap_liquidacion_dias`);
  - su orden de fabricación (`ProductionOrders`).

  Sale una fila por orden y lote, con la columna «Entrada SAP» (número del documento). Si en el futuro se configura
  `sap_consultas["LIQUIDACION"]`, se usa esa consulta en lugar de los objetos estándar.
- **Aviso «Se conservó lo que escribió…»:** ya no aparece en formularios que solo tienen botones (como las tarjetas de Traer
  de SAP).
- **Detalle de la carga:** la lista de almacenes larga ya no desborda la pantalla.

## 4. Probar la creación de OV en la base de pruebas de SAP

La creación de OV en SAP ya existía (V15). Solo escribe si se cumplen dos condiciones:

- el parámetro `sap_escritura_ov` está activado;
- la base conectada está en `sap_escritura_empresas`. Hoy solo figura `ZZZ_CORPRODUC_TEST260826`.

Esta ronda añade el botón **«Verificar con SAP»** en la OV. Revisa sin crear nada:

- que la escritura esté habilitada para esa base;
- que el cliente tenga código de SAP, exista en esa base, sea cliente y esté activo;
- que cada artículo exista en esa base, sea de venta y esté activo.

Además avisa si a una línea le falta el código de impuesto o tiene precio 0.

### Pasos sugeridos (con la base de pruebas)

1. En el servidor, `SAP_SL_COMPANY=ZZZ_CORPRODUC_TEST260826`. La URL depende de la conexión: con el túnel actual,
   `SAP_SL_URL=https://127.0.0.1:50000/b1s/v1`; con la VPN, la de la sección 5.
2. En el servidor, `python -m app.cli sap-diagnostico` (ingreso, maestros, almacenes y cola de OV); el estado también se ve en «Integración SAP (estado y cola)».
3. En Parámetros: `sap_escritura_ov` = activado y `sap_escritura_empresas` = `["ZZZ_CORPRODUC_TEST260826"]`.
4. Crear una OV de prueba con un cliente y artículos que existan en la base de pruebas, y pulsar **Verificar con SAP**.
5. Si no hay problemas, pulsar **Enviar a SAP ahora** y comprobar en SAP (base de pruebas) el número de OV. El número
   también queda en la OV del módulo.
6. Recién después de varias OV correctas y revisadas en SAP, decidir el paso a la base origen. Ese paso es una decisión
   de la empresa: hay que agregar la base productiva a `sap_escritura_empresas` y cambiar `SAP_SL_COMPANY`. Este cambio
   no se hizo.

**Licencia indirecta:** con la licencia de acceso indirecto ya no hay riesgo por usar varias sesiones del Service Layer. El
código no limita el número de sesiones. Aun así se recomienda un usuario de integración dedicado en lugar de manager,
para auditar en SAP lo que crea el módulo y poder cambiar su contraseña sin afectar a nadie.

## 5. VPN punto a punto (WireGuard) en lugar del túnel de la máquina virtual

### Situación actual

`deploy/tunel_sap.bat` abre un túnel SSH inverso desde una máquina virtual de la empresa hacia el servidor en AWS.
Depende de que esa ventana siga abierta.

### Propuesta

Una VPN WireGuard, cifrada y que se reconecta sola. Solo expone el puerto 50000 del servidor SAP al servidor del módulo.

| | Opción A (recomendada) | Opción B |
|---|---|---|
| Equipo en la empresa | Pasarela Linux (VM pequeña o mini PC siempre encendida) | WireGuard para Windows en el propio servidor SAP, como servicio |
| Archivo de ejemplo | `deploy/vpn/wg-pasarela-linux.conf.ejemplo` | `deploy/vpn/wg-sap-windows.conf.ejemplo` |
| ¿Instala algo en SAP? | No | Sí |
| `SAP_SL_URL` | `https://172.18.103.1:50000/b1s/v1` | `https://10.77.0.2:50000/b1s/v1` |
| Firewall | Reenvía solo hacia 172.18.103.1:50000 | Regla de Windows: 50000 solo desde 10.77.0.1 |

### Pasos

1. **AWS:** en el Security Group del servidor, abrir **UDP 51820** solo desde la IP pública de la empresa.
2. **Servidor (AWS):** ejecutar `sudo bash deploy/vpn/instalar_wireguard_servidor.sh`. Crea las claves y muestra la clave
   pública del servidor.
3. **Equipo de la empresa:**
   - generar sus claves;
   - completar el archivo de ejemplo de la opción elegida con la clave pública del servidor y la IP pública de AWS;
   - activar el túnel.

   La conexión sale desde la empresa (`PersistentKeepalive`), así que no hay que abrir puertos en el router de la empresa.
4. **Servidor:** ejecutar `sudo bash deploy/vpn/instalar_wireguard_servidor.sh <clave_pública_del_equipo_de_la_empresa>`.
   Deja `wg0` activo al arrancar.
5. **Probar:** `wg show` (último saludo reciente) y `curl -k https://172.18.103.1:50000/b1s/v1/Login`. En la opción B,
   usar `10.77.0.2`.
6. **Cambiar `SAP_SL_URL`** en `/etc/operaciones.env`. El nombre del certificado del Service Layer no coincide con la IP,
   así que se mantiene la misma configuración que con el túnel: `SAP_SL_CA` con el certificado del servidor SAP, o
   `SAP_SL_VERIFY=0` mientras tanto. Luego `sudo systemctl restart operaciones` y repetir `python -m app.cli sap-diagnostico`.
7. **Dejar el túnel anterior:** cuando todo funcione, cerrar `tunel_sap.bat` y quitarlo del inicio de la máquina virtual.

Los archivos no se probaron contra la red real desde este entorno. La IP del servidor SAP (172.18.103.1) sale del
`tunel_sap.bat` actual; si cambió, se pasa como segundo argumento del instalador.

## 6. Guía para el inventario del fin de semana

**1. Antes de contar** (viernes):

- traer el stock de SAP (Traer de SAP → Stock) y que lo autorice un perfil autorizado (sección 2);
- descargar **Lotes a corregir** en Excel (sección 1) y repartirlo a los equipos de conteo.

**2. Conteo:** Almacén → Conteos. Se abre un conteo por almacén o por producto, se registra lote por lote y se corrige el
número de lote en la hoja de los lotes observados.

**3. Validación:** el Jefe de Logística valida los conteos. Las diferencias quedan registradas.

**4. Ajuste en SAP:** quien corresponda en SAP hace las entradas y salidas de ajuste. En los lotes del Excel:

- reclasificar las comas;
- unificar las variantes con las mismas fechas;
- completar las fechas que faltan.

**5. Después del ajuste:** volver a traer el stock de SAP y autorizarlo. **Lotes y variantes** debería quedar vacío o casi
vacío. Desde ese momento, Producción solo escribe el número del lote y el sistema pone los puntos.

## 7. Ajustes tras la revisión del 05-nov-2026 (V21b)

### La coma vale como punto

Producción confirmó que las comas son errores de digitación del punto. En el módulo, `201025IN,` es el mismo lote que
`201025IN.` (2.ª producción):

- **Al asignar lotes:** la coma ocupa su variante, así que la siguiente producción toma el punto siguiente.
- **En el picking:** si en SAP el lote está con coma y el operario escribe el punto, se acepta y se registra el lote tal
  como está en SAP.
- **Al cruzar datos:** liquidación con stock, registros de Calidad con liquidación, precertificado y tránsito de
  Producción reconocen las dos formas.
- **En la carga de stock:** el aviso dice que la coma se toma como punto y que se corrija en SAP cuando se pueda.
- **En Lotes y variantes:**
  - la coma figura como «Es el mismo lote que…»;
  - hay un tipo nuevo, «Mismo lote con coma y con punto», para cuando existen las dos escrituras y hay que unificarlas.

En SAP los lotes siguen con su escritura actual hasta que se corrijan en el inventario: el módulo no cambia nada en SAP.

### Artículos de SAP en la OV y en el catálogo

**Causa.** Los artículos traídos del maestro de SAP llegan sin la columna TIPO (PT/GR/MP). La OV, el catálogo, las
oportunidades y los informes de menos vendidos solo listaban artículos con TIPO, así que no aparecían, y la unidad se
quedaba en «—».

**Arreglo.** Ahora también se listan los artículos sin TIPO cuyo prefijo tiene una unidad de venta definida en
`um_por_prefijo`: PT, AB y MQ en unidades; MP, GR y SER en kilos. Los demás (envases, suministros con otro TIPO) siguen
fuera. La unidad se completa al elegir el producto.

### Catálogo por canal

El catálogo tiene un filtro **Canal**:

- **Canal con lista general:** muestra los productos con precio vigente en esa lista, con su precio.
- **Canal granel** (`lista_granel_canales`): muestra la lista mayorista granel, con el precio por kg y por saco.
- **Sin canal:** muestra todo el catálogo.

Si un canal no muestra productos, falta cargar su lista de precios (Comercial → Listas de precios).

## 8. Archivos tocados

| Archivo | Cambio |
|---|---|
| `app/services/lotes.py` | Funciones `asignar` y `anomalias` |
| `app/services/parte.py` | Asigna el lote al iniciar el parte |
| `app/views/produccion_mb2.py` | Muestra el código del lote al iniciar el parte |
| `app/templates/prod_reports.html` | Campo «Lote PT (solo el número)» |
| `app/views/almacen.py`, `app/templates/lotes.html`, `app/templates/base.html` | Revisión de lotes |
| `app/services/uploads.py` | Alerta a quien autoriza y mensaje nuevo; columna «Entrada SAP» en liquidaciones |
| `app/services/sap_sl.py` | `rows_liquidacion`, rango de entregas y `preflight_order` |
| `app/views/comercial.py`, `app/templates/ov_detail.html` | Botón «Verificar con SAP» |
| `app/static/app.js` | Aviso de texto conservado solo en formularios con campos |
| `app/static/style.css`, `app/templates/upload_detail.html` | Detalle de carga sin desbordes |
| `app/catalogs.py` | Alerta `CARGA_POR_AUTORIZAR`, parámetros `sap_despachos_dias` y `sap_liquidacion_dias` |
| `deploy/vpn/` | Instalador y archivos de ejemplo de WireGuard |
| `tests/test_v21.py` | Pruebas de esta ronda |

No se agregaron tablas: no hay migración nueva y la cabeza sigue en 0032.

V21b también tocó:

- `app/services/lotes.py` (`normal`, `escrituras`, `misma`);
- `app/services/orders.py` (`condicion_vendible` y el picking con coma);
- `app/services/picking.py`, `production.py`, `quality.py` y `process_liq.py` (cruce de lotes);
- `app/views/comercial.py`, `app/views/comercial_mb2.py`, `app/services/market.py` y `app/services/commercial_mgmt.py`
  (artículos de SAP);
- `app/templates/catalog.html` (filtro por canal).
