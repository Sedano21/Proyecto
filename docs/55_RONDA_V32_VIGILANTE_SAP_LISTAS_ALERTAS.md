# Ronda V32 (13-nov-2026): vigilante de SAP cada minuto, listas con fecha y paginador, alertas por área y compras

Pruebas con datos ficticios.
- **Escritura en SAP:** nada nuevo.
- **Migración:** sin migración nueva.
- **Servidor:** hay un **servicio nuevo, `operaciones-sap`**, que se instala solo con la actualización automática.

## 1. Por qué «Actualizar con SAP» no terminaba ni se actualizaba solo

**Qué pasaba:**
- La sincronización con SAP corría **dentro de los procesos de la web** (gunicorn).
- Esos procesos se renuevan solos cada cierto número de pedidos (`max_requests`) y, al renovarse, **cortan los hilos en segundo plano**. Una sincronización larga, como la primera carga del historial desde julio, quedaba cortada y la pantalla seguía en «Actualizando…».
- El botón traía todo de una vez: facturas, OV, clientes, artículos, guías e historial completo. Era lento a través del túnel.
- La sincronización automática dependía de `SAP_SYNC_MIN`; en la marcha blanca se recomendó 60 minutos, no cada minuto.

**Qué se hizo:** un **vigilante de SAP** en su propio servicio del servidor (`operaciones-sap.service`, comando `app.cli sap-vigilar`). No depende de la web y se reinicia solo si falla.

**Cada minuto**, dentro de `sap_sync_horario` (06:00-21:00):
1. Pregunta a SAP qué documentos se **crearon o modificaron desde ayer**: OV, guías, facturas y notas de crédito, entradas y salidas de inventario. Es una consulta liviana: solo número, fecha y hora de modificación.
2. **Si algo cambió**, trae solo eso:
   - **OV:** carga de OV e historial;
   - **guías:** carga de guías e historial;
   - **facturas:** facturas y notas de crédito de los últimos 3 días, notas de crédito sobre OV y facturas de reserva;
   - **inventario:** consumos de producción y balance de peso de las órdenes de fabricación.
3. Si nada cambió, no trae nada.
4. **Cada hora** trae clientes, artículos y stock, si están en `sap_sync_tipos` y solo si SAP cambió.
5. Envía a SAP las OV y guías del módulo pendientes, en las bases autorizadas.

**Botón «Actualizar con SAP»:** deja el pedido al vigilante, que lo atiende **en segundos** y revisa todo sin esperar el minuto. Si el vigilante no está corriendo, la web hace la misma revisión en segundo plano.

**Importante sobre las OV:**
- Lo que entra de SAP se registra en una carga. Se aplica sola si el tipo está en `sap_autoconfirmar`, por ejemplo `["OV", "CLIENTES", "PRODUCTOS"]`.
- Si no, queda **para revisar y confirmar**, como se decidió para la marcha blanca. Si quieren que todo lo de SAP se aplique solo, configuren ese parámetro.
- El historial, las facturas, las notas de crédito y las facturas de reserva se aplican siempre solas.

**Instalación:**
- La actualización automática (`deploy/actualizar.sh`) instala, habilita y reinicia el servicio. Como el script que corre es el anterior, el servicio queda activo **en la siguiente actualización** después de esta.
- El verificador (`verificar_servidor.sh`) revisa que esté activo.
- Para activarlo a mano de inmediato:

```
sudo install -m 644 /opt/operaciones/deploy/operaciones-sap.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now operaciones-sap
sudo journalctl -u operaciones-sap -f      # ver lo que hace
```

Necesita `SAP_SYNC_USER` (p. ej. `sistemas`) en `/etc/operaciones/operaciones.env`. Si no está, usa el primer usuario de Sistemas. La sincronización que corría dentro de la web se detiene sola mientras el vigilante esté activo.

## 2. Listas

| Pedido | Implementación |
|---|---|
| Todas las listas, incluidas las de OV abiertas y cerradas, filtrables por fecha o mes | Ver el punto 2.1. |
| Filtro de día y mes con un calendario chiquito | Ver el punto 2.1. |
| Ordenar por fecha (de últimas a primeras o al revés) | Ver el punto 2.1. |
| Listas largas con paginador | Ver el punto 2.2. |
| Buscar con un campo y la lupa en todas las listas | Ver el punto 2.3. |
| Buscador de clientes: buscar lo escrito, limpiar con la X, al costado del filtro | Ver el punto 2.4. |

