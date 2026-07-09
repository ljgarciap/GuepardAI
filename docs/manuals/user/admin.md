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
   brand).
2. Pick a **BLUEPRINT** (visual style) and a **KNOWLEDGE** source — both
   scoped to the brand you picked.
3. Pick **TARGET REGION** (language/dialect), **DELIVERY FORMAT** (editable
   PPTX or Executive Art PDF), and **ENGINE TIER** (Free grammar layouts or
   Premium layout clone).
4. Write your request in the command box at the bottom, or use one of the
   three prompt-support cards above it to build a stronger one:
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

   Optionally toggle "Use AI generated images" for AI-generated imagery when
   nothing suitable exists in your asset library.
5. Click **CREATE PRESENTATION** and watch the live log until it finishes.
6. **DOWNLOAD STRATEGIC PORTFOLIO** downloads the file. The first download
   prompts a quick 1–5 star rating with an optional comment — a separate,
   simpler mechanism from the collaborative reviews described below.

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

Each item also has a **REVIEWS & TEAM** button that opens a presentation's
collaborative detail:
- **Collaborators** — anyone added here can leave their own review on that
  presentation, same as the owner. You (as admin) or the presentation's
  owner can add/remove collaborators for any presentation in your
  organization; anyone in your organization can see who they are.
- **Your Review** — a 1–5 star rating plus an optional comment, independent
  per teammate. Editable for up to **6 months from the presentation's
  creation date**.
- **All Reviews** — every teammate's rating and comment, including any
  flagged by the word filter (see Admin Panel → Moderation below to hide
  one).

### Your badges

The sidebar shows your progress toward the next tier, based on how many
presentations you've generated: **Starter** (5), **Expert** (10), **Genius**
(20).

### Admin Panel (`/admin`)

Four tabs, visible only to `admin`/`superadmin`:

- **Departments** — create/list/delete departments for your organization
  (delete is blocked with a `409` if anyone is still assigned — reassign or
  clear them first), and assign a department to any teammate. Purely a
  grouping label used by Analytics; it doesn't gate access to anything.
- **Moderation** — the queue of reviews across your organization, filterable
  by status (defaults to **Flagged**: comments the word filter caught).
  **HIDE** removes a review from everyone's normal view (only admins still
  see it); **RESTORE TO VISIBLE** undoes that. You do **not** see the
  blocklist editor here — the list of blocked terms is platform-wide and
  only the superadmin can change it.
- **Analytics** — a table per teammate: presentations created, edits made,
  time spent, and average rating received, scoped to your organization.
- **Reports** — the monthly usage reports already generated for your
  organization (presentations/edits/time/rating/contributors, plus the top
  user and top department by activity). These are also emailed to you
  automatically on the 1st of each month if SMTP is configured for this
  deployment (see `docs/manuals/technical/email-and-celery-beat-deployment.md`)
  — if a report shows "not emailed", it was still generated correctly, the
  email step alone didn't go out.

### Template Merge (`/template-merge`)

Keeps an existing PPTX's visual design and only replaces its text content
from a knowledge-base document — an alternative to the fully AI-designed
Synthesis Studio flow. Upload or reuse a `.pptx` template, pick a knowledge
source, write a content directive, and download the result. The "THIS
SESSION" list only covers jobs launched in the current browser session; switch
to the **HISTORY** tab for a durable, searchable list of every completed merge
(search by name, filter by date, rename, delete) — this is separate from
Strategic Assets → Portfolios, which only lists Synthesis Studio output.

## Adding teammates to your organization

There is no screen for this yet — it's done via API by whoever manages your
deployment (see `docs/api/auth-and-users.md`, `POST /api/users`). As an
`admin`, any account created this way automatically belongs to your
organization with the `cliente` role — you cannot create another `admin` or
assign someone to a different organization. You (and any other `admin` in
your organization) can also list (`GET /api/users`) and deactivate
(`PATCH /api/users/{id}/deactivate`) accounts in your own organization the
same way.

## What you won't see

A few actions (wiping the entire platform database, and a cross-tenant
"see everything" view) are reserved for the platform superadmin — those
controls simply don't appear in your UI, so there's nothing to avoid here.
