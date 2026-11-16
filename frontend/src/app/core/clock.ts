import { InjectionToken } from '@angular/core';

/** The current time; replaced by a fixed one in specs. */
export const NOW = new InjectionToken<() => Date>('NOW', {
  providedIn: 'root',
  factory: () => () => new Date(),
});
