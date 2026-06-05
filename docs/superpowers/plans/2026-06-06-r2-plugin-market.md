# Plugin Distribution System PR Split Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the full Shinsekai plugin distribution chain, then split it into reviewable PRs after the end-to-end path works.

**Architecture:** GitHub remains the author-facing source of truth for plugin code, tags, and releases. Shinsekai-owned CI validates approved plugin entries, packages clean zip artifacts, uploads them to R2, and updates registry metadata. The Shinsekai client and plugin market consume the same registry, prefer verified R2 packages for downloads, and fall back to GitHub only when package metadata is absent or non-security download failures occur.

**Tech Stack:** Python plugin host and frontend bridge, React plugin manager, Vue plugin market, GitHub Actions, Cloudflare R2 via S3-compatible API, pytest, Vitest, Vite.

---

## Working Model

Develop the whole feature on one integration branch first:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
git fetch origin
git fetch fork
git switch -c integration/plugin-distribution-system origin/main
```

Keep commits small and scope-clean while developing. After the full system works, create PR branches from fresh `origin/main` and cherry-pick the corresponding commits.

Do not put all work into one PR. The final split should be:

1. Main client PR: registry/package schema compatibility.
2. Main client PR: verified R2 installer and GitHub fallback.
3. Main client PR: dependency install optimization.
4. Plugin market PR: package metadata display and submit guidance.
5. Registry or market CI PR: GitHub tag/commit to R2 package pipeline.
6. Main client PR: local submit helper.

This order keeps review risk low: metadata first, install behavior second, dependency behavior third, CI fourth, author-facing helper last.

## Shared Registry Contract

All PRs should converge on this backward-compatible registry shape:

```json
{
  "id": "End0rph1nww/shinsekai-plugin-demo",
  "name": "shinsekai-plugin-demo",
  "display_name": "Demo Plugin",
  "author": "End0rph1n",
  "repo": "End0rph1nww/shinsekai-plugin-demo",
  "description": "Long description",
  "short_desc": "Short card description",
  "version": "v1.0.0",
  "shinsekai_version": ">=0.0.0",
  "entry": "plugins.shinsekai_plugin_demo.plugin:DemoPlugin",
  "tags": ["tool", "demo"],
  "logo": "https://plugins-cdn.example/plugins/End0rph1nww/shinsekai-plugin-demo/assets/logo.png",
  "updated_at": "2026-06-06T00:00:00Z",
  "commit_sha": "a1b2c3d4e5f6",
  "download_url": "https://plugins-cdn.example/plugins/End0rph1nww/shinsekai-plugin-demo/v1.0.0/shinsekai-plugin-demo-v1.0.0-a1b2c3d.zip",
  "sha256": "hex-encoded-sha256",
  "size": 123456,
  "package": {
    "source": "r2",
    "url": "https://plugins-cdn.example/plugins/End0rph1nww/shinsekai-plugin-demo/v1.0.0/shinsekai-plugin-demo-v1.0.0-a1b2c3d.zip",
    "sha256": "hex-encoded-sha256",
    "size": 123456,
    "r2_key": "plugins/End0rph1nww/shinsekai-plugin-demo/v1.0.0/shinsekai-plugin-demo-v1.0.0-a1b2c3d.zip"
  },
  "fallback": {
    "github_zip": "https://github.com/End0rph1nww/shinsekai-plugin-demo/archive/refs/tags/v1.0.0.zip"
  }
}
```

## PR 1: Registry Package Metadata

**Branch:** `feat/plugin-registry-package-metadata`

**Commit style:** `feat(plugin-registry): support package metadata`

**Purpose:** Teach the client to parse and expose package metadata without changing install behavior.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\registry_catalog.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_catalog.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\entities\plugin\types.ts`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\test\pluginUtils.test.ts`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_registry_catalog.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_catalog.py`

**Steps:**

- [ ] Add fields to the normalized registry record: `id`, `display_name`, `short_desc`, `version`, `shinsekai_version`, `tags`, `logo`, `updated_at`, `commit_sha`, `download_url`, `sha256`, `size`, `package_source`, `package_url`, `package_sha256`, `package_size`, `package_r2_key`, `fallback_github_zip`.
- [ ] Keep legacy registry entries valid when they only include `name`, `author`, `repo`, `description`, and `entry`.
- [ ] Accept both root arrays and object payloads with `plugins`.
- [ ] Add parser tests for legacy rows, package rows, nested `package`, bad tag types, string and numeric package sizes.
- [ ] Expose the new fields through `/api/plugins/registry` without making the frontend depend on them.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
runtime\python.exe -m pytest test\unit\test_plugin_registry_catalog.py test\unit\test_frontend_plugin_catalog.py
cd frontend
pnpm exec vitest run src\test\pluginUtils.test.ts
```

**PR boundary:** This PR must not change package download or install behavior.

## PR 2: Verified R2 Installer

**Branch:** `feat/plugin-installer-r2-package`

**Depends on:** PR 1

**Commit style:** `feat(plugin-installer): install verified r2 packages`

**Purpose:** Make the client install from official package URLs first, with checksum verification and safe extraction.

**Files:**

- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\package_download.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_updates.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\registry_download.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_package_download.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_updates.py`

