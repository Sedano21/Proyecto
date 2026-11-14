# Ronda V35 (14-nov-2026): guías sincronizadas con SAP, préstamo por inventario negativo e ingreso de mercadería

Pruebas con datos ficticios.
- **Migración nueva:** **0044**.
- **Escritura en SAP:** nueva, el **ingreso de mercadería**. Solo en las bases autorizadas (`sap_escritura_empresas`).

## 1. Las guías y las OV se actualizan con SAP

**Guías SUNAT del módulo:**
- Cada vez que se lee SAP (vigilante cada minuto, «Actualizar con SAP» o «Actualizar historial»), cada guía que no figura en SAP se busca entre las guías de SAP por su serie y número (EG07-457 = EG07-00000457).
- Si alguien ya la registró en SAP, la guía queda **«EN SAP»** sola, con su entrega. Si tenía un préstamo pendiente, se da por resuelto.

**OV del módulo:**
- El detalle de la OV y la tarea de picking muestran **«Guías de esta OV en SAP»**: número, fecha, producto y cantidad de cada guía relacionada en SAP.
- La búsqueda usa el número de la OV o el número que SAP le asignó.
- Se actualiza sola con el vigilante.

## 2. «Quantity falls into negative inventory»: préstamo

**Qué significa el error:** SAP **ya no tiene ese stock**. En su caso, se descontó el mismo día por el reconteo del inventario, así que la entrega dejaría el inventario en negativo.

**Qué hace ahora el sistema:**
1. Guarda el error en la guía, que antes se perdía, y la marca con **«PRÉSTAMO PENDIENTE»**.
2. Envía la alerta **«Préstamo»** (alta) a la **Jefatura de Operaciones, la Coordinación de Distribución y la Jefatura de Logística**, con los productos, lotes y cantidades.
3. **No toca el inventario del módulo.** La decisión «ya se descontó / descontar ahora» que llega al Jefe de Operaciones («INVENTARIO POR DECIDIR») sigue igual, para no descontar dos veces.

## 3. Ingreso de mercadería a SAP (Jefatura de Operaciones)

**Dónde:** pantalla nueva **Distribución → «Ingreso de mercadería a SAP»** (permiso `stock.ingreso_sap`, por ahora solo la Jefatura de Operaciones).

**Datos que pide:**
- **fecha**;
- **almacén de SAP**;
- **motivo**;
- por cada producto: **producto, lote, cantidad, fecha de producción, fecha de vencimiento** y **costo unitario** (opcional; sin costo, SAP usa el del artículo).

**Desde una guía con préstamo pendiente:** el botón **«Registrar el ingreso (préstamo)»** abre el formulario ya lleno con los productos y lotes de la guía.

**Al registrar:**
1. Se crea en SAP la **entrada de mercancías** (InventoryGenEntries), con el lote, la FP y la FV.
2. Si está unida a una guía, la **guía se vuelve a enviar a SAP sola**, y el préstamo queda «INGRESADO».
3. Si SAP rechaza algo, se muestra el motivo y queda registrado.

**Stock del módulo:** no se toca aquí; lo actualiza la siguiente carga de stock de SAP. Así no se cuenta dos veces.

**Para confirmar con ustedes:**
- **Cuenta contable** de las entradas: hoy SAP usa su cuenta de compensación por defecto. Si contabilidad quiere otra, se configura en `ingreso_mercaderia_cuenta`.
- Si además de la Jefatura de Operaciones otros perfiles deben registrar ingresos, se agrega el permiso.

## 4. Verificación

- `tests/test_v35.py` (3 pruebas):
  - préstamo por inventario negativo e ingreso de mercadería con lote, FP y FV, con la guía reenviada sola;
  - pantallas del préstamo y del ingreso;
  - guías SUNAT y OV que se actualizan con las guías de SAP.
- Migración 0044 aplicada sobre una base nueva: la base coincide con el código.
- Suite completa: **633 pruebas, todas pasan**.

## 5. Ajuste V36: «Inventory account is not defined [DocumentLines.AccountCode]»

