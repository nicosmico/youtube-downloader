import { Component, OnInit, inject, signal } from '@angular/core';
import { SystemService } from './core/system.service';
import { Health } from './core/system.service';
import { TEXTS } from './core/texts';

type ShutdownState = 'idle' | 'closing' | 'done' | 'failed';

@Component({
  selector: 'app-root',
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App implements OnInit {
  private readonly system = inject(SystemService);

  protected readonly texts = TEXTS;
  protected readonly health = signal<Health | null>(null);
  protected readonly unreachable = signal(false);
  protected readonly shutdownState = signal<ShutdownState>('idle');

  ngOnInit(): void {
    this.system.health().subscribe({
      next: (health) => this.health.set(health),
      error: () => this.unreachable.set(true),
    });
  }

  protected engineLabel(): string {
    const status = this.health()?.engine.status;
    if (status === undefined) {
      return TEXTS.engine.loading;
    }
    return TEXTS.engine.status[status] ?? TEXTS.engine.unknownStatus;
  }

  protected shutdown(): void {
    this.shutdownState.set('closing');
    this.system.shutdown().subscribe({
      next: () => this.shutdownState.set('done'),
      error: () => this.shutdownState.set('failed'),
    });
  }
}
