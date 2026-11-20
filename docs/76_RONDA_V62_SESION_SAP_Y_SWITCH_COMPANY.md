# Ronda V62 (20-nov-2026): «Switch company error: -5027» y sesión de SAP del vigilante

## Observación
Datos de SAP mostraba «SAP respondió 500: Switch company error: -5027» y «SAP sin conexión desde 2026-11-20 09:52».

## Diagnóstico
El mensaje lo devuelve el **Service Layer de SAP** al intentar abrir la empresa (CompanyDB) en el ingreso. No es un
error del módulo: el Service Layer no pudo conectarse a la empresa. Lo habitual es revisar en el servidor SAP:
- el servidor de licencias;
- la base de datos de la empresa;
- las sesiones del Service Layer.

Mientras tanto el módulo funciona como está previsto: lo que se registra (OV, guías) queda en cola y se envía solo
cuando SAP vuelve.

Lo que el módulo sí podía mejorar: el vigilante **ingresaba y salía de SAP cada minuto**, una sesión nueva en cada
revisión. Eso carga justamente el paso que está fallando.

## Qué cambió
- **Una sola sesión.** El vigilante abre una sesión de SAP y la reutiliza entre revisiones, en lugar de un ingreso y
  una salida por minuto. Si SAP la da por vencida (401), el módulo vuelve a ingresar una vez y repite la llamada.
- **Reintentos espaciados.** Si SAP rechaza el ingreso (responde, pero con error), el vigilante registra el estado y
  espacia los reintentos automáticos: 2, 4, 8 minutos y luego cada 15 como máximo. El botón «Actualizar con SAP»
  sigue forzando un intento inmediato.
- **Mensaje.** El error -5027 explica qué revisar y que lo registrado queda en cola.

## No verificado
No se probó contra el SAP real. Si el error continúa, lo debe revisar el soporte de SAP del servidor (licencias,
base de la empresa y Service Layer).

**Pruebas:** `tests/test_v62.py`. Suite completa: 710 pruebas pasan.
