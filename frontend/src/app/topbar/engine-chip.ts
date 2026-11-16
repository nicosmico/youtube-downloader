import { Component, computed, inject, input, signal } from '@angular/core';
import { EngineService } from '../core/engine.service';
import { Health } from '../core/system.service';
import { TEXTS } from '../core/texts';
import { Dismissable } from '../ui/dismissable';

type Tone = 'ok' | 'warn' | 'error' | 'idle';

/** Dot-and-label chip with the Engine state; it opens a popover with versions and actions. */
@Component({
  selector: 'app-engine-chip',
  imports: [Dismissable],
  templateUrl: './engine-chip.html',
})
export class EngineChip {
  protected readonly engineService = inject(EngineService);
  readonly health = input<Health | null>(null);
  readonly unreachable = input(false);

  protected readonly texts = TEXTS.engine;
  protected readonly healthTexts = TEXTS.health;
  protected readonly open = signal(false);

  protected readonly state = computed<{ tone: Tone; label: string }>(() => {
    const chip = TEXTS.engine.chip;
    const engine = this.engineService.engine();
    if (this.unreachable()) {
      return { tone: 'error', label: chip.unreachable };
    }
    if (!engine) {
      return { tone: 'idle', label: chip.checking };
    }
    switch (engine.status) {
      case 'ready':
        if (engine.updating) {
          return { tone: 'warn', label: chip.updating };
        }
        return engine.updatePending
          ? { tone: 'warn', label: chip.updatePending }
          : { tone: 'ok', label: chip.ready };
      case 'installing':
        return { tone: 'warn', label: chip.installing };
      case 'missing':
        return { tone: 'warn', label: chip.missing };
      default:
        return { tone: 'error', label: chip.error };
    }
  });

  protected readonly versions = computed(() => {
    const versions = this.engineService.engine()?.versions;
    if (!versions) {
      return [];
    }
    return (Object.keys(TEXTS.engine.versions) as (keyof typeof TEXTS.engine.versions)[])
      .filter((key) => versions[key])
      .map((key) => ({ name: TEXTS.engine.versions[key], value: versions[key] as string }));
  });

  protected dotClass(tone: Tone): string {
    return {
      ok: 'bg-green-600 dark:bg-green-500',
      warn: 'bg-amber-500',
      error: 'bg-accent',
      idle: 'bg-muted',
    }[tone];
  }

  protected close(reason: 'escape' | 'outside', trigger: HTMLElement): void {
    if (!this.open()) {
      return;
    }
    this.open.set(false);
    if (reason === 'escape') {
      trigger.focus();
    }
  }
}
