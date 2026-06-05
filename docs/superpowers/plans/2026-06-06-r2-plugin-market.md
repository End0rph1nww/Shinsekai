# AstrBot-Style Plugin Distribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild Shinsekai plugin publishing around the AstrBot-style GitHub Issue + registry CI + R2 package flow.

**Architecture:** Authors keep plugin source code in GitHub repositories. The plugin market is a static author-facing UI that generates submission JSON and opens a GitHub Issue in the Shinsekai plugin registry; during development we use `End0rph1nww/Shinsekai-Plugin-Registry` as the staging fork, then open PRs back to the upstream author registry. Registry GitHub Actions perform maintainer-review support, PR validation, clean packaging, R2 upload, generated registry updates, and md5 publication. The Shinsekai client and market both consume the generated registry and prefer verified R2 packages, with GitHub fallback only for non-security package failures.

**Tech Stack:** Vue plugin market, Python registry tooling, GitHub Issue Forms, GitHub Actions, Cloudflare R2 S3-compatible API, Python plugin host and React plugin manager, pytest, Vitest, Vite.

---

## Current Evidence

AstrBot's public implementation is split across three surfaces:

1. `Astrbot_Plugins_Market` provides `/submit`: a form wizard that generates JSON and opens the AstrBot GitHub Issue template. It does not upload packages and does not hold object-storage credentials.
2. `AstrBot_Plugins_Collection` contains `plugins.json`, `plugin_cache_original.json`, validation workflows, and transform workflows that enrich repository metadata.
3. AstrBot clients fetch `https://api.soulter.top/astrbot/plugins`; entries include `download_url`, `commit_sha`, `sec_scan`, and package URLs like `https://astrbot-plugins-s3.astrbot.app/plugins/{owner}/{plugin}/{version}/{plugin}-{version}-{commit12}.zip`.

The public AstrBot repositories show the Issue form, registry collection, validation, and metadata transform pieces. The exact S3 upload/scanning service is not visible in the public repos, so Shinsekai should implement that missing part in registry CI, prove it in the staging fork, and then submit it upstream rather than inventing a server-side publishing backend.

## Repository Roles

Use these roles consistently. Do not move R2 secrets into the market repo or Shinsekai client repo.

| Repository | Role | Owns Secrets |
| --- | --- | --- |
| `End0rph1nww/Shinsekai-Plugin-Market` | Static market UI, plugin cards, details, `/submit` wizard | No |
| `End0rph1nww/Shinsekai-Plugin-Registry` fork | Staging/dev registry for Issue template, submission parsing, registry JSON, validation CI, R2 packaging CI, and upstream PR preparation | Test/staging secrets only |
| `RachelForster/Shinsekai-Plugin-Registry` upstream | Final review target and public source of truth after PR acceptance | Yes, configured by upstream maintainers |
| `End0rph1nww/Shinsekai` fork | Client install behavior and plugin manager UI | No R2 upload secrets |

Expected local checkouts:

```powershell
cd D:\Workspace\Assistant
git clone https://github.com/End0rph1nww/Shinsekai-Plugin-Registry.git Shinsekai-Plugin-Registry
cd Shinsekai-Plugin-Registry
git remote get-url upstream >$null 2>$null
if ($LASTEXITCODE -ne 0) { git remote add upstream https://github.com/RachelForster/Shinsekai-Plugin-Registry.git }
git fetch upstream
```

If the registry checkout already exists, fetch both `origin` and `upstream`. Build and test on the fork, but keep branches rebased onto `upstream/main` before opening public PRs.

## End-to-End Publishing Flow

```text
Plugin author visits Shinsekai plugin market or uses Shinsekai local submit helper
  -> fills the same submit form fields
  -> market/client generates the same registry JSON
  -> market/client opens Shinsekai-Plugin-Registry Issue template
  -> author pastes/submits JSON
  -> issue CI parses and validates JSON
  -> issue CI comments validation result and opens a registry PR
  -> maintainer reviews the PR
  -> PR CI smoke-validates changed plugins
  -> maintainer merges PR
  -> registry main CI packages changed plugins
  -> registry main CI uploads zip packages to R2
  -> registry main CI writes generated registry + md5
  -> market and client consume generated registry
```

