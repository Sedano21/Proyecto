# Ronda V76 (26-nov-2026): Producción, Calidad, experiencia de uso y propuesta de reingeniería

Fuente: el mensaje del usuario del 26-nov.

Adjuntos usados solo para conocer los formatos (no se guardaron en el repositorio):
- certificados de harina N°CP2026-CA0995 y CA0996;
- «Formato de control de calidad – granos 2023»;
- exportación de códigos GS1 (EAN).

Las pruebas usan solo datos ficticios.

## Qué se hizo

### Calidad
- **Todos los registros de la base:** la pantalla «Formatos (higiene y todos)» muestra cuántos registros hay de cada
  formato y cuál es el último. Incluye los formatos ya retirados o sin pantalla propia, con enlace a sus registros.
- **El certificado toma lo que registra el asistente durante la producción:** si no hay análisis del lote, la humedad se
  toma del control de Calidad registrado en el parte que produjo el lote. La fuente queda indicada en el certificado.
- **Referencias por grano:** se cargaron las normas que figuran en el pie del «Formato de control de calidad – granos
  2023». Son lenteja, pallar, arveja, garbanzo, frijol, maíz, maíz mote, trigo, trigo mote, cebada, papa seca, quinua y
  kiwicha.
  - Solo se agregan las que falten: lo que Calidad ya configuró se respeta.
  - Si dos tipos coinciden, gana el más específico (MAÍZ MOTE antes que MAÍZ), sin importar tildes.
- **Certificado de harinas (tipo HA):** sigue los modelos CA0995 y CA0996.
  - Se numera con la serie CA.
  - Usa el formato Cosecha Andina, con la columna de especificación ya llena: «Homogéneo, sin grumos», «Característico»,
    etc.
  - Humedad máxima 15 %.
  - La referencia es «FICHA TECNICA CORPORACIÓN PRODUCTIVA. {producto}», distinta para cada harina.
  - Un producto con «HARINA» en su descripción usa este tipo (parámetro «tipo_certificado_por_palabra»).

### Producción
- **Comportamiento por grano** (pantalla nueva). Por grano y por línea muestra:
  - kg por hora y kg por hora-operario;
  - minutos por cada 100 kg;
  - rendimiento y desmedro ponderados.

  También incluye:
  - la evolución semanal de la velocidad, del rendimiento y del desmedro;
  - un comparativo entre granos.

  Hace propuestas de mejora:
  - el mismo grano rinde menos en otra línea;
  - un grano tiene desmedro alto frente al resto;
  - el rendimiento cae en las últimas semanas;
  - la selección manual es lenta.

  Las propuestas se presentan como hipótesis por verificar.
- **Tiempos por producto:** filtros por grano y por producto (escribiendo), columna de grano y gráfico de evolución
  semanal.
- **Tablero OEE:** ya no falla con partes que traen datos irregulares (texto donde va un número, línea vacía,
  calificación mal configurada).
- **Nuevo parte:**
  - Ofrece todos los productos disponibles (PT, MP y granel), con búsqueda al escribir.
  - Separa el producto que se va a generar de la materia prima o granel que ingresa, y sugiere este último según la
    receta.
  - El EAN aparece solo si el producto es PT y se borra si se elige otro tipo.
- **Correcciones del parte:** se pueden corregir, siempre con motivo, estos datos:
  - la cantidad de personas y las personas asignadas (se marcan de una lista que se filtra al escribir);
  - el turno, la OF, el maquinista y los lotes;
  - los kg y las horas.

  Cada corrección queda en el historial del parte con quién, cuándo, por qué y qué cambió (antes → después). Si el parte
  ya terminó, se recalculan los indicadores.
- **Asistencia:**
  - «DM», «VACACIONES», «ASISTENCIA», «TOTAL» y similares no se cargan como colaboradores. Eran las filas de resumen de la
    hoja de Excel, con sus conteos (0, 21, 27) en la columna de línea. Los que ya estaban se desactivan solos.
  - Botón «+ Nuevo colaborador» arriba de la pantalla.
