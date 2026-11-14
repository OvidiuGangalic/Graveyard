# Design Document: 03 TypeScript Analyzer

## Overview

Same shape as the Python analyser: one pass per file to extract records, a repo-wide index, then a join. Output type is the shared `Candidate` (spec 02 design, "Shared analyser contract").

```
per file:  parser.parse(bytes, grammar) ──► definitions.py  → FunctionDef (exported?, default?, method?)
                                        ──► references.py   → Occurrence (name, line, kind)
                                        ──► exports.py      → ExportRecord, ImportSpecifier (path, kind: static|dynamic|reexport|require)
                                        ──► imports.py      → ImportBinding
repo-wide: ReferenceIndex {name → [Occurrence]}, SpecifierIndex [(file, specifier path, kind)], PackageIndex {dir → package.json facts}
join:      decide per FunctionDef / ImportBinding → Candidate
```

Entry point: `analyse_typescript(snapshot, progress, deadline) -> AnalyserResult`.

### Dependency note

Uses the `tree-sitter` Python bindings with the `tree-sitter-typescript` (TypeScript and TSX grammars) and `tree-sitter-javascript` wheels. These ship prebuilt wheels, so the Docker image needs no compiler. Task 1 is a spike that confirms the installed versions' API (`Language`, `Parser`, node type names) before any rule is written, because the bindings' API has changed between releases. Node type names below are those of the grammars as known at spec time; the spike corrects them if they differ.

## Definition rules

| ID | tree-sitter node (direct child of `program`, or of `export_statement` under `program`) | Name |
|---|---|---|
| TS-D1 | `function_declaration`, `generator_function_declaration` | `name` field |
| TS-D2 | `lexical_declaration` / `variable_declaration` → `variable_declarator` whose `value` is `arrow_function`, `function_expression` or `generator_function` | declarator `name` (identifier only; destructuring is skipped) |
| TS-D3 | `class_declaration` → `class_body` → `method_definition` (not `constructor`, not `get`/`set`), and `public_field_definition` whose value is an arrow function | `name` field, qualified as `Class.name` |
| TS-D4 | `export_statement` with `default` and an anonymous function or arrow function | name = file basename without extension; `is_default = true` |

Exported status: the node is inside an `export_statement`; or its name appears in an `export_clause` (`export { a, b as c }`) in the same file; or the file contains `module.exports = name`, `module.exports.x = name`, `exports.x = name`, or the name as a (shorthand) property in an object assigned to `module.exports`. A method is Exported if its class is.

## Reference rules