This mirrors AstrBot's user-facing path while making the hidden S3 packaging step explicit and reviewable. The staging fork is only the build-and-test runway; the finished Registry workflow should be proposed to the upstream author repo.

## Registry Contract

### Author-Facing `plugins.json`

`plugins.json` is the reviewed source of truth. It should stay readable and should not require generated package fields.

```json
{
  "shinsekai_plugin_demo": {
    "display_name": "Demo Plugin",
    "desc": "A short plugin description.",
    "author": "End0rph1n",
    "repo": "https://github.com/End0rph1nww/shinsekai_plugin_demo",
    "entry": "plugins.shinsekai_plugin_demo.plugin:DemoPlugin",
    "tags": ["demo", "tool"],
    "social_link": "https://github.com/End0rph1nww"
  }
}
```

Required fields:

- `display_name`
- `desc`
- `author`
- `repo`
- `entry`

Optional fields:

- `tags`
- `social_link`
- `logo`
- `version`
- `shinsekai_version`
- `support_platforms`

### Generated `plugin_cache_original.json`

CI writes generated install metadata. This is the file the market and client should prefer.

```json
{
  "shinsekai_plugin_demo": {
    "display_name": "Demo Plugin",
    "desc": "A short plugin description.",
    "author": "End0rph1n",
    "repo": "https://github.com/End0rph1nww/shinsekai_plugin_demo",
    "entry": "plugins.shinsekai_plugin_demo.plugin:DemoPlugin",
    "tags": ["demo", "tool"],
    "stars": 1,
    "version": "v1.0.0",
    "shinsekai_version": ">=0.0.0",
    "updated_at": "2026-06-06T00:00:00Z",
    "commit_sha": "a1b2c3d4e5f6",
    "download_url": "https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/End0rph1nww/shinsekai_plugin_demo/1.0.0/shinsekai_plugin_demo-1.0.0-a1b2c3d4e5f6.zip",
    "sha256": "hex-encoded-sha256",
    "size": 123456,
    "package": {
      "source": "r2",
      "url": "https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/End0rph1nww/shinsekai_plugin_demo/1.0.0/shinsekai_plugin_demo-1.0.0-a1b2c3d4e5f6.zip",
      "sha256": "hex-encoded-sha256",
      "size": 123456,
      "r2_key": "plugins/End0rph1nww/shinsekai_plugin_demo/1.0.0/shinsekai_plugin_demo-1.0.0-a1b2c3d4e5f6.zip"
    },
    "sec_scan": {
      "static": {
        "pass": true,
        "msg": "No blocked patterns found."
      }
    }
  }
}
```

### R2 Key Format

Follow the AstrBot shape:

```text
plugins/{owner}/{plugin_name}/{version_without_v}/{plugin_name}-{version_without_v}-{commit12}.zip
```

Public URL:

```text
https://plugins-cdn.shinsekai.end0rph1n.icu/plugins/{owner}/{plugin_name}/{version_without_v}/{plugin_name}-{version_without_v}-{commit12}.zip
```

Use `version_without_v` only for the path. Keep the registry `version` field as the source value, usually `v1.0.0`.

## PR Split

Build the integration branch first, then split into small PRs after the end-to-end path works.

1. Main client PR: registry/package schema compatibility.
2. Main client PR: verified R2 installer and GitHub fallback.
3. Main client PR: dependency install optimization.
4. Main client PR: install provenance UI.
5. Registry PR: Issue template, issue-to-PR workflow, registry validation.
6. Registry PR: package-to-R2 workflow and generated registry/md5 output.
7. Market PR: AstrBot-style submit wizard and package metadata display.
8. Main client PR: local submit helper that mirrors the market form and opens the same GitHub Issue route.

The first four are already partly implemented on `integration/plugin-distribution-system`. The next highest-value work is PR 5 in the registry staging fork, with upstream PR compatibility kept from the start.

## PR 1: Main Client Registry Package Metadata

**Branch:** `feat/plugin-registry-package-metadata`

**Repo:** `D:\Workspace\Assistant\Shinsekai-main-20260606`

**Commit style:** `feat(plugin-registry): support package metadata`

**Purpose:** Let the client parse AstrBot-style and Shinsekai generated registry fields without changing install behavior.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\registry_catalog.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_catalog.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\entities\plugin\types.ts`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_registry_catalog.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_catalog.py`

