# User Manual — Superadmin

You are the platform owner. You are not tied to any organization (tenant) —
you see and can act on every tenant's brands, presentations, and assets.
Spec: `docs/specs/autenticacion-multiusuario-multitenant.md`. API reference:
`docs/api/auth-and-users.md`.

## Signing in

Go to `/login` and sign in with your email and password. If you don't have
an account yet, a superadmin account is seeded automatically at deploy time
(see `docs/manuals/technical/auth-deployment.md`) — ask whoever runs the
deployment for your credentials rather than registering; the public
`/register` page always creates a new organization with an `admin` account,
never a superadmin.

Your session: after signing in you stay logged in across page reloads for as
long as your refresh token is valid (7 days by default). Use the logout icon
in the bottom-left of the sidebar to end your session explicitly.

## What you can do

Every screen below works the same for you as for `admin`/`cliente` users,
except that the **Identity** dropdown across the app includes a
"★ SUPERUSER / ALL ACCESS" option that lets you act across every
organization's brands at once, not just one tenant's.

### Synthesis Studio (`/` — main screen)

The main presentation-generation workflow:
1. Pick a brand in **IDENTITY** (or "Public / Generic" for no brand, or
   "★ SUPERUSER / ALL ACCESS" to see everything).
2. Pick a **BLUEPRINT** (visual style) and a **KNOWLEDGE** source — both
   scoped to the brand you picked.
3. Pick **TARGET REGION** (language/dialect), **DELIVERY FORMAT** (editable
   PPTX or Executive Art PDF), and **ENGINE TIER** (Free grammar layouts or
   Premium layout clone).
4. Write your request in the command box at the bottom, or use one of the
   four prompt-support cards above it to build a stronger one:
   - **Reuse Previous Prompt** — pick an earlier presentation and reload the
     prompt it was generated from (only presentations that have a saved
     prompt show up here).
   - **Intent Library** — pick what you're building (Executive Presentation,
     Sales Deck, Workshop, Training, Strategy, Investor, Retail, Innovation)
     and it opens the guided composer below, pre-filled with that category's
     tone/story defaults.
   - **Guide / Write My Own** — opens the guided composer directly: fill in
     Objective, Tone, Audience, Slide type, Story, Visual rules, Output
     format, and an "avoid buzzwords" toggle, then **INSERT INTO PROMPT** to
     assemble it into the command box (with a confirmation if you already
     had text there, so nothing is silently overwritten). The same panel has
     a short written guide on what makes a good prompt.
   - **Load from Favorites** — pick from any favorite saved by any user on
     the platform (see Strategic Assets → Prompts below) and reload it.

   Optionally toggle "Use AI generated images" if you want AI-generated
   imagery when nothing suitable exists in the asset library.
5. **Saving a favorite**: once you have text in the command box, click
   **☆ Save as favorite** next to it and give it a short title.
6. Click **CREATE PRESENTATION**. A live log shows each pipeline stage
   (analysis, design, writing) with a progress bar until it finishes.
7. When done, **DOWNLOAD STRATEGIC PORTFOLIO** downloads the file. The first
   download opens a quick 1–5 star rating with an optional comment — this
   feedback is saved against the job and visible later in Strategic Assets →
   Portfolios. This is separate from the collaborative reviews described
   below.

### Intelligence Hub (`/brands`) — feeding the system

Four independent upload phases, each with its own log and progress bar:
- **Phase 01 — Brand Blueprint**: upload a PDF/PPTX identity manual for a
  brand. Choose **Exclusive** (tied to one brand) or **Public** scope.
- **Phase 02 — Contextual Intelligence**: upload a strategic document (used
  as the RAG knowledge base for content generation).
- **Phase 03 — Strategic Library**: upload an image or image catalog, with
  optional manual tags (comma-separated) to help future searches.
- **Phase 04 — Corporate Signature & Footers**: create/edit footer templates
  (signature text, disclaimer, light/dark logos) and choose which one is
  active platform-wide.

Use "⊕ REGISTER NEW BRAND" at the top to create a brand inline before
uploading to it.

### Brand Directory (`/directory`) — brand records

A simple CRUD directory: name, core value/slogan, an "about" description,
and a logo image. Click **EDIT DOSSIER** on any card to update it. There is
no delete action here — brands are archived, not deleted, from this screen.

### Strategic Assets (`/library`) — browsing everything ingested

Five tabs. Images/Blueprints/Knowledge/Portfolios are each filterable by
brand via the scope dropdown; Prompts is the exception (not brand-scoped):
- **Images** — every ingested/generated image; click one for its full
  detail (AI description, tags, source document, download link).
