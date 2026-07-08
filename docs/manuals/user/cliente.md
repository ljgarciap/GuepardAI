# User Manual — Cliente

You are a member of your organization (tenant), added by one of your
organization's admins. You can create presentations and manage your
organization's brand assets, the same as an admin — the only thing you
cannot do is manage team members. Spec:
`docs/specs/autenticacion-multiusuario-multitenant.md`.

## Signing in

Go to `/login` with the email and password your admin gave you. There is no
self-registration for this role — `/register` always creates a **new**
organization with an `admin` account; if you need access to an existing
organization, ask your admin to create your account (see below).

Your session stays active across reloads for up to 7 days (refresh token
lifetime). Use the logout icon in the sidebar to end it explicitly.

## What you can do

### Synthesis Studio (`/` — main screen)

The main presentation-generation workflow:
1. Pick a brand in **IDENTITY** (or "Public / Generic" for no specific
   brand).
2. Pick a **BLUEPRINT** (visual style) and a **KNOWLEDGE** source — both
   scoped to the brand you picked.
3. Pick **TARGET REGION** (language/dialect), **DELIVERY FORMAT** (editable
   PPTX or Executive Art PDF), and **ENGINE TIER** (Free grammar layouts or
   Premium layout clone).
4. Write your request in the command box at the bottom (or use a quick-fill
   preset: Strategic Outlook, Market Entry, Culture Playbook). Optionally
   toggle "Use AI generated images" for AI-generated imagery when nothing
   suitable exists in your asset library.
5. Click **CREATE PRESENTATION** and watch the live log until it finishes.
6. **DOWNLOAD STRATEGIC PORTFOLIO** downloads the file. The first download
   prompts a quick 1–5 star rating with an optional comment.

### Intelligence Hub (`/brands`) — feeding the system

Four independent upload phases, each with its own progress log:
- **Phase 01 — Brand Blueprint**: upload a PDF/PPTX identity manual for one
  of your organization's brands (Exclusive or Public scope).
- **Phase 02 — Contextual Intelligence**: upload a strategic document used
  as the knowledge base for content generation.
- **Phase 03 — Strategic Library**: upload an image or image catalog, with
  optional comma-separated manual tags.
- **Phase 04 — Corporate Signature & Footers**: create/edit footer
  templates and pick which one is active.

### Brand Directory (`/directory`)

CRUD for your organization's brand records: name, core value/slogan, an
"about" description, and a logo. Click **EDIT DOSSIER** to update one.

### Strategic Assets (`/library`)

Four tabs — Images, Blueprints, Knowledge, Portfolios. Portfolios is where
you search, rename, rate, view feedback, download, or permanently delete
past presentations, with search-by-name and date-range filters.

### Template Merge (`/template-merge`)

Keeps an existing PPTX's visual design and only replaces its text content
from a knowledge-base document. Upload or reuse a `.pptx` template, pick a
knowledge source, write a content directive, and download the result. Switch
to the **HISTORY** tab to find, search, or download any merge you completed
in a previous session — the "THIS SESSION" list only covers the current one.

## What only an admin/superadmin can do

- Add, list, or deactivate teammates — ask your admin.
- A few actions (wiping the entire platform database, a cross-tenant "see
  everything" view) are reserved for the platform superadmin — those
  controls simply don't appear in your UI.
