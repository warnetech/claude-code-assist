# Third-party notices

## andrej-karpathy-skills

Source: <https://github.com/multica-ai/andrej-karpathy-skills>
Author: forrestchang · License: MIT

Four behavioral guidelines for LLM coding — **Think Before Coding**,
**Simplicity First**, **Surgical Changes**, **Goal-Driven Execution** — derived
from [Andrej Karpathy's observations](https://x.com/karpathy/status/2015883857489522876)
on LLM coding pitfalls.

### What this repository uses, and how

The upstream project ships the guidelines as prose: a `CLAUDE.md` and a Claude
Code skill. We use them two ways:

1. **Verbatim, as guidance.** `.claude/skills/karpathy-guidelines/SKILL.md` is
   a copy of the upstream skill, unmodified except for this attribution note.
   Sessions in this repository load it.

2. **Compiled into executable gates.** `llmforge.assurance` (Python) and
   `src/assurance.ts` (TypeScript) turn each principle into a check that
   returns a verdict and can fail a run:

   | Upstream principle    | Gate in this repo                      |
   | --------------------- | -------------------------------------- |
   | Think Before Coding   | `AssumptionLedger`                     |
   | Simplicity First      | `complexity_budget` / `complexityBudget` |
   | Surgical Changes      | `diff_discipline` / `diffDiscipline`   |
   | Goal-Driven Execution | `SuccessCriteria`                      |

   This is our own work and our own interpretation. Where a gate is stricter
   than the prose, or draws a line the prose leaves to judgment, that is our
   choice and not the upstream author's — see `docs/07-assurance.md` for the
   reasoning behind each threshold.

The MIT license text below covers the vendored guidelines. Everything else in
this repository is under the repository's own MIT license (`LICENSE`).

```
MIT License

Copyright (c) 2025 forrestchang

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Anthropic SDKs

`anthropic` (Python) and `@anthropic-ai/sdk` (TypeScript) are optional
dependencies, imported lazily and never vendored. Both are MIT licensed by
Anthropic, PBC.
