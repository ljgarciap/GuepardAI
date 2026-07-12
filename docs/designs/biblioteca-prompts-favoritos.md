# Design: Biblioteca de Prompts Favoritos

**Date**: 2026-07-12
**Architect**: aprobado (pendiente confirmación final de Luis en este documento)
**Spec**: `docs/specs/biblioteca-prompts-favoritos.md`
**Status**: Draft — listo para revisión de Luis antes de pasar al PM
**Decisiones de negocio confirmadas** (2026-07-12): visibilidad jerárquica por
rol (cliente → propios, admin → tenant, superadmin → todos), escritura
exclusiva del dueño sin excepción de rol, sin límite de favoritos, botón
"Save as favorite" junto al textarea persistente del prompt (no un modal
existente — ver Frontend).

## Riesgo arquitectónico principal

Esta es la primera vez que el proyecto necesita una visibilidad de **3
niveles** (dueño / tenant-admin / superadmin) sobre un mismo recurso. El
patrón existente más cercano, `_tenant_scoped_users()`
(`backend/routers/users.py:26`), solo resuelve 2 niveles (superadmin ve todo,
cualquier otro rol ve su tenant) — no aplica tal cual porque acá "admin" y
"cliente" no deben ver lo mismo. Se escribe un helper nuevo específico de este
router (`_visible_favorites_query`) en vez de generalizar prematuramente
`_tenant_scoped_users()` para 3 niveles — si aparece un segundo caso real con
la misma jerarquía, ahí se extrae. El riesgo real a vigilar es de permisos:
la visibilidad extendida de admin/superadmin es **de solo lectura** — el
Senior Reviewer debe verificar explícitamente que ningún endpoint de escritura
(`PUT`/`DELETE`) usa `_visible_favorites_query` como única puerta de
autorización (ver Backend §3).

## Backend

### 1. Modelo y tabla nueva

```sql
CREATE TABLE IF NOT EXISTS prompt_favorites (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    tenant_id INTEGER REFERENCES tenants(id),
    title VARCHAR(120) NOT NULL,
    prompt_text TEXT NOT NULL,
    prompt_metadata JSONB,
    source_job_id INTEGER REFERENCES generation_jobs(id),
    created_at TIMESTAMP DEFAULT now(),
    updated_at TIMESTAMP DEFAULT now()
);
```

- Tabla nueva (no ALTER) → creada por `Base.metadata.create_all()` al
  arrancar, mismo criterio que `presentation_reviews`/
  `generation_job_collaborators`.
- `models.PromptFavorite`:
  - `user_id = Column(Integer, ForeignKey("users.id"), nullable=False)` —
    a diferencia de `GenerationJob.owner_id`, acá es obligatorio: un favorito
    sin dueño no tiene sentido de negocio (no es un dato histórico
    migrado, nace siempre con owner).
  - `tenant_id = Column(Integer, ForeignKey("tenants.id"), nullable=True)` —
    nullable solo para permitir que un `superadmin` (sin tenant) cree
    favoritos propios; se asigna de `current_user.tenant_id` al crear, nunca
    del body.
  - `prompt_metadata = Column(JSONB, nullable=True)` — mismo shape que
    `GenerationJob.prompt_metadata` (`models.py:312`) y la interfaz TS
    `PromptMetadata` (`brand.service.ts:37-47`). No se define un tipo
    compartido a nivel Pydantic en esta iteración (serían 2 líneas de
    duplicación, no vale la pena la abstracción todavía).
  - `source_job_id = Column(Integer, ForeignKey("generation_jobs.id"), nullable=True)`.
    **Sin `ondelete=` a nivel DB** — el proyecto no usa `ondelete=` en ningún
    `ForeignKey` existente (verificado, cero ocurrencias en `models.py`);
    la limpieza es explícita a nivel aplicación, mismo patrón que
    `GenerationJobFeedback`/`ArtDirectorDecision` en el delete de portfolio.
  - `updated_at` — primer uso de este patrón en el proyecto junto a
    `created_at` con default separado; usar
    `Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)`
    para que `PUT` lo actualice solo, sin lógica manual en el router.

### 2. Integración obligatoria con el delete de portfolio (evita un FK error 500)

