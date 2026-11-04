# Ronda V20: capacidad, velocidad, notificaciones en el celular, lotes con variantes y pantallas que se acomodan (04-nov-2026)

## 1. ¿Cuántas personas pueden usar el sistema a la vez?

### Cómo se midió

- Prueba de carga en PostgreSQL con gunicorn, igual que en el servidor, sobre una base con volumen realista:
  - 1 505 clientes, 1 517 lotes, 435 OV, 3 288 alertas abiertas y 20 473 registros de auditoría.
- Máquina de prueba: 4 procesadores. La base de datos, el sistema y el generador de carga corrían en la misma máquina, así que los resultados son **conservadores**.
- Usuarios simulados de 7 perfiles (ventas, almacén, logística, producción, distribución, gerencia, operaciones). Recorrían inicio, alertas, OV, clientes, stock, cargas, partes, liquidaciones y pre-guías, además del aviso de alertas que cada pantalla consulta sola.

### Lo que se encontró y se corrigió

Antes de corregir, con **un solo usuario**:

- «Alertas» tardaba **17,8 s**.
- El inicio del Jefe de Logística tardaba **2,7 s**.

| Causa | Corrección |
|---|---|
| Parámetros y permisos se leían de la base miles de veces por página (32 000 lecturas en «Alertas») | Se leen una vez por petición |
| Indicadores, despachos y gestión comercial leían las líneas y reservas de cada OV una por una | Se leen todas juntas, en pocas consultas |
| El número rojo de alertas y el aviso sonoro (cada 10 s por pestaña) recalculaban todas las alertas | Solo se recalcula si alguna alerta cambió |
| La lista de OV leía las condiciones de cada cliente una por una | Se leen una vez |
| Los indicadores del mes (inicio) se recalculaban en cada visita | Se reutilizan hasta 60 s. Las tareas y alertas siempre están al día |
| «Alertas» mostraba también todas las alertas cerradas de la historia | Muestra las abiertas y las cerradas de los últimos 30 días (se puede filtrar por estado) |
| **Error 500** en el inicio de Comercial y Gerencia cuando había OV en el tablero de despachos (`o.vendedor`) | Corregido |

Tiempos después de corregir, con un usuario:

| Pantalla | Antes | Después |
|---|---|---|
| Alertas | 17,8 s | 0,25 s |
| Inicio | 2,7 s | 0,35–0,9 s (según el perfil) |
| Lista de OV | 1,2 s | 0,3 s |
| Aviso de alertas (cada 10 s) | 0,22 s | 0,007 s |
| Clientes | — | 0,07 s |
| Stock | — | 0,18 s |

### Capacidad medida

Configuración nueva: 5 procesos × 4 hilos en 4 procesadores.

| Escenario | Peticiones/s | Mediana | 95 % de las respuestas |
|---|---|---|---|
| 30 usuarios haciendo clic cada 2 s (uso intenso) | 10 | 0,2 s | 1,3 s |
| 60 usuarios haciendo clic cada 2 s | 17 | 0,5 s | 3,2 s |
| 100 usuarios conectados, un clic cada ~10 s (uso normal) | 6 | 0,2 s | 3,4 s |
| 200 usuarios conectados, un clic cada ~10 s | 9 | 0,9 s | 10,9 s |

- No hubo ningún error en ninguna de estas pruebas.

**En resumen:** con un servidor de 4 procesadores, hasta unas **100 personas conectadas** a la vez trabajan con respuestas de menos de medio segundo en la mayoría de las pantallas. Para **200 o más** conviene un servidor de 8 procesadores; la configuración se ajusta sola al número de procesadores.

### Configuración del servidor

Llega sola con la actualización.

- **gunicorn** (`deploy/gunicorn.conf.py`):
  - procesos = procesadores + 1, con 4 hilos cada uno;
  - una exportación pesada ya no bloquea a los demás.
  - Se puede cambiar con `GUNICORN_WORKERS` y `GUNICORN_THREADS`.
