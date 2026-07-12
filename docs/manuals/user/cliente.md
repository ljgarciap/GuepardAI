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
   - **Load from Favorites** — pick from prompts you saved earlier (see
     "Saving a favorite" below) and reload it into the command box.

   Optionally toggle "Use AI generated images" for AI-generated imagery when
   nothing suitable exists in your asset library.
5. **Saving a favorite**: once you have text in the command box, click
   **☆ Save as favorite** next to it, give it a short title, and it's saved
   for reuse from the "Load from Favorites" card above — yours only, unless
   your organization's admin also needs to see it (see below).
6. Click **CREATE PRESENTATION** and watch the live log until it finishes.
7. **DOWNLOAD STRATEGIC PORTFOLIO** downloads the file. The first download
   prompts a quick 1–5 star rating with an optional comment — a separate,
   simpler mechanism from the collaborative reviews described below.

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

Five tabs — Images, Blueprints, Knowledge, Portfolios, Prompts. Portfolios is
where you search, rename, rate, view feedback, download, or permanently
delete past presentations, with search-by-name and date-range filters.

**Prompts** lists your saved favorites (title, prompt text, who saved it) —
edit the title/text inline with the pencil icon, or delete with the trash
icon (asks for confirmation first). If your admin also sees favorites your
teammates saved, they can view them here but cannot edit or delete anything
that isn't theirs.

Each item also has a **REVIEWS & TEAM** button that opens a presentation's
collaborative detail:
- **Collaborators** — anyone added here can leave their own review on that
  presentation, same as the owner. Only the presentation's owner or an admin
  of your organization can add or remove collaborators; anyone in your
  organization can see who they are.
- **Your Review** — a 1–5 star rating plus an optional comment, independent
  per teammate (the average shown is across everyone who reviewed it, not
  just yours). Editable for up to **6 months from the presentation's
  creation date** — after that the window closes and you can no longer
  change or delete your review, only view it. You can delete your own
  review within that window.
- **All Reviews** — every teammate's rating and comment. A comment flagged
  by the platform's word filter still shows up here (only an admin can hide
  it); it's not silently removed.

### Your badges

The sidebar shows your progress toward the next tier, based on how many
presentations you've generated: **Starter** (5), **Expert** (10), **Genius**
(20). It updates automatically — there's nothing to configure.

### Template Merge (`/template-merge`)

Keeps an existing PPTX's visual design and only replaces its text content
from a knowledge-base document. Pick a **brand** first (required — jobs
without one won't save to your history), then upload or reuse a `.pptx`
template, pick a knowledge source, write a content directive, and download
the result. Switch to the **HISTORY** tab to find, search, or download any
merge you completed in a previous session — the "THIS SESSION" list only
covers the current one.

## What only an admin/superadmin can do

- Add, list, or deactivate teammates — ask your admin.
- The **Admin Panel** (`/admin` — departments, review moderation, usage
  analytics, monthly reports) isn't in your sidebar at all; it's reserved
  for `admin`/`superadmin`. If your organization uses departments, an admin
  assigns you to one from there — you can't set your own.
- A few actions (wiping the entire platform database, a cross-tenant "see
  everything" view) are reserved for the platform superadmin — those
  controls simply don't appear in your UI.
