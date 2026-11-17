import { Component, OnInit, inject, signal, viewChild } from '@angular/core';
import { EngineService } from './core/engine.service';
import { EventStreamService, eventData } from './core/event-stream.service';
import { JobsService } from './core/jobs.service';
import { AppUpdate, Health, SystemService } from './core/system.service';
import { TEXTS } from './core/texts';
import { Downloads } from './downloads/downloads';
import { Logs } from './logs/logs';
import { UrlPreview } from './preview/url-preview';
import { TopBar } from './topbar/top-bar';
import { Icon } from './ui/icon';

/** `closedIdle`: the server closed itself (Idle Shutdown: no tab and nothing to do). */
type ShutdownState = 'idle' | 'closing' | 'done' | 'closedIdle' | 'failed';

@Component({
  selector: 'app-root',
  imports: [UrlPreview, Downloads, Logs, TopBar, Icon],
  templateUrl: './app.html',
})
export class App implements OnInit {
  private readonly system = inject(SystemService);
  private readonly engineService = inject(EngineService);
  private readonly jobsService = inject(JobsService);
  private readonly stream = inject(EventStreamService);
  private readonly topBar = viewChild(TopBar);

  protected readonly texts = TEXTS;
  protected readonly health = signal<Health | null>(null);
  protected readonly update = this.system.update;
  protected readonly unreachable = signal(false);
  protected readonly shutdownState = signal<ShutdownState>('idle');
  protected readonly logsOpen = signal(false);

  ngOnInit(): void {
    this.engineService.connect();
    this.jobsService.connect();
    this.system.connectSettings();
    this.stream.on('app.update', (event) => this.system.update.set(eventData<AppUpdate>(event)));
    this.stream.on('shutdown', (event) => this.serverClosed(eventData<{ reason: string }>(event)));
    this.system.health().subscribe({
      next: (health) => this.health.set(health),
      error: () => this.unreachable.set(true),
    });
  }

  protected closeLogs(): void {
    this.logsOpen.set(false);
    this.topBar()?.focusSettings();
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
