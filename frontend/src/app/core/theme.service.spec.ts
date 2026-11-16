import { TestBed } from '@angular/core/testing';
import { THEME_STORAGE_KEY, ThemeService } from './theme.service';

describe('ThemeService', () => {
  let systemDark: boolean;
  let changeListener: ((event: { matches: boolean }) => void) | null;

  const create = () => TestBed.inject(ThemeService);
  const isDark = () => document.documentElement.classList.contains('dark');

  beforeEach(() => {
    systemDark = false;
    changeListener = null;
    localStorage.clear();
    document.documentElement.classList.remove('dark');
    // jsdom has no matchMedia
    window.matchMedia = vi.fn(
      () =>
        ({
          get matches() {
            return systemDark;
          },
          addEventListener: (_: string, listener: (event: { matches: boolean }) => void) =>
            (changeListener = listener),
        }) as unknown as MediaQueryList,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    delete (window as { matchMedia?: unknown }).matchMedia;
    document.documentElement.classList.remove('dark');
  });

  it('follows the system by default, also when it changes', () => {
    systemDark = true;
    const theme = create();

    expect(theme.preference()).toBe('system');
    expect(isDark()).toBe(true);

    changeListener!({ matches: false });
    expect(isDark()).toBe(false);
    expect(theme.effective()).toBe('light');
  });

  it('fixes light or dark, remembers it and ignores the system from then on', () => {
    systemDark = true;
    const theme = create();

    theme.set('light');
    expect(isDark()).toBe(false);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light');

    theme.set('dark');
    changeListener!({ matches: false });
    expect(isDark()).toBe(true);
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');
  });

  it('reads the saved preference on start, and ignores garbage', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(create().preference()).toBe('dark');
    expect(isDark()).toBe(true);

    TestBed.resetTestingModule();
    localStorage.setItem(THEME_STORAGE_KEY, 'purple');
    expect(create().preference()).toBe('system');
  });

  it('toggles what is shown now and remembers the choice', () => {
    const theme = create();
    theme.toggle();
    expect(theme.preference()).toBe('dark');
    theme.toggle();
    expect(theme.preference()).toBe('light');
    expect(isDark()).toBe(false);
  });

  it('keeps working when localStorage is blocked', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    const theme = create();

    theme.set('dark');

    expect(theme.preference()).toBe('dark');
    expect(isDark()).toBe(true);
  });
});
