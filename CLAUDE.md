## Code Style

This project uses TypeScript. Always generate `.ts`/`.tsx` files with proper types — never use `any` without justification.

## Deployment

- Always verify which project directory/codebase is being modified before making changes. Multiple projects may share similar names (e.g., 'AIFred Vault' vs 'AIFred Trading V2').
- After any deployment fix, verify the deployed version actually updated (check Vercel/Railway build logs) before debugging further.

## Frontend (Next.js/React)

- Framer Motion opacity:0 and animation patterns break interactivity and cause hydration issues. Avoid opacity:0 initial states; prefer CSS transitions or visibility toggling.
- Always check for SSR/hydration compatibility when adding animation libraries.
- Never render raw objects as JSX children — always extract primitive values first.

## Wallet Integration

- Coinbase Wallet hijacks `window.ethereum` — always use explicit provider detection (check `window.ethereum.providers` array) rather than assuming MetaMask is the default.
- Wallet addresses and env vars change frequently; always re-verify current values before deploying.

## Environment & Build

- Next.js bakes env vars at build time (NEXT_PUBLIC_*). Changing them requires a full rebuild, not just a restart.
- On Railway, Docker layer caching can prevent rebuilds — add cache-bust args when needed.
- Ensure .dockerignore does not exclude required runtime files (e.g., src/data/).

## Pre-Deploy Checklist

After any component change that touches animations or client-side libraries (Framer Motion, wallet connectors), run `next build` locally before pushing to Vercel to catch hydration mismatches early.

## Debugging Protocol

- **Verify deploy target first.** Before fixing anything, confirm: (1) you're in the correct repo (`git remote -v`), (2) the last push triggered a build (`vercel ls` or Railway logs), (3) the live site reflects the latest commit. Show proof before proceeding.
- **Local validation before push.** Always run `npx tsc --noEmit` and `npm run build` locally before pushing. If either fails, fix the errors first. Only push when the local build succeeds. This eliminates most deploy-fix-deploy spirals.
- **Python syntax check.** For Python changes: `python3 -c "import ast; ast.parse(open('file.py').read())"` before pushing.

## Session Workflow

- **Work in checkpoints.** For multi-feature sessions, commit after each working milestone (e.g., "auth works" → commit → "wallet works" → commit). Tag checkpoints so you can revert if the next change breaks something.
- **Define 3-4 checkpoints upfront** for complex tasks. List what needs to be done and where the natural commit points are before starting.
- **Never tackle deployment + auth + UI + wallet in one uncommitted batch.** Cascading regressions with no rollback point waste hours.