- **Asistentes de Producción:**
  - Ven «Eficiencia por persona» (antes «Productividad por persona»), también desde Partes.
  - Pueden solicitar movimientos punto a punto. Se deja sin efecto, solo para ellos, el retiro de V7.
- **Planeamiento:**
  - El registro manual pide el granel o la MP a utilizar y lo sugiere según la receta.
  - El plan diario, semanal y mensual muestra dos columnas de rotación: la del producto y la de su grano, del periodo
    frente al mismo periodo del año anterior (guías de SAP o historial).
  - El plan semanal y el mensual también avisan a Almacén qué materiales entregar y cuándo.
  - El aviso llega también a la Jefatura de Logística y a la Jefatura de Operaciones.
- **Tabla GS1 (EAN):**
  - Se carga con la exportación de GS1 Perú, donde «Código» es el EAN y «Código interno» el código SAP, o con la
    plantilla propia.
  - El EAN es solo de producto terminado.
  - Las filas sin código interno se emparejan con el PT por marca, grano, variedad y contenido (450 GR = 0,45 kg).
  - Las que no se pueden emparejar con certeza quedan para asignarlas a mano, escribiendo el PT.
  - La carga también la hace la Jefatura de Producción, en Configuración de Producción.
- **Liquidaciones con SAP:**
  - **Traer liquidaciones de SAP:** trae las entradas por producción contra la OF, con el contenido de SAP.
  - **Enviar a SAP:** registra la liquidación del módulo como recibo de producción contra la OF, con su lote y fechas.
  - El envío está apagado por defecto (parámetro «sap_escritura_liquidacion»). Además, la base de SAP debe estar en
    «sap_escritura_empresas».
  - No se pudo probar contra SAP real: se debe probar primero en la base de pruebas.

### Experiencia de uso (reglas generales)
- **Menú anclado:** al abrir una opción, el menú lateral conserva su posición y muestra la opción activa.
- **Escribir y filtrar:**
  - Toda lista desplegable de más de 8 opciones agrega un buscador; también las que se agregan con «+», como cada
    colaborador del parte.
  - Los campos con sugerencias muestran las coincidencias mientras se escribe, también en el celular.
- **Hora:**
  - Se puede digitar en formatos como 7:30, 0730, 7.30 o 730.
  - La lista de minutos va de 5 en 5: ya no son 60 opciones.
  - Siguen los botones ±1 y ±5 minutos y «Ahora».
- **Alertas y tareas:** muestran quién las generó o solicitó (o «sistema»), en la lista, el detalle y el inicio.

### Reingeniería (fases 1 a 3)
- Diagnóstico, arquitectura de información, sistema visual, prioridades y prototipos publicados como página para
  revisar y aprobar.
- La reorganización del menú y el rediseño de pantallas e informes esperan su aprobación. No se modificaron pantallas
  de forma masiva, como pidió la metodología.

## Por decidir

| Punto | Situación |
|---|---|
| Arquitectura de 9 espacios y sistema visual | Esperan aprobación (ver la página de la propuesta). |
| Normas por grano con posibles erratas | El formato dice «NTP. 2050.025:2014» (arveja) y «NTP 205.2009.2014» (trigo). Se cargaron tal cual; Calidad debe confirmarlas en «Referencias de certificados». |
| Envío de liquidaciones a SAP | Implementado y apagado. Se activa después de probarlo en la base de pruebas. |
| Códigos EAN del archivo adjunto | No se guardaron en el repositorio (son datos de la empresa). Se cargan en el servidor desde Configuración de Producción. |
| Umbral de las sugerencias por grano | 75 % de la mejor línea (tiempo) y 1,5 veces la mediana (desmedro), propuestos. |

## Pruebas
- `tests/test_v76.py`: 11 pruebas.
- `tests/test_v27.py` y `tests/test_ronda_23oct_b.py`: se ajustaron a las reglas nuevas (fumigación por pasos y tabla
  GS1 también para Producción).
