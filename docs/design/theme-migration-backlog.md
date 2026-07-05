# Backlog: Migración a tokens de tema (light/dark)

**Contexto**: la infraestructura de theming (tokens, `ThemeService`, toggle, logos correctos) ya está implementada y verificada en el shell (sidebar + fondo general de la app). Esta lista es lo que falta para que el modo oscuro cubra el 100% de las vistas.

**Cómo leer la tabla**: "Colores hardcodeados" = literales `#hex` fuera del sistema de tokens — cada uno es un color que **no responde** al toggle hoy. "Ya usa tokens" = referencias `var(--...)` que sí heredan el cambio de tema automáticamente.

## Prioridad 1 — Vistas de página (rutas)

| # | Ruta | Componente | Colores hardcodeados | Ya usa tokens | Cobertura |
|---|---|---|---|---|---|
| 1 | ✅ `/template-merge` | `template-merge.component.css` | ~~82~~ ~30**** | — | **migrado 2026-07-04** |
| 2 | ✅ `/` (home) | `generator.component.css` | ~~35~~ 8* | — | **migrado 2026-07-04** |
| 3 | ✅ `/brands` (Intelligence Hub) | `brand-hub.component.css` | ~~45~~ ~15** | — | **migrado 2026-07-04** |
| 4 | ✅ `/library` (Strategic Assets) | `asset-library.component.css` | ~~51~~ 1*** | — | **migrado 2026-07-04** |
| 5 | ✅ `/directory` (Brand Directory) | `brand-manager.component.css` | ~~31~~ 0 | — | **migrado 2026-07-04** |

\* `generator.component.css`: el bloque `.synthesis-console`/`.console-*`/`.log-*`/`.progress-*`/`.status-*` (consola de generación en vivo) se dejó intencionalmente sin migrar — es un widget de terminal permanentemente oscuro, igual que el bloque equivalente en `styles.css` global (fila 6). Se agregó además un fix de `:host-context([data-theme="dark"])` para el ícono de flecha de los `<select>` (SVG con stroke oscuro embebido, invisible en fondo oscuro sin este override).

\*\* `brand-hub.component.css`: colores dentro de `.synthesis-console` (mismos widgets de consola) se dejaron igual. De paso se corrigió un bug preexistente: `.reset-label`/`.reset-desc` estaban duplicados en el archivo (dos bloques con el mismo selector) y el segundo, pensado para un contexto oscuro que ya no existe, pisaba silenciosamente al primero — el texto de descripción real era casi invisible (blanco translúcido sobre fondo claro). Se eliminó el duplicado y se tokenizó el que queda.

\*\*\* `asset-library.component.css` conserva 1 literal intencional (`.btn-mini` — chip oscuro fijo, ver nota abajo).

\*\*\*\* `template-merge.component.css` originalmente conservaba su propio morado (`#7c3aed`/`#4f46e5`, mismo acento del badge "NEW" del sidebar) como identidad deliberada de "feature nueva". **Corrección 2026-07-04 (mismo día, tras revisión visual de Luis en `:4200`):** el morado se veía inconsistente contra el resto de la app ya con naranja — Luis pidió unificar. Se migró también el morado a `var(--brand-accent)` (naranja), en `template-merge.component.css`, el badge "NEW" y `.nav-item-template-merge` del sidebar, y un inline-style suelto en el HTML (`isUploading` span). Verde/rojo semánticos (success/error de jobs) se mantienen sin tocar.

**Las 5 vistas de página están migradas (2026-07-04).** Todos verificados: build limpio, 33/33 Karma en verde, capturas visuales en modo claro y oscuro sin texto ilegible. Nota de QA pendiente: en Chromium headless los `<select>` con `<option disabled>` como placeholder (Blueprint/Knowledge en Synthesis Studio) mostraron un posible parche blanco nativo pese a que `getComputedStyle` confirma el fondo oscuro correcto — probable limitación de renderizado nativo de `<option>`, no un bug de CSS. Confirmar en navegador real.

## Prioridad 2 — Shell y globales

| # | Archivo | Colores hardcodeados | Ya usa tokens | Nota |
|---|---|---|---|---|
| 6 | ✅ `src/styles.css` (global) | 26 | — | **Decisión final (2026-07-04): se deja intencionalmente sin migrar.** `.synthesis-console`/`.console-*` es un widget de terminal/log de generación en vivo (`#0f172a`, `#1e293b`, `#334155`, `#94a3b8`, `#cbd5e1`), reutilizado igual en `generator.component.css` y `brand-hub.component.css`. Es un diseño deliberado — terminal siempre oscura, con texto monoespaciado ya calibrado para ese fondo — no un bug de tema. No requiere más trabajo. |
| 7 | ✅ `sidebar.component.css` | 0 | — | Migrado 2026-07-04, incluyendo la corrección posterior del badge/nav "Template Merge" (morado → naranja, ver nota **** arriba). |
| 8 | `app.component.css` | 0 | 4 | Ya completo |

## Orden de trabajo sugerido

1. ✅ ~~`asset-library` y `brand-manager` primero~~ — hecho 2026-07-04.
2. ✅ ~~`brand-hub` y `generator`~~ — hecho 2026-07-04.
3. ✅ ~~`template-merge`~~ — hecho 2026-07-04. **Las 5 vistas de página están migradas.**
4. ✅ **`styles.css` global** — decisión tomada 2026-07-04: se deja como está (ver fila 6). Backlog cerrado — no queda ningún ítem pendiente.

## Qué significa "migrar" un componente

Reemplazar cada literal `#hex` por el token semántico equivalente:
- Fondos → `var(--bg-surface)` o `var(--bg-app)`
- Texto principal → `var(--text-body)` / `var(--text-title)`
- Texto secundario → `var(--text-muted-2)`
- Bordes → `var(--border-color)`
- Acentos/CTA/estados activos → `var(--brand-accent)` / `var(--brand-accent-soft)`

Colores que **no** se migran (son intencionales, no bugs de tema): rojo de "Reset System" (`#ef4444`, acción destructiva), verde/ámbar de estados semánticos (success/rating). El morado del badge "Template Merge" **ya no aplica aquí** — se decidió unificar a naranja (ver nota **** arriba); todo acento interactivo de la app usa `var(--brand-accent)`.

## Acceptance criteria por componente (QA)

- [ ] Cero literales `#hex` de color en el archivo (excepto los intencionales listados arriba).
- [ ] Toggle de modo oscuro probado manualmente: texto legible, contraste suficiente, ningún fondo "congelado" en blanco/negro fijo.
- [ ] Sin regresión visual en modo claro (el objetivo es agregar dark mode, no romper light mode).
