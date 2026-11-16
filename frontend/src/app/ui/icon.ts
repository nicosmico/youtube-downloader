import { Component, computed, inject, input } from '@angular/core';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import {
  ArrowDownToLine,
  Check,
  ChevronDown,
  CircleAlert,
  ClipboardPaste,
  Download,
  EllipsisVertical,
  FileSearch,
  Film,
  FolderOpen,
  Link,
  Monitor,
  Moon,
  Music,
  Power,
  RefreshCw,
  RotateCcw,
  ScrollText,
  Settings,
  Sun,
  Trash2,
  TriangleAlert,
  X,
  ExternalLink,
  Copy,
  type IconNode,
} from 'lucide';

/** The Lucide icons the app uses (ISC license), bundled: nothing is loaded from a CDN. */
const ICONS = {
  'arrow-down-to-line': ArrowDownToLine,
  check: Check,
  'chevron-down': ChevronDown,
  alert: CircleAlert,
  paste: ClipboardPaste,
  copy: Copy,
  download: Download,
  more: EllipsisVertical,
  detail: FileSearch,
  film: Film,
  folder: FolderOpen,
  link: Link,
  monitor: Monitor,
  moon: Moon,
  music: Music,
  power: Power,
  refresh: RefreshCw,
  retry: RotateCcw,
  logs: ScrollText,
  settings: Settings,
  sun: Sun,
  trash: Trash2,
  warning: TriangleAlert,
  close: X,
  external: ExternalLink,
} satisfies Record<string, IconNode>;

export type IconName = keyof typeof ICONS;

/** Decorative inline SVG. Size it with classes on the element (`size-5`); it takes the text color. */
@Component({
  selector: 'app-icon',
  host: { class: 'inline-flex shrink-0', 'aria-hidden': 'true', '[innerHTML]': 'markup()' },
  template: '',
})
export class Icon {
  private readonly sanitizer = inject(DomSanitizer);
  readonly name = input.required<IconName>();

  protected readonly markup = computed<SafeHtml>(() => {
    const body = (ICONS[this.name()] as IconNode)
      .map(([tag, attrs]) => {
        const list = Object.entries(attrs)
          .filter(([, value]) => value !== undefined)
          .map(([key, value]) => `${key}="${value}"`)
          .join(' ');
        return `<${tag} ${list}/>`;
      })
      .join('');
    // Built from the bundled icon data above, never from user input.
    return this.sanitizer.bypassSecurityTrustHtml(
      `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="100%" height="100%" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`,
    );
  });
}
