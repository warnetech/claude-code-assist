# Git Workflow

## Branch Strategy

### Development Branch

```
claude/termux-cli-cloudflare-nemotron-pve6ca
```

All development happens on this branch. Once complete:

1. Create PR to `main`
2. Verify CI/CD passes
3. Merge to `main`
4. Tag release version
5. Push to GitHub

### Feature Branches (from development branch)

For specific features, create feature branches:

```bash
git checkout -b feat/command-ai
git checkout -b feat/worker-security
git checkout -b feat/github-automation
```

Then merge back to development branch when complete.

---

## Commit Guidelines

### Commit Message Format

```
<type>: <description>

<optional detailed explanation>
```

### Types

- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring (no behavior change)
- `test`: Add or modify tests
- `docs`: Documentation changes
- `chore`: Build, deps, config

### Examples

```
feat: add warnetech ai command for Nemotron integration
feat: implement AES-256-GCM encryption
fix: handle rate limit 429 responses
test: add integration tests for gh-push
docs: update architecture diagram
chore: upgrade dependencies
```

### Commit Best Practices

- One feature per commit (atomic)
- Complete, working code (passes tests)
- Include test updates in same commit
- Never commit secrets or .env files
- Write clear, descriptive messages

---

## Common Workflows

### Feature Development

```bash
# Start feature
git checkout -b feat/new-command

# Make changes
vim worker/commands/newcmd.js
git add worker/commands/newcmd.js
git commit -m "feat: add new command"

# Push to feature branch
git push -u origin feat/new-command

# Create PR for review
# (After review, merge to development branch)
git checkout claude/termux-cli-cloudflare-nemotron-pve6ca
git merge feat/new-command
git push origin claude/termux-cli-cloudflare-nemotron-pve6ca

# Cleanup
git branch -d feat/new-command
```

### Bug Fix

```bash
# Create fix branch
git checkout -b fix/rate-limit-handling

# Make changes, test, commit
vim worker/utils/validate.js
npm test
git add worker/utils/validate.js
git commit -m "fix: improve rate limit handling"

# Push and merge same as feature
git push -u origin fix/rate-limit-handling
# ... create PR, merge, cleanup
```

### Pull Latest Changes

```bash
# Update development branch
git fetch origin
git pull origin claude/termux-cli-cloudflare-nemotron-pve6ca

# Update feature branch
git rebase origin/claude/termux-cli-cloudflare-nemotron-pve6ca
```

---

## CI/CD Pipeline

### Pre-commit Checks (Local)

```bash
npm run lint     # ESLint
npm run format   # Prettier
npm run test     # Jest
```

### GitHub Actions (on push)

1. **Lint & Format**
   - Check code style
   - Check formatting
   - Fail if issues found

2. **Run Tests**
   - Unit tests
   - Integration tests
   - Coverage reporting

3. **Security Scan**
   - Check for secrets
   - Check dependencies
   - OWASP scanning

4. **Build & Deploy**
   - Build CLI binary
   - Build Worker code
   - Deploy to staging (on development branch)
   - Deploy to production (on main branch)

### Status Checks

All PRs must pass:

- ✓ Lint
- ✓ Tests
- ✓ Security scan
- ✓ Code coverage (>80%)
- ✓ Approval from reviewer

---

## Release Process

### Version Numbering

Follow Semantic Versioning (MAJOR.MINOR.PATCH):

- MAJOR: Breaking changes (1.0.0 → 2.0.0)
- MINOR: New features (1.0.0 → 1.1.0)
- PATCH: Bug fixes (1.0.0 → 1.0.1)

### Release Steps

```bash
# 1. Prepare release on development branch
npm version patch|minor|major

# 2. This updates package.json and creates git tag
# Example: v1.0.1

# 3. Push changes and tag
git push origin claude/termux-cli-cloudflare-nemotron-pve6ca
git push origin --tags

# 4. Merge development to main
git checkout main
git pull origin main
git merge claude/termux-cli-cloudflare-nemotron-pve6ca
git push origin main

# 5. GitHub automatically creates release from tag
# 6. Deployment happens automatically via CI/CD
```

### Release Notes

Create CHANGELOG.md entry:

```markdown
## [1.0.1] - 2026-08-05

### Added

- warnetech ai command for Nemotron integration
- Streaming support for reasoning tokens

### Fixed

- Rate limit handling in Worker
- SSH key validation in gh-push

### Security

- Implemented AES-256-GCM encryption
- Added anti-tamper heuristics
```

---

## Reviewing PRs

### Before Reviewing

```bash
# Check out PR branch locally
git fetch origin
git checkout <feature-branch>

# Run tests
npm test

# Test manually
npm run dev
warnetech ai "test prompt"
```

### Review Checklist

- [ ] Code follows standards (04_CODE_STANDARDS.md)
- [ ] Tests added/updated
- [ ] No secrets committed
- [ ] Commit messages clear
- [ ] Performance acceptable
- [ ] Security concerns addressed
- [ ] Documentation updated

### Approval & Merge

```bash
# After approval, merge to development
git checkout claude/termux-cli-cloudflare-nemotron-pve6ca
git merge <feature-branch>
git push origin claude/termux-cli-cloudflare-nemotron-pve6ca
```

---

## Resolving Merge Conflicts

### When Conflicts Occur

```bash
# Fetch latest
git fetch origin

# Rebase to latest development
git rebase origin/claude/termux-cli-cloudflare-nemotron-pve6ca

# Git shows conflicts
# Edit files to resolve, keep the good parts from both sides

# Mark resolved
git add resolved-file.js

# Continue rebase
git rebase --continue

# Push (may need --force-with-lease since we rebased)
git push -u origin feat/branch --force-with-lease
```

### Conflict Guidelines

- Keep code that makes sense from both sides
- Avoid deleting large sections without reason
- Test after resolving
- Commit message: "Merge: resolve conflicts with development"

---

## Disaster Recovery

### Undo Recent Commits

```bash
# Undo last commit (keep changes)
git reset HEAD~1

# Undo last commit (discard changes)
git reset --hard HEAD~1

# Undo push (if not merged to main)
git reset --hard <previous-commit>
git push -u origin <branch> --force-with-lease
```

### Recovering Deleted Commits

```bash
# Find deleted commit
git reflog

# Restore branch to that commit
git reset --hard <commit-hash>
```

### Stashing Changes

```bash
# Save uncommitted changes
git stash

# List stashed changes
git stash list

# Apply stashed changes
git stash apply stash@{0}

# Delete stashed changes
git stash drop stash@{0}
```

---

## Tips

### Useful Aliases

```bash
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.st status
git config --global alias.unstage 'reset HEAD --'
git config --global alias.last 'log -1 HEAD'
git config --global alias.visual 'log --graph --oneline --all'
```

### Viewing History

```bash
# View last 5 commits
git log -5

# View commits with changes
git log -p

# View commits for specific file
git log -- worker/index.js

# Visual branch history
git log --graph --oneline --all
```

### Before Pushing

```bash
# Review changes before push
git diff origin/<branch>

# Ensure tests pass
npm test

# Lint code
npm run lint
```
