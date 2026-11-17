import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, inject, input, output, signal, viewChild } from '@angular/core';
import { AppUpdate, Health, SystemService } from '../core/system.service';
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
  private readonly system = inject(SystemService);
  protected readonly downloadDir = this.system.downloadDir;
  /** The native folder dialog is open (it blocks on the server until the user answers). */
  protected readonly choosing = signal(false);
  protected readonly dirError = signal<string | null>(null);
  readonly health = input<Health | null>(null);
  readonly update = input<AppUpdate | null>(null);
  readonly unreachable = input(false);
  readonly closing = input(false);
  readonly logsRequested = output<void>();
  readonly shutdownRequested = output<void>();

  protected readonly texts = TEXTS;
  protected readonly newVersion = TEXTS.menu.newVersion;
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

  protected chooseDir(): void {
    this.dirError.set(null);
    this.choosing.set(true);
    this.system.chooseDownloadDir().subscribe({
      next: () => this.choosing.set(false),
      error: (error: unknown) => {
        this.choosing.set(false);
        this.dirError.set(serverMessage(error) ?? TEXTS.downloadDir.changeFailed);
      },
    });
  }

  protected resetDir(): void {
    this.dirError.set(null);
    this.system.resetDownloadDir().subscribe({
      error: (error: unknown) =>
        this.dirError.set(serverMessage(error) ?? TEXTS.downloadDir.resetFailed),
    });
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

function serverMessage(error: unknown): string | null {
  return error instanceof HttpErrorResponse ? (error.error?.message ?? null) : null;
}
