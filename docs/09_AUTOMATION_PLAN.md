# Automation Plan: Self-Updating CLI

## Overview

The `warnetech evolve` command enables self-updating through ASAEAI's sandbox synthesis, automated verification, and atomic deployment patterns.

## Evolution Architecture

```
┌──────────────────────────────────────────────────┐
│  User runs: warnetech evolve                        │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│  1. SYNTHESIS: Generate code changes             │
│     - Fetch latest code from GitHub              │
│     - Apply AST mutations                        │
│     - Generate patches                           │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│  2. VERIFICATION: Test in sandbox                │
│     - Run unit tests                             │
│     - Run integration tests                      │
│     - Check for regressions                      │
│     - Validate security                          │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│  3. DEPLOYMENT: Atomic update                    │
│     - Backup current version                     │
│     - Deploy new version                         │
│     - Verify functionality                       │
│     - Cleanup backups                            │
└──────────────────────────────────────────────────┘
                      ↓
┌──────────────────────────────────────────────────┐
│  4. ROLLBACK (if needed): Restore                │
│     - Detect failures                            │
│     - Restore from backup                        │
│     - Verify restoration                         │
└──────────────────────────────────────────────────┘
```

## Phase 1: Synthesis

### Code Change Sources

1. **GitHub Releases**: New versions from repo
2. **Patch Queue**: Staged patches waiting deployment
3. **AST Mutations**: AI-generated improvements

### Fetching New Code

```javascript
async function fetchLatestCode() {
  const releases = await github.releases.listLatest();
  const latest = releases[0];

  if (latest.version > currentVersion()) {
    const code = await download(latest.download_url);
    return { version: latest.version, code, hash: sha256(code) };
  }
}
```

### AST Mutation Engine

The Worker includes an AST mutation engine that can:

- Refactor code patterns
- Apply security patches
- Optimize performance
- Update dependencies

**Example Mutation:**

```javascript
// Input: Unencrypted response
const response = { data: secretData };
res.json(response);

// Mutation: Add encryption
const response = { data: await encrypt(secretData) };
res.json(response);
```

### Patch Queue

Patches staged in D1 cache:

```sql
CREATE TABLE patches (
  id TEXT PRIMARY KEY,
  version TEXT,
  changes TEXT,
  verified BOOLEAN,
  applied_at TIMESTAMP
);
```

---

## Phase 2: Verification

### Testing Strategy

All changes verified before deployment to production.

#### Unit Tests

```bash
npm test --coverage

# Must pass:
# - 100% of existing tests
# - 80%+ code coverage
# - No regressions
```

#### Integration Tests

```bash
npm run test:integration

# Must verify:
# - CLI commands work
# - Worker endpoints work
# - External API calls work
# - Data flow intact
```

#### Security Validation

```javascript
async function validateSecurity(newCode) {
  const checks = [
    checkForSecrets(newCode), // No API keys hardcoded
    checkEncryption(newCode), // Uses AES-256-GCM
    checkInputValidation(newCode), // Validates all inputs
    checkDependencies(newCode), // No vulnerable deps
  ];

  return Promise.all(checks);
}
```

#### Sandbox Environment

```javascript
async function runInSandbox(code) {
  // 1. Create isolated environment
  const sandbox = createWorkerSandbox();

  // 2. Deploy code to sandbox
  await sandbox.deploy(code);

  // 3. Run all tests
  const testResults = await sandbox.runTests();

  // 4. Run smoke tests
  const smokeTests = await sandbox.smokeTest();

  // 5. Monitor for 1 minute
  const metrics = await sandbox.monitor(60000);

  // 6. Check results
  if (testResults.passed && smokeTests.passed && metricsHealthy(metrics)) {
    return true;
  } else {
    throw new Error("Verification failed");
  }
}
```

### Validation Checklist

- [ ] Unit tests pass (100%)
- [ ] Integration tests pass
- [ ] No new security vulnerabilities
- [ ] Performance metrics acceptable
- [ ] Code style compliant
- [ ] Documentation updated
- [ ] Rollback plan exists

---

## Phase 3: Deployment

### Atomic Deployment

Deployment is atomic: entire update succeeds or entire update fails.

```javascript
async function atomicDeploy(newCode, newVersion) {
  try {
    // 1. Backup current version
    const backup = await backupCurrent();
    console.log("✓ Backed up current version");

    // 2. Mark deployment as in-progress
    await setDeploymentStatus("in_progress", newVersion);
    console.log("✓ Marked deployment in-progress");

    // 3. Deploy to staging first
    await deployToStaging(newCode);
    console.log("✓ Deployed to staging");

    // 4. Test on staging
    const stagingTests = await runStagingTests();
    if (!stagingTests.passed) throw new Error("Staging tests failed");
    console.log("✓ Staging tests passed");

    // 5. Deploy to production
    await deployToProduction(newCode);
    console.log("✓ Deployed to production");

    // 6. Verify functionality
    const healthCheck = await verifyDeployment();
    if (!healthCheck.ok) throw new Error("Deployment verification failed");
    console.log("✓ Deployment verified");

    // 7. Update metadata
    await updateMetadata(newVersion);
    console.log("✓ Metadata updated");

    // 8. Cleanup old backups
    await cleanupOldBackups();
    console.log("✓ Cleanup complete");

    return { success: true, version: newVersion };
  } catch (error) {
    // Rollback on any error
    await rollback(backup);
    throw error;
  }
}
```

### Deployment Stages

1. **Sandbox**: Test in isolated environment
2. **Staging**: Deploy to staging environment
3. **Canary**: Route 5% of traffic to new version
4. **Production**: Full production deployment

