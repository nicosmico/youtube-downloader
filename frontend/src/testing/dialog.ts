type FakeDialog = HTMLDialogElement & { __returnFocusTo?: Element | null; __keys?: boolean };

/**
 * jsdom has no `<dialog>` behavior. This stands in for the parts of the native one the app
 * relies on: `showModal` / `close` (with the `close` event), the focus on the first button when
 * it opens and back on the previous element when it closes, and `Esc` (a cancelable `cancel`
 * event, then close).
 */
export function installDialogPolyfill(): void {
  const proto = HTMLDialogElement.prototype as FakeDialog;
  proto.showModal = function (this: FakeDialog) {
    this.__returnFocusTo = document.activeElement;
    this.setAttribute('open', '');
    this.querySelector<HTMLElement>('button, [href], input, select, textarea')?.focus();
    if (!this.__keys) {
      this.__keys = true;
      this.addEventListener('keydown', (event: KeyboardEvent) => {
        if (event.key === 'Escape' && this.open) {
          const cancel = new Event('cancel', { cancelable: true });
          this.dispatchEvent(cancel);
          if (!cancel.defaultPrevented) {
            this.close();
          }
        }
      });
    }
  };
  proto.close = function (this: FakeDialog) {
    if (!this.open) {
      return;
    }
    this.removeAttribute('open');
    (this.__returnFocusTo as HTMLElement | null)?.focus?.();
    this.dispatchEvent(new Event('close'));
  };
}
