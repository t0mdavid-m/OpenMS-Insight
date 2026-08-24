"""Custom Hatchling build hook.

Builds the Vue/Vite frontend (``js-component``) and stages its compiled output
into ``openms_insight/js-component/dist`` so it is packaged into the wheel/sdist
and found at runtime by ``openms_insight/rendering/bridge.py``.

The hook is robust to building a wheel from an sdist: in that case the frontend
*source* is absent and only the pre-built ``dist`` ships, so the npm build is
skipped and the existing dist is reused.

Discovered automatically by ``[tool.hatch.build.hooks.custom]`` because the class
is named ``CustomBuildHook`` and lives in ``hatch_build.py`` at the project root.
"""

from __future__ import annotations

import os
import shutil
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

# Set this to a truthy value to skip the npm build and rely on a pre-built dist
# (useful for editable dev installs that manage the frontend via ``npm run dev``,
# or for air-gapped builds that ship a pre-built dist).
SKIP_ENV_VAR = "OPENMS_INSIGHT_SKIP_NPM_BUILD"


class CustomBuildHook(BuildHookInterface):
    PLUGIN_NAME = "custom"

    def initialize(self, version, build_data):
        root = self.root
        frontend_dir = os.path.join(root, "js-component")
        package_json = os.path.join(frontend_dir, "package.json")
        source_dist = os.path.join(frontend_dir, "dist")
        target_dir = os.path.join(root, "openms_insight", "js-component")
        target_dist = os.path.join(target_dir, "dist")

        # 1) Explicit opt-out: rely on an existing pre-built dist.
        if self._is_truthy(os.environ.get(SKIP_ENV_VAR)):
            self.app.display_info(
                f"{SKIP_ENV_VAR} is set; skipping npm frontend build."
            )
            self._require_prebuilt(target_dist)
            return

        # 2) No frontend source present (e.g. building a wheel from an sdist, which
        #    ships the pre-built dist but not package.json / src). Reuse the dist.
        if not os.path.isfile(package_json):
            self.app.display_info(
                "Frontend source not found (js-component/package.json); assuming a "
                "pre-built dist (e.g. building from an sdist). Skipping npm build."
            )
            self._ensure_target_dist(source_dist, target_dist)
            self._require_prebuilt(target_dist)
            return

        # 3) Source is present -> the frontend must be buildable. Locate npm.
        npm = shutil.which("npm") or shutil.which("npm.cmd")
        if npm is None:
            raise RuntimeError(
                "Frontend source was found at 'js-component/' but the 'npm' "
                "executable is not on PATH, so the Vue component cannot be built. "
                f"Install Node.js/npm, or set {SKIP_ENV_VAR}=1 to use a pre-built "
                "dist."
            )

        # 4) Build the frontend.
        self.app.display_waiting("Installing frontend dependencies (npm ci)...")
        self._run([npm, "ci"], cwd=frontend_dir)
        self.app.display_waiting("Building Vue frontend (npm run build)...")
        self._run([npm, "run", "build"], cwd=frontend_dir)

        if not os.path.isdir(source_dist):
            raise RuntimeError(
                f"'npm run build' completed but produced no dist at {source_dist}."
            )

        # 5) Stage js-component/dist -> openms_insight/js-component/dist.
        self.app.display_info(
            "Staging frontend build into openms_insight/js-component/dist"
        )
        os.makedirs(target_dir, exist_ok=True)
        if os.path.isdir(target_dist):
            shutil.rmtree(target_dist)
        shutil.copytree(source_dist, target_dist)
        self.app.display_info("Frontend build complete.")

    @staticmethod
    def _is_truthy(value):
        return bool(value) and value.lower() not in ("0", "false", "no", "")

    def _run(self, cmd, cwd):
        try:
            subprocess.run(cmd, cwd=cwd, check=True)
        except FileNotFoundError as exc:  # npm vanished between which() and run()
            raise RuntimeError(
                f"Could not execute {cmd[0]!r}: {exc}. Is Node.js/npm installed "
                "and on PATH?"
            ) from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(
                f"Command {' '.join(cmd)} (in {cwd}) failed with exit code "
                f"{exc.returncode}."
            ) from exc

    def _ensure_target_dist(self, source_dist, target_dist):
        """Populate openms_insight/js-component/dist from js-component/dist if the
        former is missing but the latter (pre-built) is present."""
        if os.path.isdir(target_dist):
            return
        if os.path.isdir(source_dist):
            self.app.display_info(
                "Populating openms_insight/js-component/dist from the pre-built "
                "js-component/dist."
            )
            os.makedirs(os.path.dirname(target_dist), exist_ok=True)
            shutil.copytree(source_dist, target_dist)

    def _require_prebuilt(self, target_dist):
        if not os.path.isdir(target_dist):
            raise RuntimeError(
                "No pre-built frontend found at 'openms_insight/js-component/dist' "
                "and the npm build was skipped. Provide the dist, or allow the hook "
                f"to run npm (unset {SKIP_ENV_VAR} and provide js-component sources)."
            )
