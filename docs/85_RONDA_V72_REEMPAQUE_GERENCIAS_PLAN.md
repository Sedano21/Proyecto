# Ronda V72 (24-nov-2026): reempaque, gerencias, plan de producción hacia Almacén y tiempos por producto

Fuente: el mensaje del usuario del 24-nov. Las pruebas usan solo datos ficticios.

## Qué se hizo

### Reempaque
- **Pueden solicitarlo:**
  - el Líder Operativo y su Asistente;
  - el Supervisor de Almacén;
  - los Coordinadores de Almacén 1560 y 1524, de Logística, de Distribución y de Ventas;
  - las Jefaturas de Logística, Operaciones, Producción y Comercial.
- **Calidad no lo solicita.** Lo evalúa (aprueba o desaprueba), para no aprobar sus propias solicitudes (IF §9.1).

### Gerencias: ven todo, aprueban lo suyo
- La **Gerencia Comercial** y la **Gerencia de Administración y Finanzas** tienen la vista total: entran a todas las
  pantallas en modo consulta, como ya la tenían la Gerencia General y la Gerencia General Adjunta.
- Aprueban solo lo que les corresponde por su perfil.

### El plan de producción avisa a Almacén
- **Al cargar el plan** (desde el Excel o con «+ productos»), cada producto del plan diario se explota con su lista de
  materiales: granel, MP, envases, etiquetas e insumos, sin mano de obra ni CIF.
- **Almacén recibe un aviso** con qué materiales debe entregar y cuándo: un día antes de producir, ajustable en
  «plan_almacen_anticipacion_dias».
- **La pantalla «Plan: materiales y revisión»** (en Almacén, «Materiales para Producción») muestra por fecha de entrega:
  - el material;
  - cuánto se requiere y cuánto hay disponible;
  - lo que falta (descontando día a día lo ya comprometido);
  - de qué almacén sale;
  - para qué producto y línea es.
  - Los productos del plan sin lista de materiales se informan aparte.

### Revisión del plan (avisos a Producción)
Al cargar el plan, o con el botón «Avisar a Almacén y a Producción», se revisa:
- **Capacidad baja**: líneas programadas por debajo del 80 % de su capacidad («plan_capacidad_minima_pct»).
- **Entregas no incluidas**: lo que se debe entregar y no está en el plan del periodo, con su cantidad y su origen:
  - OV con faltante de productos con lista de materiales;
  - solicitudes de producción;
  - facturas de reserva aprobadas.
- **Horario extendido**: si lo programado supera la capacidad de la línea, las horas extra necesarias en total y por
  día, con la jornada de «demanda_jornada_horas».
  - Si pasan de «demanda_horas_extra_max_dia» por día, se recomienda un tercero o pasar parte a otra línea.
- Producción recibe el aviso «Revise el plan de producción» con lo encontrado.

### Tiempos por producto
- Pantalla **Producción → Tiempos por producto**; abre en selección manual. Por producto y línea muestra:
  - partes;
  - kg procesados;
  - horas;
  - **kg por hora**;
  - **kg por hora y operario**;
  - **minutos por cada 100 kg**.
- Primero salen los más lentos. Filtros por línea y fechas.
- **Las horas** son las del parte o, si no las tiene, de la hora de inicio a la de fin menos el refrigerio y las
  paradas.

## Por decidir
| Punto | Situación |
|---|---|
| Gerencia General y Gerencia General Adjunta aprueban «en nombre de otros roles» | Hoy tienen todos los permisos de aprobación por la decisión Q4 del 13-oct («puede aprobar en nombre de otros roles»). El pedido de ahora dice que las gerencias aprueben solo lo que les corresponde. **No lo cambié**, porque contradice esa decisión vigente. Si se confirma que la Gerencia General y la Adjunta solo deben aprobar lo suyo, falta definir cuáles son sus aprobaciones (por ejemplo, decisión de OV que no cumple la fecha, OV fuera de horario elevada, salida con discrepancia) para quitarles las demás. |
| Anticipación de la entrega a Producción | 1 día (propuesta). Ajustable. |

## Pruebas
`tests/test_v72.py` (5 pruebas). `tests/test_controles.py` se ajustó a la nueva lista de quienes solicitan reempaque.
