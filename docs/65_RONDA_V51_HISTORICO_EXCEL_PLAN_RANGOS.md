# Ronda V51 (17-nov-2026): histórico del Excel CONTROL DE PRODUCCION y planeamiento por rangos

Decisiones del usuario: cargar el histórico del Excel desde 2026; desde que se use el módulo, todo se registra en el
módulo; los nombres y DNI del personal se guardan en el módulo (son del personal). El archivo real se usó solo para
conocer el formato y probar la carga en una base local; **no se guarda en el repositorio**. Las pruebas usan un libro
ficticio con la misma forma.

## 1. Dónde se carga
**Producción → «Cargar histórico (Excel de control)»** (`/produccion/historico-excel`; Producción: liquidar o
programar). Se sube el libro tal cual. Al terminar muestra, por pestaña: dónde se cargó, cuántos registros nuevos,
cuántos ya estaban (se puede volver a subir: no duplica), cuántos sin producto reconocido y las filas no cargadas con su
motivo (sobre todo fechas mal digitadas: 2024, 2025, 2027, negativas).

## 2. Qué se carga de cada pestaña
| Pestaña | Destino |
|---|---|
| PROGRAMACION | Planeamiento diario (como «Actualizar con Excel»; un código que no existe en el maestro se busca por nombre) |
| IQ+CIMB, TRUER | Partes de selección: entrada = TOTAL (MP + calidad 3 + desmedro, cuadra con el % de rendimiento), salida MP, calidad 3, desmedro, % rendimiento, OF, estado, horas efectivas, ratio, maquinistas y colaboradores |
| SEL. MANUAL | Partes de selección manual: entrada = TOTAL MP-KG, desmedro, saldo; salida MP = entrada − desmedro − saldo; la seleccionadora con sus kg y horas (producción por persona) |
| ENV. MANUAL, ENVASADO R1 R2 R3, CANARIO SUMAQ | Partes de envasado: línea (RAUMAK 1/2/3 → R1/R2/R3), unidades, presentación, kg envasados, kg de MP, % rendimiento, OF, estado, horas, maquinista y colaboradores |
| (líneas) TIEMPO INACTIVO, REFRIG. U OTROS, CAUSA, PARADA DE MAQ. | Paradas: minutos = (tiempo inactivo − refrigerio) + parada de máquina, en horas × 60 (se comprobó que el tiempo inactivo incluye el refrigerio con las horas efectivas); causa |
| ASISTENCIA… | Colaboradores (por DNI, con línea y sublínea) y asistencia diaria: marcado = ASISTENCIA; sin marcar de lunes a sábado = FALTA, hasta el último día llenado (domingo sin marcar = descanso) |
| CONTROL DE MERMA, CONTROL MP-CAL 3, DESMT. Y/O TRANSF., REQ. DE MP, SUMINISTROS, hoja de OF de SAP («Hoja 31») | Histórico de movimientos (tabla nueva `historico_produccion`, migración 0047), visible en la misma pantalla con filtro por tipo y buscador; cada fila guarda todas sus columnas |
| REPORTE DE PRODUCCION, DASHBOARD, TABLERO, AdC, tablas dinámicas | No se cargan: son resúmenes con fórmulas que el módulo calcula (AdC con #REF!) |
| OV, STOCK ALM, Hoja 16, COD, EANS | No se cargan: llegan de SAP o se mantienen en Configuración |
| REQ | No se carga: asistencia antigua sin fechas |

- Producto de los partes: por código si lo hay; si no, por el nombre (sin adivinar). Sin coincidencia, el parte se carga
  igual con el nombre del Excel y se cuenta como «sin producto reconocido» (no cruza con el plan por producto).
- Los estados del Excel se llevan a los del módulo («LIQ. EXT.» → «LIQ. EXT. LIQUIDADO»); otro estado queda como
  LIQUIDADO con el estado original en la observación.
- Rango: `historico_produccion_desde` (1-ene-2026) hasta hoy.
- Prueba con el libro real (base local): ~5 700 registros (≈4 000 partes, ≈1 100 asistencias, movimientos), 7 s; las
  pantallas de partes, informe de producción, control y planeamiento responden en menos de 1 s.

## 3. Planeamiento: semanal y mensual por rango de fechas
- **Diario**: se elige cualquier día (‹ › y los días de la semana) — sin cambios.
- **Semanal / Mensual**: no se elige un día sino un **rango de fechas** (Desde/Hasta; atajos semana o mes anterior,
  actual y siguiente). Cada línea muestra lo programado en el rango frente a su capacidad del rango (kg/día × jornadas),
  el % de cada día del rango (clic → ese día en el Diario) y la lista de lo programado en el rango.

**Pruebas:** `tests/test_v51.py`.
- Suite completa V51: **672 pruebas, todas pasan**.
