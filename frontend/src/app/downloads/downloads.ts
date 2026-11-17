import { NgTemplateOutlet } from '@angular/common';
import {
  Component,
  ElementRef,
  Injector,
  afterNextRender,
  computed,
  effect,
  inject,
  signal,
  untracked,
} from '@angular/core';
import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Observable } from 'rxjs';
import { NOW } from '../core/clock';
import { JOB_FILTERS, Job, JobFilter, JobsService, isInProgress } from '../core/jobs.service';
import { SystemService } from '../core/system.service';
import { TEXTS } from '../core/texts';
import { formatDuration } from '../preview/url-preview';
import { ConfirmDialog } from '../ui/confirm-dialog';
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

/** The cards of one local day, under its heading. */
export interface DayGroup {
  key: string;
  label: string;
  items: ListItem[];
}

/** `createdAt` of the newest job of a card: the day a Batch goes under. */
function itemDate(item: ListItem): string {
  return item.kind === 'job'
    ? item.job.createdAt
    : item.jobs.reduce((newest, job) => (job.createdAt > newest ? job.createdAt : newest), '');
}

function dayKey(date: Date): string {
  return `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}

/** "Hoy", "Ayer", then "12 nov" ("12 nov 2025" when it is not this year); the browser's local day. */
export function dayLabel(date: Date, now: Date): string {
  const texts = TEXTS.downloads;
  if (dayKey(date) === dayKey(now)) {
    return texts.today;
  }
  const yesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (dayKey(date) === dayKey(yesterday)) {
    return texts.yesterday;
  }
  const short = `${date.getDate()} ${texts.months[date.getMonth()]}`;
  return date.getFullYear() === now.getFullYear() ? short : `${short} ${date.getFullYear()}`;
}

/** Cards in order, split in a group per local day (they are newest first, so days are runs). */
export function groupByDay(items: readonly ListItem[], now: Date): DayGroup[] {
  const days: DayGroup[] = [];
  for (const item of items) {
    const date = new Date(itemDate(item));
    const key = dayKey(date);
    const last = days.at(-1);
    if (last?.key === key) {
      last.items.push(item);
    } else {
      days.push({ key, label: dayLabel(date, now), items: [item] });
    }
  }
  return days;
}

export const BATCH_OPEN_STORAGE_KEY = 'batchOpen';
/** Manual open/close choices kept in `localStorage`: the newest ones, so it never grows forever. */
const BATCH_OPEN_LIMIT = 200;

/** What the user is asked to confirm. */
type Confirmation =
  | { kind: 'batch'; batchId: string; count: number }
  | { kind: 'cancelBatch'; batchId: string; count: number }
  | { kind: 'history' };

/** One card per DownloadJob, live through `JobsService`; a playlist groups its jobs. */
@Component({
  selector: 'app-downloads',
  imports: [NgTemplateOutlet, Icon, Dismissable, MenuKeys, ConfirmDialog],
  templateUrl: './downloads.html',
})
export class Downloads {
  protected readonly jobsService = inject(JobsService);
  private readonly system = inject(SystemService);
  private readonly injector = inject(Injector);
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly document = inject(DOCUMENT);

  protected readonly texts = TEXTS;
  private readonly now = inject(NOW);
  protected readonly filters = JOB_FILTERS;
  /** Job whose "⋮" menu is open (a Batch's, as `batch:<id>`; the list's, as `history`). */
  protected readonly menuFor = signal<string | null>(null);
  /** The jobs of the current filter, as cards under a heading per day. */
  protected readonly days = computed(() =>
    groupByDay(groupJobs(this.jobsService.visibleJobs(), this.jobsService.jobs()), this.now()),
  );
  /** Batches with a job in the Queue: open unless the user chose otherwise. */
  private readonly activeBatches = computed(
    () =>
      new Set(
        this.jobsService
          .jobs()
          .filter((job) => job.batchId && isInProgress(job))
          .map((job) => job.batchId),
      ),
  );
  /** What the user chose by hand per Batch (oldest first, as kept in `localStorage`). */
  private readonly batchChoices = signal<ReadonlyMap<string, boolean>>(this.storedChoices());
  /** Jobs running and waiting: the counter of the "En curso" chip. */
  protected readonly activeCount = computed(() => {
    const { active, queued } = this.jobsService.queue();
    return active + queued;
  });
  protected readonly confirmation = signal<Confirmation | null>(null);
  private confirmTrigger: HTMLElement | null = null;
  protected readonly confirmTexts = computed(() => {
    const request = this.confirmation();
    const texts = TEXTS.downloads;
    if (request?.kind === 'batch' || request?.kind === 'cancelBatch') {
      const dialog =
        request.kind === 'batch'
          ? { ...texts.removeBatchConfirm, dismiss: texts.cancel }
          : texts.cancelBatchConfirm;
      return {
        title:
          request.count === 1 ? dialog.titleOne : dialog.title.replace('{n}', `${request.count}`),
        text: dialog.text,
        confirm: dialog.confirm,
        dismiss: dialog.dismiss,
      };
    }
    const dialog = { ...texts.clearHistoryConfirm, dismiss: texts.cancel };
    return request ? dialog : { title: '', text: '', confirm: '', dismiss: texts.cancel };
  });
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
  /** Ids ticked in the "Con error" filter (the only one with selection). */
  private readonly ticked = signal<ReadonlySet<string>>(new Set());
  /** The bulk retry of the selection is in flight. */
  protected readonly retryingSelection = signal(false);
  /** The jobs of the "Con error" filter can be ticked; no other filter has selection. */
  protected readonly selecting = computed(() => this.jobsService.filter() === 'failed');
  /** What can be ticked right now: the jobs of the filter, as the list shows them. */
  private readonly selectable = computed(() =>
    this.selecting() ? this.jobsService.visibleJobs() : [],
  );
  /** The ticked jobs still in the filter (one that leaves it, e.g. retried elsewhere, is dropped). */
  protected readonly selectedIds = computed(() =>
    this.selectable()
      .map((job) => job.id)
      .filter((id) => this.ticked().has(id)),
  );
  protected readonly allSelected = computed(
    () => this.selectable().length > 0 && this.selectedIds().length === this.selectable().length,
  );
  protected readonly folderMessage = signal<{ ok: boolean; text: string } | null>(null);

  private knownActive = new Set<string>();
  /** Jobs the user just retried from the selection: they join the Queue without leaving "Con error". */
  private retriedFromSelection = new Set<string>();

  constructor() {
    // The selection belongs to one visit to "Con error": changing filter empties it.
    effect(() => {
      this.jobsService.filter();
      untracked(() => this.ticked.set(new Set()));
    });

    // A job that just joined the Queue (enqueued or retried) must be seen: a filter that hides
    // it gives way to "Todas".
    effect(() => {
      const ids = new Set(
        this.jobsService
          .jobs()
          .filter(isInProgress)
          .map((job) => job.id),
      );
      const joined = [...ids].filter((id) => !this.knownActive.has(id));
      const expected = joined.filter((id) => this.retriedFromSelection.delete(id));
      if (joined.length > expected.length) {
        untracked(() => {
          if (this.jobsService.filter() !== 'active') {
            this.jobsService.select('all');
          }
        });
      }
      this.knownActive = ids;
    });
  }

  protected filterLabel(filter: JobFilter): string {
    const label = TEXTS.downloads.filters[filter];
    return filter === 'active' ? `${label} · ${this.activeCount()}` : label;
  }

  /** Rows of a Batch are shown: always in "Con error" (its rows are ticked there), else by choice. */
  protected isOpen(group: BatchGroup): boolean {
    return (
      this.selecting() ||
      (this.batchChoices().get(group.batchId) ?? this.activeBatches().has(group.batchId))
    );
  }

  protected toggleBatch(group: BatchGroup): void {
    const choices = new Map(this.batchChoices());
    choices.delete(group.batchId);
    choices.set(group.batchId, !this.isOpen(group));
    for (const id of [...choices.keys()].slice(0, Math.max(0, choices.size - BATCH_OPEN_LIMIT))) {
      choices.delete(id);
    }
    this.batchChoices.set(choices);
    try {
      this.document.defaultView?.localStorage.setItem(
        BATCH_OPEN_STORAGE_KEY,
        JSON.stringify([...choices]),
      );
    } catch {
      // storage blocked: the choice still holds until the page closes
    }
  }

  private storedChoices(): ReadonlyMap<string, boolean> {
    try {
      const raw = this.document.defaultView?.localStorage.getItem(BATCH_OPEN_STORAGE_KEY);
      const entries: unknown = raw ? JSON.parse(raw) : [];
      return new Map(
        Array.isArray(entries)
          ? entries
              .filter(
                (e): e is [string, boolean] =>
                  Array.isArray(e) && typeof e[0] === 'string' && typeof e[1] === 'boolean',
              )
              .slice(-BATCH_OPEN_LIMIT)
          : [],
      );
    } catch {
      return new Map();
    }
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
          parts.push(this.options(job), texts.preparing);
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

  protected toggleMenu(key: string): void {
    this.menuFor.set(this.menuFor() === key ? null : key);
  }

  /** Terminal jobs of a Batch that the client knows, whichever filter shows them. */
  private removableOf(batchId: string): number {
    return this.jobsService.jobs().filter((job) => job.batchId === batchId && !isInProgress(job))
      .length;
  }

  protected canRemoveBatch(group: BatchGroup): boolean {
    return this.removableOf(group.batchId) > 0;
  }

  /** Queued and running jobs of a Batch that the client knows. */
  private pendingOf(batchId: string): number {
    return this.jobsService.jobs().filter((job) => job.batchId === batchId && isInProgress(job))
      .length;
  }

  protected canCancelBatch(group: BatchGroup): boolean {
    return this.pendingOf(group.batchId) > 0;
  }

  /** Failed, canceled or interrupted jobs of a Batch that the client knows. */
  protected canRetryBatch(group: BatchGroup): boolean {
    return this.jobsService
      .jobs()
      .some((job) => job.batchId === group.batchId && this.canRetry(job));
  }

  /** The "⋮" of a Batch has something to offer. */
  protected hasBatchActions(group: BatchGroup): boolean {
    return this.canCancelBatch(group) || this.canRetryBatch(group) || this.canRemoveBatch(group);
  }

  protected askCancelBatch(group: BatchGroup, trigger: HTMLElement): void {
    this.ask(
      { kind: 'cancelBatch', batchId: group.batchId, count: this.pendingOf(group.batchId) },
      trigger,
    );
  }

  protected retryBatch(group: BatchGroup): void {
    this.menuFor.set(null);
    this.bulk(this.jobsService.retryBatch(group.batchId));
  }

  protected isSelected(job: Job): boolean {
    return this.ticked().has(job.id);
  }

  protected toggleSelected(job: Job): void {
    this.ticked.update((ids) => {
      const next = new Set(ids);
      if (!next.delete(job.id)) {
        next.add(job.id);
      }
      return next;
    });
  }

  /** Ticks every job of the filter, or none when they all are already. */
  protected toggleAll(): void {
    this.ticked.set(this.allSelected() ? new Set() : new Set(this.selectable().map((j) => j.id)));
  }

  protected retrySelected(): void {
    const ids = this.selectedIds();
    if (ids.length === 0 || this.retryingSelection()) {
      return;
    }
    this.retryingSelection.set(true);
    this.retriedFromSelection = new Set(ids);
    this.bulk(this.jobsService.retryMany(ids), {
      next: (retried) => {
        // The server skips what could not be retried: those never join the Queue.
        const returned = new Set((retried as Job[]).map((job) => job.id));
        this.retriedFromSelection = new Set(
          [...this.retriedFromSelection].filter((id) => returned.has(id)),
        );
        this.ticked.set(new Set());
      },
      error: () => (this.retriedFromSelection = new Set()),
      finally: () => this.retryingSelection.set(false),
    });
  }

  /** A request over several jobs; the states come by SSE and in the response. */
  private bulk(
    request: Observable<unknown>,
    hooks: { next?: (value: unknown) => void; error?: () => void; finally?: () => void } = {},
  ): void {
    this.actionMessage.set(null);
    request.subscribe({
      next: (value) => {
        hooks.next?.(value);
        hooks.finally?.();
      },
      error: () => {
        hooks.error?.();
        hooks.finally?.();
        this.actionMessage.set(TEXTS.downloads.actionFailed);
      },
    });
  }

  protected askRemoveBatch(group: BatchGroup, trigger: HTMLElement): void {
    this.ask(
      { kind: 'batch', batchId: group.batchId, count: this.removableOf(group.batchId) },
      trigger,
    );
  }

  protected askClearHistory(trigger: HTMLElement): void {
    this.ask({ kind: 'history' }, trigger);
  }

  private ask(request: Confirmation, trigger: HTMLElement): void {
    this.menuFor.set(null);
    this.confirmTrigger = trigger;
    this.confirmation.set(request);
  }

  protected dismissConfirmation(): void {
    this.confirmation.set(null);
  }

  protected confirm(): void {
    const request = this.confirmation();
    this.confirmation.set(null);
    if (!request) {
      return;
    }
    if (request.kind === 'cancelBatch') {
      this.bulk(this.jobsService.cancelBatch(request.batchId));
      return;
    }
    this.actionMessage.set(null);
    const done =
      request.kind === 'batch'
        ? this.jobsService.removeBatch(request.batchId)
        : this.jobsService.clearHistory();
    done.subscribe({
      // The card of a removed Batch takes its "⋮" with it: the focus must not fall to the page.
      complete: () => afterNextRender(() => this.focusFilters(), { injector: this.injector }),
      error: () => this.actionMessage.set(TEXTS.downloads.actionFailed),
    });
  }

  private focusFilters(): void {
    const host = this.host.nativeElement;
    if (!host.contains(document.activeElement) || document.activeElement === host) {
      host.querySelector<HTMLElement>('[data-testid=filters] [aria-pressed=true]')?.focus();
    }
  }

  /** The dialog is closed: the focus goes back to the "⋮" that opened it (a gone Batch's: to the filters). */
  protected restoreFocus(): void {
    const trigger = this.confirmTrigger;
    this.confirmTrigger = null;
    if (trigger?.isConnected) {
      trigger.focus();
    } else {
      this.focusFilters();
    }
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
