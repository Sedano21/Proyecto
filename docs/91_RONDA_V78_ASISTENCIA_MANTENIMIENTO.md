# Ronda V78 (27-nov-2026): asistencia del personal de Mantenimiento

Fuente: el mensaje del usuario del 27-nov. En «Asistencia de mi personal», el Jefe de Mantenimiento debe ver a los de su
área: los usuarios con perfil Técnico de Mantenimiento y Personal de Limpieza.

## Qué pasaba
- **De dónde sale la lista:** la asistencia se registra sobre los «colaboradores» (tabla `workers`), no sobre los usuarios
  del sistema.
- **Por qué estaba vacía:** los técnicos y el personal de limpieza tenían usuario, pero nadie los había dado de alta como
  colaboradores del área. Por eso el Jefe de Mantenimiento veía la lista vacía.

## Qué se hizo
- **Alta automática:** al abrir Asistencia, los usuarios activos de los perfiles configurados figuran solos como
  colaboradores de su área, ligados a su usuario.
  - Parámetro nuevo «asistencia_roles_por_area»: `{"Mantenimiento": ["TECNICO_MANTENIMIENTO", "PERSONAL_LIMPIEZA"]}`.
  - Se puede ampliar a otras áreas desde Configuración.
- **Usuario y rol en pantalla:** cada persona muestra, bajo su nombre, «Usuario: tecnico.mant1».
  - Su rol (Técnico de Mantenimiento, Personal de Limpieza) va en la columna de puesto.
  - El nombre y el rol se mantienen como están en Usuarios: si se corrigen allí, se ven aquí.
  - En el resumen de los últimos 30 días, el usuario aparece entre paréntesis.
- **Sin duplicados:**
  - Si ya hay un colaborador ligado al usuario, no se crea otro.
  - Si ya había un colaborador de Mantenimiento con el mismo nombre (registrado a mano o desde Limpieza), se le liga.
- **Usuario desactivado:** deja de figurar en la asistencia. Si se reactiva, vuelve.
- **Baja manual del jefe:** si el jefe da de baja al colaborador, se respeta y la sincronización no lo reactiva.
- **Trazabilidad:** cada alta, enlace, baja o reactivación queda en la auditoría.
- **Otras pantallas:** el mismo personal aparece en las pantallas de Mantenimiento que usan los colaboradores del área
  (limpieza por persona, disponibilidad del personal).

## Qué no cambia
- **Permisos:** cada jefatura sigue viendo solo su área. Producción no ve al personal de Mantenimiento.
- **Servidor:** no cambian la base de datos (sin migración) ni las variables del servidor. El parámetro nuevo lo agrega
  `app.cli init`, que la actualización automática ya ejecuta.

## Pruebas
`tests/test_v78.py`: 8 pruebas.
- Aparecen en la lista que ve y registra el jefe.
- Aparecen en la pantalla del jefe y no en la de Producción.
- No hay duplicados y se ligan a un colaborador existente.
- Un usuario desactivado sale y vuelve al reactivarse.
- Se respeta la baja manual del jefe.
- Sin configuración, la sincronización no hace nada.
- Se muestran el usuario y el rol.
- El nombre y el rol siguen al usuario.