- **Páginas lentas:**
  - las que tardan más de 2 s (`LENTA_SEG`) quedan en el registro (`journalctl -u operaciones`) con la ruta y el usuario;
  - cada respuesta lleva su tiempo en la cabecera `Server-Timing`.

## 2. Protección contra ataques (DDoS) y abusos

| Capa | Qué hace | Estado |
|---|---|---|
| Límite por usuario | 240 peticiones por minuto por persona con sesión: frena un script o recargas sin parar | Activo |
| Límite sin sesión | 600 por minuto por IP. Es alto a propósito: toda la oficina puede salir con la misma IP pública | Activo |
| Ingreso | 20 intentos por minuto por IP, más el bloqueo de cuenta por intentos fallidos que ya existía | Activo |
| IP real | Detrás de Caddy, el sistema ve la IP real del usuario (`PROXY_HOPS=1`) | Activo |
| Conexiones lentas (slowloris) | Límites de tiempo de lectura en Caddy | Propuesto en `deploy/Caddyfile` |
| **Ataque masivo de red (DDoS real)** | Un servidor solo no lo resiste: tiene que filtrarse **antes** de llegar al servidor | **Requiere decisión**: ver 3 |

- Todo se configura con las variables `LIMITE_USUARIO_MIN`, `LIMITE_IP_MIN` y `LIMITE_LOGIN_MIN`.
- Quien pasa el límite ve «Un momento, por favor» y puede seguir a los pocos segundos.

**Caddy:** el archivo no se instala solo, porque tiene el dominio. Para aplicar los límites de tiempo:

1. Valide primero con `sudo caddy validate --config /etc/caddy/Caddyfile`.
2. Luego aplique con `sudo systemctl reload caddy`.

No lo pude validar aquí (no hay Caddy en este entorno).

**Solo los empleados tienen acceso:** sin usuario y contraseña no se ve nada del sistema, más allá de la pantalla de ingreso. Si además quieren que **ni siquiera la pantalla de ingreso** sea visible desde fuera, hay dos opciones:

- restringir por IP (solo la red de la oficina, con los choferes por VPN);
- usar Cloudflare Access, que pide el correo de la empresa antes de mostrar el sistema.

Ambas son decisiones de la empresa.

## 3. El celular no abre «coprod-one.duckdns.org» («problema de DNS»)

**Qué pasa:** el celular le pregunta a su servidor de nombres (DNS) qué dirección tiene `coprod-one.duckdns.org`. Algunos DNS, sobre todo los de algunos operadores móviles y los de «DNS privado» o filtros, no responden bien a los dominios gratuitos de DuckDNS.

- Brave funciona porque usa su propio DNS seguro (DNS sobre HTTPS) y no el del operador.
- El sistema y el servidor están bien. El problema está en el DNS del dispositivo.

**Solución inmediata** (para cada persona con el problema):

- **Android:** Ajustes → Conexiones / Redes → «DNS privado» → «Nombre de host del proveedor» → `dns.google` (o `1dot1dot1dot1.cloudflare-dns.com`) → Guardar.
- **Chrome** (celular o PC): Configuración → Privacidad y seguridad → Seguridad → «Usar DNS seguro» → Google (DNS público) o Cloudflare.
- **iPhone:** instalar la app «1.1.1.1» de Cloudflare (gratuita) y activarla. También puede usar Brave o Chrome con DNS seguro.
- **Red de la oficina (Wi-Fi):** configurar el router con DNS `8.8.8.8` / `1.1.1.1`. Así lo resuelve para todos los equipos conectados.

**Solución definitiva (recomendada; requiere decisión):**

1. Comprar un dominio propio (por ejemplo `<nombre>.com` o `<nombre>.pe`) o usar un subdominio de la página web de la empresa. Un `.com` cuesta unos USD 10–15 al año; un `.pe`, unos USD 40–50 al año.
2. Administrar ese dominio en **Cloudflare (plan gratuito)**. Esto da:
   - DNS que responde bien en cualquier operador;
   - **protección DDoS gratuita** (el tráfico pasa primero por Cloudflare);
   - la opción de Cloudflare Access para que solo entren correos de la empresa.
