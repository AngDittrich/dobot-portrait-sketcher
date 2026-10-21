# Estándar de Diseño (Design Context) — Portal de Licenciamiento SYSCOM

> **Fuente de verdad**: este documento se deriva del código real del frontend (`frontend/src/styles/global.css`, `frontend/src/styles/presentation.css`, `frontend/index.html` y componentes en `frontend/src/`) **y, desde la §17, también de la Cabina de Retratos (`windows/src/`)**. Si el CSS cambia, este documento debe actualizarse.
>
> **Alcance**: identidad visual y de marca **SYSCOM** — colores, tipografía, formas, bordes, sombras, espaciado, iconografía, motion y patrones de componentes de todo el portal (público, wizard, tutoriales, FAQ, presentación y panel admin) y de la Cabina de Retratos (§17). **Excluye** el branding de UNITREE (logos/fotos de robots: vivimos en un proyecto distribuidor; la marca visual del portal es SYSCOM).

---

## 1. Stack y arquitectura visual

| Aspecto | Valor |
|---|---|
| Framework | React 18 + Vite (SPA, `react-router-dom` v6) |
| Estilos | **CSS plano con variables custom** (2 archivos): `src/styles/global.css` (todo el portal) y `src/styles/presentation.css` (solo `/presentation`) |
| Preprocesador / Tailwind | **Ninguno.** Todo es BEM-ish por clases globales (`.card`, `.btn`, `.form-input`, `.tut-*`, `.wizard-*`, `.admin-*`, `.faq-*`) |
| Fuente | **Inter** (Google Fonts, pesos 400/500/600/700 cargados; el código ocasionalmente usa 750/800) |
| Monospace | `Consolas`, `"Courier New"` (para códigos, licencias y `kbd`) |
| Idioma de la UI | Español (`lang="es"`) |
| Iconografía | **lucide-react** (SVG inline; heredan `currentColor`) |
| Tema base | Claro, fondo global `--slate-50`, texto `--slate-800` |

**Regla de oro:** nunca hardcodear colores nuevos en componentes; usar las variables CSS definidas en `:root` de `global.css`. (Excepciones históricas existen — ver §15.)

---

## 2. Assets de marca SYSCOM

Copias de referencia en **`docs/assets/brand/`** (originales en `frontend/src/assets/`):

| Archivo | Uso en el portal | Tratamiento |
|---|---|---|
| `syscomLargeLogo.webp` | Logo principal. Navbar pública (`Header.jsx`), sidebar admin (`AdminSidebar.jsx`), página de login (`Admin.jsx`) | Sobre fondos oscuros se aplica `filter: brightness(0) invert(1)` → versión **monocromática blanca**. Nunca dibujar el logo en un color distinto a blanco (sobre oscuro) o su color original (sobre claro) |
| `favicon.webp` | Favicon del sitio (`frontend/index.html`, `rel="icon" type="image/x-icon"`) | — |
| `syscom-logo-vector.png` | Respaldo vectorial exportado (original: `SYSCOM-Parent/SYSCOM-Logo-Vector.svg-.png`) | No se importa directamente en Vite (el nombre contiene un punto); usar `syscomLargeLogo.webp` en componentes |

### Reglas de uso del logo

- **Navbar pública:** altura fija `26px`, `width: auto`, `draggable={false}`, enlaza a `/wizard`.
- **Sidebar admin:** altura fija `24px`, mismo filtro de blanco.
- **Login:** escala `32px` centrada dentro de `.login-card`.
- **Separación de marca:** el logo SYSCOM va acompañado de un divisor vertical (1px `rgba(255,255,255,0.2)`, 24px alto) + el título de producto en `rgba(255,255,255,0.85)`, `0.875rem`.
- **Favicon:** se referencia vía `href="src/assets/favicon.webp"` (funciona en dev; ⚠️ ver §15 — en producción conviene moverlo a `public/`).

---

## 3. Tokens de color

Definidos en `:root` de `global.css`. La familia base es **azul marino corporativo SYSCOM**.

### 3.1 Azules de marca

