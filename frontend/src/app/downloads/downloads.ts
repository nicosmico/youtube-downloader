import { Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { Job, JobsService } from '../core/jobs.service';
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

/** One card per DownloadJob, live through `JobsService`. */
@Component({
  selector: 'app-downloads',
  templateUrl: './downloads.html',
  styleUrl: './downloads.css',
})
export class Downloads {
  protected readonly jobsService = inject(JobsService);
  private readonly system = inject(SystemService);

  protected readonly texts = TEXTS;
  protected readonly folderMessage = signal<{ ok: boolean; text: string } | null>(null);

  protected statusLabel(job: Job): string {
    return TEXTS.downloads.status[job.status] ?? TEXTS.downloads.unknownStatus;
  }

  protected title(job: Job): string {
    return job.title || TEXTS.downloads.untitled;
  }

  protected showsProgress(job: Job): boolean {
    return job.status === 'downloading' || job.status === 'processing';
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
