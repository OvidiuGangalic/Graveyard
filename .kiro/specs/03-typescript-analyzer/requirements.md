# Requirements Document: 03 TypeScript Analyzer

## Introduction

The TypeScript analyser reads every TypeScript and JavaScript Source file with tree-sitter and returns `Candidate`s using the same contract as the Python analyser (spec 02, "Shared analyser contract"). It does not run `tsc`, does not read `node_modules`, and does not resolve types. Like the Python analyser it is scope-aware where the code makes the target certain and name-based elsewhere (spec 02, Requirement 2). A function that is **not exported** from an ES module can only be used inside its own file, so its liveness is decided by that file alone. An exported function is tied to the import statements that name its file, so two files exporting a function with the same name are judged separately. Method calls on arbitrary objects are matched by name, since types are not resolved.

Exported functions are never dead just because they are exported and unused in their own file. The analyser looks for imports of the export across the repo, and anything exported can never reach `high` confidence.

Priority: P0 (Requirements 1–9), P1 (Requirement 10).

## Glossary

- **Analyser**: `backend/graveyard/analyzers/typescript/`.
- **Analysable function**: at module top level, a `function` declaration, a generator function declaration, or a `const`/`let`/`var` declarator whose value is an arrow function or function expression; and a method definition directly inside a top-level class body. Each may be wrapped in an `export` statement.
- **Span**: the lines from the start of the enclosing `export` statement or declaration (decorators included, a preceding JSDoc comment not included) to the end of the declaration, inclusive.
- **ES module**: a file with at least one top-level `import` or `export` statement. **Script**: any other `.js`/`.jsx`/`.cjs` file.
- **Exported**: declared with `export`, named in an `export { ... }` clause of the same file, or assigned to `module.exports`/`exports.x`.
- **Framework file**: a file whose exports a framework loads by convention (rules TS-E1 to TS-E3).
- **Library package**: the nearest ancestor `package.json` is not `"private": true` and has at least one of `main`, `module`, `exports`, `types`, `typings`, `bin`.
- **Occurrence**, **Resolved occurrence**, **Unresolved occurrence**, **Direct reference**, **Test reference**, **Candidate**: as in spec 02, using occurrence rules TS-R1 to TS-R7, resolution rules TS-S1 to TS-S6 and arity rule TS-A1.

## Requirements

### Requirement 1: Find analysable functions

**User Story:** As a developer, I want functions, arrow-function constants and class methods all considered, so that modern TypeScript code is covered.

#### Acceptance Criteria

1. THE Analyser SHALL parse `.ts` files with the TypeScript grammar, `.tsx` files with the TSX grammar, and `.js`, `.jsx`, `.mjs` and `.cjs` files with the JavaScript grammar.
2. THE Analyser SHALL collect every Analysable function with name, qualified name (`Class.method`), file path, Span, exported status, default-export status and method status.
3. THE Analyser SHALL NOT collect nested functions, callbacks passed inline, object-literal methods, or class `constructor`s, getters and setters.
4. THE Analyser SHALL NOT collect functions from Test files as Candidates in P0.
5. WHEN a file's parse tree contains an `ERROR` or `MISSING` node, THE Analyser SHALL collect no definitions from that file, SHALL still collect references from it, and SHALL count it in `files_skipped`.

### Requirement 2: Non-exported functions

**User Story:** As a developer, I want private helpers that nothing calls reported with certainty, so that the easy deletions are obvious.

#### Acceptance Criteria

1. WHEN an Analysable function in an ES module is not Exported, THE Analyser SHALL report it as a Candidate if and only if its name has no occurrence (rules TS-R1 to TS-R7) in the same file outside its own Span.
2. WHEN an Analysable function in a Script is not Exported, THE Analyser SHALL decide by repo-wide occurrences and SHALL set flag `SCRIPT_GLOBAL` on the resulting Candidate.
3. WHEN a class method has no Direct reference, THE Analyser SHALL report it as a Candidate. `this.name` inside a class resolves to that class's family only (TS-S4); a property access on any other receiver is unresolved and refers to every method of that name.
4. WHEN an unresolved member call in a `.ts` or `.tsx` file passes a number of arguments that a method's parameter list in a `.ts` or `.tsx` file cannot accept (rule TS-A1), THE Analyser SHALL NOT count it as a reference to that method; IF the method is reported as a result, THEN THE Analyser SHALL set flag `ARITY_MISMATCH` with the location of the first such call.

