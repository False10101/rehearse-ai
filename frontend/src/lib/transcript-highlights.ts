export type TextChange = { text: string; changed: boolean };

/** Word comparison for the review modal; never alters the original text. */
export function compareWords(before: string, after: string): { before: TextChange[]; after: TextChange[] } {
  const a = before.match(/\s+|[^\s]+/g) ?? [];
  const b = after.match(/\s+|[^\s]+/g) ?? [];
  const left = a.map((text) => ({ text, changed: true }));
  const right = b.map((text) => ({ text, changed: true }));
  if (a.length * b.length <= 300_000) {
    const rows = Array.from({ length: a.length + 1 }, () => new Uint32Array(b.length + 1));
    for (let i = a.length - 1; i >= 0; i--) {
      for (let j = b.length - 1; j >= 0; j--) {
        rows[i][j] = a[i] === b[j] ? rows[i + 1][j + 1] + 1 : Math.max(rows[i + 1][j], rows[i][j + 1]);
      }
    }
    let i = 0, j = 0;
    while (i < a.length && j < b.length) {
      if (a[i] === b[j]) { left[i++].changed = false; right[j++].changed = false; }
      else if (rows[i + 1][j] >= rows[i][j + 1]) i++;
      else j++;
    }
  } else {
    // Large selections still get a useful comparison without a quadratic pause.
    let start = 0;
    while (start < a.length && start < b.length && a[start] === b[start]) {
      left[start].changed = right[start].changed = false; start++;
    }
    let i = a.length - 1, j = b.length - 1;
    while (i >= start && j >= start && a[i] === b[j]) {
      left[i--].changed = right[j--].changed = false;
    }
  }
  const merge = (parts: TextChange[]) => parts.reduce<TextChange[]>((result, part) => {
    const changed = part.changed && Boolean(part.text.trim());
    const last = result.at(-1);
    if (last?.changed === changed) last.text += part.text;
    else result.push({ text: part.text, changed });
    return result;
  }, []);
  return { before: merge(left), after: merge(right) };
}

/** Exact phrases only, with word boundaries so AI does not match inside paid. */
export function phraseMatches(text: string, phrase: string): Array<{ start: number; end: number }> {
  if (!phrase.trim()) return [];
  const escaped = phrase.trim().replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
  const matches = [];
  for (const match of text.matchAll(new RegExp(escaped, "giu"))) {
    const start = match.index, end = start + match[0].length;
    const first = match[0][0], last = match[0].at(-1) ?? "";
    if (/\p{L}|\p{N}/u.test(first) && /\p{L}|\p{N}/u.test(text[start - 1] ?? "")) continue;
    if (/\p{L}|\p{N}/u.test(last) && /\p{L}|\p{N}/u.test(text[end] ?? "")) continue;
    matches.push({ start, end });
  }
  return matches;
}
