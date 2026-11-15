/** Minimal EventSource stand-in for specs: tests call `open()` and `emit()` by hand. */
export class FakeEventSource {
  static instances: FakeEventSource[] = [];

  closed = false;
  private readonly listeners = new Map<string, ((event: MessageEvent<string>) => void)[]>();

  constructor(readonly url: string) {
    FakeEventSource.instances.push(this);
  }

  static reset(): void {
    FakeEventSource.instances = [];
  }

  static factory(): (url: string) => EventSource {
    return (url) => new FakeEventSource(url) as unknown as EventSource;
  }

  addEventListener(name: string, listener: (event: MessageEvent<string>) => void): void {
    this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.dispatch('open', new MessageEvent('open'));
  }

  emit(name: string, data: unknown): void {
    this.dispatch(name, new MessageEvent(name, { data: JSON.stringify(data) }));
  }

  private dispatch(name: string, event: MessageEvent<string>): void {
    this.listeners.get(name)?.forEach((listener) => listener(event));
  }
}
