import { HttpTestingController, TestRequest } from '@angular/common/http/testing';
import { Job } from '../app/core/jobs.service';

/**
 * Answers the two requests a (re)connect makes: the Queue (unfinished jobs) and the first page
 * of the History (finished ones).
 */
export function flushRehydration(
  http: HttpTestingController,
  answer: { queue?: Job[]; history?: Job[]; nextBefore?: string | null } = {},
  requests: TestRequest[] = http.match((r) => r.url === '/api/jobs'),
): void {
  if (requests.length !== 2) {
    throw new Error(`expected 2 requests to /api/jobs, got ${requests.length}`);
  }
  for (const req of requests) {
    const history = req.request.params.get('status')?.includes('completed') ?? false;
    req.flush(
      history
        ? { jobs: answer.history ?? [], nextBefore: answer.nextBefore ?? null }
        : { jobs: answer.queue ?? [], nextBefore: null },
    );
  }
}
