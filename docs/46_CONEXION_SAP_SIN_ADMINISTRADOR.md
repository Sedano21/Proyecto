# 46 · Conexión con SAP cuando no hay permisos de administrador en la VM

**Situación (08-nov-2026):**
- El Service Layer de SAP (`172.18.103.1:50000`) está en una red privada.
- En la máquina virtual (VM) desde la que se entra a SAP se pueden descargar programas, pero no instalarlos: piden una
  cuenta de administrador.
- WireGuard para Windows se instala como servicio, así que necesita administrador.

## 1. Lo que hay que saber

Para que el servidor de Lightsail llegue a SAP **de forma permanente**, sin depender de que alguien tenga una sesión
abierta, **alguien con permisos sobre la red o sobre un equipo de esa red debe hacer una configuración una sola vez**.

Sin administrador, cualquier conexión (túnel SSH, cloudflared portátil, etc.) es un programa que corre dentro de la
sesión de un usuario:
- se corta si se cierra la sesión;
- se corta si la VM se reinicia (por ejemplo, por las actualizaciones de Windows).

No hay forma técnica de evitarlo sin ese permiso.

## 2. Solución definitiva: pedirla una vez a quien administra SAP o su red (partner o TI)

Cualquiera de estas tres opciones. Están ordenadas de la más simple a la más compleja:

| Opción | Qué hace el proveedor | Qué se hace en el servidor |
|---|---|---|
| **A. Regla de firewall (recomendada)** | Publica el puerto 50000 del Service Layer **solo para la IP 32.198.172.171** (NAT + regla de origen). El tráfico ya va cifrado por HTTPS. | `SAP_SL_URL=https://<IP pública de SAP>:50000/` y el certificado en `sap_ca.pem`. Nada más. |
| B. WireGuard en un equipo de esa red | Con su cuenta de administrador instala WireGuard (10 min) en la VM, en el servidor SAP o en un Linux siempre encendido. Usa la configuración `deploy/vpn/wg-sap-windows.conf.ejemplo`. Queda como servicio y arranca solo. | Paso 9 de la guía 44 (ya preparado). |
| C. VPN de sitio a sitio | Configura su firewall (IPsec) contra el servidor. | Requiere coordinación técnica; solo si su política lo exige. |

**Texto para enviar al proveedor (opción A o B):**

> Necesitamos que el sistema de operaciones, alojado en AWS con la IP fija **32.198.172.171**, consuma el **Service
> Layer de SAP Business One** (`https://172.18.103.1:50000/b1s/v1`) con un usuario de integración.
>
> Solicitamos una de estas opciones:
> (A) publicar el puerto 50000/TCP del Service Layer únicamente para el origen 32.198.172.171 e indicarnos la IP
> pública; o
> (B) instalar WireGuard con su cuenta de administrador en un equipo de la red de SAP, con la configuración que les
> enviamos (solo permite el tráfico hacia 172.18.103.1:50000).
>
> Además pedimos:
> - un **usuario de integración** de SAP (no *manager*) con los permisos del Service Layer para la base
>   ZZZ_CORPRODUC_TEST260826 y luego para la productiva;
> - el certificado (o la CA) del Service Layer.

## 3. Mientras tanto: túnel de respaldo (sin administrador, sin instalar nada)

Usa el `ssh.exe` que ya trae Windows. La llave solo sirve para abrir el puerto 50000 local del servidor: con ella no
se entra a la consola ni se llega a ningún otro sitio.

**En la VM (cmd, una sola vez):**
```bat
ssh-keygen -t ed25519 -f "%USERPROFILE%\.ssh\tunel_sap" -N "" -C tunel-sap
type "%USERPROFILE%\.ssh\tunel_sap.pub"
```
Copie la línea que muestra (empieza con `ssh-ed25519`).

**En el servidor:**
```bash
sudo bash /opt/operaciones/deploy/vpn/tunel_ssh_servidor.sh "ssh-ed25519 AAAA…  tunel-sap"
```
En Lightsail → Networking, el puerto **22** debe estar abierto. Lo ideal es abrirlo solo para la IP pública de salida
de la red de la VM.

**En la VM:**
1. Copie `deploy/tunel_sap.bat` (ya apunta a 32.198.172.171) a la carpeta que abre `shell:startup`
   (Win + R → `shell:startup`).
2. Ejecútelo una vez. La ventana debe quedar en «Conectando…» sin errores. Minimícela.
3. Al salir del Escritorio remoto, **desconecte con la X; no use «Cerrar sesión»**. Así el túnel sigue abierto.

**En el servidor:**
```bash
ss -ltn | grep 127.0.0.1:50000           # el túnel está arriba
# El certificado del Service Layer trae el nombre del servidor SAP, no 127.0.0.1. Se lee y se apunta ese nombre a 127.0.0.1:
openssl s_client -connect 127.0.0.1:50000 </dev/null 2>/dev/null | openssl x509 -noout -subject
#   p. ej. «subject=CN = hanab1» → nombre = hanab1
echo "127.0.0.1 hanab1" | sudo tee -a /etc/hosts
openssl s_client -connect 127.0.0.1:50000 -showcerts </dev/null 2>/dev/null | sed -n '/BEGIN CERT/,/END CERT/p' | sudo tee /etc/operaciones/sap_ca.pem
sudo sed -i 's#^SAP_SL_URL=.*#SAP_SL_URL=https://hanab1:50000/#' /etc/operaciones/operaciones.env
sudo sed -i 's#^SAP_SL_CA=.*#SAP_SL_CA=/etc/operaciones/sap_ca.pem#' /etc/operaciones/operaciones.env
sudo systemctl restart operaciones
sudo bash /opt/operaciones/deploy/verificar_servidor.sh coprod-one.duckdns.org --sap
```
Confirme la huella del certificado con el partner antes de dar por buena la conexión.

