import { Component, ElementRef, effect, input, output, untracked, viewChild } from '@angular/core';

let nextId = 0;

/**
 * A modal confirmation on a native `<dialog>`: the browser traps the focus, `Esc` closes it and
 * the first button ("Cancelar") has the focus. `open` drives it; `dismissed` fires when the user
 * cancels (button, `Esc` or a click outside) and `confirmed` on the confirm button. The owner
 * sets `open` to false in both cases. `closed` fires once the dialog is really closed, which is
 * when the owner can give the focus back.
 */
@Component({
  selector: 'app-confirm-dialog',
  host: { class: 'contents' },
  template: `
    <dialog
      #dialog
      data-testid="confirm-dialog"
      class="m-auto w-[min(calc(100vw-2rem),24rem)] rounded-2xl border border-line bg-bg p-5 text-fg shadow-xl backdrop:bg-black/50"
      [attr.aria-labelledby]="id + '-title'"
      [attr.aria-describedby]="id + '-text'"
      (close)="onClose()"
      (click)="onClick($event)"
    >
      <h2 class="m-0 text-base font-semibold" [id]="id + '-title'" data-testid="confirm-title">
        {{ title() }}
      </h2>
      <p class="mb-0 mt-2 text-sm text-muted" [id]="id + '-text'" data-testid="confirm-text">
        {{ text() }}
      </p>
      <div class="mt-5 flex justify-end gap-2">
        <button
          type="button"
          data-testid="confirm-no"
          class="h-9 rounded-full bg-surface px-4 text-sm font-medium hover:bg-surface-2"
          (click)="dismissed.emit()"
        >
          {{ cancelLabel() }}
        </button>
        <button
          type="button"
          data-testid="confirm-yes"
          class="h-9 rounded-full bg-accent-solid px-4 text-sm font-medium text-on-accent"
          (click)="confirmed.emit()"
        >
          {{ confirmLabel() }}
        </button>
      </div>
    </dialog>
  `,
})
export class ConfirmDialog {
  protected readonly id = `confirm-dialog-${nextId++}`;
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  readonly open = input.required<boolean>();
  readonly title = input.required<string>();
  readonly text = input.required<string>();
  readonly confirmLabel = input.required<string>();
  readonly cancelLabel = input.required<string>();
  readonly confirmed = output<void>();
  readonly dismissed = output<void>();
  readonly closed = output<void>();

  constructor() {
    effect(() => {
      const open = this.open();
      const element = this.dialog().nativeElement;
      untracked(() => {
        if (open && !element.open) {
          element.showModal();
        } else if (!open && element.open) {
          element.close();
        }
      });
    });
  }

  /** The browser's `close` event: after `Esc` (still `open` here) or after our own `close()`. */
  protected onClose(): void {
    if (this.open()) {
      this.dismissed.emit();
    }
    this.closed.emit();
  }

  /** A click on the backdrop lands on the dialog element itself, not on its content. */
  protected onClick(event: MouseEvent): void {
    if (event.target === this.dialog().nativeElement) {
      this.dismissed.emit();
    }
  }
}