**Steps:**

- [ ] Implement URL validation: allow only `http` and `https`; reject missing hosts.
- [ ] Add optional host allowlist through `SHINSEKAI_PLUGIN_PACKAGE_HOSTS`.
- [ ] Add max-size guard through `SHINSEKAI_PLUGIN_PACKAGE_MAX_BYTES`, default `16777216`.
- [ ] Require SHA-256 for official package installs.
- [ ] Download to memory or a temp file with size checks before extraction.
- [ ] Verify `sha256` and optional `size`.
- [ ] Extract zip with zip-slip prevention: reject absolute paths and `..` escapes.
- [ ] Normalize single top-level archive roots so files land under `plugins/<safe-plugin-name>`.
- [ ] Prefer package install when registry entry has `package.url` or `download_url`.
- [ ] Do not fall back to GitHub on checksum mismatch or unsafe zip paths.
- [ ] Allow GitHub fallback only when package metadata is absent or a non-security download failure occurs.
- [ ] Add kill switch: `SHINSEKAI_PLUGIN_DISABLE_PACKAGE_INSTALL=1`.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
runtime\python.exe -m pytest test\unit\test_plugin_package_download.py test\unit\test_frontend_plugin_updates.py
```

**PR boundary:** This PR may change install behavior but must not introduce dependency installer changes or CI.

## PR 3: Dependency Install Optimization

**Branch:** `feat/plugin-deps-mirror-precheck`

**Depends on:** PR 2

**Commit style:** `feat(plugin-deps): optimize requirements installation`

**Purpose:** Solve slow and unreliable dependency installation after plugin download.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\plugin_requirements_install.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\runtime_dependencies.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_updates.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_requirements_install.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_updates.py`

**Steps:**

- [ ] Add requirements parsing that supports plain package lines, version specifiers, comments, markers, and nested `-r`.
- [ ] Detect installed distributions before pip install.
- [ ] Build a temporary requirements file containing only missing or version-mismatched dependencies.
- [ ] Fall back to full `requirements.txt` install when requirements contain unsafe-to-split direct references or unsupported options.
- [ ] Add configurable PyPI index URL: `SHINSEKAI_PIP_INDEX_URL`.
- [ ] Add configurable extra pip args: `SHINSEKAI_PIP_INSTALL_ARGS`.
- [ ] Preserve the existing PyTorch special index handling for `torch`, `torchvision`, and `torchaudio`.
- [ ] Stream pip logs to frontend task logs.
- [ ] Return structured pip result codes: `pip_ok`, `pip_skip_no_requirements`, `pip_failed`, `pip_timeout`, `pip_exception`, `pip_conflict`.
- [ ] Add manual pip install endpoint or reuse the existing runtime dependency installer with mirror support.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
runtime\python.exe -m pytest test\unit\test_plugin_requirements_install.py test\unit\test_frontend_plugin_updates.py
```

**PR boundary:** This PR must not alter registry schema or R2 upload CI.

## PR 4: Plugin Market Display and Submit Guidance

**Branch:** `feat/plugin-market-package-display`

**Repo:** `D:\Workspace\Assistant\Shinsekai-Plugin-Market`

**Commit style:** `feat(plugin-market): display package metadata`

**Purpose:** Make the public plugin market explain and display the new distribution model.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\utils\pluginNormalizer.js`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\components\PluginCard.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\components\PluginDetails.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\views\SubmitPlugin.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\README.md`

**Steps:**

- [ ] Normalize `package.url`, `package.sha256`, `package.size`, `package.r2_key`, and `fallback.github_zip`.
- [ ] Show official package source, version, package size, and checksum summary on cards or details.
- [ ] Keep existing side drawer interaction.
- [ ] Update submit guidance: authors manage versions through GitHub tags/releases; Shinsekai CI mirrors approved packages to R2.
- [ ] Keep the market static; do not add R2 credentials or direct upload from the static site.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Market
npm run build
```

**PR boundary:** This PR changes market display and docs only. It must not introduce backend upload logic.

## PR 5: Registry CI to Package GitHub Plugins to R2

**Branch:** `ci/plugin-distribution-r2`

**Repo:** Prefer the plugin registry repo if it exists; otherwise use `D:\Workspace\Assistant\Shinsekai-Plugin-Market` until a registry repo is split out.

**Commit style:** `ci(plugin-distribution): package approved plugins to r2`

**Purpose:** Give authors GitHub-based version management while giving users fast R2 downloads.

**Files:**

- Create: `.github\workflows\publish-plugin-r2.yml`
- Create: `tools\plugin_registry\package_plugin.py`
- Create: `tools\plugin_registry\validate_registry.py`
- Create: `tools\plugin_registry\update_registry_package.py`
- Create: `docs\plugin-distribution-ci.md`