`DELETE /api/library/portfolios/{job_id}` (`backend/main.py:699-720`) borra
`GenerationJobFeedback`/`ArtDirectorDecision` explícitamente antes de
`db.delete(job)` porque no hay cascade a nivel DB. `PromptFavorite.source_job_id`
queda en la misma situación: si no se toca, borrar un job que tiene favoritos
apuntándolo revienta con `IntegrityError` (500), no con un error controlado.
Agregar, en el mismo bloque (antes de `db.delete(job)`):

```python
db.query(models.PromptFavorite).filter(
    models.PromptFavorite.source_job_id == job_id
).update({"source_job_id": None}, synchronize_session=False)
```

Esto es parte de esta feature, no un fix aparte — sin este paso, el criterio
de aceptación "`source_job_id` queda huérfano, no bloquea ni rompe el
favorito" (spec, Edge cases) es falso en la práctica.

### 3. Endpoints nuevos — `backend/routers/prompt_favorites.py`

Prefijo `/api/prompts/favorites`, mismo patrón inline-Pydantic que
`template_merge.py` (sin `backend/schemas/` dedicado — no hay otro consumidor
de estos shapes todavía).

```python
def _visible_favorites_query(db: Session, current_user: models.User):
    """Visibilidad de 3 niveles, exclusiva de PromptFavorite — NO usar como
    puerta de escritura, solo de lectura (ver §4)."""
    query = db.query(models.PromptFavorite)
    if current_user.role == models.UserRole.SUPERADMIN.value:
        return query
    if current_user.role == models.UserRole.ADMIN.value:
        return query.filter(models.PromptFavorite.tenant_id == current_user.tenant_id)
    return query.filter(models.PromptFavorite.user_id == current_user.id)
```

- `POST /api/prompts/favorites` — body `{title, prompt_text, prompt_metadata?,
  source_job_id?}`. `user_id`/`tenant_id` del `current_user`, nunca del body
  (mismo criterio que `owner_id` en `create_template_merge_job`). 201.
- `GET /api/prompts/favorites` — `_visible_favorites_query(...).order_by(desc(created_at))`.
  Cada item de la respuesta incluye `owner_email` (join simple a `User`) —
  siempre presente, no solo cuando el rol lo requiere, para no bifurcar el
  contrato de respuesta por rol.
- `PUT /api/prompts/favorites/{id}` y `DELETE /api/prompts/favorites/{id}` —
  ver §4, autorización estricta de dueño.

### 4. Autorización de escritura (el punto que el Senior Reviewer debe auditar)

```python
def _get_favorite_or_404(db, current_user, favorite_id):
    fav = _visible_favorites_query(db, current_user).filter(
        models.PromptFavorite.id == favorite_id
    ).first()
    if fav is None:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return fav

@router.put("/{favorite_id}")
def update_favorite(favorite_id: int, payload: ..., db=Depends(get_db), current_user=Depends(get_current_user)):
    fav = _get_favorite_or_404(db, current_user, favorite_id)
    if fav.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can edit this favorite")
    ...
```

- `_get_favorite_or_404` reusa la visibilidad de lectura de 3 niveles para
  decidir 404 vs "existe pero no es tuyo": un `cliente`/`admin` de otro tenant
  recibe 404 (no revela que el recurso existe fuera de su alcance de
  lectura); un `admin` del mismo tenant que ve el favorito pero no es el
  dueño recibe 403 (lo ve, no puede tocarlo). Mismo comportamiento para
  `DELETE`.
- Esta es la única puerta de escritura — no hay bypass de rol acá, a
  diferencia de `_require_job_owner_or_tenant_admin` en `collaborators.py`
  (que sí deja escribir a un tenant-admin). Divergencia intencional,
  confirmada por Luis en la spec: favoritos son de escritura exclusiva del
  dueño.

### AI Decision Records
No aplica — sin llamadas a `providers/llm_provider.py` en esta spec. No
requiere consulta al AI Architect.

## Frontend (Angular 19, standalone)

### Servicio nuevo — `services/prompt-favorites.service.ts`
Separado de `brand.service.ts`, mismo criterio que
`services/collaboration.service.ts` (creado en la spec de reviews/colaboración
"por sugerencia del propio design doc" — favoritos es un recurso con
lifecycle propio, no una extensión de Brand/Portfolio). Métodos:
`listFavorites()`, `createFavorite()`, `updateFavorite(id, ...)`,
`deleteFavorite(id)`.

### `generator.component.ts` / `.html`

Corrección sobre la spec: no existe un "Step 3, Content Directive" en este
componente (esa numeración es de `template-merge.component.html`) — el
prompt libre vive en el `command-area` persistente
(`generator.component.html:164-190`), fuera del hero/tarjetas.