| Variable | Hex | Rol |
|---|---|---|
| `--syscom-blue` | `#091f3e` | **Primario.** Navbar, botones primarios, enlaces activos, textos "de marca" (`.flow-guide-title`, `.admin-modal-title`), fondos de iconos/chevrons de pasos |
| `--syscom-blue-light` | `#0c2447` | Hover del primario (un paso más claro) |
| `--syscom-blue-accent` | `#1a3a6b` | Acento: enlaces (`a`), links activos del sidebar, hover de enlaces, gradiente del avatar |
| `--blue-50` | `#eef2f7` | Fondos suaves azulados (íconos, cards de aprobación, callout info, método seleccionado) |
| `--blue-100` | `#d4e0ed` | Bordes suaves azulados, focus ring en inputs, badges azules |
| `--blue-500` | `#2a5494` | Azul intermedio: hovers de dots del wizard, botones activos de selector tutorial |
| `--blue-600` | `#081a33` | Tonos muy oscuros (hover gradiente) |
| `--blue-700` | `#061428` | Muy oscuro (estado hover) |
| `--blue-800` | `#04101f` | El más oscuro de la familia |

### 3.2 Neutrales (slate — paleta Tailwind)

| Variable | Hex | Rol |
|---|---|---|
| `--slate-50` | `#f8fafc` | Fondo de página, fondo de tablas hover, footer wizard |
| `--slate-100` | `#f1f5f9` | Fondos secundarios, botones secundarios, badges neutros, th de tabla, overlay claro |
| `--slate-200` | `#e2e8f0` | **Borde estándar** de cards/tablas/divisores |
| `--slate-300` | `#cbd5e1` | Bordes de inputs, bordes "hover", checkboxes vacíos |
| `--slate-400` | `#94a3b8` | Texto placeholder, texto muted (`text-muted`), íconos inactivos |
| `--slate-500` | `#64748b` | Texto secundario, subtítulos, hints, labels |
| `--slate-600` | `#475569` | Texto secundario más legible, body de docs (`tut-p`) |
| `--slate-700` | `#334155` | Texto principal en superficies claras (`tut-p`, botones sec. texto) |
| `--slate-800` | `#1e293b` | **Texto base del body** y de cards; barra de código (header) |
| `--slate-900` | `#0f172a` | Títulos H1/H2, texto destacado, fondo de bloques de código (`tut-code`) |

### 3.3 Semánticos (estado)

| Variable | Hex | Rol |
|---|---|---|
| `--green-50` / `--green-600` / `--green-700` | `#f0fdf4` / `#16a34a` / `#15803d` | Éxito: badge verde, alert-success, callout tip, dot fase final, ícono done |
| `--red-50` / `--red-600` | `#fef2f2` / `#dc2626` | Error: alert-error, badge rojo, callout danger, botón de logout/confirmación |
| `--amber-50` / `--amber-600` | `#fffbeb` / `#d97706` | Advertencia: badge ámbar, warning modal, callout warning, dot fase intermedia |

### 3.4 Colores de peligro crítico (hardcoded, usados por el sistema)

| Valor | Contexto |
|---|---|
| `#feecac` / `#fde68a` / `#854d0e` | Nota importante del wizard (`wizard-important-note`: fondo amarillo claro, borde ámbar, texto ámbar oscuro) |
| `rgba(255,119,0,0.08)` + borde `rgba(255,98,0,0.35)` + título `#ff6f00` | `.activation-warning` (advertencia irreversible de activación) |
| `#fff1e6` / `#c2410c` | Badge-naranja (por expirar pronto) |
| `#b45309` | Badge-amarillo (por expirar) |
| `#ff6f00` | Orange (confirmación de expiración) |
| `#3b82c4` | Azul "tecnológico" para gradientes decorativos (barra superior de diapositivas, barra de progreso de presentación) |
| `#2563eb` | Dot fase 2 (fase intermedia en tutoriales) |

### 3.5 Temas multi-tenant (integradores)

- `--tenant-primary` (default `--syscom-blue`) y `--tenant-secondary` (default `--syscom-blue-accent`): cada integrador puede definir los suyos vía `ui_config` (multi-tenant RBAC). El modo oscuro básico, oculto tras `[data-theme="dark"]`, pinta `.admin-main` en `#0f172a` (cards `#1e293b`, bordes `#334155`).
- **Regla:** los componentes del panel admin que respetan el tenant NO deben usar `--syscom-blue` directo; usar `--tenant-primary`.

---

## 4. Tipografía