| ID | Node | Name recorded |
|---|---|---|
| TS-R1 | `identifier` (any position except the definition's own name node) | text |
| TS-R2 | `property_identifier` in `member_expression` (`obj.name`, `this.name`) | text |
| TS-R3 | `shorthand_property_identifier`, `shorthand_property_identifier_pattern` | text |
| TS-R4 | `type_identifier`, and identifiers inside `type_query` (`typeof name`) | text |
| TS-R5 | JSX: the name of `jsx_opening_element` / `jsx_self_closing_element`, including each part of a `member_expression` / `nested_identifier` name | text |
| TS-R6 | `import_specifier` and `export_specifier`: the **imported/exported** name (the `name` field, not the alias) | text |
| TS-R7 | **Path-suffix match (used by specifier resolution for non-relative specifiers).** A specifier string from a static `import`, `export ... from`, `require("...")` or `import("...")` matches file `F` when, after removing a leading `./`, `../` sequence, `@/`, `~/` or `src/`, and a trailing extension or `/index`, the remainder is a path-segment suffix of `F` without its extension (or of `F`'s directory when `F` is an `index` file). Bare package specifiers (no `/` and not starting with `.`, `@/` or `~/`) never match. | file |

For a parse-error file, every `[A-Za-z_$][A-Za-z0-9_$]*` token in its text is recorded as an occurrence.

## Resolution rules (which definition an occurrence means)

Same idea as spec 02 "Resolution rules": use what the file states, no type inference. `F` is the file containing the occurrence. Rules are tried in order.

| ID | Occurrence | Resolves to |
|---|---|---|
| TS-S1 | Identifier or JSX name `x` in `F`, and `F` declares `x` at top level | `F`'s own `x` only. |
| TS-S2 | Identifier or JSX name `x` bound in `F` by `import { y as x } from "spec"`, `import x from "spec"`, or `const { y: x } = require("spec")`; the specifier entry itself; `export { y } from "spec"` | The export `y` (or the default export) of the file(s) `spec` resolves to. |
| TS-S3 | Member `ns.x` (or JSX `<ns.x />`) where `ns` is bound in `F` by `import * as ns from "spec"` or `const ns = require("spec")` | The export `x` of the file(s) `spec` resolves to. |
| TS-S4 | `this.x` inside class `C`; `super.x` inside `C`; `C.x` where `C` resolves by TS-S1/S2 to a repo class | Method `x` of every class in `C`'s family (`C`, ancestors and descendants through `extends`, by class name among repo classes). |
| TS-S5 | Identifier `x` in an ES module `F` with no top-level declaration and no import of `x` | No repo function: ES modules share no globals, so it is a local, a parameter or a platform global. |
| TS-S6 | Everything else: a member access on any other receiver (`obj.x`, `a.b().x`); any identifier in a Script; every token of a parse-error file; a name imported through a specifier that is unresolved | **Unresolved.** An identifier refers to every Exported function and every Script function named `x`; a member access refers to every method named `x` and every Exported function named `x`. Member calls are subject to TS-A1. |

### Specifier resolution

| Specifier | Resolves to |
|---|---|
| Relative (`./x`, `../x`) | The one file at that path from `F`'s directory, trying each Source extension and `/index`. No file: nothing in the repo. |
| Workspace package: the specifier's package name equals the `name` of a `package.json` in the repo | With a subpath: files in that package matching the subpath by TS-R7 suffix. Without one: every file in that package (the entry point may re-export anything). |
| External package: the package name is listed under `dependencies`, `devDependencies`, `peerDependencies` or `optionalDependencies` of any repo `package.json` and is not a workspace package; or starts with `node:` | Nothing in the repo. |
| Anything else (aliases such as `@/lib/x`, `~/x`, `src/x`, `baseUrl` imports) | Every file matching by TS-R7 suffix. No match: **unresolved** (TS-S6). |

Following re-exports: if a resolved file does not itself declare the export but has `export { y } from`, `export * from`, or imports and re-exports it, follow, at most 5 steps. If the chain ends without a declaration, the occurrence is unresolved.

### Arity rule

| ID | Rule |
|---|---|
| TS-A1 | Applies only to unresolved member calls `obj.x(a, b)` without spread arguments, where the call site and the method definition are both in `.ts` or `.tsx` files. With `n` arguments, the call is incompatible with method `d` when `d` has no rest parameter and `n` exceeds its parameter count, or `n` is less than the number of required parameters (no `?`, no default; a leading `this` parameter is not counted). An incompatible call is not a reference to `d`. Never applied to `.js`/`.jsx`/`.mjs`/`.cjs` code, which may legally pass any number of arguments. |

A type-checked build rejects such a call, but the runtime does not, and an `any`-typed receiver escapes the check. That is why `ARITY_MISMATCH` always caps confidence at `medium`.

TypeScript overload signatures (`function x(a: string): void; function x(a: number, b: number): void; function x(...) { }`) are one function with one implementation; they are merged (TS-E6), not treated as separate items.

### Direct references

An occurrence in a Production file, outside `f`'s Span, is a Direct reference to `f` when:
- `f` is not Exported and in an ES module → it is in the same file and is an identifier or JSX name `f.name` (TS-S1).
- `f` is Exported → it resolves to `f` (TS-S1 in `f`'s own file, TS-S2, TS-S3), or it is unresolved and carries `f.name`.
- `f` is a default export → additionally, any specifier of kind `static`, `reexport` or `require` that resolves to `f`'s file.
- `f` is a method → it resolves to `f` by TS-S4, or it is an unresolved member access (TS-R2/TS-R3) named `f.name` that TS-A1 does not exclude. A bare identifier `save` never keeps method `Store.save` alive.
- `f` is in a Script → any occurrence of `f.name` (TS-S6).

## Exemption rules (never reported)

| ID | Rule |
|---|---|
| TS-E1 | **Next.js.** In a file named `page`, `layout`, `template`, `loading`, `error`, `global-error`, `not-found`, `default`, `route`, `middleware`, `instrumentation`, `sitemap`, `robots`, `manifest`, `opengraph-image`, `twitter-image`, `icon`, `apple-icon` (any Source extension): the default export and any export named `GET`, `POST`, `PUT`, `PATCH`, `DELETE`, `HEAD`, `OPTIONS`, `generateMetadata`, `generateStaticParams`, `generateViewport`, `generateImageMetadata`, `generateSitemaps`, `middleware`, `register`, `onRequestError`. In any file under a `pages/` directory: the default export and `getServerSideProps`, `getStaticProps`, `getStaticPaths`, `getInitialProps`, `reportWebVitals`. |
| TS-E2 | **Other route-module conventions.** Exports named `loader`, `action`, `meta`, `links`, `headers`, `handle`, `shouldRevalidate`, `ErrorBoundary`, `HydrateFallback`, `clientLoader`, `clientAction` in any file under a `routes/` directory; exports named `load`, `actions`, `prerender`, `entries` in files named `+page`, `+layout`, `+server`, `+page.server`, `+layout.server`; the default export of any file under `routes/`, `api/`, `functions/`, `netlify/functions/`, `supabase/functions/`. |
| TS-E3 | **Entry files.** Every export of a file named by `main`, `module`, `bin`, `types` or any string under `exports` in the nearest `package.json` is not exempt but gets `LIBRARY_API` (see Requirement 3.4). The default export of a file named `main`, `index`, `server`, `app`, `worker`, `sw`, `service-worker`, `background`, `content` at a package root or in `src/` **is** exempt. |
| TS-E4 | **Framework methods.** Methods named `render`, `componentDidMount`, `componentDidUpdate`, `componentWillUnmount`, `shouldComponentUpdate`, `getSnapshotBeforeUpdate`, `componentDidCatch`, `getDerivedStateFromProps`, `getDerivedStateFromError`, `ngOnInit`, `ngOnDestroy`, `ngOnChanges`, `ngAfterViewInit`, `ngAfterContentInit`, `ngDoCheck`, `connectedCallback`, `disconnectedCallback`, `attributeChangedCallback`, `adoptedCallback`, `onModuleInit`, `onModuleDestroy`, `onApplicationBootstrap`, `canActivate`, `intercept`, `transform`, `use`, `catch`, `toJSON`, `toString`, `valueOf`, `then`. |
| TS-E5 | **Decorators.** Any method with a decorator, and any method of a class that has a decorator (Angular, NestJS, TypeORM, lit). |
| TS-E6 | **Stubs and overloads.** Function overload signatures (no body); `abstract` methods; functions whose body is empty or only `throw`. |

## Flag rules

| ID | Flag | Rule |
|---|---|---|
| TS-F1 | `EXPORTED` | Candidate is Exported. |
| TS-F2 | `LIBRARY_API` | Candidate is Exported and (its package is a Library package, or its file is an entry file per TS-E3, or its file is the target of `export * from` in a file belonging to a Library package). |
| TS-F3 | `DYNAMIC_IMPORT` | Requirement 3.5. |
| TS-F4 | `SCRIPT_GLOBAL` | Requirement 2.2. |
| TS-F5 | `STRING_MATCH` | Whole-token match in `string` / `template_string` nodes of any Source file outside own Span, or in Text-reference files (shared helper from spec 02 task 6.4). Import specifier strings are not searched. Names of 3 characters or fewer are not searched in Text-reference files. |
| TS-F6 | `DYNAMIC_PATTERN_IN_FILE` | Requirement 5.2. |
| TS-F7 | `REPO_HAS_REFLECTION` | Requirement 5.3. |
| TS-F8 | `EXTERNAL_BASE_CLASS` | Requirement 5.4. |
| TS-F9 | `ARITY_MISMATCH` | Requirement 2.4. Detail: `path:line` of the first excluded call. |

`package.json` facts (`private`, `main`, `module`, `exports`, `types`, `typings`, `bin`) are read with the stdlib `json` module; an unreadable `package.json` is treated as absent. A file with no ancestor `package.json` is in an application package.

## Import rules

ImportBinding: each local name bound by an `import_statement`: default import, each `import_specifier` (local name = alias if present), `namespace_import`. `import type` and inline `type` specifiers are included.

Used: the local name has an occurrence by TS-R1 to TS-R5 in the same file outside `import_statement` nodes, or appears in an `export_clause`.

Exclusions and flags: Requirement 7.2, 7.4, 7.5.

## Error Handling

- tree-sitter does not raise on bad syntax; it returns `ERROR`/`MISSING` nodes. `root_node.has_error` → Requirement 1.5 path.
- Tree walks are iterative (cursor-based), not recursive, so deeply nested generated code cannot overflow the stack.
- Any exception inside one file's pass is caught, logged with the path, and the file is treated as a parse-error file.
- Bytes are passed to the parser as-is; line numbers come from node `start_point`/`end_point` rows + 1.

## Correctness Properties

`ts_repo()` in `strategies.py` generates 1–5 modules with functions (names unique by default, with an option to repeat an exported name across modules), a random subset exported, and a random import/call graph using relative specifiers.

- **Property P1-ts (never crashes).** For any byte string in a `.ts`, `.tsx` or `.js` file, `analyse_typescript` returns without raising. **Validates: Requirement 8.1.**
- **Property P2-ts (bounded and well-formed).** Function Candidates ≤ `functions_defined`; line ranges within the file; snippet equals those lines. **Validates: Requirements 1.2, 9.1.**
- **Property P3-ts (a caller flips the result).** For a generated uncalled non-exported function `f`: reported. Adding a call in the same file: not reported. Renaming the call: reported again. For an uncalled exported `g`: reported with `EXPORTED`; adding `import { g }` plus a call in another file: not reported. **Validates: Requirements 2.1, 3.1, 3.2.**
- **Property P24-ts (same name, different file).** For any generated repo in which two modules each export a function `g`, and a third module imports `g` from exactly one of them by relative path and calls it: exactly the other one is reported. Switching the specifier switches the result. **Validates: Requirement 3.1.**
- **Property P25-ts (resolution only adds).** Every function reported with `resolve_all_unresolved=True` is also reported by the normal analysis. **Validates: Requirements 3.1a, 3.1b.**
- **Property P7-ts (exports are never unflagged).** Every Candidate whose definition is Exported carries `EXPORTED`. **Validates: Requirement 3.7.**
- **Property P5-ts (adding files never kills).** As P5 in spec 02. **Validates: Requirement 3.1.**
- **Property P13-ts (using an import revives it).** As P13 in spec 02. **Validates: Requirement 7.1.**
- **Property P4a-ts (deterministic).** Shuffling `source_files` does not change the output. **Validates: Requirement 8.2.**

## Testing Strategy

- One unit test per rule ID (`test_TS_E1_next_page_default_export_is_live`, ...), each on an inline repo in `tmp_path`.
- Regression corpus `backend/tests/unit/analyzers/typescript/cases/` with `// expect: dead=... live=...` headers, same harness as Python.
- The accuracy gate (spec 05, task 7) is the acceptance test.
