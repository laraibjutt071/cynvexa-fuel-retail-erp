# CYNVEXA — Frontend Audit

**Date:** 2026-11-15
**Purpose:** Complete inventory of the frontend before any premium redesign begins. Every finding below was confirmed by reading the actual source files, not assumed from names.

---

## 1. Technology Stack

| Component | Version | Notes |
|---|---|---|
| Next.js | 16.4.3 | App Router, standalone output, Turbopack for CSS |
| React | 19.3.0 | Client components only (no RSC data fetching) |
| TypeScript | ^5 | Strict mode, zero `tsc --noEmit` errors |
| Tailwind CSS | v4 | `@theme inline` block + `:root` custom properties |
| Recharts | ^3.10.1 | 7 chart components |
| Lucide React | ^1.64.0 | Icon library |
| Playwright | ^1.64.1 | 3 e2e spec files (10 tests) |
| Font | Geist Sans + Geist Mono | Google Fonts, loaded via `next/font` |

**No Tailwind config file** — Tailwind v4 reads its theme from `globals.css`'s `@theme inline` block and `next.config.ts`'s Turbopack `@tailwindcss/turbopack` loader.

---

## 2. Route Inventory

### Public Routes (no auth required)
| Route | File | Purpose |
|---|---|---|
| `/` | `app/page.tsx` | Root redirect |
| `/login` | `app/login/page.tsx` | Login form with atom decoration |
| `/register` | `app/register/page.tsx` | Self-service org registration |

### Authenticated Routes (no AppShell sidebar)
| Route | File | Purpose |
|---|---|---|
| `/dashboard` | `app/dashboard/page.tsx` | Org/station picker (auto-redirects single-station users) |
| `/dashboard/platform` | `app/dashboard/platform/page.tsx` | Platform admin panel (superuser only) |

### Authenticated Routes (inside AppShell sidebar)
| Route | File | Purpose |
|---|---|---|
| `/dashboard/org/[orgId]` | `app/dashboard/org/[orgId]/page.tsx` | Org dashboard: 5 tabs (overview, suppliers, credit, expenses, audit) |
| `/dashboard/org/[orgId]/settings` | `…/settings/page.tsx` | Org settings: account, billing, expense categories, users |
| `/dashboard/org/[orgId]/credit-customers` | `…/credit-customers/page.tsx` | Credit customer list, create, statement, ageing |
| `/dashboard/org/[orgId]/station/[stationId]` | `…/[stationId]/page.tsx` | Station dashboard: 4 tabs (sales, variance, reconciliation, inventory) |
| `/dashboard/org/[orgId]/station/[stationId]/today` | `…/today/page.tsx` | Today's Overview with live data cards + charts |
| `/dashboard/org/[orgId]/station/[stationId]/daily-entry` | `…/daily-entry/page.tsx` | Guided daily entry workflow (readings → sales → cash → summary) |
| `/dashboard/org/[orgId]/station/[stationId]/purchases` | `…/purchases/page.tsx` | Tanker receipt lifecycle |
| `/dashboard/org/[orgId]/station/[stationId]/tanks` | `…/tanks/page.tsx` | Tank management |
| `/dashboard/org/[orgId]/station/[stationId]/reading-corrections` | `…/reading-corrections/page.tsx` | 24h correction workflow |
| `/dashboard/org/[orgId]/station/[stationId]/attendance` | `…/attendance/page.tsx` | Attendance and payroll |
| `/dashboard/org/[orgId]/station/[stationId]/settings` | `…/settings/page.tsx` | Station config: profile, fuel grades, tanks, shift templates, tolerances |

**Total: 16 routes** (3 public + 2 auth-no-shell + 11 auth-with-shell)

---

## 3. Component Inventory

### Layout & Navigation
| Component | File | Purpose |
|---|---|---|
| `AppShell` | `components/AppShell.tsx` (302 lines) | Sidebar + mobile drawer, permission-gated nav, language toggle |
| Root Layout | `app/layout.tsx` | Wraps AuthProvider → LanguageProvider → ToastProvider |

### Design System (Reusable UI)
| Component | File | Props/API |
|---|---|---|
| `Button` | `components/ui/Button.tsx` | `variant: primary\|secondary\|danger\|ghost`, `size: sm\|md`, `busy` |
| `Card` | `components/Card.tsx` | `title`, `description`, `action` slot, `children` |
| `Field` | `components/ui/Field.tsx` | `label`, `hint`, `error`, `required`, render-prop `children(id)` |
| `TextInput` | `components/ui/Field.tsx` | Standard input with design tokens, `invalid` prop |
| `Select` | `components/ui/Field.tsx` | Standard select with design tokens |
| `Badge` | `components/ui/Badge.tsx` | Status badges |
| `EmptyState` | `components/ui/EmptyState.tsx` | Empty data placeholder |
| `Toast` | `components/ui/Toast.tsx` | ToastProvider + useToast hook |
| `ExportButton` | `components/ExportButton.tsx` | CSV export trigger |
| `DateRangeFilter` | `components/DateRangeFilter.tsx` | Date range picker with presets |
| `TankGauge` | `components/TankGauge.tsx` | Visual fuel level indicator |