| Elemento | Especificación |
|---|---|
| Base | `16px`, `line-height: 1.5`, `--slate-800`, `-webkit-font-smoothing: antialiased` |
| H1 admin (`admin-panel-header h1`) | `1.35–1.5rem`, `700`, `--slate-900` |
| Título de página larga (`tutorial-page-title`, `faq-page-title`, `tut-hub-title`) | `2rem`, `800`, `--slate-900`, `letter-spacing: -0.02em`, `line-height: 1.15` |
| H2 sección (`tut-heading--l1`) | `1.35rem`, `700`, `--slate-900` |
| Subsecciones (`tut-heading--l2`) | `1.05rem`, `700`, `--slate-800` |
| Subtítulo/label (`card-subtitle`, `admin-panel-meta`) | `0.85–0.925rem`, `--slate-500` |
| Cuerpo doc (`tut-p`) | `0.925rem`, `--slate-700`, `line-height: 1.7` |
| Botones | `0.925rem`, `600` (`.btn-sm` `0.8rem`) |
| **Micro-headers / uppercase** | `0.68–0.72rem`, `700`, `text-transform: uppercase`, `letter-spacing: 0.04–0.08em`, color `--slate-400/500` (ej. `toolbar-label`, `tut-page-header-badge`, `approval-dl dt`) |
| Enlaces | `color: var(--syscom-blue-accent)`; hover `--syscom-blue`; inline-flex con icono + `gap: 0.45rem` |
| Código inline | `Consolas`, `0.78–0.82rem`, a veces `--syscom-blue` para resaltar comandos |
| `kbd` | `--slate-100` bg, borde `--slate-300`, radio `5px`, `0.8rem/600`, padding `0.1rem 0.45rem` |

**Escala mental actual (rem):** ~0.68 / 0.8 / 0.85 / 0.925 / 1.1 / 1.35 / 2.0, con excepciones fluidas vía `clamp()` en FAQ: `clamp(1.55rem, 2.6vw, 1.95rem)`.

---

## 5. Radios y formas

La familia del producto es **cuadrada/cuasi-cuadrada con esquinas redondeadas generosas**, no redondeo tipo píldora genérico.

| Radio | Uso |
|---|---|
| `4px` | Botones micro (copy-command-btn, chevrons) |
| `5px` | Código inline, `kbd` |
| `6px` | Chips, mini-botones de copiado, badges de switch |
| `8px` | **Botones**, inputs, links de sidebar, códigos inline en tarjeta, iconos dentro de listas |
| `10px` (`--radius`, **estándar del sistema**) | `card`, resúmenes del wizard (`wizard-summary`), `metric-card`, `tut-callout`, bloques de código, selectores activos de 2px |
| `12px` | Cards grandes (`login-card`, `card-flat` en admin, `tut-hub-card`, `faq-empty`, `coming-soon`, iconbullets de presentación) |
| `14px` | **Modales** (`admin-modal`), header/contenedor de FAQ |
| `20px` | Diapositiva de presentación (`pres-slide`) |
| `999px` (pill) | Badges (`badge`), chips de categoría (`faq-cat-chip`), botones pill CTA (`wizard-tutorial-btn`, `tut-mob-toggle`), barras de progreso de presentación (`pres-progress`) |
| `50%` (círculo) | Dots de progreso del wizard, pasos numerados (`flow-step-number`, `tut-step-num`), avatares redondos, checks finales |

### Bordes

- **Estándar:** `1px solid var(--slate-200)` (cards, tablas, dividers laterales, cajones).
- **Input:** `1px solid var(--slate-300)`, focus → `1px solid var(--syscom-blue-accent)` + ring.
- **Selectores activos tipo "radio card"** (`wizard-method-card`, `tut-conn-btn`): `2px solid var(--slate-200)` → al activar `2px solid var(--syscom-blue)` (o `--blue-500`) + fondo `--blue-50` + ring suave.
- **Acento lateral:** para jerarquía en cards de datos: `border-left: 4px` o `5px` en color de estado/tenant (metric-card verde/ámbar, `pres-unit`).
- **Divisores:** `1px solid var(--slate-200)` horizontales (secciones); `border-bottom: 2px` en tabs activas; dashed `--slate-200/300` para estados vacíos/coming-soon y separadores de "related".
- **Fondos suaves alternativos:** `--blue-50` (finalidad informativa), `--slate-50` (sección neutra), `--green/red/50` (estados).

---

## 6. Sombras y elevación

| Token | Definición | Uso |
|---|---|---|
| `--shadow` | `0 1px 3px rgba(8,26,51,0.08), 0 4px 16px rgba(8,26,51,0.06)` | Elevación estándar: cards, tablas, toggles |
| `--shadow-lg` | `0 8px 32px rgba(8,26,51,0.14)` | Modales, login, sidebar móvil, hover de cards navegables |
| Ring de foco | `0 0 0 3px var(--blue-100)` (inputs) / `0 0 0 3px rgba(26,58,107,0.12)` (search FAQ) | Focos de inputs y búsquedas |
| Halo de step actual | `0 0 0 4px rgba(9,31,62,0.18)` | Dot del wizard en paso activo |
| Sombra flotante mobile | `0 4px 16px rgba(9,31,62,0.35)` | `.tut-mob-toggle` (FAB de sidebar en móvil) |

