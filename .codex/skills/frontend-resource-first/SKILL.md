---
name: frontend-resource-first
description: Use when building, redesigning, or polishing Vue, Nuxt, or Vue-adjacent frontend experiences, especially dynamic landing pages, AI product pages, tech sites, login pages, portfolios, dashboards, admin systems, mobile H5 pages, component selection, animation choices, or UI library decisions.
---

# Frontend Resource First

## Overview

Use this skill before choosing frontend components, UI libraries, or animation approaches for Vue/Nuxt work. The core rule is: inspect the project's stack first, then look for suitable resources from the curated sites before inventing custom UI from scratch.

## Required Workflow

1. Confirm the target stack and constraints from the project:
   - Vue, Nuxt, TypeScript, Tailwind CSS, existing UI library, animation library, package manager, SSR requirements, and design style.
   - If the project is not Vue/Nuxt, still use the resource list for design inspiration, but avoid adding Vue-only dependencies unless the user approves.
2. Before implementation, search or open the relevant official sites from the Resource Map below.
   - If the user asks for a current component, install command, API, or compatibility detail, browse the official source and cite it in the response.
   - Prefer source-copy libraries when the project needs easy customization.
3. Select resources by scenario, then implement using the project's existing patterns.
4. Keep dependencies conservative:
   - Do not install multiple animation libraries for the same purpose.
   - Prefer `motion-v` for new Vue animation work unless the project already uses VueUse Motion or needs GSAP-level timeline control.
   - Prefer low-level unstyled primitives only when building a custom design system.
5. After implementing, verify visually for frontend changes when a local app can run.

## Resource Map

| Need | Look First | Use For |
| --- | --- | --- |
| Dynamic Vue/Nuxt visual components | Inspira UI: https://inspira-ui.com | Aurora, particles, beams, spotlight cards, 3D cards, text effects, mouse effects, glowing borders, Bento Grid |
| Creative Vue 3 animations | Vue Bits: https://vue-bits.dev | AI product pages, tech sites, animated login pages, portfolios, product showcases, cursor effects, docks, WebGL effects |
| Editable component source | shadcn-vue: https://www.shadcn-vue.com | Drawers, command palettes, data tables, carousels, dialogs, hover cards, sidebars, source-owned components |
| Community component registries | shadcn-vue Directory: https://www.shadcn-vue.com/docs/directory | Inspira UI and other shadcn-vue compatible community components |
| Accessible unstyled primitives | Reka UI: https://reka-ui.com | Dialog, menu, tooltip, tabs, combobox, keyboard behavior, accessibility foundations |
| Vue animation primitives | Motion for Vue: https://motion.dev/docs/vue | Enter/exit, hover, tap, drag, scroll-triggered, layout, gesture, shared-element style animations |
| VueUse-integrated animation | VueUse Motion: https://motion.vueuse.org | `v-motion`, presets, composables, Nuxt/VueUse-heavy projects, SSR-friendly animation |
| Complex timelines | GSAP: https://gsap.com | ScrollTrigger storytelling, multi-element timelines, SVG path animation, large product-showcase animation |

## Scenario Choices

| Scenario | Recommended Starting Point |
| --- | --- |
| AI product homepage | Inspira UI + Vue Bits + Motion for Vue |
| Tech-style marketing site | Vue Bits or Inspira UI, then Motion for Vue |
| Dynamic login page | Vue Bits for background/text/cursor effects, shadcn-vue for form components |
| Portfolio | Vue Bits for expressive sections, Inspira UI for cards/backgrounds |
| Product showcase | Vue Bits or Inspira UI, GSAP only for complex timeline storytelling |
| Traditional admin system | Element Plus or Naive UI |
| Highly customized product UI | shadcn-vue + Reka UI + Tailwind CSS + Motion for Vue |
| Enterprise dashboard | Ant Design Vue, Arco Design Vue, Element Plus, or Naive UI |
| Mobile H5 | Vant |
| Cross-platform app | Quasar |
| Material Design app | Vuetify |
| Broad component catalog/templates | PrimeVue |

## Library Guidance

- Use Inspira UI or Vue Bits first when the request asks for "dynamic", "cool", "animated", "tech", "AI", "hero", "background effects", "Bento", "3D card", "particles", "aurora", "beams", or "cursor".
- Use shadcn-vue when the user values owning component source, deep customization, Tailwind styling, or modern app primitives.
- Use Reka UI when behavior, keyboard interaction, focus management, accessibility, or custom design-system primitives matter more than ready-made styling.
- Use one animation family by default:
  - New Vue/Nuxt project: `motion-v`.
  - Existing VueUse-heavy project: `@vueuse/motion`.
  - Complex timeline or ScrollTrigger requirement: GSAP.
- For standard management systems, choose a complete UI library instead of assembling every primitive manually.

## Common Mistakes

- Do not build custom animated effects before checking Inspira UI and Vue Bits for a close source component.
- Do not add GSAP for ordinary button, modal, card hover, or simple page-transition animation.
- Do not combine Element Plus, Naive UI, Ant Design Vue, and Arco Design Vue in the same app unless the existing project already does so.
- Do not install a library only because it is popular; match it to the user's scenario and the current project stack.
- Do not rely on memory for latest install commands, package names, component APIs, or registry commands; verify from the official site when those details matter.