Judge check: in the sample graveyard, `padLeftLegacy` in `web/src/utils/format.ts` is a tombstone with a `high` badge.

### Requirement 3: Exported functions

**User Story:** As a developer, I want exports checked against imports across the whole repo, so that an export nobody imports is surfaced without being called dead outright.

#### Acceptance Criteria

1. WHEN an Exported named function has at least one Direct reference anywhere in the repo outside its own Span, THE Analyser SHALL NOT report it. An `import { name } from "<specifier>"` or `export { name } from "<specifier>"` in another file counts as a Direct reference only to the export called `name` in the file(s) that specifier resolves to (TS-S2); it does not keep a same-named export of another file alive.
1a. IF a specifier cannot be resolved to repo files and is not a known external package, THEN THE Analyser SHALL treat its imported names as Unresolved occurrences, which refer to every Exported function of that name.
1b. THE Analyser SHALL report every function that pure name matching would report: resolution may only add Candidates, never remove one.
2. WHEN an Exported named function has zero Direct references, THE Analyser SHALL report it as a Candidate with flag `EXPORTED`.
3. WHEN a default-exported function's file is the target of any import, `require`, re-export or dynamic `import()` specifier in a Production file (matched by rule TS-R7), THE Analyser SHALL NOT report it; a dynamic `import()` match is the exception in criterion 5.
4. WHEN an Exported Candidate belongs to a Library package, THE Analyser SHALL set flag `LIBRARY_API`.
5. WHEN the only path-matched specifiers that target an Exported Candidate's file are dynamic `import()` calls (including inside `React.lazy`, `next/dynamic`, `loadable`), and the Candidate has no Direct reference by name, THE Analyser SHALL report it with flag `DYNAMIC_IMPORT` and a caller of kind `dynamic_import`.
6. WHEN an Exported Candidate's file is re-exported by `export * from` in another file, THE Analyser SHALL add a caller of kind `reexport`, and SHALL set `LIBRARY_API` if that other file is in a Library package.
7. THE Analyser SHALL never emit a Candidate for an Exported function without the `EXPORTED` flag.

Judge check: in the sample graveyard, `formatCurrencyOld` shows `medium`, and its reason says it is exported and that nothing in the repo imports it. `formatDate` in `web/src/utils/dates-v1.ts` is a tombstone although `web/src/utils/dates.ts` exports a `formatDate` that is used.

### Requirement 4: Never report framework entry points

**User Story:** As a developer, I want pages, layouts, route handlers and components that the framework loads left alone.

#### Acceptance Criteria

1. THE Analyser SHALL treat as Exempt any function matching rules TS-E1 to TS-E6 in `design.md`, which cover: Next.js App Router and Pages Router conventions; Remix/React Router, SvelteKit, Nuxt and Astro route-module exports; route-handler method exports (`GET`, `POST`, ...); class lifecycle and framework methods (React, Angular, NestJS, web components); decorated methods and methods of decorated classes; stubs.
2. THE Analyser SHALL count a JSX element name (`<Banner />`, `<ui.Banner />`) as a Direct reference to the function of that name.
3. THE Analyser SHALL count a function name passed as an argument, assigned to a property, or placed in an array or object literal as a Direct reference (route handlers registered as `app.get("/x", handler)`).
4. THE Analyser SHALL NOT report an Exempt function under any circumstances.

### Requirement 5: Weak evidence

#### Acceptance Criteria

1. WHEN a Candidate's name appears as a whole identifier token inside a string or template literal in any TypeScript/JavaScript Source file (outside its own Span), or as a whole word in any Text-reference file, THE Analyser SHALL add a caller of kind `string_match` and set flag `STRING_MATCH`.
2. WHEN the file defining a Candidate contains `eval(`, `new Function(`, a computed member access on `this`, `window`, `globalThis`, `global`, `module.exports` or `exports` (`x[expr]` where `expr` is not a literal), or a dynamic `import()` with a non-literal argument, THE Analyser SHALL set flag `DYNAMIC_PATTERN_IN_FILE`.
3. WHEN a Candidate is a method and any TypeScript/JavaScript Source file contains a computed member call `obj[expr](...)` with non-literal `expr`, THE Analyser SHALL set flag `REPO_HAS_REFLECTION`.
4. WHEN a Candidate is a method of a class with an `extends` clause naming a class not defined in the repo, or with an `implements` clause, THE Analyser SHALL set flag `EXTERNAL_BASE_CLASS`.
5. THE Analyser SHALL cap callers at 20 per Candidate.

