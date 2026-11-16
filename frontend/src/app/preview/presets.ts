import { AudioFormat } from '../core/jobs.service';
import { Quality } from '../core/preview.service';

/** A one-click shortcut for the mode, quality and format selectors. They are fixed: not saved. */
export interface Preset {
  id: string;
  name: string;
  mode: 'video' | 'audio';
  quality: Quality | null;
  audioFormat: AudioFormat | null;
}

export const PRESETS: readonly Preset[] = [
  { id: 'best-video', name: 'Mejor video', mode: 'video', quality: 'best', audioFormat: null },
  { id: 'mp3', name: 'MP3', mode: 'audio', quality: null, audioFormat: 'mp3' },
];
