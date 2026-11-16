import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
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
/** yt-dlp output (stdout and stderr, no progress lines) of one Attempt. */
export interface JobOutput {
  attempt: number;
  lines: string[];
}

export interface Job {
  id: string;
  batchId: string | null;
  /** Title and size of the Batch the job belongs to (null for a single video). */
  batchTitle: string | null;
  batchEntryCount: number | null;
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

/** An Entry chosen from a playlist preview. */
export interface EnqueueEntry {
  id: string;
  url: string;
  index: number;
  title: string;
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

/** Jobs the Queue is working on or has waiting; every other status is the History. */
export const IN_PROGRESS_STATUSES: readonly JobStatus[] = ['queued', 'downloading', 'processing'];
const HISTORY_STATUSES = 'completed,failed,canceled,interrupted';

export function isInProgress(job: Job): boolean {
  return IN_PROGRESS_STATUSES.includes(job.status);
}

const QUEUE_LIMIT = 200;
const HISTORY_PAGE = 50;

/** Live list of jobs: REST for commands and rehydration, SSE (`job.updated`) for changes. */
@Injectable({ providedIn: 'root' })
export class JobsService {
  private readonly http = inject(HttpClient);
  private readonly stream = inject(EventStreamService);
  private connected = false;

  /** Newest first. */
  readonly jobs = signal<Job[]>([]);
  /** `before` cursor of the next page of the History; null when it is all loaded. */
  private readonly historyCursor = signal<string | null>(null);
  readonly hasMoreHistory = computed(() => this.historyCursor() !== null);
  readonly loadingMore = signal(false);
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
    this.stream.on('job.removed', (event) => this.drop(eventData<{ id: string }>(event).id));
    this.stream.on('queue.updated', (event) => this.queue.set(eventData<QueueCounts>(event)));
    this.stream.connect();
  }

  /**
   * Fetches the Queue (everything unfinished) and the first page of the History again. The
   * pages of the History loaded with `loadMore` are dropped: the list starts over.
   */
  refresh(): void {
    this.http
      .get<JobPage>('/api/jobs', {
        params: { status: IN_PROGRESS_STATUSES.join(','), limit: QUEUE_LIMIT },
      })
      .subscribe({
        next: (page) => this.replace(page.jobs, isInProgress),
        error: () => undefined,
      });
    this.http
      .get<JobPage>('/api/jobs', { params: { status: HISTORY_STATUSES, limit: HISTORY_PAGE } })
      .subscribe({
        next: (page) => {
          this.replace(page.jobs, (job) => !isInProgress(job));
          this.historyCursor.set(page.nextBefore);
        },
        error: () => undefined,
      });
  }

  /** The next (older) page of the History. */
  loadMore(): void {
    const before = this.historyCursor();
    if (before === null || this.loadingMore()) {
      return;
    }
    this.loadingMore.set(true);
    this.http
      .get<JobPage>('/api/jobs', {
        params: { status: HISTORY_STATUSES, limit: HISTORY_PAGE, before },
      })
      .subscribe({
        next: (page) => {
          page.jobs.forEach((job) => this.upsert(job));
          this.historyCursor.set(page.nextBefore);
          this.loadingMore.set(false);
        },
        error: () => this.loadingMore.set(false),
      });
  }

  /** Takes a finished job out of the History. The downloaded file stays on disk. */
  remove(jobId: string): Observable<unknown> {
    return this.http.delete(`/api/jobs/${encodeURIComponent(jobId)}`).pipe(
      tap(() => this.drop(jobId)),
      catchError((error: unknown) => this.failed(error)),
    );
  }

  /** The last yt-dlp output of the failed Attempt ("Ver detalle"); an error when there is none. */
  output(jobId: string): Observable<JobOutput> {
    return this.http.get<JobOutput>(`/api/jobs/${encodeURIComponent(jobId)}/output`);
  }

  /** Shows the file of a completed job in Finder/Explorer (host action). */
  reveal(jobId: string): Observable<unknown> {
    return this.http
      .post(`/api/jobs/${encodeURIComponent(jobId)}/reveal`, {})
      .pipe(catchError((error: unknown) => throwError(() => toEnqueueError(error))));
  }

  /**
   * Enqueues one video, or a playlist when `entries` is given (one job per entry). The new jobs
   * show up in `jobs` right away.
   */
  enqueue(
    url: string,
    options: DownloadOptions,
    title: string | null,
    entries?: EnqueueEntry[],
  ): Observable<Job[]> {
    const body: Record<string, unknown> = { url, ...options };
    if (title) {
      body['title'] = title;
    }
    if (entries) {
      body['entries'] = entries;
    }
    return this.http.post<{ batchId: string | null; jobs: Job[] }>('/api/jobs', body).pipe(
      tap((response) => response.jobs.forEach((job) => this.adopt(job))),
      map((response) => response.jobs),
      catchError((error: unknown) => throwError(() => toEnqueueError(error))),
    );
  }

  /** Cancels a queued or running job. Resolves once it has ended (a running one is stopped). */
  cancel(jobId: string): Observable<Job> {
    return this.command(jobId, 'cancel');
  }

  /** A new Attempt of a failed, canceled or interrupted job, at the end of the queue. */
  retry(jobId: string): Observable<Job> {
    return this.command(jobId, 'retry');
  }

  private command(jobId: string, action: 'cancel' | 'retry'): Observable<Job> {
    return this.http.post<Job>(`/api/jobs/${encodeURIComponent(jobId)}/${action}`, {}).pipe(
      tap((job) => (action === 'retry' ? this.adopt(job) : this.upsert(job))),
      catchError((error: unknown) => this.failed(error)),
    );
  }

  /** The job probably changed under the user's feet (409): show the truth. */
  private failed(error: unknown): Observable<never> {
    this.refresh();
    return throwError(() => toEnqueueError(error));
  }

  /** Replaces the jobs of one group (Queue or History) with a fresh page. */
  private replace(fresh: Job[], inGroup: (job: Job) => boolean): void {
    this.jobs.update((jobs) => sortNewestFirst([...jobs.filter((j) => !inGroup(j)), ...fresh]));
  }

  private drop(jobId: string): void {
    this.jobs.update((jobs) => jobs.filter((j) => j.id !== jobId));
  }

  /**
   * Takes a job from an HTTP response (enqueue, retry). The response is a snapshot from before
   * the job was dispatched and can arrive after the SSE `job.updated` that already says
   * `downloading`, so SSE wins: the job is added only when it is unknown or the response starts
   * a newer Attempt than the one the list has. It never overwrites a state of the same Attempt.
   */
  private adopt(job: Job): void {
    const known = this.jobs().find((j) => j.id === job.id);
    if (!known || known.attempt < job.attempt) {
      this.upsert(job);
    }
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
