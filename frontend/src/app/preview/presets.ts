import { AudioFormat } from '../core/jobs.service';
import { Quality } from '../core/preview.service';

/** A one-click chip of the format control ("Mejor video", "MP3"). They are fixed: not saved. */
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