**Reglas de elevación:**

- Las tarjetas navegables/clickeables suben en hover: `transform: translateY(-2px/-3px)` + `--shadow-lg`.
- Las píldoras/toggles NO usan sombra salvo estado "activo/seleccionado".
- El overlay de modales es `rgba(15,23,42,0.55)` (download) / `rgba(8,26,51,0.55)` + `backdrop-filter: blur(3px)` (admin modal).

---

## 7. Espaciado y layout

| Escala | Nota |
|---|---|
| Gaps de UI | `0.35 / 0.5 / 0.65 / 0.75 / 1 / 1.25 / 1.5 / 1.75 / 2 / 2.5rem` |
| Padding de cards | `2rem` (card grande), `1.25–1.5rem` (cards de lista, aprobación, tiles) |
| Página contenido | `.page` `padding: 5rem 1rem`; `.admin-content` `1.5rem 1.75rem 2.25rem`; docs `tut-main` `2.5rem 2rem 4rem` |
| Anchos máximos | `420px` login · `540px` wizard-step · `680px` page-narrow · `720px` docs content · `960px` hub tutoriales · `1080px` FAQ · sin límite (admin) |
| Layouts | Sidebar fija `260px` (admin) / `272px` sticky (tutoriales); grids `1fr 2fr` (admin-grid), `250px + 1fr` (FAQ), `auto-fit minmax(200–280px, 1fr)` (métricas/hub) |

**Breakpoints responsive:** `1100px` (docs padding) · `960px` (admin sidebar→drawer + mobile bar) · `900px` (FAQ → 1 col + chips) · `860px` (tutoriales sidebar→drawer + FAB) · `768px` (nav compacta, cards apiladas) · `720px` (action-split) · `640px` (wizard compacto, toolbar, keys-guide) · `480px` (tipografía docs menor).

---

## 8. Iconografía

- Librería: **lucide-react** (siempre SVG inline, tamaño `~1rem–1.5rem`, `currentColor`).
- Iconos con contenedor cuadrado redondeado: `2.25–2.5rem` (wizard-method-icon, install-option-icon, tut-conn-btn-icon), radio `8–10px`, fondo `--syscom-blue` sobre oscuro o `--blue-50` sobre claro.
- Iconos en círculo para estados de éxito/final: `3.5–5rem` radio `50%` fondo `--green-50` / `--blue-50`.
- En navbar/dividers secos NO hay iconos; en tablas los iconos de acción aparecen en hover con `opacity: 0 → 1` (`.copyable-cell-btn`).

---

## 9. Movimiento (motion)

| Patrón | Especificación |
|---|---|
| Transición estándar | `0.15s ease` en `background/border/color/box-shadow` — TODO componente interactivo la tiene |
| Aperturas/collapses de acordeón y toggles | `cubic-bezier(0.4, 0, 0.2, 1)` con duración `0.25–0.35s`; el acordeón de docs usa `grid-template-rows 0fr→1fr` |
| Entrada de panel admin | `@keyframes adminFadeIn` (`opacity 0 + translateY(6px)` → `0.28s ease`) |
| Hover elevación | `translateY(-2px/-3px)` + cambio de sombra en cards; `translateY(-1px)` en toggles |
| Hover lateral | Botones "avanzar" (`tut-portal-link`, `btn-third`) se desplazan `translateX(2–5px)` |
| Presentación (`/presentation`) | Slide in direccional `translateX(±56px) + scale(0.992)` en `0.38s cubic-bezier(0.22, 0.9, 0.28, 1)`; contenido en cascada (`pres-rise`, 0.05–0.3s de delay escalonado) |
| Accesibilidad | `@media (prefers-reduced-motion: reduce)` desactiva animaciones de presentación |

---

## 10. Z-index (escala acordada)

| Contexto | Valor |
|---|---|
| Contenido normal | 1 |
| FAQ panel sticky | 2 |
| Sticky bar admin móvil | 20 |
| Sidebar admin desktop | 40 |
| Backdrop admin móvil | 45 |
| Drawer admin móvil | 50 |
| Overlay docs móvil | 150 |
| FAB docs móvil | 160 |
| Toggle collapse (sin overlay) | 200 |
| **Navbar pública** | 300 |
| Modal descarga | 400 |
| Modal admin | 500 |