**Steps:**

- [ ] Add normalized fields: `display_name`, `desc`, `short_desc`, `version`, `shinsekai_version`, `tags`, `logo`, `updated_at`, `commit_sha`, `download_url`, `sha256`, `size`, `package_source`, `package_url`, `package_sha256`, `package_size`, `package_r2_key`, `sec_scan`.
- [ ] Accept legacy registry objects whose values only contain `name`, `author`, `repo`, `description`, and `entry`.
- [ ] Accept object-shaped payloads like AstrBot's `plugins.json` and generated `plugin_cache_original.json`.
- [ ] Add parser tests for legacy entries, generated package entries, nested `package`, missing tags, invalid tag types, string sizes, and numeric sizes.
- [ ] Expose fields through `/api/plugins/registry` without making the frontend require generated package data.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
python -m pytest test\unit\test_plugin_registry_catalog.py test\unit\test_frontend_plugin_catalog.py -q
cd frontend
pnpm exec vitest run src\test\pluginUtils.test.ts
```

**PR boundary:** Do not change package download or install behavior.

## PR 2: Main Client Verified R2 Installer

**Branch:** `feat/plugin-installer-r2-package`

**Repo:** `D:\Workspace\Assistant\Shinsekai-main-20260606`

**Depends on:** PR 1

**Commit style:** `feat(plugin-installer): install verified r2 packages`

**Purpose:** Install from official package URLs first, verify checksum, extract safely, then fall back to GitHub only for non-security package failures.

**Files:**

- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\package_download.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_updates.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\registry_download.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_package_download.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_updates.py`

**Steps:**

- [ ] Allow only `http` and `https` package URLs with non-empty hosts.
- [ ] Add optional host allowlist through `SHINSEKAI_PLUGIN_PACKAGE_HOSTS`.
- [ ] Add max-size guard through `SHINSEKAI_PLUGIN_PACKAGE_MAX_BYTES`, default `16777216`.
- [ ] Require SHA-256 for official package installs.
- [ ] Stream download to a temp file with size checks.
- [ ] Verify `sha256` and optional `size`.
- [ ] Reject zip-slip paths: absolute paths, drive-letter paths, and `..` escapes.
- [ ] Normalize single top-level archive roots so files land under `plugins/<safe-plugin-name>`.
- [ ] Prefer package install when registry entry has `package.url` or `download_url`.
- [ ] Do not fall back to GitHub on checksum mismatch, unsafe zip path, or max-size violation.
- [ ] Fall back to GitHub on transient package download errors such as timeout, 404, or network failure.
- [ ] Add kill switch: `SHINSEKAI_PLUGIN_DISABLE_PACKAGE_INSTALL=1`.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
python -m pytest test\unit\test_plugin_package_download.py test\unit\test_frontend_plugin_updates.py -q
```

**PR boundary:** Do not introduce dependency-installer changes or registry CI.

## PR 3: Main Client Dependency Install Optimization

**Branch:** `feat/plugin-deps-mirror-precheck`

**Repo:** `D:\Workspace\Assistant\Shinsekai-main-20260606`

**Depends on:** PR 2

**Commit style:** `feat(plugin-deps): optimize requirements installation`

**Purpose:** Reduce failures and latency after plugin download, especially for domestic users.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\plugin_requirements_install.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\runtime_dependencies.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_updates.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_requirements_install.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_updates.py`

**Steps:**

- [ ] Parse requirements lines with comments, markers, version specifiers, nested `-r`, and direct references.
- [ ] Detect installed distributions before pip install.
- [ ] Build a temporary requirements file containing only missing or incompatible dependencies.
- [ ] Fall back to full `requirements.txt` when requirements contain unsupported options.
- [ ] Add configurable index priority: `SHINSEKAI_PIP_INDEX_URL` and `SHINSEKAI_PIP_EXTRA_INDEX_URLS`.
- [ ] Add configurable extra args: `SHINSEKAI_PIP_INSTALL_ARGS`.
- [ ] Preserve special handling for `torch`, `torchvision`, and `torchaudio`.
- [ ] Stream pip logs to frontend task logs.
- [ ] Return structured result codes: `pip_ok`, `pip_skip_no_requirements`, `pip_failed`, `pip_timeout`, `pip_exception`, `pip_conflict`.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
python -m pytest test\unit\test_plugin_requirements_install.py test\unit\test_frontend_plugin_updates.py -q
```

**PR boundary:** Do not alter registry schema or R2 upload CI.

## PR 4: Main Client Install Provenance UI

**Branch:** `feat/plugin-install-provenance-ui`

**Repo:** `D:\Workspace\Assistant\Shinsekai-main-20260606`

**Depends on:** PR 2

**Commit style:** `feat(plugin-manager): surface install provenance`

**Purpose:** Show the user where a package came from and what dependency state the installer reached.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_updates.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\shared\platform\types.ts`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\shared\ui\TaskProgress.tsx`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\shared\ui\TaskProgress.css`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\test\shared\ui\TaskProgress.test.tsx`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_frontend_plugin_updates.py`

