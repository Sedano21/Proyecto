# Ronda V16: perfiles, avisos en rojo y sonidos por urgencia (02-nov-2026)

## 1. Avisos en rojo con letras blancas

Los recuadros «Atención» del Inicio y de los informes pasan a **rojo con letras blancas**. Un ejemplo es «N producto(s) con stock y sin venta en el periodo…».
- «Acción urgente» y «Requiere acción» usan un rojo más intenso con un borde que late.
- Si el usuario pidió reducir el movimiento en su equipo, el borde no late.
- «Seguimiento» y «Sugerencia» siguen en verde o azul. No son avisos de atención.
- Las notificaciones y los mensajes de error ya eran rojos con letras blancas desde V14.

## 2. Sonidos por urgencia

| Urgencia | Sonido |
|---|---|
| Urgente (ALTA) | Sirena aguda de unos 4 segundos en la zona de 2 a 4 kHz, la más sensible del oído. Tiene cuatro patrones (barrido, pulsos rápidos, dos tonos y caída con golpe). Se repite hasta que la tarea se atienda, cada `alerta_sonido_repetir_seg` segundos (120 por defecto). |
| Media | Pitidos agudos dobles o ascendentes, unos 1,5 segundos. Tiene tres patrones. |
| Baja | Dos pitidos cortos. Antes no sonaba. |

- Cada aviso **elige un patrón al azar** y cambia el tono en ±8 %, para que el oído no se acostumbre.
- Un compresor permite subir el volumen sin distorsión.
- En **Administración → Configuración de alertas** hay botones para probar cada sonido.
- Solo suenan las tareas **dirigidas** a la persona: por su perfil, su usuario o una designación.

## 3. Perfiles

| Indicación | Implementación |
|---|---|
| Retirar Gerencia de Operaciones; sus funciones pasan al Gerente General Adjunto | El perfil se elimina. El Gerente General Adjunto recibe todo lo suyo: permisos, alertas, aprobación del despacho parcial y del transporte tercero, y su lugar como jefe de Logística, Producción, Calidad y Seguridad en los avisos por tareas vencidas. |
| No hay Coordinador de Almacén 1560 y 1524; hay un Supervisor de Almacén 1560 y otro 1524 | Los perfiles pasan a llamarse **Supervisor de Almacén 1560** y **Supervisor de Almacén 1524**. Conservan sus permisos y sus almacenes: 1560 con ALM-001 y el tránsito ALM-003; 1524 con EXT-002. Los textos del sistema dicen «Supervisor de Almacén». |
| Jefe de Administración y Finanzas, con el mismo poder y autoridad que la Coordinación de Finanzas | Perfil nuevo con los mismos permisos. Además ve, aprueba y atiende todo lo de la Coordinación (parámetro `roles_equivalentes`), así que también tiene lo que se agregue a ella en el futuro. |
| Si la Coordinación de Finanzas no atiende, alertar al Jefe | Organigrama `jefe_por_rol`: Coordinación de Finanzas → Jefe de Administración y Finanzas. Si una tarea de Finanzas vence su plazo sin atenderse, le llega «Tarea vencida sin completar». Esa alerta sí le suena. Las tareas de la Coordinación no le suenan mientras están en plazo, para no duplicar avisos. |
| «Ejecutivo comercial 1…n» en vez de «vendedor 1…n» | El perfil pasa a llamarse **Ejecutivo Comercial**. Las cuentas de ejemplo se llaman «Ejecutivo Comercial 1 y 2». En pantallas, informes y mensajes, «vendedor» pasa a «ejecutivo comercial». |

### Bases existentes (servidor)

Se aplica sola con la actualización automática (`python -m app.cli init`). No hay migración de esquema.

**Gerencia de Operaciones:**
- sus **usuarios** pasan al perfil Gerente General Adjunto;
- sus permisos, sus destinatarios de alertas (también los de alertas abiertas) y los parámetros que la nombraban pasan al Gerente General Adjunto;
- el perfil se elimina;
- queda en la auditoría como `PERFIL_RETIRADO_CATALOGO`, con la lista de usuarios movidos.

**Otros cambios:**
- `jefe_por_rol` suma «Coordinación de Finanzas → Jefe de Administración y Finanzas» si no estaba.
- Los nombres de los perfiles cambian.
- Las cuentas de ejemplo cambian de nombre solo si conservan el anterior.

**No se cambia** el nombre de usuario con que se ingresa; por ejemplo, `vendedor1` sigue igual.

Para crear la cuenta del Jefe de Administración y Finanzas en el servidor:

```bash
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/python -m app.cli crear-usuario <usuario> JEFE_ADMIN_FINANZAS "<Nombre>" <correo>'
```

## 4. Por confirmar

- **Perfil «Supervisión de Almacén (por almacén)»** (`SUPERV_ALMACEN`): es un perfil de apoyo con menos permisos. Sus cuentas de ejemplo se renombraron a «Supervisión de Almacén (por almacén) 1560 / 1524» para no confundirlas con los supervisores. Confirmar si ese puesto existe o se retira.
- **Jefe del Jefe de Administración y Finanzas** en el organigrama (`jefe_por_rol`): no se indicó y no se asignó. Si no atiende una tarea, por ahora no se escala a nadie más.

## 5. Datos técnicos

- Catálogo:
  - bloque V16 al final de `app/catalogs.py`;
  - `ROLES_FUSIONADOS`, `roles_equivalentes`, `DEMO_RENOMBRE`.
- Sincronización: `seed._merge_roles`.
- `core.roles_of` incluye los perfiles equivalentes.
- `alerts.is_direct` decide qué tareas suenan.
- Interfaz:
  - sonidos en `app/static/app.js`;
  - colores en `app/static/style.css`.
- Pruebas: `tests/test_v16.py`. Suite completa: 410 pasan y 1 se omite (SQLite); las de V16, V14 y flujos también en PostgreSQL 16.
