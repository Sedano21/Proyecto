# Ronda V48 (16-nov-2026): lo que falta con el stock real de SAP, guía de remisión completa en SAP y plan diario

Solo datos ficticios en pruebas. No verificado contra la base real de SAP.

## 1. «Traer lo que falta» usaba un stock viejo
Usaba la última carga de stock de SAP del módulo (12/11), por eso salía stock 0. Ahora consulta **SAP en el momento**:
- Con la consulta de stock por lote configurada en `sap_consultas` («STOCK»): por artículo, **lote** y almacén.
- Sin ella: por artículo y almacén (entidad estándar `Items` → `ItemWarehouseInfoCollection`); el stock del artículo se
  reparte entre sus líneas de la guía en orden (SAP no da el lote por esta vía).
- Si SAP no responde, se usa la última carga de stock y se avisa en pantalla. La pantalla dice de dónde salió el stock.

## 2. Panel «Guía de remisión» de la entrega en SAP
La asistente también llena en SAP: modalidad de traslado, motivo de traslado, transportista (RUC, nombre, dirección),
conductor (nombre, licencia), placa, marca, fecha de inicio de traslado, peso, motivo / otros. Ahora:
- Al subir la guía se leen del XML (modalidad, código de motivo, transportista, conductor, licencia, peso bruto) y, en
  lo posible, del PDF; todo se puede completar o corregir en «Editar la guía» (sección Transporte).
- Al enviar a SAP, se leen los campos de usuario de la entrega (`UserFieldsMD` de ODLN) y se llenan los que se
  reconocen por su descripción (placa, licencia, conductor, marca, transportista, modalidad, motivo, fechas, peso, UM).
  En los campos con lista de valores se elige el valor cuya descripción coincide (p. ej. «Transporte Privado»).
- Se envía solo lo que la guía tiene. Lo enviado queda en el registro de la guía.
- Migración `0046` (columna `transporte` en `sunat_guides`).

## 3. Plan del Excel solo se veía en «Semanal»
El plan se guardaba con la periodicidad de la pestaña abierta al subir. Ahora el Excel se guarda siempre **por día**
(trae fechas por día) y las vistas **semanal y mensual suman el plan diario** (salvo que exista un plan semanal o
mensual propio para ese producto y periodo).

**Pruebas:** `tests/test_v48.py`.
