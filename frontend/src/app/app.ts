import { Component, OnInit, inject, signal } from '@angular/core';
import { EngineService } from './core/engine.service';
import { JobsService } from './core/jobs.service';
import { Health, SystemService } from './core/system.service';
import { TEXTS } from './core/texts';
import { Downloads } from './downloads/downloads';
import { UrlPreview } from './preview/url-preview';

type ShutdownState = 'idle' | 'closing' | 'done' | 'failed';

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

  protected readonly texts = TEXTS;
  protected readonly health = signal<Health | null>(null);
  protected readonly unreachable = signal(false);
  protected readonly shutdownState = signal<ShutdownState>('idle');

  ngOnInit(): void {
    this.engineService.connect();
    this.jobsService.connect();
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

  protected shutdown(): void {
    this.shutdownState.set('closing');
    this.system.shutdown().subscribe({
      next: () => this.shutdownState.set('done'),
      error: () => this.shutdownState.set('failed'),
    });
  }
}
