import { Component, computed, inject, signal } from '@angular/core';
import { NgTemplateOutlet } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Job, JobsService, isInProgress } from '../core/jobs.service';
import { SystemService } from '../core/system.service';
import { TEXTS } from '../core/texts';
import { formatDuration } from '../preview/url-preview';

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

/** Jobs of a Batch gather under one heading, at the place of their newest job; the rest stay alone. */
export function groupJobs(jobs: readonly Job[]): ListItem[] {
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
    group.total = Math.max(group.jobs[0].batchEntryCount ?? 0, group.jobs.length);
    group.completed = group.jobs.filter((j) => j.status === 'completed').length;
    group.failed = group.jobs.filter((j) => j.status === 'failed').length;
    group.running = group.jobs.filter(
      (j) => j.status === 'downloading' || j.status === 'processing',
    ).length;
  }
  return items;
}

/** One card per DownloadJob, live through `JobsService`; a playlist groups its jobs. */
@Component({
  selector: 'app-downloads',
  imports: [NgTemplateOutlet],
  templateUrl: './downloads.html',
  styleUrl: './downloads.css',
})
export class Downloads {
  protected readonly jobsService = inject(JobsService);
  private readonly system = inject(SystemService);

  protected readonly texts = TEXTS;
  /** "En curso": queued, downloading and processing jobs. */
  protected readonly queueItems = computed(() =>
    groupJobs(this.jobsService.jobs().filter(isInProgress)),
  );
  /** "Historial": the finished ones, newest first. */
  protected readonly historyItems = computed(() =>
    groupJobs(this.jobsService.jobs().filter((job) => !isInProgress(job))),
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
  /** Why showing the file of a job failed (the server's Spanish message). */
  protected readonly revealError = signal<{ jobId: string; text: string } | null>(null);
  /** Job whose cancellation awaits the user's confirmation (only running jobs ask). */
  protected readonly confirming = signal<string | null>(null);
  /** Jobs with a cancel or retry request in flight. */
  protected readonly busy = signal<ReadonlySet<string>>(new Set());
  protected readonly actionMessage = signal<string | null>(null);
  protected readonly folderMessage = signal<{ ok: boolean; text: string } | null>(null);

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

  protected statusLabel(job: Job): string {
    if (this.isPreparing(job)) {
      return TEXTS.downloads.preparing;
    }
    return TEXTS.downloads.status[job.status] ?? TEXTS.downloads.unknownStatus;
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

  protected eta(job: Job): string | null {
    return job.status === 'downloading' && job.eta !== null ? formatDuration(job.eta) : null;
  }

  protected canCancel(job: Job): boolean {
    return job.status === 'queued' || this.showsProgress(job);
  }

  protected canRetry(job: Job): boolean {
    return job.status === 'failed' || job.status === 'canceled' || job.status === 'interrupted';
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

  protected retry(job: Job): void {
    this.send(job, this.jobsService.retry(job.id));
  }

  protected remove(job: Job): void {
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
