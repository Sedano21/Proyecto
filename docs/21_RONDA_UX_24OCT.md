# Ronda UX/UI del 24-oct-2026

Objetivo aplicado en cada pantalla modificada: menos carga por pantalla, divulgación progresiva (ventanas, paneles
laterales y asistentes por pasos), tarjetas en lugar de tablas con filas vacías, y lápiz en todo lo editable.

Componentes comunes (`app/static/ux.js`, estilos al final de `style.css`):
- `dialog.modal` / `dialog.drawer` + botón `data-open` (los valores se pasan con `data-set-*`).
- Asistente por pasos `form.wizard` (valida cada paso antes de avanzar).
- Tarjetas según cantidad `data-repeat`: al indicar N se muestran solo N tarjetas.
- Horas en 12 h o 24 h `data-hora` (parámetro `formato_hora`; se aceptan ambos al escribir).
- Selector con búsqueda `select[data-search]`, firma en pantalla `canvas[data-signature]`, recarga periódica `data-refresh`.

## 1. Producción
| Pedido | Cómo quedó |
|---|---|
| Personal dinámico | Al finalizar el parte se indica el número de operarios y aparece una tarjeta por persona |
| Solo colaboradores registrados | Cada tarjeta elige de la lista de Asistencia; el servidor rechaza nombres no registrados, repetidos o más personas que operarios |
| Un solo formato con «Registrar» y «Programar» | «Nuevo parte» (panel lateral en 3 pasos). Registrar inicia hoy; Programar deja fecha y horario. Se retiró el segundo formulario |
| Editable salvo liquidado / terminado; «Pendiente de: motivo» | Lápiz en cada tarjeta (fecha y cantidad, con motivo) mientras no esté LIQUIDADO, LIQ. EXT. LIQUIDADO o ANULADO. Al finalizar queda «Pendiente de: liquidación de la OF en SAP»; pasar a PENDIENTE exige el motivo |
| Programación en tarjetas | Partes programados y programa del planeamiento en tarjetas con lápiz (fecha y cantidad) |
| Hora de fin | No menor que la de inicio ni que la hora actual: al programar se valida; al finalizar, la hora de fin es la del cierre |
| 12 h y 24 h | `formato_hora` en Configuración de Producción |
| Validación por producto y paquete en tiempo real | En envasado: producto terminado, presentación del artículo, EAN contra la tabla GS1, unidades por paquete enteras, pallets en paquetes enteros, unidades sueltas menores que un paquete; producción ideal en pantalla; rendimiento y desmedro en vivo al finalizar (avisa si queda fuera de tolerancia) |
| Planeamiento sin selector duplicado | El formulario toma la periodicidad del selector superior |
| Receta con lápiz y validación de categoría | Lápiz por componente; el reemplazo solo ofrece y acepta el mismo grano (MP / granel) o la misma categoría de envase o insumo |
| Monitoreo en tiempo real | Producción → Monitoreo: partes en curso y del día con rendimiento y desmedro (parciales con los pallets registrados), se actualiza cada minuto |
| Liquidación parcial filtrable por fecha | Desde la solicitud se marca «parcial»: la solicitud sigue en proceso hasta completar la cantidad. Liquidaciones: filtros por fecha, tipo (parcial / total) y producto |

## 2. Distribución y transporte
- **GEOSATELITAL**: Distribución → Rastreo. Se conecta solo cuando Sistemas configura el servicio del proveedor en el
  servidor (`GEOSAT_API_URL`, `GEOSAT_TOKEN`) y, si el proveedor lo permite, su panel (`geosatelital_url_panel`). Sin
  configuración no hay conexión y se muestran las unidades con sus rutas del sistema. **Pendiente**: la documentación del
  servicio de GEOSATELITAL (se reconocen los nombres de campo más comunes; ajustar al formato real).
- **SOAT**: una unidad sin SOAT vigente no se asigna a rutas (propuesta automática, ajuste y confirmación) y se alerta
  (`exigir_soat_vigente`). La flota muestra el estado del SOAT de cada placa.
- **Incidencias**: panel por pasos: OV en ruta (selector con búsqueda) → ítems de esa OV con su novedad y lo devuelto.
- **Conformidad digital del chofer**: «Mis entregas» del chofer: «Llegué» y la conformidad en 3 pasos (nombre y DNI de
  quien recibe, firma en pantalla, foto de la entrega y guía firmada). Solo la registra el chofer de la ruta (permiso
  `distribucion.conformidad`); ya no el auxiliar.

## 3. Mantenimiento (nuevo módulo)
- Preventivo: tareas por unidad cada N km y/o N días; alerta próxima o vencida (`margen_km_mantenimiento`,
  `dias_aviso_mantenimiento`); «Registrar realizado» reinicia el contador.
- Correctivo: avería reportada → programada → en reparación → cerrada; una avería grave saca la unidad de servicio.
- Saneamiento: zonas con frecuencia de limpieza y fumigación; bitácora con responsable, producto, certificado y evidencia.
- Fumigación de unidades (control de gorgojo) con vigencia y alerta (`vigencia_fumigacion_unidad_dias`, por definir).

## 4. Cadena de suministro y almacén
- Aviso a Comercial a 48 h y 24 h de la fecha comprometida si la OV corre riesgo (stock incompleto, NO CUMPLE o aviso de
  Logística) (`horas_aviso_riesgo_ov`).
- El Jefe de Logística avisa en la OV que no llegará a tiempo, el día de creación o el siguiente, con motivo obligatorio.
- Proyección de demanda (Comercial la carga por formulario o Excel; Logística la consulta frente al stock libre).
- Stock sin rotación: pantalla y aviso mensual a Comercial, Almacén y Gerencia (`dias_sin_rotacion`, `dia_aviso_sin_rotacion`).
- Almacén: programación de picking organizada por cliente con selector de clientes con búsqueda (opcional); carga de
  solicitudes de reempaque por Excel; conteo sobre la lista de un conteo anterior o una lista de productos; movimientos punto
  a punto para el montacarguista (cualquier área solicita; foto de origen y foto de validación obligatoria), y el
  montacarguista vuelve a ver los traslados.

## 5. Matriz de accesos
| Perfil | Cambio |
|---|---|
| Producción | Ya no recibe las alertas de quiebre de stock (tampoco tenía el análisis de reposición) |
| Jefe y Coordinador de Logística | Sin el módulo de Producción (partes, control, OEE). Ven: asistencia de su propio personal, ingresos de producto a almacén con estado y observación, y el estado de las OV |
| Auxiliar de Despacho | Solo «Guías de remisión» (consultar y reportar su estado). Conserva el visto bueno de salida y la validación de carga de la decisión Q16, que se registran en la ruta |
| Auxiliar de Almacén | Alertas operativas de OV, stock sin rotación y cambio de estado de lotes |
| Coordinación de Almacén 1560 | Se llama «Supervisor de 1524 y 1560» |
En bases existentes, `python -m app.cli init` aplica estos cambios una sola vez (queda en la auditoría).

## Decisiones técnicas y puntos a confirmar
1. Perfiles asignados a lo nuevo (ajustables en Permisos por rol): saneamiento lo registra Calidad; mantenimiento de flota,
   Distribución y Logística; proyección de demanda la cargan Jefe y Coordinador Comercial y Gerente Comercial.
2. Valores propuestos (PROPUESTO, editables): aviso de mantenimiento 7 días, de saneamiento 3 días, sin rotación 90 días.
3. El Auxiliar de Despacho conserva el visto bueno de salida (Q16); si debe quitarse, hay que definir quién lo da.
4. La vigencia de la fumigación de las unidades está por definir.
