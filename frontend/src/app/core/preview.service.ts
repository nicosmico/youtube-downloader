import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, catchError, throwError } from 'rxjs';

export type Quality = 'best' | '2160p' | '1080p' | '720p' | '480p';

/** What `POST /api/preview` returns for a single video. */
export interface VideoPreview {
  kind: 'video';
  id: string;
  url: string;
  title: string;
  thumbnail: string | null;
  /** Seconds. */
  duration: number | null;
  author: string | null;
  availableQualities: Quality[];
  maxQuality: Quality;
  /** Short side of the best format, for display. */
  maxResolution: number | null;
  playlistUrl?: string;
}

/** One video of a playlist or channel, as listed by `--flat-playlist`. */
export interface PlaylistEntry {
  id: string;
  url: string;
  /** Position in the playlist, starting at 1. */
  index: number;
  title: string;
  thumbnail: string | null;
  /** Seconds. */
  duration: number | null;
  available: boolean;
  /** Spanish; only when `available` is false. */
  unavailableReason?: string;
}

/** What `POST /api/preview` returns for a playlist or a channel (up to 500 entries). */
export interface PlaylistPreview {
  kind: 'playlist';
  id: string;
  url: string;
  title: string;
  author: string | null;
  thumbnail: string | null;
  entryCount: number;
  /** The playlist has more than the 500 entries listed. */
  truncated: boolean;
  entries: PlaylistEntry[];
}

export type MediaPreview = VideoPreview | PlaylistPreview;

/** Codes of the API plus `network` (no answer from the local server) and `unknown`. */
export type PreviewErrorCode =
  | 'invalid_url'
  | 'unsupported_site'
  | 'mix_playlist'
  | 'live_content'
  | 'not_public'
  | 'unavailable'
  | 'timeout'
  | 'preview_failed'
  | 'engine_not_ready'
  | 'network'
  | 'unknown';

export class PreviewError extends Error {
  constructor(
    readonly code: PreviewErrorCode,
    message: string,
  ) {
    super(message);
  }
}

const API_CODES: ReadonlySet<string> = new Set<PreviewErrorCode>([
  'invalid_url',
  'unsupported_site',
  'mix_playlist',
  'live_content',
  'not_public',
  'unavailable',
  'timeout',
  'preview_failed',
  'engine_not_ready',
]);

/** Asks the server what a URL is. Unsubscribing cancels the HTTP request. */
@Injectable({ providedIn: 'root' })
export class PreviewService {
  private readonly http = inject(HttpClient);

  fetch(url: string): Observable<MediaPreview> {
    return this.http
      .post<MediaPreview>('/api/preview', { url })
      .pipe(catchError((error: unknown) => throwError(() => toPreviewError(error))));
  }
}

function toPreviewError(error: unknown): PreviewError {
  if (!(error instanceof HttpErrorResponse)) {
    return new PreviewError('unknown', '');
  }
  if (error.status === 0) {
    return new PreviewError('network', '');
  }
  const body = error.error as { code?: string; message?: string } | null;
  const code = body?.code;
  if (code && API_CODES.has(code)) {
    return new PreviewError(code as PreviewErrorCode, body?.message ?? '');
  }
  return new PreviewError('unknown', body?.message ?? '');
}
