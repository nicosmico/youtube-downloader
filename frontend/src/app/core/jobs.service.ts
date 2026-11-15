import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, catchError, map, tap, throwError } from 'rxjs';
import { EventStreamService, eventData } from './event-stream.service';
import { Quality } from './preview.service';

export type AudioFormat = 'mp3' | 'm4a' | 'opus';

/** What to download: video takes a Quality, audio an AudioFormat; never both. */
export type DownloadOptions =
  { mode: 'video'; quality: Quality } | { mode: 'audio'; audioFormat: AudioFormat };

export type JobStatus =
  'queued' | 'downloading' | 'processing' | 'completed' | 'failed' | 'canceled' | 'interrupted';

/** A DownloadJob as the API sends it (camelCase). */
export interface Job {
  id: string;
  batchId: string | null;
  playlistIndex: number | null;
  url: string;
  title: string | null;
  mode: 'video' | 'audio';
  quality: Quality | null;
  audioFormat: AudioFormat | null;
  status: JobStatus;
  progressPercent: number;
  downloadedBytes: number | null;
  totalBytes: number | null;
  /** Bytes per second. */
  speed: number | null;
  /** Seconds. */
  eta: number | null;
  outputPath: string | null;
  error: string | null;
  attempt: number;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
}

export interface QueueCounts {
  active: number;
  queued: number;
}

interface JobPage {
  jobs: Job[];
  nextBefore: string | null;
}

/** A rejected enqueue: the API `code` (or `network`/`unknown`) and the Spanish server message. */
export class EnqueueError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

const REHYDRATE_LIMIT = 200;

/** Live list of jobs: REST for commands and rehydration, SSE (`job.updated`) for changes. */
@Injectable({ providedIn: 'root' })
export class JobsService {
  private readonly http = inject(HttpClient);
  private readonly stream = inject(EventStreamService);
  private connected = false;

  /** Newest first. */
  readonly jobs = signal<Job[]>([]);
  /** Jobs running and waiting, from `queue.updated` (also sent as a snapshot on connect). */
  readonly queue = signal<QueueCounts>({ active: 0, queued: 0 });

  /** Starts listening (idempotent). On every (re)connect the list is fetched again. */
  connect(): void {
    if (this.connected) {
      return;
    }
    this.connected = true;
    this.stream.on('open', () => this.refresh());
    this.stream.on('job.updated', (event) => this.upsert(eventData<Job>(event)));
    this.stream.on('queue.updated', (event) => this.queue.set(eventData<QueueCounts>(event)));
    this.stream.connect();
  }

  refresh(): void {
    this.http.get<JobPage>('/api/jobs', { params: { limit: REHYDRATE_LIMIT } }).subscribe({
      next: (page) => this.jobs.set(sortNewestFirst(page.jobs)),
      error: () => undefined,
    });
  }

  /** Enqueues one video; the new jobs show up in `jobs` right away. */
  enqueue(url: string, options: DownloadOptions, title: string | null): Observable<Job[]> {
    const body: Record<string, unknown> = { url, ...options };
    if (title) {
      body['title'] = title;
    }
    return this.http.post<{ batchId: string | null; jobs: Job[] }>('/api/jobs', body).pipe(
      tap((response) => response.jobs.forEach((job) => this.upsert(job))),
      map((response) => response.jobs),
      catchError((error: unknown) => throwError(() => toEnqueueError(error))),
    );
  }

  private upsert(job: Job): void {
    this.jobs.update((jobs) => {
      const rest = jobs.filter((j) => j.id !== job.id);
      return sortNewestFirst([...rest, job]);
    });
  }
}

function sortNewestFirst(jobs: Job[]): Job[] {
  return [...jobs].sort((a, b) =>
    a.createdAt < b.createdAt ? 1 : a.createdAt > b.createdAt ? -1 : 0,
  );
}

function toEnqueueError(error: unknown): EnqueueError {
  if (!(error instanceof HttpErrorResponse)) {
    return new EnqueueError('unknown', '');
  }
  if (error.status === 0) {
    return new EnqueueError('network', '');
  }
  const body = error.error as { code?: string; message?: string } | null;
  return new EnqueueError(body?.code ?? 'unknown', body?.message ?? '');
}
