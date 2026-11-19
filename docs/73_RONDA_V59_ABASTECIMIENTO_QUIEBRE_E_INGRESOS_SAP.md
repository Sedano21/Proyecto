# Ronda V59 (19-nov-2026): abastecimiento: quiebre de stock, origen nacional o importado e ingresos en SAP

## Observaciones
- El Coordinador de Importación y el Asistente de Compras e Importaciones también deben ver la proyección de demanda.
- El Coordinador de Compras compra solo producto nacional y el Coordinador de Importación trae el importado. Piden
  granel cuando se está acabando el stock. Como excepción, Compras nacionales a veces pide MP.
- Hay que anticiparse con la suma de lo que sale en las OV de cada producto. Puede que justo ese día, o dos días antes,
  entre un pedido que se coma el stock de reserva, y el punto es no llegar a cero.
- Hay que analizar si conviene traer cada producto importado o nacional.
- Debe verse en una pestaña lo ya registrado en SAP como ingreso, para monitorearlo y no pedir de más ni de menos.

## Qué cambió
**Roles.**
- El rol «Asistente de Importaciones» pasa a llamarse **Asistente de Compras e Importaciones**.
- Él y el Coordinador de Importación reciben `demanda.ver` (Proyección de demanda, en el menú de Almacén) y
  `compras.ver`.
- El Coordinador de Compras ya lo tenía.
- No se cambió qué puede registrar cada uno: el asistente sigue registrando lo mismo que el Coordinador de
  Importación.

**Nueva pantalla «Abastecimiento (quiebre y por ingresar)»** (`/gestion/abastecimiento`, menú principal).
- Por defecto, el Coordinador de Compras ve lo nacional y el de Importación y su asistente, lo importado; se puede
  cambiar el filtro.
- **Proyección de quiebre.** Para el granel, los insumos, la MP y todo lo que tenga OC en SAP (nunca el PT), recorre
  día a día los próximos 60 días (`abastecimiento_horizonte_dias`):
  - parte del **stock libre** de hoy, sin lo ya reservado para OV;
  - resta lo que falta salir de cada **OV abierta en su fecha comprometida**;
  - suma lo **por ingresar de las OC abiertas de SAP** en su fecha de entrega;
  - pasada la última OV conocida, resta el consumo diario histórico.

  Muestra:
  - la fecha en que el saldo baja de la **reserva** (stock mínimo + stock de seguridad) y la fecha en que llegaría a
    cero;
  - las **OV que se comen la reserva** ese día;
  - la fecha límite para pedir (quiebre − plazo del origen sugerido);
  - la cantidad a pedir para no bajar de la reserva, menos lo ya solicitado en el módulo sin OC.
- **Origen sugerido.** Se basa en las OC de SAP del último año: país del proveedor (nacional si es el de
  `pais_empresa`, PE), costo unitario en soles y plazo (entrega − fecha de la OC).
  - Si solo una vía llega antes del quiebre, esa.
  - Si llegan las dos, la más barata.
  - Si ninguna llega a tiempo, la más rápida.
  - Si solo hay historial de una vía, esa.
  - Sin historial, «por definir».
  - La **MP** siempre es nacional (Compras).
  - Indica el responsable (Coordinador de Compras o de Importación) y el porqué.
- **Por ingresar (OC abiertas en SAP):** cada OC con lo pedido, lo recibido, lo que falta ingresar, la fecha de
  entrega (marca las vencidas), el proveedor y el origen.
- **Ya ingresado (entradas en SAP):** las entradas de mercancías de compra del periodo, con cantidad y valor.

**Lectura de SAP.** El vigilante lee también las entradas de mercancías de compra (PurchaseDeliveryNotes) y el país de
cada proveedor (BusinessPartners.Country) y los guarda junto a las OC (migración 0053). La primera vez relee todo.

**Reposición existente (V31).** «En camino» ahora es el saldo por ingresar de las OC abiertas de SAP más las
solicitudes del módulo que aún no tienen OC, para no contar dos veces lo que ya está en SAP.

## Por confirmar
- **Nacional o importado:** se separa por el país del proveedor en SAP. Si algún proveedor nacional representa a uno
  extranjero, o al revés, hará falta otro criterio, por ejemplo la serie de la OC.
- **Asistente de Compras e Importaciones:** si también debe registrar compras nacionales como el Coordinador de
  Compras, hay que darle esos permisos.

## No verificado
No se probó contra la base real de SAP.

**Pruebas:** `tests/test_v59.py`. Suite completa: 698 pruebas pasan.
