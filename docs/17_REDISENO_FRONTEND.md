# Versión 0.8 – Rediseño integral del frontend

Rediseño visual y de experiencia de uso del Módulo de Operaciones con la identidad de Corporación Productiva.
**No cambia reglas de negocio, flujos de aprobación, permisos, rutas ni estructuras de datos.** Las 178 pruebas
automatizadas pasan después del rediseño.

## 1. Diagnóstico (antes)

| Problema | Efecto |
|---|---|
| Barra lateral verde oscuro saturado, sin iconos ni grupos claros | Pesada visualmente; costaba ubicarse. |
| Inicio con 15 indicadores del mismo tamaño y las tareas y alertas al final | Lo urgente quedaba fuera de la vista. |
| Celular: la página se desbordaba en horizontal (1358 px a 390 px de ancho) | Había que desplazar la pantalla completa. |
| Filtros, acciones y títulos mezclados en un mismo bloque | Acciones principales poco visibles. |
| Datos técnicos en JSON crudo (decisiones y modificaciones de OV) | Ilegibles para el usuario. |
| Error 404 del ícono del sitio y páginas de error sin diseño | Errores de consola y pantallas sin contexto. |
| Sin marca de campos obligatorios ni foco visible consistente | Accesibilidad limitada. |

## 2. Sistema visual corporativo

- **Colores (tokens en `app/static/style.css`, `:root`):**
  - `--cp-verde` #00923f (verde principal, «Corporación»).
  - `--cp-verde-700` #007a3d (acciones y texto sobre blanco, contraste AA).
  - `--cp-verde-800` (hover).
  - `--cp-verde-50` (selección suave).
  - `--cp-lima` #7ab829 (verde secundario, «Productiva»; solo acentos).
  - Neutros: fondo #f5f6f5, superficies blancas, bordes #e2e6e3, texto #1c2621.
  - Funcionales: verde favorable, ámbar advertencia, rojo error y crítico, azul informativo.
  - **Los verdes son provisionales:** se tomaron a la vista del logotipo adjunto, porque la imagen no llegó como archivo y
    no se pudieron extraer sus píxeles. Se cambian en `:root`.
- **Logotipo:**
  - La barra lateral y la pantalla de acceso usan `static/img/logo_oficial.svg` o `.png` si existe.
  - Mientras tanto se usa el logo de la empresa ya presente en los formatos impresos, sin deformarlo (se ajusta solo
    por ancho).
- **Tipografía:**
  - Fuente del sistema (Segoe UI / Roboto), sin dependencias externas.
  - Escala: títulos 22 px, secciones 16,5 px, texto 14 px (15 px en celular), auxiliares 12,5 px.
  - Cifras tabulares en tablas e indicadores.
- **Iconos:** conjunto propio de 45 iconos SVG de trazo uniforme (`_icons.html`), sin emojis ni librerías externas.
- **Componentes:**
  - Encabezado de página, tarjetas e indicadores (con variantes principal, advertencia y crítico).
  - Tablas con encabezado fijo, alineación numérica y desplazamiento horizontal dentro del componente.
  - Fichas por registro en celular.
  - Etiquetas de estado con punto y texto (no dependen solo del color).
  - Avisos y mensajes, botones (principal, secundario, peligro, pequeño), campos con foco visible y marca de obligatorio.
  - Estados vacíos, páginas de error, menú de usuario y migas de pan.

## 3. Estructura y navegación

- **Barra lateral clara:**
  - Logo y grupos por área: Panel, Comercial, Almacén, Producción, Calidad, Abastecimiento, Distribución y Administración.
  - Icono por opción e indicador verde de la opción activa.
  - Contador de alertas.
  - Se **contrae** a iconos en escritorio y recuerda la preferencia.
  - Solo muestra las opciones que el rol tiene autorizadas (mismos permisos de antes).
  - Se agregó al menú el *Planeamiento* de producción, una pantalla que ya existía.
- **Encabezado:**
  - Migas de pan (área / pantalla / registro).
  - Fecha de la última carga de stock de SAP («no es tiempo real»).
  - Campana de alertas y menú de usuario (cambiar contraseña y salir).
- **Tablet y celular:**
  - Menú desplegable con fondo y cierre con Escape o al tocar fuera.
  - Encabezado compacto y filtros plegables («Filtros», abiertos si hay alguno aplicado).
  - Listados principales en fichas por registro.
  - Controles de 44 px para uso táctil.
  - Formularios en una columna y sin desplazamiento horizontal de la página.

## 4. Pantallas rediseñadas

- **Inicio:**
  1. Mis tareas y alertas abiertas, las de prioridad alta primero.
  2. Indicadores agrupados: Pedidos; Comercial (según permiso); Operación (según permiso).
  3. Seguimiento: detenidos, estados, faltantes, fill rate, errores por etapa, incidencias y merma (según permiso).
  4. Accesos rápidos según permisos.

  No se agregaron indicadores nuevos ni cifras.
- **Alertas y tareas:**
  - Filtros por naturaleza (acción requerida o información), estado, urgencia, área, grupo y tipo.
  - El título enlaza al detalle; se muestran responsable y fecha.
  - El detalle muestra qué ocurrió, el documento relacionado y los destinatarios con el nombre del cargo.
- **Órdenes de venta:** título con acciones (registrar, importar, exportar) y filtros separados. El detalle de
  decisiones y modificaciones es legible en lugar de JSON.
- **Acceso (login)** y **páginas de error 403, 404 y 400.**
- **Todas las demás pantallas** heredan el nuevo sistema: tablas, formularios, etiquetas, avisos, filtros, botones y
  fichas en celular.

## 5. Verificación

- **Recorrido automatizado de 90 rutas del sistema** (las de la prueba web más los detalles de OV, opciones,
  alertas, preparación, ruta y folio) a 1440, 1024, 768, 390 y 360 px:
  - Sin desbordes horizontales de la página.
  - Sin errores de JavaScript.
  - Los únicos errores de consola son los 403 esperados de pantallas sin permiso para el rol.
- **Capturas de pantalla** antes y después revisadas en escritorio y celular.
- **178 pruebas automatizadas**: acceso, CSRF, permisos por pantalla, flujos de OV, aprobaciones, alertas, picking,
  flota y migraciones.
- **Documentos impresos sin cambios:** OV, guía, certificados y folio. Sus estilos (`.doc`) se aislaron para que las
  nuevas reglas de tabla no los alteren.

## 6. Pendiente o por confirmar

1. **Logotipo oficial:** cargar el archivo (preferible SVG) como `app/static/img/logo_oficial.svg`. Con el archivo se
   extraen los verdes exactos y se actualizan los dos tokens.
2. Variante compacta del logo para la barra contraída: hoy se muestra el inicio del logo recortado por ancho. Si existe
   un isotipo oficial, se usará.
3. Más listados en fichas por registro (hoy: OV, alertas, clientes, picking, flota y las tablas principales de listado).
   Las tablas con celdas combinadas mantienen el desplazamiento horizontal controlado.
