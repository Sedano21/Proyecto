# Ronda V28 (11-nov-2026): ejecución de la demanda, importaciones (historial y retrasos) y conductores en Flota

Pruebas con datos ficticios. Migración nueva: **0040**.

| Pedido | Implementación | Dónde |
|---|---|---|
| Proyección de demanda: ver la ejecución del mes con un rango de fechas, con las OV abiertas, cerradas o incompletas | Filtro **Desde / Hasta**. Por defecto es el mes elegido; al cambiar de mes se vuelve al mes completo. El cumplimiento usa ese rango. Sección nueva **«Ejecución del periodo»** con las OV cuya fecha comprometida cae en el rango, en tres grupos que también sirven de filtro: **Abiertas** (sin despacho), **Incompletas** (despacho parcial, o cerradas con saldo) y **Cerradas** (atendidas completas). Cada grupo muestra cuántas OV hay y los kg pedidos y despachados. Por cada OV: pedido, despachado y % de avance. Se incluye en el PDF y el Excel del informe. | Análisis → Demanda proyectada |
| Cuadro de importaciones como el de la empresa y alerta por la fecha máxima de retiro | El cuadro ya tenía las columnas del Excel de la empresa: código SAP, contrato, proveedor, ítem, país, contenedores, llegada, días libres, fecha máxima de retiro, SENASA, BL, retiro y almacén. También tenía las alertas: a 5, 2 y 0 días de la fecha máxima de retiro, y sobreestadía cuando se pasa. Se mantienen. | Seguimiento de importaciones |
| SENASA y BL: saber qué día y a qué hora cambió cada status | Cada cambio de SENASA, BL, llegada o retiro queda con **día, hora y usuario**. Bajo cada status se ve la fecha y hora del último cambio. El botón **«Historial»** muestra todos los cambios (de → a, quién y motivo). | Ídem |
| Botón para indicar un retraso (motivo y fecha modificada) | Botón **«Retraso»** para el Coordinador y el Asistente de Importaciones. Se indica qué se retrasó (SENASA, liberación de BL, llegada del buque o naviera, retiro del contenedor u otro), el **motivo** y la **fecha modificada**. Si es de llegada o retiro, se actualiza esa fecha en el cuadro. Queda en el historial y se ve en la fila («Retraso: … → fecha»). Avisa a Gerencia Adjunta e Importaciones; si la nueva fecha pasa la fecha máxima de retiro, la alerta es **alta** por riesgo de sobreestadía. | Ídem |
| Flota y conductores: que aparezcan los usuarios con perfil de conductor | Cada usuario activo con perfil **Conductor** aparece solo en «Conductores», con la marca **USUARIO**. Su ficha se crea vinculada a su usuario, y su nombre se actualiza si él lo corrige en «Mi cuenta». El botón pasa a ser **«Agregar conductor externo»**, para los que no tienen usuario. | Distribución → Flota y conductores |

**Verificación:**
- `tests/test_v28.py` (3 pruebas):
  - ejecución abiertas, incompletas y cerradas, con la pantalla filtrada;
  - historial de status y retrasos, incluida la alerta de sobreestadía;
  - conductores con usuario en Flota.
- Prueba de migraciones hasta la 0040.
- Revisión en navegador del cuadro y del historial.