**Qué significa el error:**
- SAP no pide el costo: pide la **cuenta contable de compensación** de la entrada de mercancías.
- En su SAP esa cuenta no está definida en la determinación de cuentas del almacén ni del grupo de artículos. Por eso, en una entrada de mercancías sin documento base, SAP exige indicarla en cada línea.

**Qué cambió:**
- Se quitó la columna de **costo**: el préstamo se ingresa sin costo, como lo hace la empresa, y SAP usa el costo del artículo.
- Se agregó el campo **«Cuenta contable de compensación»**. Se puede dejar por defecto en Parámetros → `ingreso_mercaderia_cuenta`.
- Cuando SAP rechaza un ingreso, la lista explica qué falta. El botón **«Reintentar en SAP»** lo vuelve a enviar con la cuenta, sin digitar de nuevo; si estaba unido a una guía, también la reenvía.
- El mensaje de rechazo ahora se muestra como error y no como aviso verde.

**Lo que hace falta de ustedes:**
1. Pedir a **Contabilidad la cuenta que usan para los préstamos** cuando los registran en SAP.
2. Registrarla en el parámetro o escribirla en el ingreso #1.
3. Pulsar **«Reintentar en SAP»**.

**Prueba agregada:** `test_ingreso_sin_cuenta_contable_y_reintento`. SAP rechaza el ingreso sin cuenta, el reintento con la cuenta pasa y el préstamo va sin costo.

## 6. Ajuste V37: la cuenta «2841119-00-00» seguía dando el mismo error

**Causa:** el plan de cuentas de SAP está **segmentado**.
- «2841119-00-00» es el código **visible** de la cuenta.
- El Service Layer espera su **código interno**, distinto del visible (p. ej. «_SYS00000000315»).
- Con el código visible, SAP no encuentra la cuenta y responde otra vez «Inventory account is not defined».

**Corrección:**
- El sistema busca la cuenta en el **plan de cuentas de SAP**, por el código interno, el formato visible o el formato sin separadores, y envía el **código interno**.
- La cuenta se sigue escribiendo tal como se ve en SAP. Si no existe, el ingreso lo dice.
- Al quedar en SAP, el ingreso guarda el código interno y el nombre de la cuenta.
- Si el usuario de integración no tiene permiso para leer el plan de cuentas, se envía tal como se escribió.

**Qué hacer:** pulsar **«Reintentar en SAP»** en los ingresos #1 y #2, con 2841119-00-00. No hace falta digitar nada más.

## 7. Ajuste V38: «(59) Debe indicar el tipo de operación de inventarios»

La cuenta contable ya pasó. Ahora lo que rechaza es una **validación de la localización peruana de su SAP**: la entrada de mercancías debe llevar el **tipo de operación de inventario**, el código de la tabla 12 de SUNAT. Es un **campo de usuario** de SAP; en la OV se ve en el panel izquierdo como «Tipo Operación».

**Cómo se resolvió:**
- El sistema **lee de SAP los campos de usuario** de la entrada de mercancías, de la cabecera y de las líneas: el tipo de operación y los demás que SAP marca como obligatorios o que tratan de tipo o motivo. Los lee con sus **valores válidos**.
- La lectura se hace sola cuando SAP rechaza por este motivo, o con el botón **«Leer campos de SAP»**.
- En el formulario y en «Reintentar en SAP» aparece **«Datos que pide SAP»**, con una lista para elegir el valor, p. ej. «99 · Otros». Se envía en el campo exacto de SAP.
- Se puede dejar un valor por defecto en Parámetros → `ingreso_mercaderia_valores`, p. ej. `{"U_XXXX": "99"}`, para no elegirlo cada vez.

**Qué hacer:**
1. Pulsar **«Leer campos de SAP»**, si la lista aún no aparece.
2. Preguntar a Contabilidad **qué tipo de operación usan para los préstamos**.
3. Elegirlo en el ingreso #1 o #2 y pulsar **«Reintentar en SAP»**.

**Prueba:** `test_ingreso_con_tipo_de_operacion_de_la_localizacion`. SAP rechaza sin el tipo de operación, se leen sus valores y el reintento con «99» pasa.
