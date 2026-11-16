import { Directive, ElementRef, afterNextRender, inject } from '@angular/core';

/**
 * Keyboard support of a menu: focuses the first (or the checked) item when it appears and moves
 * with the arrow keys, Home and End over the enabled `[role^=menuitem]` buttons.
 */
@Directive({
  selector: '[appMenuKeys]',
  host: { '(keydown)': 'onKey($event)' },
})
export class MenuKeys {
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;

  constructor() {
    afterNextRender(() => {
      const items = this.items();
      (items.find((item) => item.getAttribute('aria-checked') === 'true') ?? items[0])?.focus();
    });
  }

  protected onKey(event: KeyboardEvent): void {
    const items = this.items();
    const at = items.indexOf(document.activeElement as HTMLElement);
    let next: number;
    switch (event.key) {
      case 'ArrowDown':
        next = (at + 1) % items.length;
        break;
      case 'ArrowUp':
        next = (at - 1 + items.length) % items.length;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = items.length - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    items[next]?.focus();
  }

  private items(): HTMLElement[] {
    return Array.from(
      this.element.querySelectorAll<HTMLElement>('[role^=menuitem]:not([disabled])'),
    );
  }
}