- **4ta tarjeta** en `.compositor-cards` (`generator.component.html:76-92`,
  junto a `openReuseModal()`/`openIntentModal()`/`openComposerModal()`):
  `openFavoritesModal()` — lista los favoritos visibles del usuario (propios;
  el filtro de rol lo resuelve el backend, el frontend no reimplementa
  lógica de visibilidad), al elegir uno llama `applyPromptText(fav.prompt_text)`
  (`generator.component.ts:144`, ya devuelve `boolean` y ya maneja el
  confirm-antes-de-sobreescribir) y, si aceptó, `promptMetadata = fav.prompt_metadata`
  — mismo flujo exacto que `openReuseModal`/`openComposerModal`, sin lógica
  nueva de confirmación.
- **Botón "☆ Save as favorite"** en `.input-actions`
  (`generator.component.html:172-188`, junto al toggle de AI images y el
  botón `CREATE PRESENTATION`), `[disabled]="!prompt"`. Abre un modal mínimo
  (`.feedback-modal-card`, mismo patrón visual que el modal de rating ya
  existente en este mismo archivo, líneas 193-230) que solo pide `title` y
  llama `createFavorite({title, prompt_text: this.prompt, prompt_metadata: this.promptMetadata})`.

### `asset-library.component.ts` / `.html`

- `activeTab` (`asset-library.component.ts:26`) gana `'prompts'` como quinta
  opción.
- Panel nuevo: lista de favoritos visibles (columna "Owner" siempre visible —
  para un `cliente` siempre es su propio email, no hace daño mostrarlo, evita
  bifurcar la plantilla por rol), edición inline de `title`/`prompt_text` o
  modal (`.feedback-modal-card`), borrado con `confirm()` nativo — mismos 3
  patrones ya usados en el panel de Reviews & Team.
- Sin botón "crear nuevo" en esta pestaña — la creación nace en
  `GeneratorComponent` (spec no pide lo contrario; evita duplicar el flujo de
  "escribir un prompt desde cero" en dos lugares).

## Dependencias entre tareas

1. Tabla + modelo `PromptFavorite` — sin dependencias, arranca primero.
2. Fix del delete de portfolio (§2) — depende de (1) (necesita el modelo
   importado), pero es un cambio de una función existente, no bloquea nada
   más; puede ir en el mismo PR que (1).
3. Endpoints CRUD (§3-4) — depende de (1).
4. `prompt-favorites.service.ts` — depende de (3) estar desplegado en un
   entorno de prueba (o mockeado para maquetar en paralelo).
5. `generator.component` (4ta tarjeta + botón guardar) — depende de (4).
6. `asset-library.component` (pestaña Prompts) — depende de (4), sin
   dependencia con (5) (pueden ir en paralelo, son componentes distintos).

## Riesgos y mitigación

- **Confusión de autorización lectura-vs-escritura** (ver Riesgo arquitectónico
  principal): mitigado con test de regresión explícito — un `admin` que ve un
  favorito ajeno de su tenant en `GET` debe recibir 403 en `PUT`/`DELETE`
  sobre ese mismo `id`. QA debe incluir este caso, no es opcional.
- **Olvidar el fix del delete de portfolio** (§2): sin él, esta feature
  introduce una regresión en un endpoint existente y ya en producción (500 en
  vez del comportamiento actual). Se marca como parte del mismo PR, no como
  tarea separada que el PM pueda posponer.
- **Duplicar lógica de confirm-antes-de-sobreescribir** en el modal de
  favoritos: mitigado reusando `applyPromptText()` tal cual, sin reimplementar
  el confirm.

## Estimación de esfuerzo

- Backend (modelo + tabla + 4 endpoints + fix del delete de portfolio +
  tests): 1–1.5 días.
- Frontend (servicio + 4ta tarjeta + modal de guardado + pestaña en
  Library): 1.5–2 días.
- Tech Writer (doc de API + actualización de manuales de usuario): 0.5 día,
  en paralelo.

---

## Extensión: facilidad compartida con Template Merge + modal de confirmación estilizado (2026-07-12)

**Feedback de Luis sobre lo ya entregado**: (1) el alert de "reemplazar tu
prompt" era el `window.confirm()` genérico del navegador, no un modal propio;
(2) Template Merge no tenía ninguna de las 4 ayudas (era un textarea suelto)
y no tiene sentido mantener dos implementaciones de lo mismo — pidió una sola
facilidad compartida entre las dos pantallas de generación.

