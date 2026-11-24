# Ronda V73 (24-nov-2026): capacitación de choferes

Fuente:
- la transcripción de la capacitación de choferes;
- las notas del usuario del 24-nov.

Las pruebas usan solo datos ficticios. No se guardó ningún dato del material recibido: nombres, placas ni clientes.

## Qué se hizo

### Pantalla «Mi ruta (paso a paso)»
Está en Distribución, `/distribucion/mi-ruta`. La usan el chofer y el auxiliar de despacho asignados a la ruta.
Pensada para el celular, con botones grandes.

Muestra:
- La placa, el chofer y el auxiliar.
- **El peso de la ruta frente a la capacidad de la unidad.**
  - Si la excede, sale en rojo con el aviso «EXCEDE la capacidad»
  - Es solo un aviso: no bloquea la salida (ver «Por decidir»).
- Los documentos de cada OV, para verlos o imprimirlos:
  - pre-guía;
  - guía y factura de SAP;
  - certificado de calidad aprobado;
  - correo de la cita.

#### 1. Validar la carga guía por guía
- Por cada guía (OV) aparece la lista de SKU de la pre-guía.
  - El lote, la FP y la FV salen solos, de lo reservado.
- Cada SKU viene marcado «Está bien».
  - Si se desmarca, aparece la cantidad para corregirla.
  - La diferencia se registra como faltante o sobrante en las novedades de la carga, y la salida espera a que
    Almacén la resuelva.
- Se puede marcar **«La mercadería va mal paletizada»** y escribir una observación.
  - Se crea la incidencia «Mercadería mal paletizada» con su alerta.
- Queda registrado quién validó cada guía y si fue conforme o con observaciones.

#### 2. En cada cliente
Botones en orden: **Llegué → Me están atendiendo → Conformidad → Salí**.
- Cada paso guarda la hora, para medir la espera y la atención.
- La conformidad es la recepción de V71: conforme o con observaciones por SKU, con la guía firmada al expediente.
- **«No me dejan ingresar»** (impedimento de ingreso):
  - registra la incidencia;
  - avisa a Comercial (Coordinación y Jefatura de Ventas) y a Distribución, para que habiliten el acceso con el
    cliente.
- **Correo de la cita**: Distribución adjunta a la parada el correo de coordinación (foto, PDF o captura). El chofer lo
  ve desde la misma pantalla.

#### Peaje, combustible o parqueo
- **Deuda de peaje o tarjeta de combustible sin saldo** avisa con prioridad alta a:
  - Coordinación y Jefatura de Administración y Finanzas;
  - Coordinación de Distribución;
  - Jefatura de Operaciones.
- **Parqueo y otros gastos**:
  - piden el monto;
  - se puede indicar que no hay comprobante y adjuntar foto;
  - avisan a Coordinación de Distribución y de Finanzas, para el reembolso.

### Demoras en clientes
- Pantalla en Distribución: «Demoras en clientes».
- Por cliente muestra, con las horas registradas por el chofer:
  - la espera, de la llegada a la atención;
  - la atención, de la atención a la salida.
- Filtros por fecha.

### Cancelación tardía de OV
- Si una OV se cancela con menos de 24 h para su fecha de despacho, se avisa a:
  - Jefatura de Operaciones;
  - Coordinación de Distribución;
  - Jefatura de Ventas.
- La anticipación se ajusta en «ov_cancelacion_anticipacion_horas».
- La cancelación no se bloquea.

### Checklist vehicular
- Nuevo punto: **luces diurnas (camionetas)**.
- Nuevo dato: **cantidad de conos**.
- Lo que hoy se marca como malo y en el checklist anterior estaba bien sale **en rojo**, con su leyenda. Así se ve
  qué es nuevo.

### Celular
- Las tablas largas se desplazan dentro de su recuadro.
- Las filas de botones bajan de línea.
- La barra superior entra completa en pantallas de 390 px. Antes se salía 15 px y la página se movía hacia el costado.

### Ya existía
- Mantenimiento y fumigación de unidades: sus alertas ya existían (programación de mantenimiento y vencimientos de la
  unidad).

## Por decidir
| Punto | Situación |
|---|---|
| «Dani» en las alertas de peaje y combustible | No sé qué usuario es. Se agrega como destinatario adicional en Configuración → Alertas, en «FLOTA_PEAJE_COMBUSTIBLE». |
| Exceso de peso | Hoy solo avisa. Si Operaciones decide que bloquee la salida, es un cambio pequeño. |
| Programación anticipada y espacio para parquear | Son temas de proceso, no del sistema. La programación ya se ve en «Mi ruta» apenas Distribución confirma la ruta. |
| Sistemas de seguridad de los clientes | Están fuera del módulo. El impedimento de ingreso queda registrado y avisado a Comercial. |
| Cancelación con 24 h | Se avisa, no se bloquea. Falta la regla de Comercial. |

## Pruebas
`tests/test_v73.py` (6 pruebas):
- checklist por guía;
- paso a paso y demoras;
- gastos y correo de la cita;
- exceso de peso;
- cancelación tardía;
- checklist vehicular con conos y luces diurnas.