**Required Secrets:**

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_PUBLIC_BASE_URL
```

**R2 key format:**

```text
plugins/{owner}/{repo}/{version}/{repo}-{version}-{commit_sha7}.zip
```

**Steps:**

- [ ] Add manual `workflow_dispatch` inputs: `repo`, `ref`, `version`, `registry_id`.
- [ ] Add PR validation mode that checks registry entries without uploading.
- [ ] Checkout the registry repo.
- [ ] Download the target plugin GitHub archive by tag, release, or commit.
- [ ] Validate metadata, entry path, package size, and excluded files.
- [ ] Build a clean zip excluding `.git`, `.env`, `__pycache__`, `.venv`, `node_modules`, build output, logs, and caches.
- [ ] Compute `sha256`, `size`, `commit_sha`, and `updated_at`.
- [ ] Upload zip to R2 through the S3-compatible endpoint:

```bash
aws s3 cp "$ZIP_PATH" "s3://${R2_BUCKET}/${R2_KEY}" \
  --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
```

- [ ] Update registry package fields with R2 URL and checksum.
- [ ] Either commit registry updates to a bot branch or open a PR, depending on branch protection.
- [ ] Run workflow against one test plugin before enabling automatic sync.

**PR boundary:** CI owns packaging and R2 upload. Client install behavior belongs to PR 2.

## PR 6: Local Submit Helper

**Branch:** `feat/plugin-publisher-local-submit`

**Depends on:** PR 1 and PR 4. Can be implemented after PR 5 if the submit flow should trigger CI.

**Commit style:** `feat(plugin-publisher): add local submit helper`

**Purpose:** Make #69's local one-click flow useful without bypassing GitHub version management.

**Files:**

- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\publisher\metadata.py`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\publisher\validate.py`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_publisher.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\handler.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\features\plugin-manager\PluginManagerPage.tsx`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\features\plugin-manager\PluginPublisherDialog.tsx`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_publisher.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\test\pluginPublisher.test.tsx`

**Steps:**

- [ ] Add a local publisher API that scans a plugin directory and returns metadata candidates.
- [ ] Validate entry, version, repo, README, requirements, icon, unsafe files, and package-size estimate.
- [ ] Generate a registry entry draft using the shared schema.
- [ ] Generate a GitHub issue or PR body. Do not upload to R2 from the client.
- [ ] Add a plugin manager button: `Submit Plugin`.
- [ ] Add a dialog with fields for display name, repo, version, entry, description, short description, tags, and Shinsekai version.
- [ ] Add a preview panel showing the generated registry JSON.
- [ ] Add an action to open the registry issue URL with the generated body.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
runtime\python.exe -m pytest test\unit\test_plugin_publisher.py
cd frontend
pnpm exec vitest run src\test\pluginPublisher.test.tsx
pnpm run build
```

**PR boundary:** This PR helps authors submit; it must not own R2 upload secrets or CI packaging.

## Final Cherry-Pick Workflow

After the integration branch is fully working:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
git fetch origin
git switch -c feat/plugin-registry-package-metadata origin/main
git cherry-pick <commits-for-pr-1>
git push fork feat/plugin-registry-package-metadata
```

Repeat for each client PR branch. For the market repo:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Market
git fetch origin
git switch -c feat/plugin-market-package-display origin/main
git cherry-pick <commits-for-pr-4>
git push origin feat/plugin-market-package-display
```

If commits are mixed, rebuild the PR split with a soft reset:

```powershell
git switch integration/plugin-distribution-system
git reset --mixed origin/main
git add -p
git commit -m "feat(plugin-registry): support package metadata"
git add -p
git commit -m "feat(plugin-installer): install verified r2 packages"
```

## End-to-End Verification Before Opening PRs

Run these after the integration branch works:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
runtime\python.exe -m pytest test\unit\test_plugin_registry_catalog.py test\unit\test_plugin_package_download.py test\unit\test_plugin_requirements_install.py test\unit\test_frontend_plugin_catalog.py test\unit\test_frontend_plugin_updates.py
cd frontend
pnpm exec vitest run src\test\pluginUtils.test.ts src\test\pluginPublisher.test.tsx
pnpm run build
```

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Market
npm run build
```

Manual checks:

- R2-backed plugin shows official package metadata in the client and market.
- R2 install verifies checksum and extracts safely.
- Checksum mismatch blocks install and does not fall back to GitHub.
- GitHub-only legacy plugin still installs.
- `requirements.txt` install uses mirror settings and streams logs.
- Local submit helper generates a valid registry draft without exposing secrets.

## PR Review Order

1. Merge PR 1 first because it is schema-only and backward compatible.
2. Merge PR 4 after PR 1 because market display depends on normalized fields but does not affect install behavior.
3. Merge PR 2 after PR 1 because it changes install behavior.
4. Merge PR 3 after PR 2 because dependency install logs attach to install tasks.
5. Merge PR 5 after PR 1 and PR 4 because CI produces the package fields that both surfaces display.
6. Merge PR 6 last because it depends on the registry contract and submission policy.

This split lets us build everything first while still giving maintainers small PRs that can be reviewed and rolled back independently.
