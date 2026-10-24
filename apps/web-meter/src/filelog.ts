// CSV log written straight to a user-chosen file (File System Access API, Chromium only).
// The browser cannot append in place: each flush opens a writable that keeps the existing data, writes at the
// end and closes, which commits it to disk. Rows are buffered between flushes, so a crash loses at most one
// flush interval.

type SavePicker = (o: object) => Promise<FileSystemFileHandle>;
const picker = () => (window as unknown as { showSaveFilePicker?: SavePicker }).showSaveFilePicker;

export class FileLog {
  private buf: string[] = [];
  private busy: Promise<void> = Promise.resolve();

  private constructor(private handle: FileSystemFileHandle) {}

  get name() {
    return this.handle.name;
  }

  static supported() {
    return !!picker();
  }

  /** Ask for a file and write the header; null if the user cancels. */
  static async create(suggestedName: string, header: string): Promise<FileLog | null> {
    let handle: FileSystemFileHandle;
    try {
      handle = await picker()!({ suggestedName, types: [{ description: "CSV", accept: { "text/csv": [".csv"] } }] });
    } catch (e) {
      if ((e as Error).name === "AbortError") return null;
      throw e;
    }
    const w = await handle.createWritable(); // truncates
    await w.write(header + "\n");
    await w.close();
    return new FileLog(handle);
  }

  append(line: string) {
    this.buf.push(line + "\n");
  }

  /** Write buffered rows to the end of the file (flushes run one at a time). */
  flush(): Promise<void> {
    this.busy = this.busy.catch(() => {}).then(async () => {
      if (!this.buf.length) return;
      const text = this.buf.join("");
      this.buf = [];
      try {
        const size = (await this.handle.getFile()).size;
        const w = await this.handle.createWritable({ keepExistingData: true });
        await w.write({ type: "write", position: size, data: text });
        await w.close();
      } catch (e) {
        this.buf.unshift(text); // keep the rows for the next attempt
        throw e;
      }
    });
    return this.busy;
  }
}