**Steps:**

- [ ] Add task fields: `installSource`, `installSourceLabel`, `packageStatus`, `packageUrl`, `packageSource`, `packageSha256`, `dependencyInstallStatus`.
- [ ] Return `install` metadata in installed plugin payloads.
- [ ] Show source, package state, dependency state, and compact SHA in `TaskProgress`.
- [ ] Add tests for R2 package success and GitHub fallback.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
python -m pytest test\unit\test_frontend_plugin_updates.py -q
pnpm --dir frontend test src/test/shared/ui/TaskProgress.test.tsx
pnpm --dir frontend build
```

**PR boundary:** Do not change registry CI or market submit behavior.

## PR 5: Registry Issue Template and Maintainer Review CI

**Branch:** `feat/registry-issue-review-ci`

**Repo:** `D:\Workspace\Assistant\Shinsekai-Plugin-Registry`

**Remote policy:** Develop in the `End0rph1nww` fork, but branch from `upstream/main` when available. Before opening the real PR, rebase or recreate the branch on `RachelForster/Shinsekai-Plugin-Registry` `main`.

**Commit style:** `feat(plugin-registry): add issue based submission flow`

**Purpose:** Recreate AstrBot's author-facing flow: market/client-generated JSON lands in a GitHub Issue, CI validates it, and maintainers review a generated registry PR.

**Files:**

- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\.github\ISSUE_TEMPLATE\PLUGIN_PUBLISH.yml`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\.github\workflows\issue-to-registry-pr.yml`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\.github\workflows\validate-registry.yml`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\plugins.json`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\scripts\registry\parse_issue_submission.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\scripts\registry\validate_plugins.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\tests\test_parse_issue_submission.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\tests\test_validate_plugins.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\README.md`

**Issue template requirements:**

```yaml
name: Publish Plugin
description: Submit a Shinsekai plugin to the registry
title: "[Plugin] YOUR PLUGIN NAME"
labels: ["plugin-publish"]
body:
  - type: markdown
    attributes:
      value: |
        Paste the JSON generated by the Shinsekai plugin market or local submit helper.
  - type: textarea
    id: plugin-info
    attributes:
      label: Plugin Info
      value: |
        ```json
        {
          "display_name": "Human-readable plugin name",
          "desc": "Short description",
          "author": "author",
          "repo": "https://github.com/owner/repo",
          "entry": "plugins.package.plugin:PluginClass",
          "tags": [],
          "social_link": ""
        }
        ```
    validations:
      required: true
```

**Steps:**