### 2.1 Fechas, mes y orden

El buscador de cada lista («Buscar en la lista») tiene ahora:
- **Desde / Hasta**, con calendario;
- **Mes**, con calendario de mes;
- **Orden por fecha**: más recientes primero o más antiguas primero.

Detalles:
- Se usa la fecha principal de cada lista: en las OV, la comprometida; en otras, la de creación.
- **Quitar búsqueda** limpia los filtros de texto y de fecha.
- Al tocar un encabezado de fecha (**Fecha, Comprometida, Emisión, Llegada, Vence**…) se ordena de últimas a primeras, y al volver a tocarlo, al revés.
- Los selectores de mes de **Órdenes vs guías** y **Demanda proyectada** son ahora un **calendario de mes**.

### 2.2 Paginador

Tienen paginador las listas que no lo tenían:
- órdenes vs guías;
- notas de crédito sobre OV;
- facturas de reserva;
- clientes sin movimiento;
- balance de peso;
- guías, facturas y notas de crédito del cliente;
- ejecución de la demanda.

Antes se cortaban en 300 o se mostraban completas.

### 2.3 Buscador con lupa

Todas las listas de la ronda anterior y las anteriores tienen buscador con lupa. Busca al pulsar Enter o la lupa.

### 2.4 Buscador de clientes (y de todo selector con buscador)

- El campo de búsqueda quedó **al costado** de la lista, no encima. Por ejemplo, en Expedientes por cliente y despacho.
- Al escribir, elige el cliente que **mejor coincide con lo escrito**: el nombre exacto, luego el que empieza igual, luego el que lo contiene. Antes tomaba el primero que contenía el texto.
- Con **Enter o la lupa** busca por ese cliente.
- La **«X»** del buscador limpia el cliente elegido y vuelve a buscar sin ese filtro. Lo mismo en todos los buscadores de las listas.

## 3. Alertas y tareas por área

- Al entrar, se ven **tarjetas por área** (Compras, Almacén, Logística…) con el número de alertas abiertas:
  - en **rojo** si hay urgentes abiertas;
  - en **amarillo** si hay tareas por atender;
  - en **verde** si no hay nada pendiente.
- Al **tocar un área** se despliega su lista, con paginador, buscador y fechas, y el enlace «Todas las áreas» para volver.
- **«Ver todas en una sola lista»** muestra la lista completa, como antes.
- Con cualquier filtro aplicado se ve directamente la lista.

## 4. Compras

Corrección de la ronda anterior, según su indicación:
- Compras adquiere el **granel** y, **eventualmente, MP o MQ**, con su orden de compra.
- Solo el **PT** no se compra (`compras_no_comprables` = `["PT"]`): lo fabrica la empresa.
- La reposición automática sigue igual: PT, MQ y MP generan pre-solicitudes de **producción** y el granel, de **compra**. Comprar MP o MQ es una decisión manual cuando haga falta.

**Pregunta:** dijeron «solo compra GR y eventualmente MP, MQ». Hoy también se pueden pedir **insumos** (envases, etiquetas, suministros), porque la lista de materiales los necesita y no hay otro proceso del módulo que los compre. Si esa compra la hace otra área fuera del módulo, me lo indican y los bloqueo también.

## 5. Verificación

- `tests/test_v32.py` (5 pruebas):
  - vigilante: la primera revisión trae todo, sin cambios no trae nada, con una OV nueva solo trae OV e historial, y el botón fuerza todo;
  - el botón con el vigilante activo deja el pedido;
  - listas por fecha, mes y orden;
  - alertas por área;
  - compras de GR y, eventualmente, MP o MQ.
- Ajustes a pruebas anteriores: `test_v31` (el botón usa la revisión del vigilante; la MP se puede comprar).
- Revisión en navegador:
  - tarjetas de alertas por área;
  - expedientes con el buscador del cliente al costado;
  - lista de OV con fechas, mes y orden.
- Suite completa: **624 pruebas, todas pasan**.
