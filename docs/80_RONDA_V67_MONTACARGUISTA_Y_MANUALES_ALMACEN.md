# Ronda V67 (23-nov-2026): marcha blanca del montacarguista y manuales con capturas de Almacén

Fuentes: la transcripción de la capacitación del montacarguista (17 páginas, leída completa) y las notas de la
reunión. Las pruebas y las capturas usan solo datos ficticios.

## Qué se hizo

### Aviso claro del dato que falta
- Al guardar sin un dato obligatorio, aparece abajo un aviso rojo que dice cuál falta, por ejemplo «Falta adjuntar:
  Foto de validación en el destino».
- El campo queda marcado en rojo y la pantalla se desplaza hasta él.
- Antes el navegador solo decía «complete este campo» y no se entendía qué faltaba; en la capacitación faltaba la
  foto de cierre.

### Movimientos
- **Más fotos.** Al terminar un movimiento, además de la foto del destino se pueden adjuntar más (contenedor vacío,
  firma del cliente…). Se ven en la tarjeta del movimiento.
- **Ubicación al terminar.** Se puede indicar en qué rack quedó el lote movido.
- **Tareas propias.** El montacarguista puede registrar su propia tarea aunque no se la hayan asignado (por ejemplo,
  la recepción de un contenedor). La solicita, se la asigna a sí mismo y la ejecuta con sus fotos. Ya no hace falta
  avisar por el grupo de WhatsApp.
- **Varias personas** en un mismo movimiento (V66).

### Ubicación de los lotes
- Un mismo lote puede estar en varios lugares: «A-01-2: 30; B-03-1: 20».
- Se registra en Stock y reservas o al terminar un movimiento, y queda el historial.
- Si las cantidades suman más que el lote, el sistema avisa.
- Pueden registrarla el montacarguista, el auxiliar, el líder y el asistente.

### Estado del lote
- El montacarguista puede pasar un lote a Observado (por ejemplo, si llegó roto, abierto o con plaga), con su motivo.
- Solo Calidad lo libera.

### Chat con foto
- En los mensajes se puede adjuntar una foto, o enviar solo una foto.

### Inicio en las tareas
- El montacarguista entra directo a sus movimientos. Se configura por perfil en «inicio_por_rol».

### Usuarios que hacen dos funciones
- En Administración → Usuarios → «Perfiles adicionales» se le da a una persona uno o más perfiles además del suyo.
  Ejemplo: un montacarguista que a veces hace de conductor.
- Tiene los permisos de ambos perfiles.

## Manuales con capturas por rol (Almacén)
En `docs/capacitacion/almacen/`:
- Manual_Auxiliar_de_Almacen.pdf (capturas en celular);
- Manual_Asistente_de_Almacen.pdf;
- Manual_Lider_Operativo.pdf;
- Manual_Coordinador_de_Almacen.pdf.

Cada uno trae una portada, el contenido y, por tarea, los pasos con la captura de la pantalla. Las tareas cubiertas:
- entrar e inicio;
- reportar avería u observación;
- picking (iniciar, formato, cambiar lote, otro lote, etiqueta de Calidad, listo);
- movimientos;
- stock y ubicación;
- consolidado;
- pedidos de última hora;
- requerimientos a Producción;
- traslados;
- conteos;
- chat;
- aviso de dato faltante.

Se regeneran con `docs/capacitacion/generar_manuales_almacen.py`, que usa la base de demostración. Para la demostración
se agregó el usuario «asist.almacen» (Asistente de Almacén).

## Pendiente o fuera del sistema

| Punto | Situación |
|---|---|
| Calidad no está en la madrugada para liberar lo observado | Es una decisión de personal. Se pidió una persona adicional; el sistema deja el lote Observado y Calidad lo ve al día siguiente. |
| Duplicidad con los grupos de WhatsApp | Lo que es una tarea se registra en el módulo (con fotos). Falta que Operaciones defina qué avisos dejan de ir al grupo. |
| Celulares corporativos | Es una decisión de la empresa. Mientras tanto se usa el celular personal, según lo autorizado. |
| «Solo está en el navegador, no se descarga la aplicación» | No se revisó en esta ronda si el módulo se puede instalar en la pantalla de inicio del celular. |
| Reportar un problema a otra área (por ejemplo, Calidad no llega a tiempo) | Hoy se hace por el chat (con foto). La «observación» va a Sistemas. |
| Usuario dual en pantallas que filtran por perfil (por ejemplo, la lista de conductores de una ruta) | Esas listas siguen usando el perfil principal. Si hace falta, se ajustan pantalla por pantalla. |

## Pruebas
`tests/test_v67.py` (4 pruebas).
