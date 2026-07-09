# Spec: Soporte para Indicaciones (Biblioteca de Recursos y Estructura de Prompt)

**Date**: 2026-07-08
**Requested by**: Luis
**Status**: Draft
**Project**: GuepardAI

## Problem

Hoy el punto de partida de una generación es un único `<textarea>` de texto libre
(`frontend/src/app/pages/generator/generator.component.ts`, campo `prompt`) enviado
tal cual a `POST /api/presentations/generate` (`PresentationRequest.prompt`,
`backend/main.py:149-158`). La calidad del resultado depende directamente de la
calidad de ese texto, y no hay ninguna ayuda en el producto para escribir un buen
prompt: no hay reutilización de prompts anteriores, no hay categorías de intención
que sugieran estructura, y no hay guía de cómo componerlo. Además, aunque
`GenerationJob.prompt` sí se guarda en BD (`backend/models.py:290`), el endpoint de
biblioteca (`GET /api/library/portfolios`) no lo expone hoy — no hay forma de
recuperarlo desde el frontend para reutilizarlo.

Esto es un problema de negocio, no solo de UX: cuanto peor el prompt, más ciclos de
QA rework y peor la percepción de calidad del producto, sin que el pipeline tenga
ninguna culpa.

## Solution summary

Añadir, en el panel de control (dashboard/generador), tres puntos de entrada para
construir el prompt en vez de partir de un textarea vacío:

1. **Reutilizar una indicación anterior**: el usuario abre la biblioteca de
   presentaciones (ya existe, `docs/specs/gestion-portfolios.md`) y selecciona una
   presentación pasada; su prompt original se copia al editor para ajustarlo.
2. **Biblioteca de intenciones**: una taxonomía fija de categorías (Presentación
   ejecutiva, Presentación de ventas, Discurso, Taller, Interactivo, Capacitación,
   Interno, Estrategia, Plan a 3 años, Inversor, Recaudación de fondos, Venta
   minorista, Reunión con clientes, Innovación, Lanzamiento de producto). Cada
   categoría trae metadata sugerida (tono esperado, duración esperada, estilo
   narrativo, densidad visual, diseños preferidos) que pre-rellena el editor
   estructurado; el usuario la ajusta libremente después.
3. **Guía para construir la indicación**: un compositor guiado, siempre visible
   desde el dashboard, que expone la fórmula explícita
   `Objetivo + Tono + Audiencia + Tipo de diapositiva + Historia + Reglas visuales
   + Formato de salida + Sin Buzzwords` como campos independientes, más contenido
   de ayuda/tutorial sobre cómo usar cada campo. Al completarlo, los campos se
   ensamblan en el texto final del prompt.

Los tres puntos de entrada convergen en el mismo editor de texto final — el que hoy
ya existe — por lo que el usuario siempre puede editar el resultado a mano antes de
generar. No se reemplaza el textarea libre; se le da estructura opcional alrededor.

## Users and roles

- **Cliente / Admin de tenant**: usa las tres ayudas al generar una presentación.
  Sin diferencias de permisos entre roles — es la misma pantalla que ya usan hoy.
- **Superadmin**: sin cambios de comportamiento particular en esta spec.
- La taxonomía de categorías (Ayuda 2) es global para toda la plataforma en esta
  iteración (ver Open questions — confirmar si debe ser configurable por tenant).

## Acceptance criteria

### Ayuda 1 — Reutilizar una indicación anterior
- [ ] `GET /api/library/portfolios` (o un nuevo endpoint de detalle
      `GET /api/library/portfolios/{id}`) expone el campo `prompt` del
      `GenerationJob`, respetando el scoping de tenant existente
      (`check_brand_tenant_access` / `tenant_brand_ids_filter`).
- [ ] Desde la biblioteca, el usuario puede elegir "Usar como base" sobre una
      presentación pasada; el generador se abre con el campo de prompt
      pre-rellenado con el texto original, editable.
- [ ] Si el job de origen no tiene `prompt` (null o vacío — jobs muy antiguos o
      con error temprano), la opción "Usar como base" no se muestra para ese item.

### Ayuda 2 — Biblioteca de intenciones
- [ ] El dashboard muestra las categorías de intención listadas en la sección
      Solution summary, seedeadas en `system_configs` o tabla dedicada (decisión
      de Architect — ver Open questions).
- [ ] Cada categoría, al seleccionarse, pre-rellena en el compositor guiado
      (Ayuda 3): tono, duración esperada, estilo narrativo, densidad visual y
      diseños preferidos como valores por defecto editables — no bloquea al
      usuario de cambiarlos.
- [ ] Seleccionar una categoría no genera la presentación por sí sola; solo
      pre-rellena el compositor. El usuario sigue controlando cuándo generar.

