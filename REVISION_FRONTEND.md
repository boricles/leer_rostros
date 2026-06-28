# Revisión frontend — `frontend/index.html` (handoff para el equipo de frontend)

Hallazgos de **lógica/UX** detectados en una revisión (skill `ui-ux-pro-max` + auditoría
de lógica). **No se modificó `index.html`** — el frontend lo maneja otro equipo. Aquí van
los defectos con fix concreto. No son cambios de diseño visual.

> **La card de "Conectar WhatsApp (QR)" fue REMOVIDA de `index.html`** (el frontend lo
> implementa este equipo). El backend ya expone lo necesario para construirla:
> `GET /api/addon/whatsapp/qr` (devuelve `{enabled, instance, state, connected, base64,
> pairing_code}`, con **cache ~25 s** para no resetear el emparejamiento) y
> `GET /api/addon/whatsapp/estado` (solo estado, sin regenerar QR). Ambos requieren el
> header `Authorization: Bearer <token>` del admin. Los puntos 1–2 de abajo son la guía
> para implementarla bien.

## Mayores

1. **El poll del QR debe pegarle a `/estado`, no a `/qr`.**
   `waStart` hace `setInterval` cada 6 s sobre `/api/addon/whatsapp/qr`; ese endpoint
   dispara `connect()` en Evolution. Fix: traer el QR **una vez** al pulsar "Mostrar QR",
   y en el intervalo consultar `/api/addon/whatsapp/estado`; parar cuando `connected===true`.

2. **Expiración del QR.** El QR de Evolution caduca (~20–60 s). Hoy se muestra fijo y, si no
   conecta, el usuario escanea un QR muerto sin aviso. Fix: al pasar la vida útil sin
   conectar, mostrar "El QR expiró, genera uno nuevo" y re-pedir `/qr` una vez.

3. **Expiración de sesión (JWT 401) sin manejo.** Cuando el token vence, los `fetch`
   autenticados devuelven 401. En `cargarModeracion` se hace `.json()` sin chequear `r.ok` y
   luego `d.map()` sobre un cuerpo de error → `TypeError`, panel muerto y sin mensaje. Fix:
   guard central — si `r.status===401`: limpiar `ADMIN_TOKEN`, mostrar `loginCard`, ocultar
   `adminPanel`, `waStopPoll()`, y avisar "Tu sesión expiró, vuelve a iniciar sesión".
   En `cargarModeracion`, chequear `r.ok` antes de `.json()` y `Array.isArray(d)` antes de `.map()`.

4. **`moderar()` / `eliminar()` no revisan la respuesta.** Si el PATCH/DELETE falla (401, 502,
   red) se ignora y se re-renderiza la lista como si hubiera funcionado. Fix: chequear `r.ok`,
   mostrar error, y deshabilitar el botón mientras está en vuelo (evita doble click).

5. **Botón de login sin guard de doble submit.** `adminLogin` no deshabilita `adm_login`
   durante el POST. Fix: `b.disabled=true` al entrar y `finally{ b.disabled=false }`,
   como hacen `f_btn`/`r_btn`/`a_btn`.

## Menores

6. **Errores/estados solo visuales.** Los contenedores de resultado/error (`f_res`, `r_res`,
   `a_res`, `m_res`, `adm_loginres`, `wa_estado`) no tienen `role="alert"` / `aria-live`, así
   que lectores de pantalla no anuncian fallos ni "Cargando…". Fix: `aria-live="assertive"`
   en los de error y `aria-live="polite"` en los de carga.

7. **Fuga de object URLs en `preview()`.** `URL.createObjectURL` se llama en cada cambio de
   archivo sin `revokeObjectURL` del anterior. Fix: revocar el blob previo antes de asignar
   el nuevo `src`.

8. **`personTitle(c,'Menor')` ignora el 2º argumento.** `personTitle(p)` solo acepta uno; un
   registro sin nombre y sin `es_menor` muestra "Sin nombre registrado" en vez de "Menor".
   Fix: agregar parámetro `fallback` real o quitar el argumento.

9. **Limpieza de polling incompleta.** `waStopPoll()` corre al cambiar de pestaña pero no en
   logout/expiración de sesión ni en `beforeunload`. Fix: llamarlo en el handler de 401 y en
   `window.addEventListener('beforeunload', waStopPoll)`.

10. **Focus / accesibilidad de botones.** No hay regla `:focus-visible` para `.tab/.go/.esmifam`;
    tras login el foco queda en el botón oculto. Fix: outline en `:focus-visible` y mover foco
    al panel/heading tras login y a la región de resultados tras renderizar.

11. **Sin espacio reservado para contenido async.** `wa_qrbox` (display:none) y las áreas de
    resultados causan salto de layout al llegar el contenido. Fix: `min-height` acorde.

## Nota
La parte 1 ya está mitigada en backend (cache del QR + endpoint `/estado`), pero el cambio del
poll en el cliente es lo que realmente evita el churn. Las demás (3, 4, 5) son las de mayor
impacto en uso real del panel.