3. Cambiar `DOMINIO` en el Caddyfile; los certificados se renuevan solos.

Si la empresa ya tiene un dominio (el de su página web o su correo), basta con crear un subdominio, por ejemplo `operaciones.<dominio de la empresa>`. Es la opción más simple.

## 4. Notificaciones en el celular (aunque la pantalla esté apagada)

- **Activar:**
  - al entrar aparece «¿Recibir las alertas en este dispositivo?» → **Activar**;
  - o desde el menú del usuario → «Notificaciones en el celular».

  Se activa por dispositivo (celular, PC) y se puede activar en varios.
- **Qué llega:** las alertas de prioridad **ALTA** y **MEDIA** de las que la persona es destinataria (parámetro `push_prioridades`).
  - Llegan como notificación del sistema operativo, con la pantalla apagada o el navegador cerrado.
  - Las urgentes vibran más y quedan en pantalla hasta que se tocan.
  - Al tocar una, se abre esa alerta.
- **Se envía solo si la acción se guardó:** si algo se deshace, no se avisa. El envío no demora la pantalla de quien registra.
- **Mis dispositivos:** en «Notificaciones en el celular» se ve en qué equipos está activa, se puede enviar una **prueba** y quitar un dispositivo. Los que ya no existen se quitan solos.
- **Según el equipo:**

| Equipo | Funciona | Qué hacer |
|---|---|---|
| Android con Chrome | Sí, con pantalla apagada | Permitir notificaciones del sitio. Si llegan tarde, quitar la «optimización de batería» de Chrome |
| Android con Brave | Sí | Activar en Brave: Configuración → Privacidad y seguridad → «Usar los servicios de Google para mensajería push» |
| iPhone (iOS 16.4 o más) | Sí, solo como app | Safari → Compartir → «Agregar a pantalla de inicio», abrir desde ese ícono y activar |
| iPhone en Safari normal | No | Apple no permite notificaciones web fuera de la app agregada al inicio |
| PC (Chrome, Edge, Firefox, Brave) | Sí, con el navegador abierto, aunque la pestaña esté cerrada | — |

- El sistema ahora se puede **instalar** como aplicación (ícono en la pantalla de inicio).
- **Técnico:**
  - Web Push con claves VAPID, generadas solas en el servidor (`instance/vapid_privada.pem`, fuera del repositorio);
  - tabla `push_subscriptions` (migración `0032`);
  - opcional: `VAPID_SUB=mailto:sistemas@<dominio>` en el `.env`.
  - Se verificó el envío completo (firma VAPID, cifrado aes128gcm y contenido) contra un servicio de push local.
  - **La prueba en un celular real queda pendiente**: hágala con «Enviar una notificación de prueba».

## 5. Lotes con puntos: cómo los trabaja el sistema

Producción explicó la regla: el mismo número de lote se vuelve a producir en otra fecha y en SAP se le agrega un punto por cada producción (`000863FA`, `000863FA.`, `000863FA..`).

- **Se guarda exacto como en SAP:** las guías y entregas a SAP lo exigen así.
- **En pantalla se ve ordenado:** `000863FA` con un indicador «2.ª», «3.ª» (la producción); al pasar el cursor se ve el lote exacto de SAP.
  - Se aplica en stock, en el picking y en «cambiar lote».
  - Las fechas de producción y vencimiento de cada variante están al lado.
- **Búsqueda:** en Stock, escribir `000863FA` muestra el lote y **todas sus variantes**.
- **Carga «6 – Stock por lote»:**
  - los puntos **ya no se marcan como advertencia**;
  - solo se avisa lo que parece un error:
    - **coma** en lugar de punto (`201025IN,`);
    - **posible duplicado**: dos variantes del mismo lote con las mismas fechas;
    - caracteres raros.
  - El sistema ahora acepta **directamente** los encabezados de la consulta de SAP que enviaron (`articulo`, `lote`, `almacen`, `fecha_venc`…).

