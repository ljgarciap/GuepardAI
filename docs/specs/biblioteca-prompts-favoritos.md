# Spec: Biblioteca de Prompts Favoritos

**Date**: 2026-07-12
**Requested by**: Luis
**Status**: Approved
**Project**: GuepardAI

## Problem

El requerimiento original de `docs/specs/soporte-indicaciones.md` pedía cuatro
ayudas para construir el prompt de generación, la cuarta como un subset del
asset library (`/library`): guardar, recuperar, editar y eliminar **prompts
favoritos**. Solo se construyeron las otras tres (Reutilizar prompt anterior,
Biblioteca de intenciones, Compositor guiado) — verificado con
`grep -ri "favorite"` sobre todo el repo (excluyendo `node_modules`): cero
resultados. No hay modelo, no hay endpoint, no hay componente.

Esto no es lo mismo que "Reutilizar prompt anterior" (Ayuda 1 de
`soporte-indicaciones.md`): esa ayuda tira del histórico de portfolios ya
generados (`GET /api/library/portfolios?has_prompt=true`), de solo lectura y
atado a una presentación concreta. Un favorito es una selección deliberada del
usuario — guarda un prompt (con o sin haber generado nada todavía) para
reutilizarlo como punto de partida, con nombre propio, editable y borrable,
independiente de si el job de origen sigue existiendo.

## Solution summary

1. **Backend**: nuevo modelo `PromptFavorite` (`user_id`, `tenant_id`, `title`,
   `prompt_text`, `prompt_metadata` JSONB — mismo shape que la interfaz
   `PromptMetadata` ya usada por el compositor guiado, `source_job_id` FK
   opcional a `GenerationJob`) con 4 endpoints CRUD en
   `backend/routers/prompt_favorites.py`.
2. **Frontend**: nueva pestaña "Prompts" en `AssetLibraryComponent` (`/library`,
   junto a Images/Blueprints/Knowledge/Portfolios) que lista, crea, edita y
   borra favoritos.
3. Los modales existentes de Reuse/Intent Library en `GeneratorComponent`
   (`/`) **no se mueven** — son flujos complementarios, no el mismo feature.
   Se agrega ahí un cuarto punto de entrada: "Load from Favorites", que abre
   un selector de favoritos y aplica su `prompt_text`/`prompt_metadata` al
   compositor (mismo patrón que ya usan Reuse Previous Prompt e Intent
   Library).
4. Se actualiza `docs/specs/soporte-indicaciones.md` agregando esta como
   Ayuda 4 explícita, con su propio criterio de aceptación (referenciando esta
   spec en vez de duplicar contenido).

## Users and roles

Visibilidad jerárquica confirmada con Luis (2026-07-12), mismo criterio ya
usado en otros recursos tenant-scoped del proyecto (analytics, directorio de
usuarios):

- **Cliente**: `GET /api/prompts/favorites` devuelve **solo los propios**
  (`user_id == current_user.id`).
- **Admin de tenant**: `GET /api/prompts/favorites` devuelve los propios **más
  los de todo su tenant** (`tenant_id == current_user.tenant_id`) — visibilidad
  de equipo, no filtrada por `user_id`.
- **Superadmin**: `GET /api/prompts/favorites` devuelve **todos**, sin filtro
  de tenant.
- **Escritura (`PUT`/`DELETE`) es exclusivamente del dueño en todos los
  roles** — la visibilidad extendida de admin/superadmin es de solo lectura.
  Un admin puede *ver* que un favorito existe pero no editarlo ni borrarlo si
  no es suyo (403 igual que hoy). Mismo criterio que reviews: moderar/ver no
  es lo mismo que editar contenido ajeno.
- `tenant_id` se guarda en el modelo precisamente para resolver este filtro de
  visibilidad de admin (no solo por consistencia de esquema).

## Acceptance criteria

- [ ] `POST /api/prompts/favorites` — crea un favorito para el usuario
      autenticado (`title`, `prompt_text` obligatorios; `prompt_metadata`,
      `source_job_id` opcionales). 201 con el objeto creado. `user_id`/
      `tenant_id` se asignan del `current_user`, nunca del body.
- [ ] `GET /api/prompts/favorites` — lista con visibilidad por rol (ver Users
      and roles): cliente ve los propios, admin ve los de su tenant, superadmin
      ve todos. Más recientes primero. Cada item incluye el `email` o nombre
      del dueño cuando el listado no es 100% propio (para que admin/superadmin
      distingan de quién es cada favorito). No requiere paginación explícita
      en esta iteración salvo que QA encuentre un volumen real que lo
      justifique (ver Edge cases).
- [ ] `PUT /api/prompts/favorites/{id}` — edita `title`/`prompt_text`/
      `prompt_metadata`. Exclusivo del dueño (`user_id == current_user.id`),
      **sin excepción de rol** — un admin o superadmin que no sea el dueño
      recibe 403 igual que cualquier otro usuario. 404 si no existe o si el
      usuario no tiene ni siquiera visibilidad de lectura sobre él (no filtrar
      por tenant acá: un cliente pidiendo el favorito de otro tenant debe ver
      404, no 403, para no confirmar que el recurso existe).
- [ ] `DELETE /api/prompts/favorites/{id}` — elimina. Mismas reglas de
      403/404 que `PUT` (exclusivo del dueño, sin excepción de rol).