---

## 11. Patrones de componentes (cómo se debe diseñar)

### 11.1 Navbar pública (`.navbar`)
- Fondo `--syscom-blue`, `height: 64px`, sticky top, texto blanco, borde inferior `rgba(255,255,255,0.08)`.
- Links `0.85rem / 500 / rgba(255,255,255,0.75)` → hover/active blanco puro.
- CTA de nav (`.btn-nav`): fondo `--syscom-blue-accent`, sin width forzada.

### 11.2 Sidebar admin (`.admin-sidebar`)
- `260px`, fondo `linear-gradient(180deg, #0b1c36 0%, var(--slate-900) 48%, #0a1628 100%)`, borde `rgba(255,255,255,0.06)`.
- Links: `0.875rem / 500 / rgba(255,255,255,0.75)`, radio `8px`, padding `0.75rem 1rem`; **activo** → `--syscom-blue-accent` + borde izquierdo `--tenant-primary`.
- Avatar usuario: cuadrado `10px` con gradiente `145deg --syscom-blue-accent → #0b2a52`, iniciales blancas.
- Zona de logout roja translúcida (`rgba(239,68,68,…)`), confirmación inline en un panel rosado.

### 11.3 Botones (`.btn*`)

| Variante | Estilo |
|---|---|
| `.btn-primary` | Fondo `--syscom-blue`, texto blanco, `width: 100%` por defecto (en admin se sobreescribe con `width: auto`); hover `--syscom-blue-light` |
| `.btn-secondary` | Fondo `--slate-100`, texto `--slate-700`, borde `--slate-200`; hover `--slate-200` |
| `.btn-third` | Solo texto `--slate-700`, hover `translateX(5px)` (para links "siguiente") |
| `.btn-ghost` | Transparente, texto `--slate-600`; hover fondo `--slate-100` |
| `.btn-sm` | `padding: 0.4rem 0.75rem`, `0.8rem` |
| `.btn-nav` / `.btn-copy` | Fondo `--syscom-blue` (o accent en nav), `width:auto` |
| `.wizard-tutorial-btn` / `.tut-mob-toggle` | **Pill**: borde `1.5px --syscom-blue`, fondo blanco, radio `5rem/999px` |
| Estados comunes | `:active` → `scale(0.98)`; `:disabled` → `opacity: 0.55` + `not-allowed` |
| Radio fijo | `8px` salvo pills y círculos |

### 11.4 Formularios
- `.form-group` con `margin-bottom: 1.25rem`; `.form-label` `0.85rem/600/--slate-700`; `.form-hint` `0.8rem/--slate-500`.
- Inputs/selects: alto estándar (padding `0.65rem 0.85rem`), radio `8px`, borde `--slate-300`, focus ring azul (§6). Disabled: fondo `--slate-100` + texto `--slate-400`.
- Checkbox custom (wizard): caja `1.2rem` borde `2px --slate-300` radio `4px`; check → fondo `--syscom-blue`.
- Píldora de reconocimiento (`.wizard-ack-pill`): borde `1.5px --syscom-blue`, radio `999px`; al marcar fondo azul + indicador blanco.
- Filas lado a lado: `.form-row` → grid `1fr 1fr` (1 col en ≤900px).

### 11.5 Cards y contenedores
- `card`: blanco + `--radius` + borde `--slate-200` + `--shadow` + padding `2rem`.
- `card-flat` (variantes embebidas sin sombra extra).
- `metric-card`: igual, con `border-left: 4px solid` opcional por estado + label uppercase mini arriba y valor `2rem/700`.
- `approval-card`: fondo `--blue-50` (resaltar pendiente de acción).
- Estados vacíos: texto centrado `--slate-500` (`empty-state`) o caja dashed (`tut-coming-soon`, `faq-empty`).

### 11.6 Tablas (`.data-table`)
- Dentro de `.table-wrap` con borde y radio; `th` fondo `--slate-50`, uppercase visual, sticky opcional en admin.
- Filas: borde inferior `--slate-100`, hover fondo `--slate-50`; celdas de código en `mono` (`Consolas 0.8rem`).
- Toolbar: tabs segmentadas (`.admin-tabs`: contenedor `--slate-100` radio, tab activa blanca + `--shadow`) + búsqueda a la derecha.

### 11.7 Badges (`.badge`)
- Pill (`999px`), `0.75rem/600`, padding `0.2rem 0.6rem`; variantes `blue/green/amber/slate/red/orange/yellow` (fondo de -50, texto de 600/700).