**Resultado con su archivo** (1 337 filas; las comprobaciones de catálogo y almacenes no cambian):

| Aviso | Filas |
|---|---|
| Antes: «caracteres inusuales» | 298 |
| Ahora: lote con coma | 26 |
| Ahora: posible duplicado | 61 |
| Ahora: otros caracteres | 31 |

### Preguntas para Producción

1. **Comas:** hay 26 lotes que terminan en coma (por ejemplo `201025IN,`, `000863FA,,`). ¿Son errores de digitación de un punto? ¿Se corrigen en SAP?
2. **Variantes con las mismas fechas:** por ejemplo, `000863FA`, `000863FA.` y `000863FA...` tienen las tres FP 13/08/2026 y FV 13/08/2027. Según la regla, cada punto es otra producción con otra fecha. ¿Es otro motivo (otro almacén, otro saco, reproceso) o un error? Hay 61 filas así.
3. **Otros formatos:**
   - lotes con sufijo numérico (`S00791.001`, `00820.002`): el sistema los toma como normales;
   - lotes que parecen fechas o textos (`18.05.2026`, `QU-0452.2026`, `FRIJOL LACTAO`, `#70459B`, `019111AS|`): ¿son correctos?
4. **Etiqueta física:** el saco o la caja, ¿lleva el número con los puntos o solo `000863FA` y las fechas? Así se define qué mostrar al pickeador para que tome el correcto (hoy se muestran el lote base, la variante y las fechas).
5. **Documentos para el cliente:** en el certificado y la guía, ¿va el lote con puntos (como SAP) o el lote base con su fecha de producción? Por ahora no se cambió lo impreso.
6. **A futuro:** ¿podrían registrar en SAP la variante con la fecha, por ejemplo `000863FA-0303`, en lugar de puntos? Es más claro para todos. El sistema funciona con cualquiera de las dos formas.

## 6. Tablas que no se acomodaban (celular y PC)

- Cualquier tabla que no entra en su espacio **se apila sola**, en celular, tablet o PC: cada fila pasa a ser una tarjeta con el nombre de cada columna junto a su dato. Si luego hay espacio (pantalla más ancha o se gira el celular), vuelve a ser tabla.
- **Barra superior:** en tablet y pantallas medianas ya no se sale de la pantalla (se ocultan el nombre del usuario y el texto del botón de observación).
- **Revisado en Chrome (Chromium)** a 390 px (celular), 768 px (tablet) y 1280 px (PC), en 9 pantallas con muchas columnas (traslados, stock, cargas, alertas, OV, clientes, partes, liquidaciones, auditoría): **ninguna se desborda**.
- **Otros navegadores:** se usan funciones disponibles en Chrome, Edge, Firefox, Brave y Safari actuales. En este entorno solo hay Chromium, así que **conviene revisar en Safari (iPhone) y Firefox** con «Reportar observación» si algo se ve mal.

## 7. Datos técnicos

- **Migración `0032`:** `push_subscriptions`.
- **Dependencias nuevas** (`requirements.txt`; el actualizador las instala):
  - `pywebpush 2.0.x` y `py-vapid 1.9.2`;
  - `cryptography < 46`, fijado para no romper `msal`.
- **Servicios:**
  - `push.py`, `limites.py`, `lotes.py`;
  - cachés por petición en `core.py` (`param`, `user_perms`, `ttl_cache`);
  - `alerts.open_count` y `alerts.huella`.
- **Rutas:** `/sw.js`, `/manifest.webmanifest`, `/notificaciones`, `/push/clave`, `/push/suscribir`, `/push/baja`.
- **Archivos estáticos:** `v20.js` (notificaciones y tablas que se apilan); íconos `icono_192.png`, `icono_512.png` e `insignia_96.png`.
- **Pruebas:** `tests/test_v20.py`.
