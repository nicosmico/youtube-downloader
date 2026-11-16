import { Component, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import { Health } from '../core/system.service';
import { TEXTS } from '../core/texts';
import { ThemePreference, ThemeService } from '../core/theme.service';
import { Dismissable } from '../ui/dismissable';
import { Icon } from '../ui/icon';
import { MenuKeys } from '../ui/menu-keys';
import { EngineChip } from './engine-chip';

/** Brand on the left; Engine chip, theme button and gear menu on the right. No text field. */
@Component({
  selector: 'app-top-bar',
  imports: [EngineChip, Icon, Dismissable, MenuKeys],
  templateUrl: './top-bar.html',
})
export class TopBar {
  protected readonly theme = inject(ThemeService);
  readonly health = input<Health | null>(null);
  readonly unreachable = input(false);
  readonly closing = input(false);
  readonly logsRequested = output<void>();
  readonly shutdownRequested = output<void>();

  protected readonly texts = TEXTS;
  protected readonly menuOpen = signal(false);
  private readonly gear = viewChild<ElementRef<HTMLButtonElement>>('gear');
  protected readonly themes: { value: ThemePreference; label: string }[] = [
    { value: 'system', label: TEXTS.menu.themeSystem },
    { value: 'light', label: TEXTS.menu.themeLight },
    { value: 'dark', label: TEXTS.menu.themeDark },
  ];

  protected closeMenu(reason: 'escape' | 'outside', trigger: HTMLElement): void {
    if (!this.menuOpen()) {
      return;
    }
    this.menuOpen.set(false);
    if (reason === 'escape') {
      trigger.focus();
    }
  }

  /** Gives the focus back to the gear (after the Registros panel closes). */
  focusSettings(): void {
    this.gear()?.nativeElement.focus();
  }

  protected openLogs(): void {
    this.menuOpen.set(false);
    this.logsRequested.emit();
  }

  protected shutdown(): void {
    this.menuOpen.set(false);
    this.shutdownRequested.emit();
  }
}