### Rollback Mechanism

```javascript
async function rollback(backup) {
  console.log("⚠ Rolling back deployment...");

  try {
    // 1. Stop accepting new requests
    await pauseRequests();

    // 2. Restore from backup
    await restoreFrom(backup);

    // 3. Verify restoration
    const healthCheck = await verifyDeployment();
    if (!healthCheck.ok) {
      // If rollback fails, manual intervention needed
      await notifyOps("CRITICAL: Rollback failed, manual intervention needed");
      throw new Error("Rollback verification failed");
    }

    // 4. Resume requests
    await resumeRequests();

    console.log("✓ Rollback complete");
  } catch (error) {
    console.error("✗ Rollback failed:", error);
    throw error;
  }
}
```

---

## Phase 4: Hot Reload

### Hot Reload Endpoint

Worker supports hot reload without downtime.

```
POST /api/hotload
{
  "action": "patch",
  "patch_id": "uuid",
  "code": "base64_encoded_code"
}
```

### Implementation

```javascript
async function hotReload(patchId, code) {
  // 1. Decode code
  const decoded = Buffer.from(code, "base64").toString("utf-8");

  // 2. Validate syntax
  try {
    new Function(decoded); // Quick syntax check
  } catch (error) {
    return { ok: false, error: "Invalid code" };
  }

  // 3. Apply patch in-memory (no restart needed)
  updateCommandHandlers(decoded);

  // 4. Run quick smoke tests
  const testResults = await runSmokeTests();
  if (!testResults.ok) {
    // Restore previous version
    restoreCommandHandlers();
    return { ok: false, error: "Smoke tests failed" };
  }

  // 5. Log change
  await logHotReload(patchId, decoded);

  return { ok: true, deployment_id: generateId() };
}
```

---

## warnetech evolve Command

### Usage

```bash
warnetech evolve
```

### Options

```
--check      Only check for updates, don't apply
--dry-run    Simulate update without deploying
--version    Install specific version
--rollback   Rollback to previous version
```

### Flow

```javascript
async function evolve(options = {}) {
  console.log("🔄 Starting evolution...");

  // 1. Check for updates
  const updates = await checkUpdates();
  if (!updates.available && !options.version) {
    console.log("✓ Already on latest version");
    return;
  }

  const targetVersion = options.version || updates.latest;
  console.log(`✓ Found version: ${targetVersion}`);

  if (options.check) {
    console.log(`Available: ${targetVersion}`);
    return;
  }

  // 2. Download & verify
  console.log("📥 Downloading code...");
  const code = await downloadVersion(targetVersion);
  const hash = await verifyHash(code);
  console.log(`✓ Verified: ${hash}`);

  // 3. Synthesize changes
  console.log("🔨 Synthesizing changes...");
  const mutations = await synthesizeChanges(code);
  console.log(`✓ Generated ${mutations.length} mutations`);

  // 4. Verification
  console.log("🧪 Running verification...");
  const verified = await verify(mutations);
  if (!verified.ok) {
    console.error("✗ Verification failed:", verified.error);
    return;
  }
  console.log("✓ All verification passed");

  if (options["dry-run"]) {
    console.log("✓ Dry run complete (no deployment)");
    return;
  }

  // 5. Deploy
  console.log("🚀 Deploying...");
  const deployed = await deploy(mutations, targetVersion);
  console.log(`✓ Deployed to ${deployed.environment}`);

  // 6. Verify
  console.log("✅ Verifying deployment...");
  const health = await verifyDeployment();
  if (health.ok) {
    console.log("✓ Evolution complete!");
    console.log(`  Version: ${targetVersion}`);
    console.log(`  Uptime: ${health.uptime}ms`);
  } else {
    console.error("✗ Deployment verification failed");
    await rollback();
  }
}
```

---

## Monitoring & Alerts

### Metrics Tracked

- Request latency (p50, p95, p99)
- Error rates
- CPU usage
- Memory usage
- Token usage (API quotas)

### Alert Conditions

- Error rate > 1%
- P99 latency > 5s
- Memory usage > 80%
- Quota approaching limit

### Response to Alerts

- Alert sent to ops team
- Automatic rollback if error rate > 5%
- Escalation after 15 minutes unresolved

---

## AST Mutation Engine

### Mutation Types

#### Pattern 1: Add Encryption

```javascript
// Detects unencrypted responses and wraps them
// Input: res.json(data);
// Output: res.json(await encrypt(data));
```

#### Pattern 2: Add Error Handling

```javascript
// Detects unchecked API calls and adds error handling
// Input: const result = await fetch(url);
// Output: const result = await fetch(url).catch(e => handleError(e));
```

#### Pattern 3: Update Dependencies

```javascript
// Updates package versions to latest stable
// Input: "crypto-js": "4.1.0"
// Output: "crypto-js": "4.1.5"
```

#### Pattern 4: Security Hardening

```javascript
// Adds input validation to functions
// Input: function handleRequest(data) { ... }
// Output: function handleRequest(data) {
//   validateInput(data);
//   ...
// }
```

### Mutation Testing

Each mutation is tested in isolation before deployment.

---

## Troubleshooting

### Evolution Failed

```bash
# Check status
warnetech status

# View logs
tail ~/.claude-cli/logs/evolution.log

# Manual rollback
warnetech evolve --rollback
```

### Verification Failed

- Check test output
- Review code changes
- File issue on GitHub
- Rollback and investigate

### Deployment Stuck

- Check Worker logs
- Check Cloudflare dashboard
- Manual intervention may be needed
- Contact ops team
