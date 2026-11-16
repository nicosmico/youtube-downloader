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
  /** URL of the thumbnail the preview showed; null when there was none (older jobs). */
  thumbnail: string | null;
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
  thumbnail: string | null;
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
const TERMINAL_STATUSES: readonly JobStatus[] = ['completed', 'failed', 'canceled', 'interrupted'];

export function isInProgress(job: Job): boolean {
  return IN_PROGRESS_STATUSES.includes(job.status);
}

/** What the list shows: every job, or only the ones in a group of statuses. */
export type JobFilter = 'all' | 'active' | 'completed' | 'failed' | 'canceled';
export const JOB_FILTERS: readonly JobFilter[] = [
  'all',
  'active',
  'completed',
  'failed',
  'canceled',
];

/** The filters whose jobs are paged from `/api/jobs` (the Queue is always loaded whole). */
type PagedFilter = Exclude<JobFilter, 'active'>;

const FILTER_STATUSES: Record<JobFilter, readonly JobStatus[] | null> = {
  all: null,
  active: IN_PROGRESS_STATUSES,
  completed: ['completed'],
  failed: ['failed', 'interrupted'],
  canceled: ['canceled'],
};

/** `status=` of the first page and of every next page of a filter ("Todas" pages the History). */
const PAGE_STATUSES: Record<PagedFilter, readonly JobStatus[]> = {
  all: TERMINAL_STATUSES,
  completed: ['completed'],
  failed: ['failed', 'interrupted'],
  canceled: ['canceled'],
};

export function matchesFilter(filter: JobFilter, job: Job): boolean {
  return FILTER_STATUSES[filter]?.includes(job.status) ?? true;
}

/** Where a filter is in its own pagination. */
interface Paging {
  /** `before` cursor of its next page; null when it is all loaded (or not loaded yet). */
  cursor: string | null;
  /** `createdAt` of the oldest job its pages reach; what lies below belongs to a page not loaded. */
  floor: string | null;
  loaded: boolean;
  /** The first page is on its way. */
  loading: boolean;
  loadingMore: boolean;
}

const unloaded = (): Paging => ({
  cursor: null,
  floor: null,
  loaded: false,
  loading: false,
  loadingMore: false,
});

const QUEUE_LIMIT = 200;
const PAGE_SIZE = 50;

/**
 * Live list of jobs: REST for commands and rehydration, SSE (`job.updated`) for changes.
 *
 * `jobs` holds every job the client knows. Each filter pages `/api/jobs` with its own statuses
 * and cursor, so it never looks empty because its jobs sit on a page another filter has not
 * loaded; `visibleJobs` is what the current filter shows: its jobs down to where its pages reach.
 */
@Injectable({ providedIn: 'root' })
export class JobsService {
  private readonly http = inject(HttpClient);
  private readonly stream = inject(EventStreamService);
  private connected = false;
  /** Bumped by every `refresh`: answers to requests of an older list are ignored. */
  private epoch = 0;

  /** Newest first. */
  readonly jobs = signal<Job[]>([]);
  readonly filter = signal<JobFilter>('all');
  private readonly paging = signal<Record<PagedFilter, Paging>>({
    all: unloaded(),
    completed: unloaded(),
    failed: unloaded(),
    canceled: unloaded(),
  });
  /** The jobs of the current filter, newest first. */
  readonly visibleJobs = computed(() => {
    const filter = this.filter();
    const floor = filter === 'active' ? null : this.paging()[filter].floor;
    return this.jobs().filter(
      (job) =>
        matchesFilter(filter, job) &&
        (floor === null || isInProgress(job) || job.createdAt >= floor),
    );
  });
  /** There is an older page of the current filter. */
  readonly hasMore = computed(() => this.current()?.cursor != null);
  readonly loadingMore = computed(() => this.current()?.loadingMore ?? false);
  /** The first page of the current filter is on its way: the list is not really empty yet. */
  readonly loading = computed(() => this.current()?.loading ?? false);
  /** Jobs running and waiting, from `queue.updated` (also sent as a snapshot on connect). */
  readonly queue = signal<QueueCounts>({ active: 0, queued: 0 });

  private current(): Paging | null {
    const filter = this.filter();
    return filter === 'active' ? null : this.paging()[filter];
  }

  /** Starts listening (idempotent). On every (re)connect the list is fetched again. */
  connect(): void {
    if (this.connected) {
      return;
    }
    this.connected = true;
    this.stream.on('open', () => this.refresh());
    this.stream.on('job.updated', (event) => this.upsert(eventData<Job>(event)));
    this.stream.on('job.removed', (event) => this.dropMany([eventData<{ id: string }>(event).id]));
    this.stream.on('jobs.removed', (event) =>
      this.dropMany(eventData<{ ids: string[] }>(event).ids),
    );
    this.stream.on('queue.updated', (event) => this.queue.set(eventData<QueueCounts>(event)));
    this.stream.connect();
  }

  /** Shows another filter; its first page is fetched when it was not loaded yet. */
  select(filter: JobFilter): void {
    if (this.filter() === filter) {
      return;
    }
    this.filter.set(filter);
    if (filter !== 'active') {
      const paging = this.paging()[filter];
      if (!paging.loaded && !paging.loading) {
        this.fetchFirstPage(filter, false);
      }
    }
  }