### Ayuda 3 — Guía / compositor estructurado
- [ ] El compositor expone como campos independientes: Objetivo, Tono (opciones
      sugeridas: Objetivo, atractivo, optimista, sentido de urgencia,
      financiero — con opción de texto libre), Audiencia (Equipo interno, Junta
      Directiva, Director Ejecutivo, Cliente — con opción de texto libre), Tipo
      de diapositiva, Historia (Centrada en el cliente, creativa — con opción de
      texto libre), Reglas visuales (usar solo recursos de la biblioteca de marca
      / permitir recursos externos), Formato de salida (Basado en datos,
      narrativo, creativo, orientado a la acción), y un toggle "Sin buzzwords".
- [ ] Al completar el compositor, los campos se ensamblan en un único texto que
      llena el `prompt` final enviado a `/api/presentations/generate` — el
      backend no cambia su contrato de request en esta spec (sigue recibiendo un
      `prompt: string`).
- [ ] Existe un enlace/panel de ayuda siempre visible desde el dashboard
      ("Cómo escribir una buena indicación") con ejemplos de cada campo de la
      fórmula. No requiere completarse para poder generar.
- [ ] El campo "Reglas visuales → usar recursos externos" no implica generación
      ni inserción de contenido con IP de terceros con marca registrada
      (confirmado con Luis — ver Out of scope).

## Edge cases and error scenarios

- Usuario abre el dashboard por primera vez, sin historial: Ayuda 1 no muestra
  presentaciones (estado vacío con mensaje), Ayuda 2 y 3 siguen disponibles.
- Usuario reutiliza un prompt de una presentación de otro `brand_id` dentro del
  mismo tenant: el prompt se copia igual (el prompt es texto, no depende del
  brand), pero el usuario debe seleccionar explícitamente el brand destino como
  ya hace hoy el generador.
- Usuario selecciona una categoría de intención y luego cambia de opinión y
  selecciona otra: los campos del compositor se sobrescriben con los nuevos
  valores por defecto; si el usuario ya había editado campos a mano, se le
  advierte antes de sobrescribir (no se pierde trabajo silenciosamente).
- Usuario deja el compositor a medias (algunos campos vacíos) y da generar: los
  campos vacíos simplemente no se incluyen en el texto ensamblado — no es
  obligatorio completar la fórmula entera para generar.
- El texto ensamblado desde el compositor supera algún límite razonable de
  longitud: mismo comportamiento que hoy tiene el textarea libre (sin límite
  duro conocido en el contrato actual) — no se introduce un límite nuevo en
  esta spec.

## Out of scope

- Reescritura/mejora automática del prompt vía LLM (un "auto-improve" asistido
  por IA) — posible fase 2, no en esta spec.
- Generación o inserción real de contenido con personajes/IP de terceros con
  marca registrada (ej. Harry Potter) — la regla visual "recursos externos" se
  limita a fuentes de imágenes genéricas (stock/web), no a temática con IP
  protegida. Confirmado con Luis.
- Editor visual tipo builder/drag-and-drop para el compositor — la Ayuda 3 es un
  formulario estructurado simple, no un editor visual avanzado.
- Panel de administración para que cada tenant configure su propia taxonomía de
  categorías (Ayuda 2) — la taxonomía es fija/global en esta iteración salvo que
  Luis confirme lo contrario (ver Open questions).
- Cambios al contrato de `POST /api/presentations/generate` — el ensamblado a
  texto libre ocurre en frontend; el backend sigue recibiendo un `prompt` plano
  en esta iteración.

## Open questions

- [Luis] ¿La taxonomía de categorías de intención (Ayuda 2) debe ser configurable
  por tenant/admin en el futuro cercano, o fija/global está bien para esta
  iteración? Afecta si el Architect diseña una tabla seedeada simple o un CRUD
  de administración.
- [Architect] ¿Dónde persisten las selecciones estructuradas del compositor
  (Ayuda 3) además del texto ensamblado? Propuesta del Analista: añadir un campo
  `prompt_metadata` (JSONB, nullable) a `GenerationJob` para guardar la
  selección estructurada (categoría usada, tono, audiencia, etc.) sin rediseñar
  el modelo — útil para analítica futura y para que "reutilizar" pueda ofrecer
  también los campos estructurados, no solo el texto plano. Confirmar si esto
  se coordina con el cambio de modelo de datos de la spec
  `reviews-analitica-colaboracion.md` (ambas tocan `GenerationJob`) para no
  duplicar migraciones.
- [Architect] La "duración esperada" de cada categoría de intención — ¿debe
  traducirse a un parámetro real que el pipeline ya use (p. ej. número de
  slides), o es solo texto informativo mostrado al usuario en esta iteración?

## References

- Related existing code:
  - `frontend/src/app/pages/generator/generator.component.ts` (editor de prompt actual)
  - `backend/main.py:149-158` (`PresentationRequest`), `backend/main.py:598-696` (biblioteca de portfolios)
  - `backend/models.py:282-306` (`GenerationJob`, campo `prompt`)
- Related specs: `docs/specs/gestion-portfolios.md`, `docs/specs/reviews-analitica-colaboracion.md`
- Prototype or mockup: ninguno aún — a definir con Frontend Dev / UX en diseño