### 11.8 Alerts y callouts
- `.alert-error/success`: fondo -50 + texto 600/700 + borde 200-tint, radio `8px`.
- Callout de docs (`.tut-callout--info|warning|danger|tip`): fondo semántica + borde 1px tint + icono lucide en color fuerte, radio `10px`.
- Estados del wizard: `.activation-warning` (naranja destructivo) y `.wizard-important-note` (amarillo).

### 11.9 Modales
- Overlay fijo (`inset: 0`, `z-index 400/500`, `rgba(8,26,51,0.55)`, blur en admin).
- `.admin-modal`: `min(520px,100%)` (wide `860px`), radio `14px`, `--shadow-lg`, header con gradiente sutil (blanco→slate-50), cuerpo scrollable, footer `--slate-50` con acciones a la derecha.
- Botón cerrar: cuadrado `2rem` radio `8px` fondo `--slate-100` (hover `--slate-200`).

### 11.10 Tabs
- **Bajo línea** (portal-tabs, faq-admin-tabs): `0.875rem/600`, activa `--syscom-blue` + `border-bottom: 2px` que tapa el borde del contenedor.
- **Segmented** (admin-tabs, §11.6): píldora contenedora con fondo gris, opción activa blanco + sombra.

### 11.11 Wizard (flujo público)
- Progreso: dots circulares `36px` (32px móvil) + labels `0.68rem` (ocultos en móvil) + conector `3px` entre pasos; actual con halo azul (§6), completados en azul, futuros en blanco/borde 300.
- Contenido centrado (max `540px`), título `1.15rem/700`, desc `0.9rem`.
- Footer de 3 zonas: Anterior izquierda, píldora "Ya terminé" centro, Siguiente derecha; borde superior `--slate-200`, fondo `--slate-50`.
- Tarjetas de método: opciones tipo "radio card" (§5) con check circular que aparece al seleccionar.

### 11.12 Bloques de código (docs)
- `.tut-code-block`: barra superior `--slate-800` con label de lenguaje en uppercase mini + botón copiar translúcido; cuerpo `--slate-900`, texto `#e2e8f0`, `Consolas 0.855rem`, `line-height: 1.65`.
- `.tut-inline-code`: `--slate-100` + borde `--slate-200` + radio `6px`.
- `.copy-command`: chip gris con texto truncado + botón copiar que en hover se vuelve azul.

### 11.13 Presentación (`/presentation`) — deck 1280×800
- Escenario fijo 1280×800 escalado (`.pres-stage`, `.pres-scaler`); al fullscreen, fondo radial de escenario (`#12294f → #070f20`).
- Diapositiva: blanco, radio `20px`, `--shadow-lg`, **barra superior 6px** con gradiente `--syscom-blue → --syscom-blue-accent → #3b82c4`.
- Kicker: pill azul accent, uppercase con `letter-spacing: 0.1em`; título `40px` azul marca.
- Stats/units: cards con `border-top: 4px` o `border-left: 5px` accent; iconos cuadrados `46px` radio `12px` fondo `--syscom-blue`.

---

## 12. Fondos y gradientes decorativos

El sistema evita hero banners; la profundidad viene de **glows radiales sutiles**:

- `.admin-layout`: `radial-gradient(1200px 500px at 100% -10%, rgba(26,58,107,0.07), transparent 55%)` sobre `--slate-50`.
- `.page-faq`: `radial-gradient(900px 420px at 0% 0%, rgba(26,58,107,0.07), transparent 55%)`.
- Sidebar admin y nav de categorías FAQ: gradiente lineal oscuro `#0b1c36 → #122a4a` (el navy profundo es la "textura" de marca).
- `.tut-action-card--primary`: `linear-gradient(180deg, var(--blue-50), #fff)`.
- Presentación fullscreen: gradiente radial azul muy oscuro (ver §11.13).

---

## 13. Accesibilidad y buenas prácticas

- `focus-visible` en tabla/cells de copiado; inputs con ring de foco azul visible.
- `draggable={false}` en imágenes de logo; `aria-hidden` en divisores decorativos.
- `alt="SYSCOM"` en el logo; `user-select: none` en controles chk custom.
- Contraste: texto base slate-700/800 sobre blanco; los secundarios nunca bajan de `--slate-400` (solo decorativos).
- `scroll-margin-top` en secciones de docs (por la navbar sticky de 64px).

---

## 14. Principios de diseño del portal (resumen ejecutivo)

