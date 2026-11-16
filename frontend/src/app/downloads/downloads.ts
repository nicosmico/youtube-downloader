import { NgTemplateOutlet } from '@angular/common';
import { Component, computed, effect, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Job, JobsService, isInProgress } from '../core/jobs.service';
import { SystemService } from '../core/system.service';
import { TEXTS } from '../core/texts';
import { formatDuration } from '../preview/url-preview';
import { Dismissable } from '../ui/dismissable';
import { Icon } from '../ui/icon';
import { MenuKeys } from '../ui/menu-keys';

/** `1536` -> `1,5 KB`; binary units, one decimal from KB up. */
export function formatBytes(bytes: number): string {
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let value = Math.max(0, bytes);
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  const text = unit === 0 ? String(Math.round(value)) : value.toFixed(1).replace('.', ',');
  return `${text} ${units[unit]}`;
}

/** The output of a failed Attempt as the card shows it. */
interface Detail {
  attempt: number;
  state: 'loading' | 'ready' | 'error';
  lines: string[];
  message: string;
}

/** A Batch with the jobs of its entries, in playlist order. */
export interface BatchGroup {
  kind: 'batch';
  batchId: string;
  title: string;
  jobs: Job[];
  /** Entries chosen when it was enqueued. */
  total: number;
  completed: number;
  failed: number;
  running: number;
}

export type ListItem = { kind: 'job'; job: Job } | BatchGroup;

/**
 * Jobs of a Batch gather under one heading, at the place of their newest job; the rest stay
 * alone. The summary counts every known job of the Batch (`all`), whichever tab shows `jobs`.
 */
export function groupJobs(jobs: readonly Job[], all: readonly Job[] = jobs): ListItem[] {
  const items: ListItem[] = [];
  const batches = new Map<string, BatchGroup>();
  for (const job of jobs) {
    if (!job.batchId) {
      items.push({ kind: 'job', job });
      continue;
    }
    let group = batches.get(job.batchId);
    if (!group) {
      group = {
        kind: 'batch',
        batchId: job.batchId,
        title: job.batchTitle || TEXTS.downloads.untitledBatch,
        jobs: [],
        total: 0,
        completed: 0,
        failed: 0,
        running: 0,
      };
      batches.set(job.batchId, group);
      items.push(group);
    }
    group.jobs.push(job);
  }
  for (const group of batches.values()) {
    group.jobs.sort((a, b) => (a.playlistIndex ?? 0) - (b.playlistIndex ?? 0));
    const members = all.filter((j) => j.batchId === group.batchId);
    group.total = Math.max(group.jobs[0].batchEntryCount ?? 0, members.length);
    group.completed = members.filter((j) => j.status === 'completed').length;
    group.failed = members.filter((j) => j.status === 'failed').length;
    group.running = members.filter(
      (j) => j.status === 'downloading' || j.status === 'processing',
    ).length;
  }
  return items;
}

/** One card per DownloadJob, live through `JobsService`; a playlist groups its jobs. */
@Component({
  selector: 'app-downloads',
  imports: [NgTemplateOutlet, Icon, Dismissable, MenuKeys],
  templateUrl: './downloads.html',
})
export class Downloads {
  protected readonly jobsService = inject(JobsService);
  private readonly system = inject(SystemService);

  protected readonly texts = TEXTS;
  protected readonly tab = signal<'active' | 'history'>('active');
  /** Job whose "⋮" menu is open. */
  protected readonly menuFor = signal<string | null>(null);
  /** "En curso": queued, downloading and processing jobs. */
  protected readonly queueItems = computed(() =>
    groupJobs(this.jobsService.jobs().filter(isInProgress), this.jobsService.jobs()),
  );
  protected readonly activeCount = computed(
    () => this.jobsService.jobs().filter(isInProgress).length,
  );
  /** "Historial": the finished ones, newest first. */
  protected readonly historyItems = computed(() =>
    groupJobs(
      this.jobsService.jobs().filter((job) => !isInProgress(job)),
      this.jobsService.jobs(),
    ),
  );
  /** Label of the reveal button: the file manager of the server's platform. */
  protected readonly revealLabel = computed(() => {
    const labels = TEXTS.downloads.reveal;
    const platform = this.system.platform();
    return platform === 'darwin'
      ? labels.darwin
      : platform === 'win32'
        ? labels.win32
        : labels.other;
  });
  /** "Ver detalle" of failed jobs: open ones by job id, tied to the Attempt they belong to. */
  protected readonly details = signal<ReadonlyMap<string, Detail>>(new Map());
  /** Why showing the file of a job failed (the server's Spanish message). */
  protected readonly revealError = signal<{ jobId: string; text: string } | null>(null);
  /** Job whose cancellation awaits the user's confirmation (only running jobs ask). */
  protected readonly confirming = signal<string | null>(null);
  /** Jobs with a cancel or retry request in flight. */
  protected readonly busy = signal<ReadonlySet<string>>(new Set());
  protected readonly actionMessage = signal<string | null>(null);
  protected readonly folderMessage = signal<{ ok: boolean; text: string } | null>(null);