- [ ] Write `parse_issue_submission.py` to extract the first fenced JSON block from an issue body.
- [ ] Normalize plugin key from `name` if provided, otherwise from the repo name.
- [ ] Reject repo URLs that are not `https://github.com/{owner}/{repo}` or that end with `.git`.
- [ ] Require `display_name`, `desc`, `author`, `repo`, and `entry`.
- [ ] Limit `desc` to 70 Unicode characters.
- [ ] Limit `tags` to 5 strings.
- [ ] Write or update the plugin entry in `plugins.json`.
- [ ] Make `issue-to-registry-pr.yml` run on `issues.opened` and `issues.edited` with label `plugin-publish`.
- [ ] Have the workflow comment validation failures back to the issue.
- [ ] Have the workflow create or update branch `submission/issue-{number}` and open a PR with the parsed plugin entry.
- [ ] Make `validate-registry.yml` run on PRs that touch `plugins.json`.
- [ ] Add tests for valid JSON, missing fenced block, malformed JSON, invalid GitHub URL, too many tags, missing entry, and updating an existing plugin.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Registry
python -m pytest tests -q
python scripts\registry\validate_plugins.py plugins.json
```

**Required permissions/secrets:**

- Use `GITHUB_TOKEN` for PR creation if repository settings allow it.
- If branch protection or cross-workflow triggering requires a token, add `REGISTRY_BOT_TOKEN` with `contents:write`, `pull_requests:write`, and `issues:write`.
- Configure these first in the staging fork for testing. Upstream maintainers should configure their own token after the PR is accepted.

**PR boundary:** This PR must not upload to R2. It only implements submission, validation, and maintainer-review PR creation.

## PR 6: Registry Package-to-R2 CI

**Branch:** `ci/registry-package-r2`

**Repo:** `D:\Workspace\Assistant\Shinsekai-Plugin-Registry`

**Remote policy:** Develop in the fork with staging R2 credentials. Do not assume the fork remains the final registry owner; upstream maintainers should receive the workflow and secret list through PR documentation.

**Depends on:** PR 5

**Commit style:** `ci(plugin-registry): package approved plugins to r2`

**Purpose:** After maintainers merge approved plugin entries, package changed plugins, upload them to R2, and update generated registry files.

**Files:**

- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\.github\workflows\publish-plugin-packages.yml`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\scripts\registry\package_plugin.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\scripts\registry\update_generated_registry.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\scripts\registry\static_security_scan.py`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\plugin_cache_original.json`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\plugins-md5.json`
- Create: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\docs\plugin-distribution-ci.md`
- Test: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\tests\test_package_plugin.py`
- Test: `D:\Workspace\Assistant\Shinsekai-Plugin-Registry\tests\test_update_generated_registry.py`

**Required secrets:**

```text
R2_ACCOUNT_ID
R2_ACCESS_KEY_ID
R2_SECRET_ACCESS_KEY
R2_BUCKET
R2_PUBLIC_BASE_URL
REGISTRY_BOT_TOKEN
```

Optional scanner secrets:

```text
VIRUSTOTAL_API_KEY
SECURITY_LLM_API_KEY
```

**Steps:**

- [ ] Add `workflow_dispatch` inputs: `plugin_names`, `force`, and `dry_run`.
- [ ] Add push trigger for `plugins.json` changes on `main`.
- [ ] Detect changed plugin keys by comparing `plugins.json` against `HEAD^`.
- [ ] For each selected plugin, query GitHub repo metadata and resolve default branch, latest tag, or configured `version`.
- [ ] Download the GitHub archive for the resolved ref.
- [ ] Reject package size over `16777216` bytes after cleanup.
- [ ] Build a clean zip excluding `.git`, `.github`, `.env`, `__pycache__`, `.venv`, `node_modules`, logs, caches, build folders, and temporary files.
- [ ] Verify `entry` points to an importable-looking module path inside the cleaned package.
- [ ] Compute `sha256`, `size`, `commit_sha`, `updated_at`, and R2 key.
- [ ] Run static security scan for blocked patterns such as `subprocess.Popen(shell=True)`, raw `eval`, suspicious network exfiltration strings, and credential-looking literals.
- [ ] Upload the zip:

```bash
aws s3 cp "$ZIP_PATH" "s3://${R2_BUCKET}/${R2_KEY}" \
  --endpoint-url "https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"
```

- [ ] Write generated metadata into `plugin_cache_original.json`.
- [ ] Write `plugins-md5.json` as `{ "md5": "<md5 of plugin_cache_original.json>" }`.
- [ ] Commit generated files back to `main` with bot identity.
- [ ] Run workflow once with `dry_run=true` against one test plugin before enabling automatic upload.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Registry
python -m pytest tests -q
python scripts\registry\validate_plugins.py plugins.json
python scripts\registry\update_generated_registry.py --dry-run --plugin-name shinsekai_plugin_demo
```

**PR boundary:** This PR owns packaging, R2 upload, and generated registry output. It must not change the market UI or the Shinsekai client installer.

## PR 7: Plugin Market Submit Wizard and Package Display

**Branch:** `feat/plugin-market-submit-wizard`

**Repo:** `D:\Workspace\Assistant\Shinsekai-Plugin-Market`

**Depends on:** PR 5's issue template shape and PR 6's generated registry shape.

