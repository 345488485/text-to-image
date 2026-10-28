export type ThemeMode = 'auto' | 'light' | 'dark';
export type EffectiveTheme = 'light' | 'dark';
export function resolveTheme(mode: ThemeMode, now = new Date()): EffectiveTheme {
  return mode === 'auto' ? (now.getHours() >= 7 && now.getHours() < 19 ? 'light' : 'dark') : mode;
}
export interface ThemeHost {
  now(): Date;
  storage: { getItem(key: string): string | null | undefined; setItem(key: string,value: string): void };
  apply(theme: EffectiveTheme, mode: ThemeMode): void;
  on(event: string, handler: () => void): void;
  off(event: string, handler: () => void): void;
  schedule(handler: () => void, delay: number): unknown;
  clear(timer: unknown): void;
}
export function startTheme(host: ThemeHost) {
  let saved: string | null | undefined;
  try { saved = host.storage.getItem('moss-theme'); } catch { /* Browser storage can be unavailable. */ }
  let mode: ThemeMode = saved === 'light' || saved === 'dark' ? saved : 'auto';
  let timer: unknown;
  const update = () => {
    host.clear(timer);
    const now = host.now();
    host.apply(resolveTheme(mode, now), mode);
    if (mode === 'auto') {
      const next = new Date(now);
      if (now.getHours() < 7) next.setHours(7,0,0,0);
      else if (now.getHours() < 19) next.setHours(19,0,0,0);
      else {next.setDate(next.getDate()+1);next.setHours(7,0,0,0);}
      timer = host.schedule(update, Math.max(1, next.getTime()-now.getTime()));
    }
  };
  host.on('focus', update);
  host.on('visibilitychange', update);
  update();
  return {
    get mode() { return mode; },
    setMode(value: ThemeMode) {
      mode = value;
      try { host.storage.setItem('moss-theme', value); } catch { /* Keep in-memory selection. */ }
      update();
    },
    stop() { host.clear(timer);host.off('focus',update);host.off('visibilitychange',update); },
  };
}
