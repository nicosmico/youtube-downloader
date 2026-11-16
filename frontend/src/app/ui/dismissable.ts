import { Directive, ElementRef, inject, output } from '@angular/core';

/**
 * Put it on a menu or popover (or on the wrapper that holds its trigger): `dismissed` fires on
 * `Esc` and on a click outside the element. The owner closes the menu and returns the focus.
 */
@Directive({
  selector: '[appDismissable]',
  host: {
    '(document:keydown.escape)': 'dismissed.emit("escape")',
    '(document:click)': 'outside($event)',
  },
})
export class Dismissable {
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  readonly dismissed = output<'escape' | 'outside'>();

  protected outside(event: Event): void {
    if (!this.element.contains(event.target as Node)) {
      this.dismissed.emit('outside');
    }
  }
}