**Decisiones confirmadas con Luis**:
- Modal de confirmación propio (mismo estilo `.feedback-modal-card`), no
  SweetAlert2 — sin dependencia nueva, reemplaza los 5 `confirm()` nativos de
  toda la app (no solo el de prompts).
- Componente común reusado por ambas rutas existentes (`/` y
  `/template-merge`) — no se fusionan en una vista con tabs, cambio acotado
  que no toca sidebar/routing/manuales de navegación.
- Slide Type y Visual Rules del compositor guiado se ocultan en modo
  `template-merge` (ese pipeline no elige layout ni assets, el template ya
  los fija) en vez de mostrarse siempre.

### `ConfirmDialogService` + `ConfirmModalComponent`

`frontend/src/app/services/confirm-dialog.service.ts` — `confirm(message):
Observable<boolean>`, backed por un `BehaviorSubject` de estado
`{visible, message}`. `frontend/src/app/components/shared/confirm-modal/` —
componente montado una sola vez en `app.component.html` (fuera del
`*ngIf="showShell()"`, visible en cualquier ruta). Reemplazó los 5
`confirm()` nativos existentes: `sidebar.component.ts` (reset de DB),
`brand-hub.component.ts` (reset de brands, borrado de footer),
`asset-library.component.ts` (borrado de favorito), y el de
`applyPromptText` (ahora dentro del componente compartido de abajo). Los
callers pasan de `if (!confirm(...)) return;` síncrono a
`.confirm(...).subscribe(ok => { if (!ok) return; ... })`.

### `PromptSupportComponent`

`frontend/src/app/components/prompt-support/` — extraído íntegro de
`generator.component` (las 4 tarjetas + sus 5 modales + todo el estado que
antes vivía ahí). Contrato:
- `@Input() mode: 'synthesis' | 'template-merge'`
- `@Input() brandId`, `@Input() currentText`, `@Input() currentMetadata` —
  el padre sigue siendo el único dueño del textarea real.
- `@Input() showCards` — permite al padre ocultar la grilla de tarjetas (ej.
  durante generación/resultados en Synthesis Studio) sin desmontar el
  componente, para que una template reference variable (`#promptSupport`)
  siga siendo alcanzable desde fuera de cualquier `*ngIf` — el botón
  "☆ Save as favorite" la usa para abrir el modal de guardado sin duplicar
  ese modal en cada página.
- `@Output() applyText` — `{text, metadata}` a aplicar, ya resuelto el
  confirm-antes-de-sobreescribir.
- `@Output() loadError` — el padre decide cómo mostrarlo (cada pantalla ya
  tenía su propio campo de error, no se inventó uno nuevo).

**Reuse Previous Prompt por modo**: en `synthesis` lee `GenerationJob` vía
`getLibraryPortfolios`/`getPortfolioDetail` (igual que antes). En
`template-merge` lee `TemplateMergeJob` vía `getTemplateMergeHistory`
(listado ya existente) y el nuevo campo `prompt` agregado a
`GET /api/template-merge/jobs/{id}` (antes esa respuesta no lo incluía).
Reusar el prompt de un `TemplateMergeJob` no trae `prompt_metadata` (ese
pipeline nunca lo persistió — no hay nada que leer).

**Favoritos guardados desde Template Merge**: siguen sin `source_job_id`
(decisión ya tomada arriba, sin cambios) — `prompt_metadata` sí se guarda
si el usuario usó el compositor, aunque `TemplateMergeRequest` no lo consuma;
es solo para que un favorito guardado ahí conserve la selección estructurada
si se reutiliza después.

**`PromptComposerComponent`**: ganó `@Input() mode` (mismo valor que el
padre) para condicionar Slide Type/Visual Rules — `assemble()` no necesitó
cambios, un campo oculto nunca tiene texto que incluir en el ensamblado.

### Verificación

Playwright real contra la stack local: favorito guardado en Synthesis Studio
aparece en Template Merge y viceversa (biblioteca realmente compartida);
modal de confirmación estilizado se dispara al sobreescribir (cero
`window.confirm()` nativo capturado); Slide Type/Visual Rules ausentes del
compositor en modo `template-merge`. 42 tests nuevos/actualizados de
Angular (`confirm-dialog.service`, `confirm-modal.component`,
`prompt-support.component`, ajustes en `generator`/`asset-library`/
`template-merge` specs).
