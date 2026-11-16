import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { ErrorHandler, Injectable, InjectionToken, inject, signal } from '@angular/core';
import { tap } from 'rxjs';

/** The oldest entries are dropped past this many: the buffer must never grow without bound. */
export const ERROR_LOG_LIMIT = 100;
const MAX_MESSAGE = 2000;

/** Where the timestamps come from (replaced in tests). */
export const ERROR_LOG_CLOCK = new InjectionToken<() => Date>('ERROR_LOG_CLOCK', {
  providedIn: 'root',
  factory: () => () => new Date(),
});

export interface ErrorLogEntry {
  /** ISO timestamp. */
  at: string;
  kind: 'js' | 'http';
  message: string;
}

/** What went wrong in this tab (uncaught JavaScript errors, failed HTTP calls). Memory only. */
@Injectable({ providedIn: 'root' })
export class ErrorLogService {
  private readonly clock = inject(ERROR_LOG_CLOCK);
  private readonly list = signal<readonly ErrorLogEntry[]>([]);

  readonly entries = this.list.asReadonly();

  record(kind: ErrorLogEntry['kind'], message: string): void {
    const entry: ErrorLogEntry = {
      at: this.clock().toISOString(),
      kind,
      message: message.length > MAX_MESSAGE ? `${message.slice(0, MAX_MESSAGE)}…` : message,
    };
    this.list.update((entries) => [...entries, entry].slice(-ERROR_LOG_LIMIT));
  }
}

/** Replaces Angular's handler: records the error and still prints it to the console. */
@Injectable()
export class AppErrorHandler implements ErrorHandler {
  private readonly log = inject(ErrorLogService);

  handleError(error: unknown): void {
    this.log.record('js', describeError(error));
    console.error(error);
  }
}

export function describeError(error: unknown): string {
  if (error instanceof Error) {
    return error.stack ? `${error.name}: ${error.message}\n${error.stack}` : String(error);
  }
  try {
    return typeof error === 'string' ? error : JSON.stringify(error);
  } catch {
    return String(error);
  }
}

/** Records every failed HTTP call (status and URL, never bodies) and lets the error through. */
export const errorLogInterceptor: HttpInterceptorFn = (req, next) => {
  const log = inject(ErrorLogService);
  return next(req).pipe(
    tap({
      error: (error: unknown) => {
        const status = error instanceof HttpErrorResponse ? error.status : 0;
        const code =
          error instanceof HttpErrorResponse
            ? (error.error as { code?: string } | null)?.code
            : undefined;
        const outcome = status === 0 ? 'sin respuesta' : `${status}${code ? ` ${code}` : ''}`;
        log.record('http', `${req.method} ${req.urlWithParams} -> ${outcome}`);
      },
    }),
  );
};
