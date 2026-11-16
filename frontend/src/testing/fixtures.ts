// Shared test data. Kept out of *.spec.ts files: a spec imported by another spec can lose its
// own suite under Vitest ("No test suite found").
import { EngineInfo } from '../app/core/engine.service';
import { Job } from '../app/core/jobs.service';
import { PlaylistPreview, VideoPreview } from '../app/core/preview.service';

export const ENGINE_READY: EngineInfo = {
  status: 'ready',
  message: null,
  versions: { ytDlp: '2026.10.26', ffmpeg: '9.0.2', ffprobe: '9.0.2', deno: '2.9.8' },
  updating: false,
  updatePending: false,
  lastUpdateCheck: null,
  updateMessage: null,
};

export const MEDIA: VideoPreview = {
  kind: 'video',
  id: 'Jt5fgKBqZSY',
  url: 'https://www.youtube.com/watch?v=Jt5fgKBqZSY',
  title: 'Un Short vertical',
  thumbnail: 'https://i.ytimg.com/vi/Jt5fgKBqZSY/maxresdefault.jpg',
  duration: 32,
  author: 'YouTube',
  availableQualities: ['best', '1080p', '720p', '480p'],
  maxQuality: '1080p',
  maxResolution: 1080,
};

export const JOB: Job = {
  id: 'job1',
  batchId: null,
  batchTitle: null,
  batchEntryCount: null,
  playlistIndex: null,
  url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw',
  title: 'Me at the zoo',
  mode: 'video',
  quality: 'best',
  audioFormat: null,
  status: 'queued',
  progressPercent: 0,
  downloadedBytes: null,
  totalBytes: null,
  speed: null,
  eta: null,
  outputPath: null,
  error: null,
  attempt: 1,
  createdAt: '2026-11-15T12:00:00.000000+00:00',
  startedAt: null,
  finishedAt: null,
};

export const PLAYLIST: PlaylistPreview = {
  kind: 'playlist',
  id: 'PL59FEE129ADFF2B12',
  url: 'https://www.youtube.com/playlist?list=PL59FEE129ADFF2B12',
  title: 'Test Playlist',
  author: 'GoogleVoice',
  thumbnail: 'https://i.ytimg.com/vi/EjN5avRvApk/hqdefault.jpg',
  entryCount: 4,
  truncated: false,
  entries: [
    entry(1, 'The Google Story', true),
    entry(2, 'Parisian Love', true),
    entry(3, 'Video no disponible', false),
    entry(4, 'Cake', true),
  ],
};

function entry(index: number, title: string, available: boolean) {
  const id = String(index).padStart(11, '0');
  return {
    id,
    url: `https://www.youtube.com/watch?v=${id}`,
    index,
    title,
    duration: available ? 60 * index : null,
    available,
    ...(available ? {} : { unavailableReason: 'Video privado o eliminado' }),
  };
}
