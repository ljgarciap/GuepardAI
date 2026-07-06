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
4. Write your request in the command box at the bottom (or use one of the
   quick-fill presets: Strategic Outlook, Market Entry, Culture Playbook).
   Optionally toggle "Use AI generated images" if you want AI-generated
   imagery when nothing suitable exists in the asset library.
5. Click **CREATE PRESENTATION**. A live log shows each pipeline stage
   (analysis, design, writing) with a progress bar until it finishes.
6. When done, **DOWNLOAD STRATEGIC PORTFOLIO** downloads the file. The first
   download opens a quick 1–5 star rating with an optional comment — this
   feedback is saved against the job and visible later in Strategic Assets →
   Portfolios.

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

Four tabs, each filterable by brand via the scope dropdown:
- **Images** — every ingested/generated image; click one for its full
  detail (AI description, tags, source document, download link).
- **Blueprints** — ingested visual-identity documents.
- **Knowledge** — ingested RAG documents (marked Public or Brand Exclusive).
- **Portfolios** — every presentation ever generated: search by name,
  filter by date range, rename, download, rate (if not already rated), view
  feedback comments, or permanently delete.

### Template Merge (`/template-merge`) — preserve a template's design

An alternative to Synthesis Studio: instead of an AI-designed layout, you
keep an existing PPTX's visual structure and only replace its text, driven
by a knowledge-base document. Upload a `.pptx` template (or reuse one already
uploaded), pick a knowledge source, write a content directive, and download
the merged file. Session history (bottom of the results panel) only lists
jobs from the current browser session — it's not persisted across reloads;
use Strategic Assets → Portfolios for a durable history of downloads.

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

## Known limitations (as of 2026-07-06)

- No screen exists yet to browse tenants or switch between them explicitly
  — the "★ SUPERUSER / ALL ACCESS" option in Identity dropdowns is the only
  cross-tenant view.
- User management (creating `admin`/`cliente` accounts) requires calling the
  API directly; there is no admin screen for it.