### Requirement 6: Static test coverage

#### Acceptance Criteria

1. THE Analyser SHALL set `test_coverage` for function Candidates by the same three rules as spec 02 Requirement 5, using TypeScript/JavaScript Test files.
2. THE Analyser SHALL set `test_coverage = "unknown"` for import Candidates.

### Requirement 7: Dead imports

**User Story:** As a developer, I want unused imports listed, including type-only imports.

#### Acceptance Criteria

1. THE Analyser SHALL report an import binding (default, named, or namespace; value or type) as a Candidate of kind `import` WHEN its local name has no occurrence in the same file outside import statements, counting identifiers, type identifiers, JSX element names, shorthand properties and `export { name }` clauses as occurrences.
2. THE Analyser SHALL NOT report: side-effect imports (`import "./x"`); the default or namespace binding `React` in `.tsx`/`.jsx` files; any binding in a file containing a `@jsx` or `@jsxImportSource` pragma that names it; imports on a line carrying `eslint-disable` or `@ts-ignore`/`@ts-expect-error` on that line or the line above; bindings in files with parse errors; `require()` bindings.
3. THE Analyser SHALL name the Candidate by its local name and set its line range to the whole import statement.
4. WHEN the statement binds several names and not all are unused, THE Analyser SHALL set flag `PARTIAL_STATEMENT`.
5. WHEN the file meets Requirement 5.2, THE Analyser SHALL set `DYNAMIC_PATTERN_IN_FILE` on its import Candidates.

Judge check: in the sample graveyard, the tombstone `useMemo` (import) points at `web/src/components/Cart.tsx`.

### Requirement 8: Robustness

#### Acceptance Criteria

1. THE Analyser SHALL NOT raise for any file content.
2. THE Analyser SHALL be a pure function of the `RepoSnapshot` and SHALL return Candidates sorted by (file path, start line, name).
3. THE Analyser SHALL call the progress callback after each file and check the pipeline deadline between files.
4. THE Analyser SHALL release each parse tree after extracting records from it.

### Requirement 9: Snippets

#### Acceptance Criteria

1. THE Analyser SHALL attach `code_snippet` and `snippet_truncated` exactly as spec 02 Requirement 8.

### Requirement 10 (P1, do not start without owner approval): Zombie tests

#### Acceptance Criteria

1. THE Analyser SHALL report a test as a Candidate of kind `test` WHEN it is declared with `it.skip`, `test.skip`, `xit`, `xtest`, `describe.skip` or `xdescribe` (flag `ZOMBIE_SKIPPED`), or WHEN its callback body is empty (flag `ZOMBIE_EMPTY`).

## Assumptions (flagged; see docs/open-decisions.md)

- A1. An export with no importers in an **application** package is reported with `EXPORTED` only, which the verdict engine turns into `bury / medium`. A strict reading of "Low / unsure = exported" would make it `unsure / low`. See D3.
- A2. Owner decision (14 Nov 2026): matching is scope-aware. Import specifiers are resolved to repo files (relative paths exactly, workspace packages by `package.json` name, aliases by path suffix); `tsconfig` paths and `node_modules` are not read. When a specifier cannot be resolved, matching falls back to name. Method calls on arbitrary objects are matched by name plus argument count, and a method found dead only through the argument count is capped at `medium`, because JavaScript does not enforce argument counts at runtime. TypeScript overload signatures are one function, not several. See D4.
- A3. JavaScript files are reported with `language = "typescript"`. See D8.
- A4. Getters, setters and constructors are not analysed.
- A5. `.vue`, `.svelte` and `.astro` files are not parsed; they are scanned as text, so a name used only in such a file yields `STRING_MATCH` (verdict `revive`), never `bury`.
- A6. `.mts` and `.cts` files are out of scope for P0.