- [ ] Los 4 endpoints operan **solo** sobre `PromptFavorite`. Ningún endpoint
      de esta feature expone `DELETE`/`PUT` sobre `GenerationJob.prompt` ni
      `TemplateMergeJob.prompt` — ese histórico sigue siendo de solo lectura,
      inalterado por esta spec.
- [ ] Pestaña "Prompts" en `/library` (`AssetLibraryComponent`): lista los
      favoritos del usuario, botón "Save current prompt as favorite" (visible
      también desde `GeneratorComponent`, ver siguiente criterio), editar
      inline o en modal (mismo patrón `.feedback-modal-card` ya usado en el
      resto del proyecto), borrar con confirmación (`confirm()` nativo, mismo
      patrón que colaboradores/reviews).
- [ ] Desde `GeneratorComponent`, un botón junto al textarea de prompt (Step 3,
      "CONTENT DIRECTIVE" — visible siempre que hay texto en el prompt, sin
      importar si vino del compositor guiado o se escribió a mano) abre un
      modal mínimo (solo pide `title`) y llama `POST /api/prompts/favorites`
      con el `prompt` y `promptMetadata` actuales.
- [ ] Un cuarto punto de entrada "Load from Favorites" en `GeneratorComponent`
      (junto a las 3 tarjetas existentes) lista los favoritos del usuario y,
      al elegir uno, aplica `prompt_text` al textarea y `prompt_metadata` al
      compositor — mismo flujo de confirmación si el usuario ya había escrito
      algo a mano (`applyPromptText` ya devuelve `boolean` desde el fix del
      Senior Review anterior, reusar ese contrato).

## Edge cases and error scenarios

- Usuario intenta guardar un favorito con `prompt_text` vacío: 422, mismo
  criterio que otros campos de texto obligatorios del proyecto (Pydantic
  `min_length=1`).
- Usuario intenta editar/borrar un favorito de otro usuario: 403, sin
  excepción de rol — confirmado con Luis, admin/superadmin tienen visibilidad
  extendida (GET) pero no permiso de escritura sobre favoritos ajenos.
- `source_job_id` apunta a un `GenerationJob` que fue borrado después: el
  favorito no depende de esa fila (`prompt_text`/`prompt_metadata` ya están
  copiados, no son una referencia viva) — `source_job_id` queda como dato
  histórico informativo, nunca bloquea ni rompe el favorito. Si se borra el
  job, el `source_job_id` queda huérfano (FK nullable, no hay `ON DELETE
  CASCADE` sobre el favorito).
- Usuario acumula muchos favoritos: sin límite ni paginación dura en esta
  iteración — confirmado con Luis, no construir para un problema hipotético
  sin datos de uso real. Si el volumen se vuelve un problema real, se agrega
  en una iteración futura.
- Título duplicado entre dos favoritos del mismo usuario: permitido, no hay
  restricción de unicidad — un favorito no es una clave, es una etiqueta
  libre.

## Out of scope

- Compartir favoritos entre usuarios del mismo tenant (visibilidad cruzada) —
  ver Open questions, default a "no" hasta confirmación explícita.
- Carpetas/categorías/tags sobre favoritos — lista plana en esta iteración.
- Sincronizar automáticamente un favorito si el usuario edita el prompt de un
  job ya generado — un favorito es una copia, no una referencia viva (ver
  Edge cases).
- Auto-mejora del prompt vía LLM al guardar como favorito — mismo out-of-scope
  ya declarado en `soporte-indicaciones.md`, no se reabre acá.

## Open questions

Todas las preguntas de esta spec fueron resueltas con Luis el 2026-07-12
(visibilidad jerárquica por rol, sin límite de favoritos, botón junto al
textarea) — incorporadas arriba en Users and roles / Acceptance criteria /
Edge cases. Sin preguntas pendientes que bloqueen al Arquitecto.

## References

- Related existing code:
  - `docs/specs/soporte-indicaciones.md` (Ayudas 1-3 ya implementadas; esta
    spec es la Ayuda 4 declarada mas no construida en esa iteración)
  - `frontend/src/app/services/brand.service.ts:37-47` (`PromptMetadata`
    interface — mismo shape a reutilizar en `prompt_metadata` JSONB)
  - `frontend/src/app/pages/generator/generator.component.ts` (3 tarjetas de
    entrada existentes: Reuse Previous Prompt, Intent Library, Guide)
  - `frontend/src/app/pages/asset-library/asset-library.component.ts:26`
    (`activeTab` — agregar `'prompts'` como quinta pestaña)
  - `backend/routers/config.py` (`GET /api/config/prompt-intents`, patrón de
    router simple a replicar para `prompt_favorites.py`)
  - `backend/models.py:282-306` (`GenerationJob`, campo `prompt_metadata` ya
    existente — mismo criterio de columna JSONB nullable para
    `PromptFavorite.prompt_metadata`)
- Related specs: `docs/specs/soporte-indicaciones.md`,
  `docs/specs/reviews-analitica-colaboracion.md` (mismo criterio de
  ownership/scoping por `user_id`+`tenant_id` ya usado ahí)
- Prototype or mockup: ninguno — a definir con Frontend Dev en diseño, reusar
  visualmente los modales `.feedback-modal-card` ya existentes.