**Commit style:** `feat(plugin-market): add issue based submit wizard`

**Purpose:** Match AstrBot's author experience while keeping the market static and credential-free.

**Files:**

- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\views\SubmitPlugin.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\components\SubmitPluginButton.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\utils\pluginNormalizer.js`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\stores\plugins.js`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\components\PluginCard.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\src\components\PluginDetails.vue`
- Modify: `D:\Workspace\Assistant\Shinsekai-Plugin-Market\README.md`

**Steps:**

- [ ] Replace the placeholder submit guide with a 3-step wizard: fill form, preview JSON, open GitHub Issue.
- [ ] Form fields: `display_name`, `desc`, `author`, `repo`, `entry`, `tags`, `social_link`.
- [ ] Validate GitHub URL with the same rule as the registry script.
- [ ] Limit `desc` to 70 Unicode characters and tags to 5.
- [ ] Generate JSON matching the registry Issue template.
- [ ] Use `VITE_SUBMIT_URL` for the Issue URL. Staging can point to `https://github.com/End0rph1nww/Shinsekai-Plugin-Registry/issues/new?template=PLUGIN_PUBLISH.yml`; production should point to the upstream registry after PR acceptance.
- [ ] Do not hard-code the fork owner into production builds.
- [ ] Keep `VITE_SUBMIT_URL` override support.
- [ ] Normalize generated package fields: `download_url`, `sha256`, `size`, `commit_sha`, `package.url`, `package.sha256`, `package.size`, `package.r2_key`, and `sec_scan`.
- [ ] Show package source, version, size, compact SHA, and scan state in details.
- [ ] Keep the existing drawer interaction and Shinsekai pink visual language.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Market
npm run build
```

**PR boundary:** The market must not upload packages, call R2, store credentials, or require a server API for publishing.

## PR 8: Main Client Local Submit Helper

**Branch:** `feat/plugin-publisher-local-submit`

**Repo:** `D:\Workspace\Assistant\Shinsekai-main-20260606`

**Depends on:** PR 5's Issue template schema and PR 7's market submit behavior. It can start once those field names are stable.

**Commit style:** `feat(plugin-publisher): add local issue submit helper`

**Purpose:** Extend #69 without creating a second publishing route. The local client should scan local plugin metadata, prefill the same form used by the market, generate the same JSON, and open/copy the same Registry Issue URL. It must not upload packages or write directly to Registry.

**Files:**

- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\publisher\metadata.py`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\publisher\submission.py`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\core\plugins\publisher\validate.py`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\plugin_publisher.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend_bridge_core\handler.py`
- Modify: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\features\plugin-manager\PluginManagerPage.tsx`
- Create: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\features\plugin-manager\PluginPublisherDialog.tsx`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\test\unit\test_plugin_publisher.py`
- Test: `D:\Workspace\Assistant\Shinsekai-main-20260606\frontend\src\test\pluginPublisher.test.tsx`

**Shared form contract:**

```json
{
  "display_name": "Human-readable plugin name",
  "desc": "Short description",
  "author": "author",
  "repo": "https://github.com/owner/repo",
  "entry": "plugins.package.plugin:PluginClass",
  "tags": [],
  "social_link": ""
}
```

**Steps:**

- [ ] Add `metadata.py` to scan a local plugin folder for README title, package folder, candidate `entry`, `requirements.txt`, logo file, and repository URL from git remote config.
- [ ] Add `submission.py` to serialize exactly the same JSON fields as PR 5 and PR 7: `display_name`, `desc`, `author`, `repo`, `entry`, `tags`, and `social_link`.
- [ ] Add `validate.py` with the same validation rules as registry CI: GitHub URL only, required fields, `desc` <= 70 Unicode characters, and at most 5 tag strings.
- [ ] Add `frontend_bridge_core\plugin_publisher.py` commands for `scanLocalPlugin`, `validatePluginSubmission`, `buildPluginSubmissionIssueUrl`, and `copyPluginSubmissionJson`.
- [ ] Add a `Submit Plugin` action in the plugin manager that opens `PluginPublisherDialog`.
- [ ] Build the dialog with the same field order as the market wizard: fill form, preview JSON, open GitHub Issue.
- [ ] Read the Issue URL from `SHINSEKAI_PLUGIN_SUBMIT_URL`; default to the staging fork only in dev builds and document the upstream production target.
- [ ] Add tests that a fixed input produces byte-equivalent JSON to the shared contract above.
- [ ] Add tests for invalid GitHub URL, missing `entry`, too-long `desc`, too many tags, and empty plugin directory scan.
- [ ] Run:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
python -m pytest test\unit\test_plugin_publisher.py -q
pnpm --dir frontend test src/test/pluginPublisher.test.tsx
pnpm --dir frontend build
```

**PR boundary:** This PR only creates a local authoring convenience layer. It must not upload to R2, commit to Registry, bypass Issue review, or define a schema different from the market wizard.

## Integration Branch Workflow

Main client integration branch:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
git fetch origin
git fetch fork
git switch integration/plugin-distribution-system
```