  private knownActive = new Set<string>();

  constructor() {
    // A job that just joined the Queue shows up in "En curso", wherever the user was looking.
    effect(() => {
      const ids = new Set(
        this.jobsService
          .jobs()
          .filter(isInProgress)
          .map((job) => job.id),
      );
      if ([...ids].some((id) => !this.knownActive.has(id))) {
        this.tab.set('active');
      }
      this.knownActive = ids;
    });
  }

  /** "3/10 completadas", plus the failed ones when there are any. */
  protected summary(group: BatchGroup): string {
    const texts = TEXTS.downloads;
    const parts = [`${group.completed}/${group.total} ${texts.batchCompleted}`];
    if (group.running > 0) {
      parts.push(`${group.running} ${texts.batchActive}`);
    }
    if (group.failed > 0) {
      parts.push(`${group.failed} ${texts.batchFailed}`);
    }
    return parts.join(' · ');
  }

  /** yt-dlp is still resolving the video: no byte received yet, so there is no real progress. */
  protected isPreparing(job: Job): boolean {
    return job.status === 'downloading' && job.downloadedBytes === null;
  }

  /** The one status line of a row: "Audio · MP3 · 45 % · quedan 0:12", "En cola", "Fallida". */
  protected statusLine(job: Job): string {
    const texts = TEXTS.downloads;
    const parts: string[] = [];
    switch (job.status) {
      case 'queued':
      case 'failed':
      case 'canceled':
      case 'interrupted':
        parts.push(texts.status[job.status]);
        break;
      case 'downloading':
        if (this.isPreparing(job)) {
          parts.push(texts.preparing);
          break;
        }
        parts.push(this.options(job), `${this.percent(job)} %`);
        if (job.eta !== null) {
          parts.push(`${texts.eta} ${formatDuration(job.eta)}`);
        }
        break;
      default:
        parts.push(this.options(job), texts.status[job.status] ?? texts.unknownStatus);
    }
    if (job.attempt > 1) {
      parts.push(`${texts.attempt} ${job.attempt}`);
    }
    return parts.join(' · ');
  }

  /** Bytes and speed, as the tooltip of the progress bar. */
  protected progressDetail(job: Job): string {
    return [this.bytes(job), this.speed(job)].filter(Boolean).join(' · ');
  }

  protected title(job: Job): string {
    return job.title || TEXTS.downloads.untitled;
  }

  /** What was requested: "Video · 720p" or "Audio · MP3". */
  protected options(job: Job): string {
    const texts = TEXTS.downloads;
    if (job.mode === 'audio') {
      const format = job.audioFormat
        ? (texts.audioFormats[job.audioFormat] ?? job.audioFormat)
        : '';
      return format ? `${texts.modeAudio} · ${format}` : texts.modeAudio;
    }
    const quality = job.quality === 'best' ? texts.qualityBest : job.quality;
    return quality ? `${texts.modeVideo} · ${quality}` : texts.modeVideo;
  }

  /** Running jobs (they can be cancelled). */
  protected showsProgress(job: Job): boolean {
    return job.status === 'downloading' || job.status === 'processing';
  }

  /** The bar and numbers appear once there is real progress. */
  protected showsBar(job: Job): boolean {
    return this.showsProgress(job) && !this.isPreparing(job);
  }

  protected percent(job: Job): number {
    return job.status === 'processing' ? 100 : Math.round(job.progressPercent);
  }

  protected bytes(job: Job): string | null {
    if (job.downloadedBytes === null) {
      return null;
    }
    const done = formatBytes(job.downloadedBytes);
    return job.totalBytes ? `${done} / ${formatBytes(job.totalBytes)}` : done;
  }

  protected speed(job: Job): string | null {
    return job.status === 'downloading' && job.speed ? `${formatBytes(job.speed)}/s` : null;
  }

  protected canCancel(job: Job): boolean {
    return job.status === 'queued' || this.showsProgress(job);
  }