- **Blueprints** — ingested visual-identity documents.
- **Knowledge** — ingested RAG documents (marked Public or Brand Exclusive).
- **Portfolios** — every presentation ever generated: search by name,
  filter by date range, rename, download, rate (if not already rated), view
  feedback comments, or permanently delete.
- **Prompts** — every favorite saved by any user across every tenant, with
  who saved each one. You can only edit or delete favorites you saved
  yourself — even as superadmin, someone else's favorite is view-only.

### Strategic Assets → Portfolios — reviews and collaborators

Every portfolio item has a **REVIEWS & TEAM** button:
- **Collaborators** — anyone added can leave their own review, same as the
  owner. As superadmin you can add/remove collaborators on any presentation
  in any tenant; the target user must belong to the same tenant as the
  presentation's brand.
- **Your Review** — a 1–5 star rating plus an optional comment, editable for
  up to **6 months from the presentation's creation date**.
- **All Reviews** — every contributor's rating and comment, including any
  flagged by the word filter.

### Your badges

The sidebar shows your own progress toward the next tier (Starter 5 / Expert
10 / Genius 20), based on presentations you personally generated — same
mechanic as every other role.

### Admin Panel (`/admin`)

Four tabs. Unlike an `admin`, every action here can target **any** tenant,
not just your own:

- **Departments** — create/list/delete departments for any tenant (pass a
  `Tenant ID` — there's no tenant picker UI yet, see "Known limitations"),
  and assign a department to any user.
- **Moderation** — the review queue across **all** tenants, filterable by
  status. This is also the only role that sees the **Moderation Blocklist**
  editor: a comma-separated list of terms (case-insensitive substring match)
  that auto-flags a review's comment on submission. It's platform-wide, not
  per-tenant — changing it affects every organization's moderation.
- **Analytics** — the usage table across all tenants, or filtered to one via
  the `Tenant ID` field.
- **Reports** — every monthly `UsageReport` generated, including the
  **global** one (`tenant_id: null`, platform-wide totals) that only you can
  see. Filter by `Tenant ID` to narrow it down. See
  `docs/manuals/technical/email-and-celery-beat-deployment.md` for what
  needs to be configured for these to actually be emailed, not just
  generated.

### Template Merge (`/template-merge`) — preserve a template's design

An alternative to Synthesis Studio: instead of an AI-designed layout, you
keep an existing PPTX's visual structure and only replace its text, driven
by a knowledge-base document. Pick a **brand** first (required — jobs
without one won't save to history), then upload a `.pptx` template (or reuse
one already uploaded), pick a knowledge source, write a content directive,
and download the merged file.

Same 4 prompt-support cards as Synthesis Studio — **Reuse Previous Prompt**
pulls from past Template Merge jobs here instead of Synthesis Studio ones,
the composer skips Slide Type and Visual Rules (no layout/asset choice in
this pipeline), and **Favorites** are shared across both screens for every
user on the platform.

The "THIS SESSION" list only covers jobs launched in the
current browser session and resets on reload; switch to the **HISTORY** tab
for a durable, searchable list of every completed merge across sessions
(search by name, filter by date, rename, delete) — separate from Strategic
Assets → Portfolios, which only lists Synthesis Studio output.

## Superadmin-only actions

- **System Reset** (⚡ "Reset System" in the sidebar, or "FACTORY RESET" in
  Intelligence Hub): wipes the **entire** database and all uploaded files,
  then reseeds default configuration. This is irreversible and affects every
  tenant, not just one. Only visible to you (`superadmin`) — `admin`/`cliente`
  accounts don't see this control at all.
- **User management** (create accounts, list users, deactivate users): there
  is no screen for this yet. It's done via API — see
  `docs/api/auth-and-users.md` (`POST /api/users`, `GET /api/users`,
  `PATCH /api/users/{id}/deactivate`). As `superadmin` you can create a user
  in **any** tenant by passing `tenant_id` explicitly; omitting it targets
  your own account's tenant (which doesn't exist for a superadmin, so always
  pass `tenant_id` when creating a user as superadmin).

## Known limitations (as of 2026-07-09)

- No screen exists yet to browse tenants or switch between them explicitly
  — the "★ SUPERUSER / ALL ACCESS" option in Identity dropdowns is the only
  cross-tenant view. In the Admin Panel (Departments/Analytics/Reports),
  targeting a specific tenant means typing its numeric `Tenant ID` — there's
  no tenant name picker yet.
- User management (creating `admin`/`cliente` accounts) requires calling the
  API directly; there is no admin screen for it.
