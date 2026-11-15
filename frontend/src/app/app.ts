import { Component, OnInit, inject, signal } from '@angular/core';
import { EngineService } from './core/engine.service';
import { EventStreamService, eventData } from './core/event-stream.service';
import { JobsService } from './core/jobs.service';
import { PresetsService } from './core/presets.service';
import { Health, SystemService } from './core/system.service';
import { TEXTS } from './core/texts';
import { Downloads } from './downloads/downloads';
import { UrlPreview } from './preview/url-preview';

/** `closedIdle`: the server closed itself after 10 minutes without use (Idle Shutdown). */
type ShutdownState = 'idle' | 'closing' | 'done' | 'closedIdle' | 'failed';

@Component({
  selector: 'app-root',
  imports: [UrlPreview, Downloads],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  private readonly system = inject(SystemService);
  protected readonly engineService = inject(EngineService);
  private readonly jobsService = inject(JobsService);
  private readonly stream = inject(EventStreamService);
  private readonly presetsService = inject(PresetsService);

  protected readonly texts = TEXTS;
  protected readonly health = signal<Health | null>(null);
  protected readonly unreachable = signal(false);
  protected readonly shutdownState = signal<ShutdownState>('idle');

  ngOnInit(): void {
    this.engineService.connect();
    this.jobsService.connect();
    this.stream.on('shutdown', (event) => this.serverClosed(eventData<{ reason: string }>(event)));
    this.presetsService.load();
    this.system.health().subscribe({
      next: (health) => this.health.set(health),
      error: () => this.unreachable.set(true),
    });
  }

  protected engineLabel(): string {
    const status = this.engineService.engine()?.status;
    if (status === undefined) {
      return TEXTS.engine.loading;
    }
    return TEXTS.engine.status[status] ?? TEXTS.engine.unknownStatus;
  }

  protected versionList(): { name: string; value: string }[] {
    const versions = this.engineService.engine()?.versions;
    if (!versions) {
      return [];
    }
    return (Object.keys(TEXTS.engine.versions) as (keyof typeof TEXTS.engine.versions)[])
      .filter((key) => versions[key])
      .map((key) => ({ name: TEXTS.engine.versions[key], value: versions[key] as string }));
  }

  /** The server announced its end: show the closed screen and stop reconnecting to it. */
  private serverClosed(message: { reason: string }): void {
    this.shutdownState.set(message.reason === 'idle' ? 'closedIdle' : 'done');
    this.stream.close();
  }

  protected shutdown(): void {
    this.shutdownState.set('closing');
    this.system.shutdown().subscribe({
      next: () => this.shutdownState.set('done'),
      error: () => this.shutdownState.set('failed'),
    });
  }
}