  protected canRetry(job: Job): boolean {
    return job.status === 'failed' || job.status === 'canceled' || job.status === 'interrupted';
  }

  protected hasMenu(job: Job): boolean {
    return job.status === 'completed' || job.status === 'failed' || this.canRemove(job);
  }

  protected closeMenu(reason: 'escape' | 'outside', jobId: string, trigger: HTMLElement): void {
    if (this.menuFor() !== jobId) {
      return;
    }
    this.menuFor.set(null);
    if (reason === 'escape') {
      trigger.focus();
    }
  }

  protected toggleMenu(job: Job): void {
    this.menuFor.set(this.menuFor() === job.id ? null : job.id);
  }

  protected canRemove(job: Job): boolean {
    return !isInProgress(job);
  }

  protected isBusy(job: Job): boolean {
    return this.busy().has(job.id);
  }

  /** A queued job is cancelled at once; a running one asks first (its progress is lost). */
  protected cancel(job: Job): void {
    if (this.showsProgress(job)) {
      this.confirming.set(job.id);
      return;
    }
    this.send(job, this.jobsService.cancel(job.id));
  }

  protected confirmCancel(job: Job): void {
    this.confirming.set(null);
    this.send(job, this.jobsService.cancel(job.id));
  }

  protected keepDownloading(): void {
    this.confirming.set(null);
  }

  protected detail(job: Job): Detail | null {
    const detail = this.details().get(job.id);
    return detail && detail.attempt === job.attempt ? detail : null;
  }

  /** Opens or closes the yt-dlp output of the failed Attempt (fetched when opened). */
  protected toggleDetail(job: Job): void {
    this.menuFor.set(null);
    if (this.detail(job)) {
      this.setDetail(job.id, null);
      return;
    }
    this.setDetail(job.id, { attempt: job.attempt, state: 'loading', lines: [], message: '' });
    this.jobsService.output(job.id).subscribe({
      next: (output) =>
        this.setDetail(job.id, {
          attempt: job.attempt,
          state: 'ready',
          lines: output.lines,
          message: '',
        }),
      error: (error: unknown) => {
        const unavailable = error instanceof HttpErrorResponse && error.status === 404;
        this.setDetail(job.id, {
          attempt: job.attempt,
          state: 'error',
          lines: [],
          message: unavailable ? TEXTS.downloads.detailUnavailable : TEXTS.downloads.detailFailed,
        });
      },
    });
  }

  private setDetail(jobId: string, detail: Detail | null): void {
    this.details.update((current) => {
      const next = new Map(current);
      if (detail) {
        next.set(jobId, detail);
      } else {
        next.delete(jobId);
      }
      return next;
    });
  }

  protected retry(job: Job): void {
    this.setDetail(job.id, null);
    this.send(job, this.jobsService.retry(job.id));
  }

  protected remove(job: Job): void {
    this.menuFor.set(null);
    this.setDetail(job.id, null);
    this.send(job, this.jobsService.remove(job.id));
  }

  protected reveal(job: Job): void {
    this.revealError.set(null);
    this.busy.update((ids) => new Set(ids).add(job.id));
    const done = () =>
      this.busy.update((ids) => {
        const rest = new Set(ids);
        rest.delete(job.id);
        return rest;
      });
    this.jobsService.reveal(job.id).subscribe({
      next: done,
      error: (error: { message?: string }) => {
        done();
        this.revealError.set({
          jobId: job.id,
          text: error.message || TEXTS.downloads.revealFailed,
        });
      },
    });
  }

  private send(job: Job, request: Observable<unknown>): void {
    this.actionMessage.set(null);
    this.busy.update((ids) => new Set(ids).add(job.id));
    const done = () =>
      this.busy.update((ids) => {
        const rest = new Set(ids);
        rest.delete(job.id);
        return rest;
      });
    request.subscribe({
      next: done,
      error: () => {
        done();
        this.actionMessage.set(TEXTS.downloads.actionFailed);
      },
    });
  }

  protected openFolder(): void {
    this.menuFor.set(null);
    this.folderMessage.set(null);
    this.system.openDownloads().subscribe({
      next: () => this.folderMessage.set({ ok: true, text: TEXTS.downloads.folderOpened }),
      error: (error: unknown) => {
        const message = error instanceof HttpErrorResponse ? error.error?.message : null;
        this.folderMessage.set({ ok: false, text: message || TEXTS.downloads.openFailed });
      },
    });
  }
}
