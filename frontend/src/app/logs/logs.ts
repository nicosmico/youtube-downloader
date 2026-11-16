import { Component, computed, inject, signal } from '@angular/core';
import { ERROR_LOG_CLOCK, ErrorLogService } from '../core/error-log.service';
import { LogsService } from '../core/logs.service';
import { TEXTS } from '../core/texts';

/** "Registros": the server log and this tab's errors. Collapsed; reads only on demand. */
@Component({
  selector: 'app-logs',
  templateUrl: './logs.html',
  styleUrl: './logs.css',
})
export class Logs {
  private readonly logs = inject(LogsService);
  private readonly clock = inject(ERROR_LOG_CLOCK);
  protected readonly errorLog = inject(ErrorLogService);

  protected readonly texts = TEXTS.logs;
  protected readonly open = signal(false);
  protected readonly loading = signal(false);
  protected readonly loadFailed = signal(false);
  protected readonly includeRequests = signal(false);
  protected readonly serverLines = signal<string[]>([]);
  protected readonly message = signal<{ ok: boolean; text: string } | null>(null);
  protected readonly frontendText = computed(() =>
    this.errorLog
      .entries()
      .map((e) => `${e.at} [${e.kind}] ${e.message}`)
      .join('\n'),
  );
  /** Whether the lines on screen were read with requests (what the report must say). */
  private loadedWithRequests = false;

  protected toggle(): void {
    this.open.update((value) => !value);
    if (this.open()) {
      this.refresh();
    }
  }

  protected toggleRequests(checked: boolean): void {
    this.includeRequests.set(checked);
    this.refresh();
  }

  protected refresh(): void {
    const withRequests = this.includeRequests();
    this.loading.set(true);
    this.loadFailed.set(false);
    this.message.set(null);
    this.logs.fetch(withRequests).subscribe({
      next: (lines) => {
        this.serverLines.set(lines);
        this.loadedWithRequests = withRequests;
        this.loading.set(false);
      },
      error: () => {
        this.loadFailed.set(true);
        this.loading.set(false);
      },
    });
  }

  protected async copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(this.report());
      this.message.set({ ok: true, text: this.texts.copied });
    } catch {
      this.message.set({ ok: false, text: this.texts.copyFailed });
    }
  }

  protected download(): void {
    const blob = new Blob([this.report()], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = this.texts.fileName;
    link.click();
    URL.revokeObjectURL(url);
  }

  private report(): string {
    return this.logs.report(
      this.serverLines(),
      this.errorLog.entries(),
      this.loadedWithRequests,
      this.clock(),
    );
  }
}
