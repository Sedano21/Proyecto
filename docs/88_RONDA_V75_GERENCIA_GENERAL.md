# Ronda V75 (25-nov-2026): inicio de Gerencia General

Fuente: el mensaje del usuario del 25-nov («gerencia general»). Las pruebas usan solo datos ficticios.

## Qué se hizo

### Devoluciones por recibir
- La tarjeta del inicio ahora se llama **«Devoluciones generales por recibir»**. Cuenta solo las devoluciones totales:
  - las pendientes;
  - las que quedaron en el vehículo.
- La tarjeta lleva a la pantalla de devoluciones ya filtrada por generales.
- La pantalla de devoluciones tiene un filtro nuevo: todas, generales (totales) o parciales.

### Resumen de Calidad en el inicio
Tarjetas nuevas, cada una con enlace a su pantalla:
- inspecciones del mes (y cuántas siguen abiertas);
- reempaques en curso (por evaluar y por ejecutar);
- lotes por revisar, observados o bloqueados;
- fumigaciones en curso;
- certificados en borrador;
- no conformidades y quejas del mes.

### Compras nacionales e importaciones en el inicio
- compras nacionales abiertas (y cuántas esperan aprobación);
- compras atrasadas (fecha prevista vencida);
- importaciones en curso (y cuántas tienen la llegada vencida);
- importaciones retiradas sin informe de Calidad.

### Comercial: OV con entrega en el mes
- Tarjeta nueva **«OV con entrega en el mes»**: OV emitidas, no canceladas, cuya fecha de entrega cae en el mes en curso.
  Muestra:
  - la cantidad de OV;
  - el monto;
  - cuántas falta despachar.
- Lleva a la lista de OV filtrada por fecha de entrega. La lista acepta ahora los filtros «entrega_desde» y
  «entrega_hasta».

### Sugerencias para mejorar la eficiencia: productividad por área
- Arriba de las sugerencias hay un resumen **«Productividad por área»** de los últimos 30 días:
  - **Producción:** kg por hora y kg por hora-operario.
  - **Almacén:** minutos por picking (mediana).
  - **Distribución:** espera en el cliente (mediana).
- Sugerencias nuevas, calculadas con los registros del propio sistema:
  - **Producción:** productos que se procesan mucho más lento que la mediana de su misma línea.
  - **Almacén:** almacenes con muchos pickings mucho más largos que lo usual.
  - **Distribución:** clientes con espera mucho mayor que la del resto.
  - **Compras e Importaciones:** compras con la fecha prevista vencida e importaciones con la llegada vencida.
  - **Calidad:** lotes por revisar, observados o bloqueados, y reempaques por evaluar.
- Se puede filtrar por área.
- «Mucho más lento» se mide con el parámetro «sugerencias_productividad_umbral_pct», propuesto en 70 %. Por ejemplo,
  un producto que rinde menos del 70 % de la mediana de su línea.

### Venta del año anterior junto al OTIF
- En «Nivel de servicio» ya se comparaba el OTIF del mismo periodo del año anterior, con SAP. Ahora también se compara la
  venta, sin IGV, con su variación:
  - **venta en OV**: el monto de las OV de venta con fecha de entrega en el periodo, el mismo universo del OTIF;
  - **facturado neto**: facturas menos notas de crédito de SAP emitidas en el periodo.

## Por decidir

| Punto | Situación |
|---|---|
| «Devoluciones generales» | Lo interpreté como devoluciones totales (el tipo TOTAL), frente a las parciales. Si «generales» significa otra cosa, es un cambio pequeño. |
| Umbral de las sugerencias de productividad | 70 % de la mediana (propuesto), ajustable. |

## Pruebas
`tests/test_v75.py` (4 pruebas).
