# Ronda V66 (23-nov-2026): marcha blanca del área de almacén

Fuentes: la transcripción de la capacitación de almacén (32 páginas, leída completa) y las notas de la reunión. Las
pruebas usan solo datos ficticios.

## Qué se hizo

### Movimientos punto a punto
- **Varios productos en una misma solicitud.** Además de la carga principal se agregan otros productos, con cantidad y
  unidad: por ejemplo, pares que combinan productos de lo picado.
- **Varias personas a la vez.** Se puede asignar el movimiento a dos o más montacarguistas o auxiliares.
  - Les llega la alerta a todos.
  - Lo inicia cualquiera del equipo, con su foto.
  - Lo termina cualquiera del equipo.
  - Nadie de fuera del equipo lo puede tomar.

### Picking
- **Otro lote cuando uno no alcanza.** Si a una línea le falta reservar, aparece «Agregar otro lote».
  - Solo ofrece lotes utilizables y con saldo libre.
  - Toma automáticamente la fecha de producción y la de vencimiento del lote.
  - Queda en el historial de cambios de lote del picking.
- **Cambio de lote con fechas automáticas.** Ya existía. También se puede cambiar solo una parte, y así la línea queda
  con dos lotes.
- **Notas de crédito.** En el picking solo aparecen las que cambian lo que se pica: las aplicadas a productos de esa
  OV. Las demás (posteriores al despacho o sin OV) se siguen viendo en la OV, no en el picking.
- **Nota de crédito con el picking ya hecho o en curso.** Comercial recibe la alerta con prioridad alta («la OV ya
  estaba picada en…») para coordinar con Almacén lo que vuelve al stock.
- **Tiempo de picking.** Ya se medía de la foto de inicio a la foto de «listo».

### Traslados
- El traslado hecho en el módulo, al confirmarse la recepción, se registra también en SAP como transferencia de stock,
  con lo recibido, el lote y los almacenes.
- Lo envía el vigilante de SAP, y solo en las bases autorizadas para escribir.
- La lista de traslados muestra si ya está en SAP (con su número) o si dio error.
- Los traslados hechos en SAP ya se veían en el módulo.
- Si los códigos de almacén del módulo y de SAP no coinciden, se usa «sap_almacenes_equivalencia».

### Pedidos grandes de última hora
- Una OV para hoy o mañana que se registra, o a la que se agrega cantidad, después de «almacen_ov_tardia_hora» (09:00)
  y supera «almacen_ov_tardia_unidades» (500) queda **por validar por Almacén**.
- No se prepara ni se puede iniciar su picking hasta que el Líder, el Asistente o el Coordinador la valide u observe
  (Almacén → Pedidos de última hora).
- Observar exige motivo. Comercial recibe la respuesta.
- La hora y la cantidad son una propuesta y se ajustan en Parámetros.

### Consolidado del picking
- Pantalla Almacén → Consolidado del picking.
- Suma lo que falta preparar de las OV abiertas por producto. Se agrupa por cliente y fecha, fecha, sede y fecha,
  producto, o almacén y fecha.
- Filtros: fechas, cliente, sede, producto y almacén.
- Varias OV del mismo cliente para la misma fecha (por ejemplo varias sedes) se suman.
- Se descarga en **PDF** y en **Excel**. Reemplaza la tabla dinámica que hoy se arma a mano.

### Etiquetas de Calidad
- Calidad registra la etiqueta que se pega en el despacho (Calidad → Etiquetas para el despacho):
  - producto;
  - cliente, si aplica;
  - marca;
  - instrucciones;
  - foto.
- En el picking de las OV de ese producto aparece la etiqueta con su foto, para pegarla sin esperar a Calidad.
- El procedimiento detallado lo define Calidad (ver Pendientes).

### Accesos
- **Rol nuevo, Asistente de Almacén.** Tiene todo lo del Líder Operativo y además:
  - recepción e ingreso de mercadería;
  - liquidaciones de producción y monitoreo de lo que se produce en el día (solo consulta);
  - requerimientos a Producción;
  - consolidado;
  - validación de pedidos de última hora.
- El rol «Auxiliar / Asistente de Almacén» se mantiene para los auxiliares de picking. **Al usuario del asistente hay
  que cambiarle el perfil al nuevo rol** (Administración → Usuarios).
- **Líder Operativo.** Recibe los mismos accesos nuevos.
- **Requerimientos a Producción.** Almacén → Requerimientos a Producción abre las solicitudes de producción. Al crear
  un requerimiento, Producción recibe la alerta. Reemplaza la pizarra.

## Pendiente (requiere datos o una decisión)

| Pedido | Por qué no se hizo | Qué se necesita |
|---|---|---|
| Estandarizar la clasificación de almacenes con la que usa Producción | El módulo ya admite una equivalencia de códigos, pero no tengo la clasificación. | La lista de cómo clasifica Producción sus almacenes (ver «sap_almacenes_equivalencia»). |
| Ver en el módulo las *solicitudes* de traslado de SAP (antes del traslado) | Hoy el módulo lee los traslados hechos en SAP, no las solicitudes. No se implementó en esta ronda. | Confirmar si se usan las solicitudes de traslado en SAP. |
| Procedimiento de la etiqueta | La pantalla está lista; falta el procedimiento de Calidad. | Que Calidad indique cómo arma la etiqueta y qué datos lleva. |
| RF (lector) en el celular | No se implementó la lectura de códigos con la cámara. | Definir qué se escanea (lote, código de producto) y con qué etiquetas. |
| Hora y cantidad de «pedido de última hora» | Son una propuesta (09:00 y 500). | Que Almacén las confirme. |
| Inquietudes del lunes | — | Las que salgan de la marcha blanca. |

## No verificado
- La transferencia de stock en SAP no se probó contra SAP real (la base productiva sigue con -5027). La prueba usa un
  SAP simulado.
- Antes de usarla en producción conviene probarla en la base de pruebas.

## Pruebas
`tests/test_v66.py` (8 pruebas).