Registry branch:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Registry
git fetch origin
git fetch upstream
git switch -c feat/registry-issue-review-ci upstream/main
```

If `upstream/main` is temporarily unavailable, create the branch from `origin/main`, but rebase onto upstream before opening the author-facing PR.

Market branch:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Market
git fetch origin
git switch -c feat/plugin-market-submit-wizard origin/main
```

Local submit helper branch:

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
git fetch origin
git fetch fork
git switch -c feat/plugin-publisher-local-submit origin/main
```

Keep commits scope-clean. If implementation work mixes scopes, rebuild PRs with `git reset --mixed` and stage by file group.

## End-to-End Verification

Run these before opening public PRs:

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Registry
python -m pytest tests -q
python scripts\registry\validate_plugins.py plugins.json
```

```powershell
cd D:\Workspace\Assistant\Shinsekai-Plugin-Market
npm run build
```

```powershell
cd D:\Workspace\Assistant\Shinsekai-main-20260606
python -m pytest test\unit\test_plugin_registry_catalog.py test\unit\test_plugin_package_download.py test\unit\test_plugin_requirements_install.py test\unit\test_frontend_plugin_catalog.py test\unit\test_frontend_plugin_updates.py -q
python -m pytest test\unit\test_plugin_publisher.py -q
pnpm --dir frontend test src/test/pluginPublisher.test.tsx
pnpm --dir frontend build
```

Manual checks:

- Market `/submit` generates valid JSON and opens the Registry Issue template.
- Local submit helper generates the same JSON as Market `/submit` for the same form input.
- Issue workflow parses the JSON and comments useful validation errors.
- Issue workflow creates a registry PR for valid submissions.
- Registry PR validation rejects malformed entries.
- Publishing workflow creates an R2 URL with the expected key format.
- Generated registry includes `download_url`, `sha256`, `size`, `commit_sha`, `package`, and `plugins-md5.json`.
- Market displays generated package metadata.
- Shinsekai client installs from R2, verifies checksum, and logs package/dependency states.
- Checksum mismatch blocks install and does not fall back to GitHub.
- GitHub-only legacy plugin still installs.
- Public PR branches for Registry are based on upstream `main` and do not hard-code `End0rph1nww` as the production registry owner.

## Review Order

1. Main client PR 1: schema compatibility.
2. Main client PR 2: verified package install.
3. Main client PR 3: dependency optimization.
4. Main client PR 4: install provenance UI.
5. Registry PR 5: Issue template and maintainer-review CI.
6. Registry PR 6: package-to-R2 CI and generated registry.
7. Market PR 7: submit wizard and package display.
8. Main client PR 8: local submit helper that mirrors the market wizard.

Registry PR 5 can be started immediately because it does not depend on client code. Market PR 7 and client PR 8 should wait until the registry Issue template shape is fixed, then both must keep the same submission contract.

## Non-Goals

- Do not build a server-side submission backend.
- Do not put R2 credentials in the plugin market or client repositories.
- Do not require plugin authors to manually write PRs.
- Do not let client-side local submit upload packages to R2.
- Do not treat `End0rph1nww/Shinsekai-Plugin-Registry` as the only or final Registry owner.
- Do not maintain separate web and local submission schemas.
- Do not bypass maintainer review just because CI can parse the issue.

This plan intentionally follows AstrBot's author-facing model while making Shinsekai's R2 packaging and generated registry output explicit. We prove the workflow in the fork first, then propose it upstream with the same Issue-based maintainer review model.
