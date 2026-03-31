## Code Style

This project uses TypeScript. Always generate `.ts`/`.tsx` files with proper types — never use `any` without justification.

## SSR / Deployment Gotchas

When using Framer Motion with Next.js/Vercel SSR, always use `initial={false}` or ensure `opacity` starts at `1` in animations. Never use `opacity: 0` as an initial state for interactive elements (buttons, modals, forms) as it breaks click handlers in SSR hydration.

## Pre-Deploy Checklist

After any component change that touches animations or client-side libraries (Framer Motion, wallet connectors), run `next build` locally before pushing to Vercel to catch hydration mismatches early.
