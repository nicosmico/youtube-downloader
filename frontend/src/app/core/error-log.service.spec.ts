import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ErrorHandler } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  AppErrorHandler,
  ERROR_LOG_CLOCK,
  ERROR_LOG_LIMIT,
  ErrorLogService,
  errorLogInterceptor,
} from './error-log.service';

describe('ErrorLogService', () => {
  let log: ErrorLogService;
  let http: HttpTestingController;
  let tick = 0;

  beforeEach(() => {
    tick = 0;
    TestBed.configureTestingModule({
      providers: [
        {
          provide: ERROR_LOG_CLOCK,
          useValue: () => new Date(Date.UTC(2026, 10, 15, 12, 0, tick++)),
        },
        { provide: ErrorHandler, useClass: AppErrorHandler },
        provideHttpClient(withInterceptors([errorLogInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    log = TestBed.inject(ErrorLogService);
    http = TestBed.inject(HttpTestingController);
  });

  it('records an uncaught error through the ErrorHandler and still prints it', () => {
    const print = vi.spyOn(console, 'error').mockImplementation(() => undefined);

    TestBed.inject(ErrorHandler).handleError(new TypeError('boom'));

    expect(log.entries()).toHaveLength(1);
    expect(log.entries()[0]).toMatchObject({ kind: 'js', at: '2026-11-15T12:00:00.000Z' });
    expect(log.entries()[0].message).toContain('TypeError: boom');
    expect(print).toHaveBeenCalled();
  });

  it('records a failed HTTP call with its method, URL and status', () => {
    TestBed.inject(HttpClient)
      .post('/api/jobs', {})
      .subscribe({ error: () => undefined });
    http
      .expectOne('/api/jobs')
      .flush(
        { code: 'invalid_options', message: 'x' },
        { status: 422, statusText: 'Unprocessable' },
      );

    expect(log.entries().map((e) => [e.kind, e.message])).toEqual([
      ['http', 'POST /api/jobs -> 422 invalid_options'],
    ]);
  });

  it('records a call that got no response', () => {
    TestBed.inject(HttpClient)
      .get('/api/health')
      .subscribe({ error: () => undefined });
    http.expectOne('/api/health').error(new ProgressEvent('error'));

    expect(log.entries()[0].message).toBe('GET /api/health -> sin respuesta');
  });

  it('does not record successful calls', () => {
    TestBed.inject(HttpClient).get('/api/health').subscribe();
    http.expectOne('/api/health').flush({});

    expect(log.entries()).toEqual([]);
  });

  it('keeps only the newest entries', () => {
    for (let i = 0; i < ERROR_LOG_LIMIT + 5; i++) {
      log.record('js', `error ${i}`);
    }

    expect(log.entries()).toHaveLength(ERROR_LOG_LIMIT);
    expect(log.entries()[0].message).toBe('error 5');
    expect(log.entries().at(-1)?.message).toBe(`error ${ERROR_LOG_LIMIT + 4}`);
  });

  it('truncates a huge message', () => {
    log.record('js', 'x'.repeat(10_000));

    expect(log.entries()[0].message.length).toBeLessThan(2_100);
  });
});
