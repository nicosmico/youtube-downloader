import { DOCUMENT } from '@angular/common';
import { Injectable, computed, inject, signal } from '@angular/core';

export type ThemePreference = 'system' | 'light' | 'dark';

export const THEME_STORAGE_KEY = 'theme';
const PREFERENCES: readonly ThemePreference[] = ['system', 'light', 'dark'];

/**
 * Light/dark theme: `system` (default) follows `prefers-color-scheme`. The preference is kept in
 * `localStorage`; index.html applies it before the first paint, this service keeps it in sync.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly query = this.document.defaultView?.matchMedia?.('(prefers-color-scheme: dark)');

  readonly preference = signal<ThemePreference>(this.stored());
  private readonly systemDark = signal(this.query?.matches ?? false);
  /** What is actually shown. */
  readonly effective = computed<'light' | 'dark'>(() => {
    const preference = this.preference();
    return preference === 'system' ? (this.systemDark() ? 'dark' : 'light') : preference;
  });

  constructor() {
    this.query?.addEventListener('change', (event) => {
      this.systemDark.set(event.matches);
      this.apply();
    });
    this.apply();
  }

  set(preference: ThemePreference): void {
    this.preference.set(preference);
    try {
      this.document.defaultView?.localStorage.setItem(THEME_STORAGE_KEY, preference);
    } catch {
      // storage blocked: the theme still applies until the tab closes
    }
    this.apply();
  }

  /** The theme button of the top bar: flips what is shown now and remembers the choice. */
  toggle(): void {
    this.set(this.effective() === 'dark' ? 'light' : 'dark');
  }

  private apply(): void {
    this.document.documentElement.classList.toggle('dark', this.effective() === 'dark');
  }

  private stored(): ThemePreference {
    try {
      const value = this.document.defaultView?.localStorage.getItem(THEME_STORAGE_KEY);
      return PREFERENCES.includes(value as ThemePreference) ? (value as ThemePreference) : 'system';
    } catch {
      return 'system';
    }
  }
}