1. **Azul marino SYSCOM como identidad absoluta** — `#091f3e` domina fuentes de interacción (nav, botones primarios, pasos, activos). El azul accesorio `#1a3a6b` es para acentos, el `#2a5494` para intermedios de foco.
2. **Superficies planas blancas sobre gris azulado neutro** (`--slate-50` global), sin sombras exageradas, con `1px` de borde slate como definición base.
3. **Formas serias/industriales**: radios de `10px`-`14px`, círculos reservados a pasos/chevrons/avatares, pills reservados a estados y CTAs externos.
4. **Elevación contenida**: solo 2 niveles de sombra + hovers con micro-translate. Los modales son la única capa oscura + blur.
5. **Jerarquía por tipografía**: título grande `-0.02em`, labels funcionales en uppercase micro con tracking amplio, body compacto (`0.85–0.925rem`).
6. **Estados claros y consistentes**: verde=éxito/saludable, ámbar=expiración próxima/advertencia, rojo=irreversible/bloqueo, azul neutro=informativo/pendiente-de-acción (cards de aprobación).
7. **Acción primero**: cada vista cierra con una CTA azul primaria o una píldora dentro del flujo.
8. **El negro no existe**: el "negro" del sistema es `--slate-900` / `--blue-800` con matiz azul; los códigos y texto técnico usan `--slate-800/900`.

---

## 15. Deudas e inconsistencias conocidas (a resolver, no a imitar)

- `var(--green-100)` se usa en `.wizard-done-icon` pero **no está definida** en `:root` (se cae a `transparent` y pinta el color del ícono con default). Definir `--green-100: #dcfce7`.
- `var(--blue-300)` se usa en `.tut-conn-btn--active` de tutoriales y tampoco existe; `box-shadow: 0 0 0 1px` debería usar un azul real (ej. `#9db8dc`).
- `font-weight: 750/800` en títulos, pero solo se cargan pesos hasta `700` de Inter → el navegador sintetiza el peso. Cargar `800` en la URL de Google Fonts (o evitar 750/800).
- `index.html` referencia el favicon con ruta relativa `src/assets/favicon.webp`; en prod conviene moverlo a `frontend/public/` y usar `/favicon.webp` (y añadir tamaños 192/512 para móvil).
- Sólo existe `title` del tab (Portal de Licenciamiento Unitree); **no hay `og:`/description**.
- Colores hardcoded de tokens asociados a expiración (`#c2410c`, `#b45309`) viven en CSS sin variable (`badge-orange/yellow`).
- `presentation.css` igualmente variará de breakpoints; este está estandarizado por reglas px fijas del escenario.
- Token `--tenant-primary` solo se consume en sidebar y hover cards — normalizar el resto de componentes del panel admin para que respeten el tenant.

---

## 16. Mapa del código (dónde tocar cada cosa)

| Necesidad | Archivo |
|---|---|
| Tokens de color/radio/sombra base | `frontend/src/styles/global.css` → `:root` (líneas 1–31) |
| Navbar/Header | `.navbar*` + `frontend/src/components/Header.jsx` |
| Wizard público | `.wizard*` + `frontend/src/pages/wizard/PublicWizard.jsx` |
| Docs/tutoriales | `.tut*` + `frontend/src/components/docs/*` + `frontend/src/pages/tutoriales/*` |
| FAQ | `.faq*` + `frontend/src/components/faq/*` + `FaqManagement.jsx` |
| Panel admin | `.admin-*`, `.metric-*`, `.approval-*` + `frontend/src/pages/Admin.jsx` + componentes panel |
| Modales | `.admin-modal*` + `frontend/src/components/AdminModal.jsx` |
| Login | `.login-*` + `frontend/src/pages/Admin.jsx` |
| Presentación | `frontend/src/styles/presentation.css` + `frontend/src/components/presentation/*` |
| Tema por tenant | variables `--tenant-*`, `[data-theme="dark"]` en `global.css` (spec: `docs/superpowers/specs/*`) |
| Cabina de Retratos (§17) | `windows/src/styles/photobooth.css` + `windows/src/components/photobooth/*` + `windows/src/hooks/usePhotobooth.ts` |

---

## 17. Cabina de Retratos (`windows/`) — Modo escenario inmersivo

La Cabina de Retratos es una **experiencia de una sola pantalla** (kiosco/photobooth): `100dvh`, **sin scroll**, todo el flujo (`idle → countdown → capture → processing → review`) ocurre dentro del visor. Es la segunda superficie de marca tras el portal y extiende el precedente del modo presentación a pantalla completa (§11.13): **el navy profundo es el escenario**.

