# API — Biblioteca de Prompts Favoritos

Referencia de `/api/prompts/favorites` (CRUD) y su integración con
`DELETE /api/library/portfolios/{job_id}`.

Implementación: `backend/routers/prompt_favorites.py`, `backend/models.py`
(`PromptFavorite`), `backend/main.py` (`delete_library_portfolio`).

Spec: `docs/specs/biblioteca-prompts-favoritos.md`
Design: `docs/designs/biblioteca-prompts-favoritos.md`

Distinto de "Usar como base" (`docs/api/prompt-support.md`, `GET
/api/library/portfolios/{job_id}`): eso lee `GenerationJob.prompt` de solo
lectura, atado a una presentación ya generada. Un favorito es una copia
editable, con nombre propio, independiente de si el job de origen sigue
existiendo.

## Visibilidad de lectura — 3 niveles por rol

`GET /api/prompts/favorites` filtra según el rol del usuario autenticado:

| Rol | Ve |
|---|---|
| `cliente` | Solo sus propios favoritos |
| `admin` | Los propios + todos los de su tenant (visibilidad de equipo) |
| `superadmin` | Todos, de cualquier tenant |

**La escritura (`PUT`/`DELETE`) es exclusiva del dueño en los tres roles, sin
excepción.** La visibilidad extendida de `admin`/`superadmin` es solo de
lectura — ver un favorito ajeno en el listado no habilita a editarlo ni
borrarlo.

## Endpoints

### `POST /api/prompts/favorites`

Crea un favorito para el usuario autenticado. `user_id`/`tenant_id` se
asignan del token, nunca del body.

**Body**:
```json
{
  "title": "string (1-120 caracteres, obligatorio)",
  "prompt_text": "string (obligatorio, no vacío)",
  "prompt_metadata": { "...": "mismo shape que PromptMetadata del compositor, opcional" },
  "source_job_id": "int opcional — referencia informativa a un GenerationJob"
}
```

**Respuestas**:
- `201` → objeto creado (ver shape de respuesta abajo)
- `422` → `title` o `prompt_text` vacíos

### `GET /api/prompts/favorites`

Lista los favoritos visibles para el rol del usuario (ver tabla arriba), más
recientes primero.

**Respuesta** (`200`) — array de:
```json
{
  "id": 1,
  "title": "Q3 Board Update",
  "prompt_text": "...",
  "prompt_metadata": { "...": "..." },
  "source_job_id": 42,
  "owner_email": "user@example.com",
  "created_at": "2026-07-12T10:00:00",
  "updated_at": "2026-07-12T10:00:00"
}
```

`owner_email` siempre está presente (no solo cuando el listado incluye
favoritos de otros usuarios) — evita bifurcar el contrato de respuesta por
rol.

### `PUT /api/prompts/favorites/{id}`

Edita `title`/`prompt_text`/`prompt_metadata` (todos opcionales — solo se
actualizan los campos presentes en el body). Exclusivo del dueño.

**Respuestas**:
- `200` → objeto actualizado
- `403` → el usuario ve el favorito (visibilidad de lectura) pero no es el
  dueño
- `404` → no existe, o el usuario no tiene ni siquiera visibilidad de lectura
  sobre él (no se distingue de "no existe" para no revelar el recurso a
  quien no debería verlo)

### `DELETE /api/prompts/favorites/{id}`

Mismas reglas de autorización que `PUT`. `200` → `{ "deleted": true, "id": N }`.

## Integración con el borrado de portfolios

`DELETE /api/library/portfolios/{job_id}` (borra un `GenerationJob`) nulea
`PromptFavorite.source_job_id` para cualquier favorito que apuntara a ese job,
**antes** de borrar el job — sin esto, el `ForeignKey` revienta con
`IntegrityError` (500). El favorito nunca se borra ni se bloquea por esto;
`source_job_id` queda como dato histórico huérfano, informativo únicamente
(nunca fue una referencia viva al contenido del favorito, que ya está
copiado en `prompt_text`/`prompt_metadata`).

## Frontend — dónde vive esto

- `generator.component` (`/`): 4ta tarjeta "Load from Favorites" (junto a
  Reuse/Intent Library/Guide) — lista los favoritos visibles y aplica
  `prompt_text`/`prompt_metadata` con el mismo flujo de confirmación que las
  otras tres ayudas (`applyPromptText`). Botón "☆ Save as favorite" junto al
  textarea del prompt (`command-area`), abre un modal mínimo que solo pide
  `title` y llama `POST /api/prompts/favorites` con el prompt actual.
- `asset-library.component` (`/library`): pestaña "PROMPTS" — lista con
  columna Owner, edición inline (título + texto), borrado con `confirm()`
  nativo.
- Servicio: `services/prompt-favorites.service.ts` (separado de
  `brand.service.ts`, mismo criterio que `collaboration.service.ts`).
