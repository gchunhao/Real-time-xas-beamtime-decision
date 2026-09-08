interface XasDesktopApi {
  select_folder(): Promise<string | null>;
  select_files(): Promise<string[]>;
}

declare global {
  interface Window {
    pywebview?: { api?: XasDesktopApi };
  }
}

function api(): XasDesktopApi {
  const bridge = window.pywebview?.api;
  if (!bridge) {
    throw new Error("Native file selection is available in the installed Windows desktop application.");
  }
  return bridge;
}

export async function selectFolder(): Promise<string | null> {
  return api().select_folder();
}

export async function selectFiles(): Promise<string[]> {
  return api().select_files();
}

export function hasDesktopBridge(): boolean {
  return Boolean(window.pywebview?.api);
}

export {};
