/**
 * The USI button: copies the Universal Spectrum Identifier of the shown
 * spectrum. The component's `usi` is a USI in which `{identifier}`
 * placeholders stand for values of the shared state.
 */

import { ICONS, type PlotTool } from "./plotTools";

const PLACEHOLDER = /\{([^{}]+)\}/g;

/** A state value as it reads in a USI, or undefined when it has none. */
function part(value: unknown): string | undefined {
  if (typeof value === "number") {
    return Number.isFinite(value) ? String(value) : undefined;
  }
  if (typeof value === "string") {
    return value.length > 0 ? value : undefined;
  }
  return undefined;
}

/** `template` with its placeholders filled from `state`; null while one has no value. */
export function fillUsi(
  template: string | undefined,
  state: Record<string, unknown>,
): string | null {
  if (!template) return null;
  let missing = false;
  const usi = template.replace(PLACEHOLDER, (_, name: string) => {
    const value = part(state[name]);
    if (value === undefined) missing = true;
    return value ?? "";
  });
  return missing ? null : usi;
}

/** Writes `text` to the clipboard, with a fallback where the Clipboard API is refused. */
export async function copyText(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch {
    // Not allowed in this frame: fall back to a selection copy
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.opacity = "0";
  document.body.appendChild(area);
  area.select();
  let ok = false;
  try {
    ok = document.execCommand("copy");
  } catch {
    ok = false;
  }
  area.remove();
  return ok;
}

/** The toolbar button, while the USI is complete. */
export function usiTool(
  usi: string,
  copied: boolean | null,
  copy: () => void,
): PlotTool {
  const outcome =
    copied === true
      ? "copied: "
      : copied === false
        ? "could not copy: "
        : "copy ";
  return {
    id: "usi",
    group: "export",
    icon: copied === true ? ICONS.check : ICONS.copy,
    label: "Copy USI",
    short: "USI",
    help: `${outcome}${usi}`,
    active: copied === true,
    run: copy,
  };
}
