# Ronda V60 (19-nov-2026): plan de abastecimiento por grano (método del Excel Maestro)

## Observaciones
- El análisis de compras nacionales e importaciones debe ser como el de la presentación de la Jefatura de Operaciones
  a Gerencia, basada en el «Excel Maestro de Abastecimiento».
- El Excel «proyectado nov 26» es la proyección de demanda de Comercial.
- Hay que registrar unidades de flota: placa, marca y capacidad.
- En Compras nacionales seguía apareciendo PT: Compras solo compra granel y, como excepción, MP de harinas y quinua.

Los archivos se usaron solo para conocer el método y el formato. No se guardaron en el repositorio y las copias
locales se borraron.

## Plan por grano
Pantalla **Abastecimiento → Plan por grano** (`/gestion/abastecimiento`, pestaña por defecto).
- Cada grano agrupa todos sus códigos GR, MP, PT y MQ, en toneladas.
- El Coordinador de Compras ve lo nacional; el de Importación y su asistente, lo importado.
- Tocando un grano se abre su explicación (`/gestion/abastecimiento/grano`), con las mismas secciones de la
  presentación:
  1. OV abiertas pendientes;
  2. demanda del horizonte por cliente;
  3. cálculo de la compra;
  4. destino;
  5. venta mensual.

**Cálculo** (servicio `plan_granos`; los supuestos son parámetros con los valores del Excel):

| Paso | Regla |
|---|---|
| Grano del artículo | El nombre o alias más largo de «abastecimiento_granos» contenido en la descripción (antes del «*»). Si no hay ninguno, OTROS. Los 28 granos del Excel vienen con su origen nacional o importado. |
| Venta mensual | kg despachados con guías de SAP en los 12 meses completos anteriores. |
| Demanda base | Promedio de 6 meses; el de 3 meses si difiere más del 30 %. Por grano se puede fijar otra base: 3m, 6m, 12m o Proyección Comercial. |
| Demanda del horizonte (LT + revisión) | Por cliente, lo mayor entre su OV vigente (≤ 60 días) y su recompra habitual: venta de 6 meses / 6 × k × horizonte / 30. Las OV de más de 60 días se muestran «a confirmar» y no se cuentan. |
| Estado del cliente | Ocasional: ≤ 2 compras en 6 meses. Inactivo: sin comprar más de 3 veces su frecuencia y más de 120 días; no se cuenta. Atrasado: pasó su frecuencia. Activo: el resto. Estas reglas se definieron para el módulo (la presentación no las detalla) y son ajustables. |
| Factor MP | (1 − %procesado) + %procesado / (rend. selección × rend. envasado). |
| Stock de seguridad | z(ABC) × min(σ, base) × √(LT/30) × factor MP. z: A 1,65 · B 1,28 · C 1,04. ABC por valor de venta: A hasta 80 %, B hasta 95 %. XYZ por CV: X ≤ 0,5, Y ≤ 1. |
| Punto de pedido | Base × factor MP × LT / 30 + stock de seguridad. |
| Compra sugerida | Demanda del horizonte × factor MP + SS − stock utilizable − en camino. Importado: redondeo a FCL (24 t; Canario 22,68 t). Nacional: redondeo a 1 t. |
| Emitir OC | Hoy si la posición (stock + en camino − OV) ya está bajo el punto de pedido; si no, la fecha en que llegaría a él. |
| Agotamiento | Simulación diaria con las llegadas en su fecha. A: solo OV. B: lo mayor entre OV y la venta histórica. C: igual con la proyección de Comercial. D: OV + recompra (el plan). |
| Compra puente (importado) | Venta del plan entre el agotamiento D y la llegada de una OC emitida hoy. |
| Clasificación | Importación inmediata o programada; compra inmediata (cobertura ≤ LT), prioritaria o programada; requiere validación (clase C); no comprar (baja rotación si cubre más de 180 días). |
| Destino | Granel / MP seleccionada / PT según la mezcla de venta de 6 meses. |
| Stock utilizable | Lotes utilizables del módulo; con «abastecimiento_almacenes_utilizables» se limita a esos almacenes (si está vacío, todos). |
| En camino | Saldo de las OC abiertas de SAP. Las de más de 60 días se muestran «por depurar» y no se cuentan. |
| Precio y presupuesto | S/ por kg de las OC de SAP del último año. |

**Supuestos editables** (Parámetros, grupo Compras, «abastecimiento_…»):
- lead time de importación 50, nacional 7 y harinas 10 días;
- revisión de importación 30 y nacional 15 días;
- z por clase;
- rendimiento de envasado 0,98 y de selección 0,95 por defecto;
- OV firme hasta 60 días;
- OC por depurar desde 60 días;
- cambio de tendencia 30 %;
- kg por FCL;
- días de simulación.

## Proyección de Comercial
«Proyección de demanda → Cargar» acepta el archivo de Comercial tal cual: hojas IMPORTADO y NACIONAL con «CODIGO DE
PRODUCTO», «UM» y «CANTIDAD PROYECTADA».
- El mes se toma del título («PROY NOV 26») o del campo del formulario.
- Los kg se pasan a la unidad del producto con su peso.
- Sigue aceptando la plantilla anterior (mes, producto, cantidad).

## Compras nacionales: no se compra PT, MQ ni MP
- «compras_no_comprables» pasa a PT, MQ y MP. La MP solo se compra si su descripción contiene una palabra de
  «compras_mp_excepciones» (HARINA, QUINUA).
- Al abrir Compras nacionales:
  - se cancelan solas las solicitudes abiertas de lo que no se compra que aún no llegaron a cotización;
  - de las que ya están en Compras, se avisa.
- La lista ya no muestra las canceladas por defecto.

## Flota
La flota ya permite registrar placa, marca y capacidad en kg (Distribución → Flota). Las unidades se registran ahí: las
placas son datos reales y no se guardan en el repositorio.

## No verificado
No se probó contra la base real de SAP. La venta es lo despachado con guías, no la venta neta de facturas menos notas
de crédito que usa el Excel.

**Pruebas:** `tests/test_v60.py`. Suite completa: 704 pruebas pasan.