### Decorative
| Component | File | Purpose |
|---|---|---|
| `AtomBackground` | `components/decor/AtomBackground.tsx` | Orbiting atom animation (login page) |
| `Particles` | `components/decor/Particles.tsx` | Floating particle effect (login page) |

### Charts (all use Recharts)
| Component | File | Data source |
|---|---|---|
| `FuelStockChart` | `components/charts/FuelStockChart.tsx` | Tank levels |
| `LitresByGradeChart` | `components/charts/LitresByGradeChart.tsx` | Daily fuel sales by grade |
| `ExpenseBreakdownChart` | `components/charts/ExpenseBreakdownChart.tsx` | Expense categories |
| `SalesOverTimeChart` | `components/charts/SalesOverTimeChart.tsx` | Daily sales trend |
| `VarianceTrendChart` | `components/charts/VarianceTrendChart.tsx` | Tank variance over time |
| `ReconciliationHistoryChart` | `components/charts/ReconciliationHistoryChart.tsx` | Reconciliation trend |
| `PaymentMethodBreakdownChart` | `components/charts/PaymentMethodBreakdownChart.tsx` | Payment method pie |
| Chart theme | `components/charts/theme.ts` | Shared chart color/style config |

---

## 4. Design System Analysis

### Color Tokens (defined in `globals.css`)
**Theme: Dark-only enterprise (black/blue)**

| Category | Tokens | Current Values |
|---|---|---|
| Canvas | `--background` | `#080d18` (darkest) |
| Surfaces | `--color-surface`, `-elevated`, `-muted`, `--color-sidebar` | `#111c30`, `#17243a`, `#0a1120`, `#0c1424` |
| Text | `--color-ink`, `-soft`, `-faint` | `#f8fafc`, `#94a3b8`, `#64748b` |
| Borders | `--color-border` | `#22304a` |
| Brand | `--color-brand-50` through `-700` | Blue scale centered on `#2563eb` |
| Accent | `--color-accent` | `#38bdf8` (electric blue) |
| Semantic | success/warning/caution/danger | Green/Amber/Orange/Red with 50/100/600 tiers |

**Key finding:** No light mode exists. The `color-scheme: dark` is set globally. There is no `prefers-color-scheme` media query for light mode. Every token is dark-only.

### Typography
- Geist Sans (body) + Geist Mono (code)
- No heading scale defined — each page uses ad-hoc `text-lg`, `text-xl`, `text-2xl`
- No consistent font-size scale beyond Tailwind defaults

### Spacing & Layout
- Sidebar: fixed `w-64` (256px)
- Max content width: `max-w-5xl` (1024px) on most pages
- Consistent `px-6 py-8` padding on content areas
- 16px mobile gutter (via Tailwind defaults)

### Animations
- `animate-fade-slide-up`: 180ms ease-out (page entry)
- `animate-slide-in-left`: 200ms ease-out (mobile drawer)
- `card-glow`: Box shadow with blue tint + hover lift
- Atom orbit animations (login only)
- Particle float animation (login only)
- `prefers-reduced-motion` respected globally

### Missing from Current Design System
1. **No Dialog/Modal component** — pages use `window.prompt()` for destructive actions (e.g., expense rejection)
2. **No Table component** — every page builds tables from scratch with inconsistent patterns
3. **No Skeleton/Loading component** — pages show `<p>Loading…</p>` text
4. **No Pagination component** — all lists load everything at once
5. **No Dropdown/Menu component**
6. **No Tabs component** — tabs are rebuilt per-page with minor variations
7. **No Breadcrumb component** — navigation context is ad-hoc
8. **No light mode** — dark-only
9. **No responsive breakpoint system** beyond Tailwind's `sm/md/lg` defaults
10. **No consistent heading hierarchy**

---

## 5. Authentication & Authorization (Frontend)

### Auth Flow
- `AuthProvider` in `lib/auth-context.tsx` manages all auth state
- Access token stored in `useRef` (memory only, never localStorage)
- Refresh token in HttpOnly cookie (sent via `credentials: "include"`)
- `authFetch()` auto-refreshes on 401 and retries once
- Login → `/auth/login` POST → access token + refresh cookie
- Register → `/auth/register` POST → creates org + station + user + subscription

### Permission Checking
- `useAuth()` exposes `user.station_roles[]` with per-role `permissions[]`
- `AppShell` computes a `permissions` Set from roles matching current orgId/stationId
- `can(codes: string[])` helper: superuser bypasses, otherwise checks Set
- Nav items filtered by `anyPermission` array
- Page-level permission checks are frontend-only visibility gates; backend is authoritative

