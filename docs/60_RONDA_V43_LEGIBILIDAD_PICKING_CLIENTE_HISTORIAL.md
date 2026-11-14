# Ronda V43 (14-nov-2026): gráficos legibles, un solo picking por cliente e historial del año anterior

Observación del usuario: la información se encimaba en los gráficos; agrupar por cliente donde corresponda (picking: un
solo picking por cliente y fecha de despacho); traer el historial de SAP para comparar con el mismo mes del año
anterior. **No se cambiaron reglas**: solo cómo se muestra la información y cómo se agrupa el trabajo.

## 1. Gráficos

- Columnas (`charts.columns`): el valor sobre la columna aparece solo si cabe, en formato compacto (858 k, 1,2 M); los
  ceros no se rotulan. Si no cabe, queda en el tooltip y en la tabla del gráfico (se avisa debajo).
- Eje Y con escala (0, 250 k, 500 k…); etiquetas del eje X inclinadas cuando son largas; leyenda debajo.
- En pantallas angostas el gráfico se desplaza en lugar de apretarse.
- Líneas (`charts.line`): solo las etiquetas que caben, sin cortar las de los bordes; eje con números compactos.
- Demanda: el eje muestra el inicio de cada periodo (dd/mm o mm/aaaa); el rango completo está en la tabla.
- Tablas: en computadora se desplazan dentro de su recuadro; solo en el celular se convierten en tarjetas (antes se
  desarmaban en tarjetas también en computadora cuando no entraban en media pantalla).
- Demanda: sin proyección cargada ya no se muestra «−100 %» ni «Caída fuerte», ni «None %».

## 2. Un solo picking por cliente y fecha de despacho

- «Programación de picking»: un bloque por cliente; dentro, sus OV por **fecha de despacho**, con el botón **«Un solo
  picking de las N OV · almacén»**.
- Pantalla del picking del cliente (`/almacen/picking/cliente/<cliente>/<fecha>/<almacén>`):
  1. validar la planificación pre-asignada de todas las OV a la vez;
  2. asignar una vez (a todas las OV);
  3. iniciar una vez (una foto);
  4. **lista consolidada** por producto y lote (suma de todas las OV, con FP/FV, ubicación y bultos; «por OV» muestra
     de qué OV sale): se registra lo pickeado y el sistema lo reparte entre las OV en orden;
  5. marcar listas todas las OV con una sola foto.
- Cada OV conserva su picking (las mismas reglas, controles y auditoría); la pantalla los hace juntos.
- «Preparación por prioridad y corte»: dentro de cada corte, agrupado por cliente y fecha de despacho.
- «Órdenes de venta y servicio vs guías»: vista «Por cliente» (órdenes por situación; al entrar, sus órdenes).

## 3. Historial de SAP del año anterior

- `sap_historial_desde` pasa de 2026-07-01 a **2025-01-01** (autorizado por el usuario). La siguiente lectura del
  vigilante trae todo una vez desde esa fecha; luego solo lo que cambie.
- Demanda: «vs mismo mes año anterior» y el promedio de 3 meses usan lo despachado según las guías de SAP (para los
  meses que SAP tiene; si no, las ventas cargadas).
- Nivel de servicio: «Mismo periodo del año anterior» con OTIF, on time, in full y fill rate de SAP y la diferencia
  en puntos frente a hoy.

**Pruebas:** `tests/test_v43.py`.
- Suite completa: **649 pruebas, todas pasan**.
