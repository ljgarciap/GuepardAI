# User Manual — Admin

You are an organization administrator. You manage your organization's
(tenant's) brands, presentations, assets, and team members. You cannot see
or affect any other organization's data. Spec:
`docs/specs/autenticacion-multiusuario-multitenant.md`. API reference:
`docs/api/auth-and-users.md`.

## Signing in

Go to `/login` with your email and password. If your organization doesn't
have an account yet, use `/register`: this creates a new organization
(optionally named) and makes you its first `admin`. Registering again with a
different email creates a **separate** organization — it does not add a
teammate to an existing one (see "Adding teammates" below for that).

Your session stays active across reloads for up to 7 days (refresh token
lifetime). Use the logout icon in the sidebar to end it explicitly.

## What you can do

### Synthesis Studio (`/` — main screen)

The main presentation-generation workflow:
1. Pick a brand in **IDENTITY** (or "Public / Generic" for no specific
   brand). **Do not select "★ SUPERUSER / ALL ACCESS"** — that option is
   reserved for the platform superadmin and will fail with an error for
   your account.
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
  of your brands. Choose **Exclusive** (tied to that brand) or **Public**
  scope (visible across all your organization's brands).
- **Phase 02 — Contextual Intelligence**: upload a strategic document used
  as the knowledge base for content generation.
- **Phase 03 — Strategic Library**: upload an image or image catalog, with
  optional comma-separated manual tags.
- **Phase 04 — Corporate Signature & Footers**: create/edit footer
  templates (signature text, disclaimer, light/dark logos) and pick which
  one is active.

Use "⊕ REGISTER NEW BRAND" to create a brand before uploading to it.

### Brand Directory (`/directory`)

CRUD for your organization's brand records: name, core value/slogan, an
"about" description, and a logo. Click **EDIT DOSSIER** to update one. There
is no delete action here.

### Strategic Assets (`/library`)

Four tabs — Images, Blueprints, Knowledge, Portfolios — scoped to your
organization's brands via the scope dropdown. Portfolios is where you
search, rename, rate, view feedback, download, or permanently delete past
presentations, with search-by-name and date-range filters plus pagination.

### Template Merge (`/template-merge`)

Keeps an existing PPTX's visual design and only replaces its text content
from a knowledge-base document — an alternative to the fully AI-designed
Synthesis Studio flow. Upload or reuse a `.pptx` template, pick a knowledge
source, write a content directive, and download the result. The "session
history" list at the bottom only covers the current browser session; use
Strategic Assets → Portfolios for a durable history.

## Adding teammates to your organization

There is no screen for this yet — it's done via API by whoever manages your
deployment (see `docs/api/auth-and-users.md`, `POST /api/users`). As an
`admin`, any account created this way automatically belongs to your
organization with the `cliente` role — you cannot create another `admin` or
assign someone to a different organization. You (and any other `admin` in
your organization) can also list (`GET /api/users`) and deactivate
(`PATCH /api/users/{id}/deactivate`) accounts in your own organization the
same way.

## Things you'll see but shouldn't use

- **"★ SUPERUSER / ALL ACCESS"** in Identity dropdowns — superadmin-only,
  will error for you.
- **"Reset System"** (sidebar) / **"FACTORY RESET"** (Intelligence Hub) —
  wipes the entire platform database; superadmin-only. If you click it,
  you'll get an error — this is expected, not a bug you need to report.
