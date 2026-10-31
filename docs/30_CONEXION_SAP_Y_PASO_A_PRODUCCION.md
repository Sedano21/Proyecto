# Conexión con SAP robusta y paso a la base real (31-oct-2026)

## 1. Qué hace el sistema si el túnel o SAP se caen

| Situación | Qué hace el módulo |
|---|---|
| Se registra una OV con SAP caído | La OV se guarda en el módulo y queda **en cola** («en cola» en su ficha). No se pierde nada. |
| Vuelve la conexión | La sincronización automática, cada minuto de 06:00 a 21:00, envía lo que está en cola, en orden. |
| El envío llegó a SAP pero se cortó la respuesta | Antes de crear, el módulo busca en SAP la OV (por «OV <número> del módulo» en Comentarios y el cliente). Si ya existe, la enlaza y **no la duplica**. |
| Alguien modificó, cerró o canceló la OV en SAP | El módulo **no la sobrescribe**. Queda «en conflicto», con una alerta al creador. Comercial o Sistemas decide en la ficha: «Enviar a SAP de todos modos» o ajustar el módulo. |
| SAP no responde | Alerta «SAP sin conexión» a Sistemas, Ventas y Gerente General Adjunto. Aviso rojo en la parte superior para quien registra OV o guías. Al volver la conexión, la alerta se cierra sola. |

Para ver el estado: **Administración → Integración SAP (estado y cola)**. Muestra:
- la conexión;
- las OV en cola y en conflicto;
- la última carga de cada tipo.

Desde la consola del servidor:

```bash
sudo -u operaciones bash -c 'set -a; . /etc/operaciones/operaciones.env; cd /opt/operaciones; .venv/bin/python -m app.cli sap-diagnostico'
```

El diagnóstico revisa:
- el ingreso a SAP;
- cuántos clientes, artículos, OV abiertas y entregas lee;
- si los almacenes habilitados existen en SAP;
- los clientes sin RUC;
- si la escritura está permitida;
- la cola de OV.

## 2. El túnel: cómo dejarlo estable

**Hoy (mientras se gestiona la solución definitiva):**
1. `tunel_sap.bat` en la carpeta Inicio del usuario de la VM. Reconecta solo cada 15 segundos.
2. En la VM:
   - la suspensión en «Nunca» (ya está así, según la captura del plan de energía);
   - **no** «Cerrar sesión»: solo cerrar la ventana de RDP con la X, para que la sesión siga abierta y el túnel también.
3. En AWS, `ClientAliveInterval 15` y `ClientAliveCountMax 3` (`/etc/ssh/sshd_config.d/tunel.conf`), para que el puerto se libere si la conexión se corta.
4. El módulo trabaja con la cola descrita arriba: si el túnel se cae, nadie pierde lo registrado.

**Definitivo (recomendado; lo debe aprobar el proveedor de la VM o de SAP):** que la conexión no dependa de una sesión de Windows. Opciones, de mejor a menor:
- **VPN sitio a sitio** entre AWS (Site-to-Site VPN) y la red del proveedor, abierta solo hacia `172.18.103.1:50000`.
- El proveedor **publica el Service Layer** (proxy inverso HTTPS) solo para la IP de AWS `13.216.163.203`.
- Que el proveedor instale el túnel como **servicio de Windows**. Requiere administrador: OpenSSH o `plink` con NSSM, que arranca sin que nadie inicie sesión.

## 3. Cargas de SAP: dónde se confirman

- `python -m app.cli cargas` lista las últimas cargas, con su estado, las filas con error y el permiso que las confirma.
- `python -m app.cli carga <n>` muestra los errores agrupados y una fila de ejemplo.
- Quién confirma cada carga:
  - **Clientes**: Comercial (permiso `ov.importar`: Coordinador o Jefe de Ventas). Menú Comercial → Cargas de archivos.
  - **Artículos**: Sistemas o Configuración. Menú Administración → Cargas de configuración.
- RUC de los clientes de SAP: si `FederalTaxID` viene vacío o con otros caracteres, el módulo usa los dígitos del propio campo o del código del cliente (8 u 11 dígitos, por ejemplo `C20123456789`).

## 4. Inventario descuadrado en SAP: cómo sincerarlo

1. **Conteo físico en el módulo** (Almacén → Conteos físicos). Por almacén, contra la cantidad de SAP, con recuento si la diferencia supera la tolerancia.
2. **Diferencias en Excel**: botón «Diferencias en Excel (para el ajuste en SAP)» en cada conteo. Trae código, lote, cantidad SAP, físico, diferencia y si es entrada o salida.
3. **Ajuste en SAP** por el responsable de SAP (recuento y contabilización de inventario, o entradas y salidas de ajuste). Así SAP queda igual al físico.
4. **Traer el stock de SAP** al módulo (carga de stock) y confirmarlo.

Mientras SAP no esté ajustado, el módulo usa para reservar y despachar **la menor** entre la cantidad de SAP y la contada. Nunca promete más de lo que hay físicamente.

## 5. Lista para pasar a la base real (lunes)

1. Conteo cerrado y ajuste registrado en SAP real (punto 4).
2. **Usuario de integración** en SAP real, con permisos solo de lo que usa: leer maestros y documentos, y crear, actualizar y cancelar OV. No usar `manager`.
3. En `/etc/operaciones/operaciones.env`:
   - `SAP_SL_COMPANY=<base real>`;
   - `SAP_SL_USER` y `SAP_SL_PASSWORD` del usuario de integración.
4. En Configuración → Integración SAP, **agregar la base real** a `sap_escritura_empresas`. Sin esto no se escribe nada en la base real.
5. `sap-diagnostico` sin fallas. Los almacenes habilitados deben existir en SAP.
6. Traer clientes, artículos y stock desde SAP real y confirmar las cargas.
7. Probar una OV de prueba controlada:
   - crearla;
   - verla en SAP;
   - modificarla;
   - cancelarla.

   Luego probar una OV creada en SAP que llegue al módulo.
8. Reiniciar el servicio: `sudo systemctl restart operaciones`.

## 6. Registros y respaldos

- **Auditoría** (Administración → Auditoría): quién hizo qué y cuándo. Incluye los cambios de datos, las OV enviadas a SAP y los conflictos.
- **Registro del servidor**: `journalctl -u operaciones` (peticiones y errores) y `/var/log/operaciones-actualizar.log` (actualizaciones).
- **Respaldo diario** de la base y de los archivos (03:00, 14 días) en `/var/backups/operaciones`. Se suma el respaldo antes de cada actualización.
- **Copia fuera del servidor** (recomendada): `deploy/respaldo_s3.sh` copia los respaldos a un bucket S3 privado. Requiere crear el bucket y darle a la instancia un rol IAM con permiso de escritura.