**Si la prueba dice «certificate has expired» (o no coincide el nombre):** el certificado propio del Service Layer
venció. Lo correcto a mediano plazo es que el partner lo renueve. Mientras tanto, se fija ese certificado exacto por su
huella: la conexión solo se acepta si SAP presenta ese mismo certificado, aunque esté vencido. No es lo mismo que
desactivar la verificación (`SAP_SL_VERIFY=0`), que no se recomienda.
```bash
H=$(openssl x509 -in /etc/operaciones/sap_ca.pem -noout -fingerprint -sha256 | cut -d= -f2); echo "$H"
grep -q '^SAP_SL_HUELLA=' /etc/operaciones/operaciones.env && sudo sed -i "s#^SAP_SL_HUELLA=.*#SAP_SL_HUELLA=$H#" /etc/operaciones/operaciones.env || echo "SAP_SL_HUELLA=$H" | sudo tee -a /etc/operaciones/operaciones.env
sudo systemctl restart operaciones
```
Cuando el partner renueve el certificado, repita la lectura del certificado y de la huella.

**Si el túnel se cae:**
- El sistema **no pierde nada**: lo que se registra para SAP queda en cola.
- Sistemas recibe la alerta «SAP sin conexión (túnel o red)», que se cierra sola al volver la conexión.
- Para reconectar basta con volver a entrar a la VM.

Cuando esté lista la opción A o B, quite `tunel_sap.bat` de `shell:startup` y bloquee el usuario del túnel:
```bash
sudo usermod -L -s /usr/sbin/nologin tunelsap && sudo rm /var/lib/tunelsap/.ssh/authorized_keys
```

## 4. Que el túnel siga al cerrar la sesión (prueba sin administrador)

El proveedor cierra las sesiones desconectadas a las ~3 horas (es su política de Escritorio remoto). Al cerrarse la
sesión se cierran sus programas, incluido el túnel. Windows permite que el propio usuario programe una tarea que corre
**aunque no haya sesión abierta**, siempre que su cuenta tenga el permiso «Iniciar sesión como proceso por lotes».
Muchos servidores no se lo dan a los usuarios comunes. No hay forma de saberlo sin probar:

1. Copie `tunel_sap.bat` a `%USERPROFILE%\tunel_sap.bat` (la carpeta del usuario).
2. En cmd (pide la contraseña de Windows de su usuario, la de la VM):
   ```bat
   schtasks /create /tn "Tunel SAP" /tr "\"%USERPROFILE%\tunel_sap.bat\"" /sc minute /mo 10 /ru "%USERDOMAIN%\%USERNAME%" /rp *
   schtasks /run /tn "Tunel SAP"
   ```
   Cada 10 minutos la tarea revisa que esté corriendo; si ya corre, no abre otra. También vuelve sola después de un
   reinicio de la VM.
3. Cierre el `.bat` abierto en pantalla y quítelo de `shell:startup` (así no corren dos). En el servidor:
   `ss -ltn | grep 127.0.0.1:50000` debe seguir mostrando el túnel. Salga del Escritorio remoto y vuelva a revisarlo
   a las 4 horas.
4. Resultado:
   - Si `schtasks /create` responde **«Acceso denegado»**, o el estado de la tarea queda en
     «No se pudo iniciar» (`schtasks /query /tn "Tunel SAP" /v /fo list`), el usuario no tiene ese permiso. Bórrela:
     `schtasks /delete /tn "Tunel SAP" /f`. Queda la solución del punto 2 de esta guía.
   - Si el túnel sigue arriba con la sesión cerrada, ya no depende de la sesión.
   - Si cambia la contraseña de Windows del usuario, la tarea deja de correr: vuelva a crearla.

## 5. Propuesta del asesor: «aplicación intermedia publicada por el partner»

Es viable, pero no evita al partner ni su posible cobro: igual tiene que **instalarla en su servidor** (con
administrador) y **publicarla** a internet (NAT/firewall). Es lo mismo que la opción A, más un programa adicional que
alguien debe mantener.

- El Service Layer ya es una aplicación web con usuario, contraseña y HTTPS. Publicarlo **solo para la IP
  32.198.172.171** da el mismo resultado y es menos trabajo para el partner.
- Si su política no permite publicar el Service Layer directamente, la alternativa equivalente es un **proxy inverso**
  (IIS/nginx) que reenvíe las mismas rutas `/b1s/v1/` y solo acepte esa IP. El sistema funciona sin cambios: solo se
  cambia `SAP_SL_URL`.
- Hay que evitar una API «a medida» del partner: obligaría a adaptar el sistema y dependeríamos de ellos para cada
  cambio.

**Qué pedir en la cotización:** el precio de (1) publicar el puerto 50000 del Service Layer restringido a la IP
32.198.172.171, o (2) un proxy inverso transparente con la misma restricción. Se elige la más barata. Es un pago único
de configuración; no debería generar costo mensual.