  /**
   * Fetches the Queue (everything unfinished) and the first page of the current filter again.
   * Whatever else was loaded is dropped: the list starts over, and the other filters fetch
   * their first page when they are selected.
   */
  refresh(): void {
    const epoch = ++this.epoch;
    this.paging.set({
      all: unloaded(),
      completed: unloaded(),
      failed: unloaded(),
      canceled: unloaded(),
    });
    this.http
      .get<JobPage>('/api/jobs', {
        params: { status: IN_PROGRESS_STATUSES.join(','), limit: QUEUE_LIMIT },
      })
      .subscribe({
        next: (page) => {
          if (epoch === this.epoch) {
            this.replace(page.jobs, isInProgress);
          }
        },
        error: () => undefined,
      });
    const filter = this.filter();
    if (filter === 'active') {
      this.jobs.update((jobs) => jobs.filter(isInProgress));
    } else {
      this.fetchFirstPage(filter, true);
    }
  }

  /**
   * The first page of a filter. After a `refresh` (`replacing`) it takes the place of every
   * finished job known; otherwise it is added to what is there.
   */
  private fetchFirstPage(filter: PagedFilter, replacing: boolean): void {
    const epoch = this.epoch;
    this.setPaging(filter, { loading: true });
    this.http
      .get<JobPage>('/api/jobs', {
        params: { status: PAGE_STATUSES[filter].join(','), limit: PAGE_SIZE },
      })
      .subscribe({
        next: (page) => {
          if (epoch !== this.epoch) {
            return;
          }
          if (replacing) {
            this.replace(page.jobs, (job) => !isInProgress(job));
          } else {
            page.jobs.forEach((job) => this.upsert(job));
          }
          this.setPaging(filter, { ...reach(page), loaded: true, loading: false });
        },
        error: () => {
          if (epoch === this.epoch) {
            this.setPaging(filter, { loading: false });
          }
        },
      });
  }

  /** The next (older) page of the current filter. */
  loadMore(): void {
    const filter = this.filter();
    if (filter === 'active') {
      return;
    }
    const before = this.paging()[filter].cursor;
    if (before === null || this.paging()[filter].loadingMore) {
      return;
    }
    const epoch = this.epoch;
    this.setPaging(filter, { loadingMore: true });
    this.http
      .get<JobPage>('/api/jobs', {
        params: { status: PAGE_STATUSES[filter].join(','), limit: PAGE_SIZE, before },
      })
      .subscribe({
        next: (page) => {
          if (epoch !== this.epoch) {
            return;
          }
          page.jobs.forEach((job) => this.upsert(job));
          this.setPaging(filter, { ...reach(page), loadingMore: false });
        },
        error: () => {
          if (epoch === this.epoch) {
            this.setPaging(filter, { loadingMore: false });
          }
        },
      });
  }

  private setPaging(filter: PagedFilter, change: Partial<Paging>): void {
    this.paging.update((all) => ({ ...all, [filter]: { ...all[filter], ...change } }));
  }

  /** Takes a finished job out of the History. The downloaded file stays on disk. */
  remove(jobId: string): Observable<unknown> {
    return this.http.delete(`/api/jobs/${encodeURIComponent(jobId)}`).pipe(
      tap(() => this.dropMany([jobId])),
      catchError((error: unknown) => this.failed(error)),
    );
  }

  /** Takes every finished job of a Batch out of the History; the ones in progress stay. */
  removeBatch(batchId: string): Observable<unknown> {
    return this.http.delete(`/api/batches/${encodeURIComponent(batchId)}`).pipe(
      tap(() =>
        this.dropMany(
          this.jobs()
            .filter((job) => job.batchId === batchId && !isInProgress(job))
            .map((job) => job.id),
        ),
      ),
      catchError((error: unknown) => this.failed(error)),
    );
  }

  /** Empties the History: every finished job goes, the ones in progress stay. */
  clearHistory(): Observable<unknown> {
    return this.http.delete('/api/history').pipe(
      tap(() => {
        // Nothing finished is left on the server, so no filter has an older page.
        const done = { ...unloaded(), loaded: true };
        this.paging.set({ all: done, completed: done, failed: done, canceled: done });
        this.jobs.update((jobs) => jobs.filter(isInProgress));
      }),
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
    thumbnail?: string | null,
  ): Observable<Job[]> {
    const body: Record<string, unknown> = { url, ...options };
    if (title) {
      body['title'] = title;
    }
    if (thumbnail) {
      body['thumbnail'] = thumbnail;
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

  /**
   * Drops jobs (the cursor of a page is the id of its last job: when that one goes, the cursor
   * moves to the oldest job left, or the filter starts over).
   */
  private dropMany(ids: readonly string[]): void {
    if (ids.length === 0) {
      return;
    }
    const gone = new Set(ids);
    this.jobs.update((jobs) => jobs.filter((job) => !gone.has(job.id)));
    for (const filter of ['all', 'completed', 'failed', 'canceled'] as const) {
      const { cursor, floor } = this.paging()[filter];
      if (cursor === null || !gone.has(cursor)) {
        continue;
      }
      const oldest = this.jobs()
        .filter(
          (job) => matchesFilter(filter, job) && !isInProgress(job) && job.createdAt >= floor!,
        )
        .at(-1);
      if (oldest) {
        this.setPaging(filter, { cursor: oldest.id, floor: oldest.createdAt });
      } else {
        this.setPaging(filter, unloaded());
        if (this.filter() === filter) {
          this.fetchFirstPage(filter, false);
        }
      }
    }
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

/** Cursor and floor of a page: where its filter reaches once the page is in. */
function reach(page: JobPage): Pick<Paging, 'cursor' | 'floor'> {
  return {
    cursor: page.nextBefore,
    floor: page.nextBefore === null ? null : (page.jobs.at(-1)?.createdAt ?? null),
  };
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
