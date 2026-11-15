import { Component, computed, inject, input, output, signal } from '@angular/core';
import { AudioFormat } from '../core/jobs.service';
import { PRESET_NAME_MAX, Preset, PresetError, PresetsService } from '../core/presets.service';
import { Quality } from '../core/preview.service';
import { TEXTS } from '../core/texts';

/** Which row of the management list is being edited, and how. */
type Editing = { id: string; kind: 'rename' | 'delete' } | null;

/**
 * Preset bar: one click applies a preset (the parent owns mode/quality/format), plus saving the
 * current pick and a small management list to rename and delete.
 */
@Component({
  selector: 'app-presets',
  templateUrl: './presets.html',
  styleUrl: './presets.css',
})
export class Presets {
  private readonly service = inject(PresetsService);

  readonly mode = input.required<'video' | 'audio'>();
  readonly quality = input.required<Quality>();
  readonly audioFormat = input.required<AudioFormat>();
  readonly applied = output<Preset>();

  protected readonly texts = TEXTS.presets;
  protected readonly maxLength = PRESET_NAME_MAX;
  protected readonly presets = this.service.presets;
  protected readonly managing = signal(false);
  protected readonly saving = signal(false);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);
  protected readonly editing = signal<Editing>(null);
  protected readonly canManage = computed(() => this.presets().length > 0);

  protected describe(preset: Preset): string {
    if (preset.mode === 'audio') {
      const format = TEXTS.presets.audioFormats[preset.audioFormat ?? ''] ?? preset.audioFormat;
      return `${this.texts.audio} · ${format}`;
    }
    const quality = preset.quality === 'best' ? this.texts.qualityBest : preset.quality;
    return `${this.texts.video} · ${quality}`;
  }

  protected apply(preset: Preset): void {
    this.applied.emit(preset);
  }

  protected toggleManage(): void {
    this.managing.update((value) => !value);
    this.editing.set(null);
    this.error.set(null);
  }

  // -- save current options as a new preset ----------------------------------------------------

  protected startSave(): void {
    this.error.set(null);
    this.saving.set(true);
  }

  protected cancelSave(): void {
    this.saving.set(false);
    this.error.set(null);
  }

  protected save(value: string): void {
    const name = this.validName(value);
    if (name === null || this.busy()) {
      return;
    }
    this.busy.set(true);
    const options =
      this.mode() === 'audio'
        ? ({ mode: 'audio', audioFormat: this.audioFormat() } as const)
        : ({ mode: 'video', quality: this.quality() } as const);
    this.service.create(name, options).subscribe({
      next: () => {
        this.busy.set(false);
        this.saving.set(false);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  // -- rename / delete -------------------------------------------------------------------------

  protected startEdit(preset: Preset, kind: 'rename' | 'delete'): void {
    this.error.set(null);
    this.editing.set({ id: preset.id, kind });
  }

  protected cancelEdit(): void {
    this.editing.set(null);
    this.error.set(null);
  }

  protected isEditing(preset: Preset, kind: 'rename' | 'delete'): boolean {
    const editing = this.editing();
    return editing?.id === preset.id && editing.kind === kind;
  }

  protected rename(preset: Preset, value: string): void {
    const name = this.validName(value);
    if (name === null || this.busy()) {
      return;
    }
    this.busy.set(true);
    this.service.rename(preset.id, name).subscribe({
      next: () => {
        this.busy.set(false);
        this.editing.set(null);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  protected remove(preset: Preset): void {
    if (this.busy()) {
      return;
    }
    this.busy.set(true);
    this.service.remove(preset.id).subscribe({
      next: () => {
        this.busy.set(false);
        this.editing.set(null);
      },
      error: (error: unknown) => this.fail(error),
    });
  }

  /** Trimmed name, or `null` after showing why it cannot be sent. */
  private validName(value: string): string | null {
    const name = value.trim();
    if (!name) {
      this.error.set(this.texts.errors['empty_name']);
      return null;
    }
    if (name.length > PRESET_NAME_MAX) {
      this.error.set(this.texts.errors['invalid_name']);
      return null;
    }
    this.error.set(null);
    return name;
  }

  private fail(error: unknown): void {
    this.busy.set(false);
    const code = error instanceof PresetError ? error.code : 'unknown';
    const known = this.texts.errors[code];
    const server = error instanceof PresetError ? error.message : '';
    this.error.set(known ?? (server || this.texts.errors['unknown']));
  }
}