### 17.1 Escenario oscuro (fondo de la experiencia)

- Base: `linear-gradient(180deg, #070f20, #04091a)` + glows radiales de marca (`#12294f` cenital, `rgba(26,58,107,0.4)` y `rgba(42,84,148,0.22)` laterales).
- **Aurora**: dos blobs radiales (`--syscom-blue-accent` / `--blue-500`, blur 90px) con deriva lenta (26–32s) — profundidad sin distracción.
- **Grano de película**: SVG `feTurbulence` inline a `opacity: 0.05` (textura, no ruido visual).
- Texto base sobre escenario: `#e2e8f0`; secundarios `rgba(203,213,225,0.72)`; títulos `#fff`.

### 17.2 Liquid glass (superficies flotantes)

Reservado para el **dock de controles**, chips sobre el visor, brand bar y toasts — nunca para todo el panel (tendencia 2026: glass estratégico, no decorativo):

- Fondo `rgba(7,15,32,0.55–0.78)` + `backdrop-filter: blur(12–16px)` + borde `1px rgba(255,255,255,0.12)` + highlight interno `inset 0 1px 0 rgba(255,255,255,0.08)`.
- El dock es pill (`999px`) y flota centrado sobre el borde inferior del visor.

### 17.3 Visor fotográfico

- Card 4:3 con radio `18px`, borde `rgba(255,255,255,0.1)`, sombra profunda `0 30px 80px rgba(2,8,20,0.6)` + glow exterior `0 0 120px rgba(26,58,107,0.28)` y viñeta interna.
- **Esquinas viewfinder**: `34px`, `2.5px rgba(255,255,255,0.85)`, glow `drop-shadow(0 0 6px rgba(42,84,148,0.8))`; pulsan durante la cuenta regresiva (anticipación).
- **Barrido ambiental** en reposo: banda de luz azul muy sutil que cruza el visor cada ~5s (la cabina "respira").
- El ancho del visor se deriva del alto disponible: `width: min(100%, calc((100dvh - var(--booth-chrome)) * 4 / 3))` — garantiza el encaje sin scroll.

### 17.4 Momentos de la experiencia

- **Cuenta regresiva**: dígito `800` con glow azul (`text-shadow` en `#3b82c4`/`--blue-100`) + anillo expansivo con glow; titular dinámico por estado (blur+fade, `0.28s`).
- **Flash**: destello blanco `0→1→0.35→0` en `0.5s`.
- **Processing**: reveal del sketch con `clip-path` descendente + **scanline** luminosa (`rgba(191,219,254,0.95)` + halo `#3b82c4`) + rail de progreso de `4px` en el borde inferior (gradiente `--syscom-blue-accent → --blue-500 → #3b82c4`).
- **Review — impresión instantánea**: el sketch entra con spring como **foto impresa** (marco `#fdfdfc`, `padding 12/12/42`, radio `4px`, rotación `-1.6deg`, caption uppercase `--slate-400`), sombra `0 40px 90px rgba(2,8,20,0.65)`.
- **CTA principal**: pill blanco (texto `--syscom-blue`) con glow `0 0 40px rgba(42,84,148,0.35)`; hover `translateY(-2px) scale(1.02)` + glow mayor. Secundarios: pill glass `rgba(255,255,255,0.09)`.

### 17.5 Toasts oscuros

Tarjeta glass (§17.2) con icono `Sparkles`/`Info` en `--blue-100`. **Sin badges semánticos estridentes ni acentos verdes** en esta superficie; la celebración la dan el confetti (paleta azules/blanco/slate) y el movimiento.

### 17.6 PROHIBIDO: labels de estado genéricos

**Regla del dueño del producto (también en `AGENTS.MD`):** quedan prohibidos los indicadores genéricos tipo "círculo verde + LIVE / EN VIVO", pills decorativas de estado y cualquier etiqueta que "grite" obviedad (se perciben como UI genérica hecha por IA). El estado se comunica con **luz, composición y movimiento**: el barrido ambiental implica reposo, el pulso de las esquinas implica cuenta regresiva, la scanline implica proceso.

### 17.7 Logo sobre escenario

El logo oficial (`assets/brand/syscomLargeLogo.webp`, servido desde `windows/public/brand/`) es **negro**: sobre el escenario oscuro siempre con `filter: brightness(0) invert(1)` (versión monocromática blanca, §2). Altura `26px` en brand bar, `draggable={false}`.