### Current Role Display
| Role | Key Frontend Capabilities |
|---|---|
| Owner | All nav items, all tabs, create org, manage users |
| Station Manager | Most nav items, station config |
| Shift Supervisor | Readings, shift operations, some inventory |
| Cashier/Operator | Shift operations, sales recording |
| Accountant | Reports, reconciliation approval, expenses |
| Storekeeper/Technician | Not explicitly differentiated in frontend nav |
| Auditor/Viewer | Read-only access |
| Platform Admin (superuser) | Platform admin panel, create org |

---

## 6. API Integration Pattern

- Base URL: `NEXT_PUBLIC_API_BASE_URL` (build-time, baked into JS bundle)
- All requests go through `lib/api.ts::apiFetch()` or `authFetch()`
- JSON body with `Content-Type: application/json` default
- Error handling: `ApiError` class with status + parsed detail message
- No request caching, no SWR/React Query — all `useEffect` + `useState` manual fetching
- No optimistic updates
- No request deduplication

---

## 7. i18n / Localization

- Client-side only via `lib/i18n/context.tsx`
- Two languages: English (`en`) and Roman Urdu (`ur`)
- Stored in `localStorage` per-device, no backend persistence
- Translation keys in `lib/i18n/translations.ts`
- Coverage: sidebar nav, login page, Today's Overview, Daily Entry workflow
- NOT translated: org dashboard tabs, station dashboard, settings pages, error messages

---

## 8. E2E Test Coverage

| Spec File | Tests | Coverage |
|---|---|---|
| `e2e/dashboard.spec.ts` | 5 | Login, expense approval, pending approvals, daily sales, tank variance, inventory receipt |
| `e2e/daily-entry.spec.ts` | 1 | Full business day lifecycle (open → readings → sales → cash → close → approve) |
| `e2e/day2-pages.spec.ts` | 4 | Tank management, reading corrections, credit customers (smoke tests) |
| **Total** | **10** | Core happy paths only |

**Not covered:** Register flow, station config, attendance, purchases, multiple roles, error states, mobile viewport.

---

## 9. Performance & Build Observations

- `output: "standalone"` in `next.config.ts` — optimized for Docker
- Turbopack for development CSS processing
- No image optimization configured (no `next/image` usage observed)
- No code splitting beyond Next.js automatic route splitting
- No lazy loading of heavy components (charts load eagerly)
- Bundle includes Recharts (~300KB) on every dashboard page
- No service worker or offline support

---

## 10. Identified Technical Debt

1. **Manual data fetching everywhere** — every page repeats `useEffect + useState + authFetch` pattern; no shared data layer
2. **No consistent table component** — 8+ pages build tables from scratch with minor variations
3. **`window.prompt()` for user input** — expense rejection, audit filter use browser prompts instead of proper UI
4. **Hardcoded strings** — many pages have untranslated English strings outside the i18n system
5. **No error boundaries** — a component error crashes the entire page
6. **No loading skeletons** — pages flash "Loading..." text
7. **Status badges repeated** — `StatusBadge` is defined inside `[orgId]/page.tsx` and can't be reused
8. **Chart data transformation in components** — each chart component fetches and transforms its own data
9. **No form validation library** — all validation is manual
10. **Mobile experience untested** — sidebar drawer exists but page content isn't optimized for small screens

---

## 11. What Must Be Preserved

Per the project constraints:
- All existing API integration and endpoint paths
- Authentication flow (access token in memory, refresh via HttpOnly cookie)
- Permission checking logic (`can()` pattern matching backend)
- i18n infrastructure and existing translations
- E2e test compatibility (selectors, flows)
- Standalone Next.js output for Docker deployment
- All 46 working features from the Day 5 pilot checklist
- 24-hour reading correction policy enforcement
- Append-only stock ledger display
- Business date resolution using station timezone

---

## 12. Recommendations for Premium Redesign

### Phase 1 Priority (Design System)
- Build a proper component library: Dialog, Table, Tabs, Skeleton, Breadcrumb, Dropdown
- Extract StatusBadge, create consistent heading/typography scale
- Add light mode support or confirm dark-only is the product direction
- Create shared data-fetching hooks (replace manual useEffect patterns)

### Phase 2 Priority (Login & Navigation)
- Login page already has premium atom decoration — enhance, don't replace
- Role-specific dashboard redirects already work — refine the experience per role
- Mobile nav drawer exists — make it feel native

### Phase 3+ Priority
- Replace `window.prompt()` with proper Dialog components
- Add loading skeletons for perceived performance
- Lazy-load Recharts only on pages that use charts
- Add error boundaries around route segments
- Extend i18n coverage to all pages
